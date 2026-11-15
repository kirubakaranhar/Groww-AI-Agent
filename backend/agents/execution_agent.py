"""
Groww AI Trading Agent - Paper Execution Agent
Simulates realistic trade fills with:
- Realistic market slippage (0.05%)
- Full statutory charges (Brokerage, STT, NSE, SEBI, Stamp Duty, GST)
- Order status tracking (PENDING -> FILLED / REJECTED)
- Position recording in SQLite database
- Strict isolation: Never dispatches live Groww orders in paper mode.
"""

import uuid
from typing import Dict, Any, Optional
from datetime import datetime
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.database.db import db
from backend.models.schemas import (
    RiskValidationResult, PaperOrder, PaperPosition, OrderStatusEnum,
    AgentStateEnum, AgentStatus
)
from backend.agents.risk_manager import risk_manager_agent

IST = pytz.timezone(config.MARKET_TIMEZONE)

class ExecutionAgent:
    def __init__(self):
        self.name = "ExecutionAgent"
        self.state = AgentStateEnum.IDLE
        self.mode = "PAPER"
        self.last_order_id: Optional[str] = None
        self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    def get_status(self) -> AgentStatus:
        return AgentStatus(
            name=self.name,
            state=self.state,
            last_heartbeat=self.last_update,
            message=f"Mode: {self.mode} | Last Order: {self.last_order_id or 'None'}"
        )

    def execute_paper_buy(
        self,
        symbol: str,
        risk_result: RiskValidationResult,
        strategy_name: str
    ) -> Optional[PaperOrder]:
        """
        Simulates execution of a BUY market order with realistic slippage and fee deduction.
        """
        self.state = AgentStateEnum.EXECUTING
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        if not risk_result.is_approved or risk_result.calculated_quantity <= 0:
            logger.error(f"Cannot execute unapproved trade for {symbol}.")
            self.state = AgentStateEnum.IDLE
            return None

        order_id = f"ORD-P-{datetime.now(IST).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        ref_price = risk_result.entry_price
        qty = risk_result.calculated_quantity

        # 1. Realistic Slippage (Entry buy price executed slightly higher)
        slippage_per_share = round(ref_price * config.SLIPPAGE_PCT, 2)
        executed_price = round(ref_price + slippage_per_share, 2)
        total_slippage = round(slippage_per_share * qty, 2)

        # 2. Calculate regulatory charges
        charges = risk_manager_agent.calculate_statutory_charges(
            quantity=qty,
            entry_price=executed_price,
            exit_price=risk_result.target
        )

        total_trade_capital = round(executed_price * qty, 2)

        # 3. Create Paper Order record
        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side="BUY",
            quantity=qty,
            order_type="MARKET",
            reference_price=ref_price,
            executed_price=executed_price,
            slippage=total_slippage,
            brokerage=charges["brokerage"],
            stt=charges["stt"],
            other_charges=charges["total_statutory"] - charges["brokerage"] - charges["stt"],
            total_charges=charges["total_charges"],
            status=OrderStatusEnum.FILLED,
            placed_at=now_str,
            executed_at=now_str
        )

        # 4. Save to Database
        conn = db.get_connection()
        conn.execute("""
        INSERT INTO paper_orders (
            order_id, symbol, side, quantity, order_type, reference_price,
            executed_price, slippage, brokerage, stt, other_charges, total_charges,
            status, placed_at, executed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            order.order_id, order.symbol, order.side, order.quantity, order.order_type,
            order.reference_price, order.executed_price, order.slippage, order.brokerage,
            order.stt, order.other_charges, order.total_charges, order.status.value,
            order.placed_at, order.executed_at
        ))

        # 5. Create Open Position
        position_id = f"POS-P-{uuid.uuid4().hex[:8].upper()}"
        conn.execute("""
        INSERT INTO positions (
            position_id, symbol, side, quantity, entry_price, current_price,
            stop_loss, target, trailing_sl, trailing_activated, unrealized_pnl,
            pnl_pct, is_open, opened_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0.0, 0.0, 1, ?);
        """, (
            position_id, symbol, "BUY", qty, executed_price, executed_price,
            risk_result.stop_loss, risk_result.target, risk_result.stop_loss, now_str
        ))

        # 6. Update Portfolio
        portfolio = db.get_portfolio()
        new_avail_cap = round(portfolio["available_capital"] - total_trade_capital, 2)
        new_invested_cap = round(portfolio["invested_capital"] + total_trade_capital, 2)
        new_trades_today = portfolio["total_trades_today"] + 1

        conn.execute("""
        UPDATE portfolio SET
            available_capital = ?,
            invested_capital = ?,
            total_trades_today = ?,
            last_updated = ?
        WHERE id = 1;
        """, (new_avail_cap, new_invested_cap, new_trades_today, now_str))

        conn.commit()
        conn.close()

        db.log_agent_event(
            self.name, "INFO",
            f"Paper BUY Executed: {qty}x {symbol} @ ₹{executed_price} (SL: ₹{risk_result.stop_loss}, TGT: ₹{risk_result.target})",
            {"order_id": order_id, "position_id": position_id, "capital": total_trade_capital}
        )

        logger.info(f"PAPER BUY: {qty}x {symbol} @ ₹{executed_price} | Order ID: {order_id}")
        self.last_order_id = order_id
        self.last_update = now_str
        self.state = AgentStateEnum.IDLE

        return order

    def execute_paper_sell(
        self,
        position_id: str,
        symbol: str,
        quantity: int,
        entry_price: float,
        exit_reference_price: float,
        exit_reason: str
    ) -> Dict[str, Any]:
        """
        Executes a paper SELL order to close an open position.
        Calculates realized P&L, final statutory charges, and reconciles portfolio.
        """
        self.state = AgentStateEnum.EXECUTING
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        # Realistic Sell Slippage (Exit executed slightly lower)
        slippage_per_share = round(exit_reference_price * config.SLIPPAGE_PCT, 2)
        executed_exit_price = round(exit_reference_price - slippage_per_share, 2)

        gross_pnl = round((executed_exit_price - entry_price) * quantity, 2)

        # Charges calculation
        charges = risk_manager_agent.calculate_statutory_charges(
            quantity=quantity,
            entry_price=entry_price,
            exit_price=executed_exit_price
        )
        total_charges = charges["total_charges"]
        net_pnl = round(gross_pnl - total_charges, 2)

        trade_id = f"TRD-{datetime.now(IST).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        conn = db.get_connection()

        # 1. Close position
        conn.execute("""
        UPDATE positions SET
            is_open = 0,
            closed_at = ?,
            exit_price = ?,
            exit_reason = ?,
            current_price = ?,
            unrealized_pnl = 0.0
        WHERE position_id = ?;
        """, (now_str, executed_exit_price, exit_reason, executed_exit_price, position_id))

        # 2. Record completed trade
        conn.execute("""
        INSERT INTO trades (
            trade_id, symbol, side, quantity, entry_price, exit_price,
            gross_pnl, net_pnl, total_charges, entry_time, exit_time, exit_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            trade_id, symbol, "BUY", quantity, entry_price, executed_exit_price,
            gross_pnl, net_pnl, total_charges, now_str, now_str, exit_reason
        ))

        # 3. Reconcile portfolio capital
        portfolio = db.get_portfolio()
        released_capital = entry_price * quantity
        new_avail_cap = round(portfolio["available_capital"] + released_capital + net_pnl, 2)
        new_invested_cap = round(max(0.0, portfolio["invested_capital"] - released_capital), 2)
        new_realized_pnl = round(portfolio["realized_daily_pnl"] + net_pnl, 2)

        winning = portfolio["winning_trades_today"] + (1 if net_pnl > 0 else 0)
        losing = portfolio["losing_trades_today"] + (1 if net_pnl <= 0 else 0)

        conn.execute("""
        UPDATE portfolio SET
            total_capital = total_capital + ?,
            available_capital = ?,
            invested_capital = ?,
            realized_daily_pnl = ?,
            winning_trades_today = ?,
            losing_trades_today = ?,
            last_updated = ?
        WHERE id = 1;
        """, (net_pnl, new_avail_cap, new_invested_cap, new_realized_pnl, winning, losing, now_str))

        conn.commit()
        conn.close()

        db.log_agent_event(
            self.name, "INFO",
            f"Position Closed: {symbol} @ ₹{executed_exit_price} | P&L: ₹{net_pnl} ({exit_reason})",
            {"trade_id": trade_id, "gross_pnl": gross_pnl, "net_pnl": net_pnl, "charges": total_charges}
        )

        logger.info(f"PAPER SELL: {symbol} exited @ ₹{executed_exit_price} | Net P&L: ₹{net_pnl} | Reason: {exit_reason}")
        self.last_update = now_str
        self.state = AgentStateEnum.IDLE

        return {
            "trade_id": trade_id,
            "symbol": symbol,
            "quantity": quantity,
            "entry_price": entry_price,
            "exit_price": executed_exit_price,
            "net_pnl": net_pnl,
            "exit_reason": exit_reason
        }

execution_agent = ExecutionAgent()
