"""
Groww AI Trading Agent - Deterministic Risk Manager Agent
Enforces strict mathematical capital preservation rules:
- Verifies available capital (₹5,000 baseline)
- Position sizing: Risk per trade / (Entry - StopLoss)
- Statutory charges calculation (Brokerage, STT, NSE, SEBI, Stamp Duty, GST, Slippage)
- Daily Maximum Loss Kill Switch (₹50 limit)
- Max Open Positions Limit (1 position max)
- Max Trades Per Day Limit (2 trades max)
- Risk-to-Reward Ratio Validation (>= 1.5)
- Duplicate trade protection
- Non-bypassable deterministic enforcement
"""

import math
from typing import Dict, Any, List, Tuple
from datetime import datetime
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.database.db import db
from backend.models.schemas import (
    DecisionSignal, RiskValidationResult, AgentStateEnum, AgentStatus
)

IST = pytz.timezone(config.MARKET_TIMEZONE)

class RiskManagerAgent:
    def __init__(self):
        self.name = "RiskManagerAgent"
        self.state = AgentStateEnum.IDLE
        self.is_kill_switch_active = False
        self.total_violations_today = 0
        self.last_validation_result: Optional[RiskValidationResult] = None
        self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    def get_status(self) -> AgentStatus:
        status_msg = (
            "KILL SWITCH TRIPPED!"
            if self.is_kill_switch_active
            else f"Active (Violations: {self.total_violations_today})"
        )
        return AgentStatus(
            name=self.name,
            state=AgentStateEnum.ERROR if self.is_kill_switch_active else self.state,
            last_heartbeat=self.last_update,
            error_count=self.total_violations_today,
            message=status_msg
        )

    def calculate_statutory_charges(self, quantity: int, entry_price: float, exit_price: float) -> Dict[str, float]:
        """
        Calculates exact Indian equity intraday regulatory and broker charges:
        1. Brokerage: ₹20 or 0.05% of turnover (whichever is lower) for buy and sell each.
        2. STT: 0.025% on sell turnover.
        3. Exchange Txn Charge (NSE): 0.00297% on both buy and sell turnover.
        4. SEBI Turnover Fee: 0.0001% (₹10/crore) on turnover.
        5. Stamp Duty: 0.003% on buy turnover.
        6. GST: 18% on (Brokerage + Exchange Txn + SEBI).
        7. Slippage: Simulated at 0.05% of price.
        """
        buy_turnover = quantity * entry_price
        sell_turnover = quantity * exit_price
        total_turnover = buy_turnover + sell_turnover

        # Brokerage (Buy + Sell)
        brokerage_buy = min(config.BROKERAGE_FLAT_INR, buy_turnover * config.BROKERAGE_PCT)
        brokerage_sell = min(config.BROKERAGE_FLAT_INR, sell_turnover * config.BROKERAGE_PCT)
        total_brokerage = round(brokerage_buy + brokerage_sell, 2)

        # STT (Intraday sell side only: 0.025%)
        stt = round(sell_turnover * config.STT_SELL_PCT, 2)

        # NSE Transaction Charges (0.00297%)
        nse_charges = round(total_turnover * config.NSE_TXN_CHARGE_PCT, 2)

        # SEBI Turnover Fee (₹10 per crore)
        sebi_charges = round(total_turnover * config.SEBI_TURNOVER_PCT, 2)

        # Stamp Duty (0.003% on buy side)
        stamp_duty = round(buy_turnover * config.STAMP_DUTY_BUY_PCT, 2)

        # GST (18% on Brokerage + NSE + SEBI)
        gst = round((total_brokerage + nse_charges + sebi_charges) * config.GST_PCT, 2)

        # Slippage estimate (0.05%)
        slippage_est = round(total_turnover * config.SLIPPAGE_PCT, 2)

        total_statutory = round(total_brokerage + stt + nse_charges + sebi_charges + stamp_duty + gst, 2)
        total_charges_with_slippage = round(total_statutory + slippage_est, 2)

        return {
            "brokerage": total_brokerage,
            "stt": stt,
            "nse_charges": nse_charges,
            "sebi_charges": sebi_charges,
            "stamp_duty": stamp_duty,
            "gst": gst,
            "slippage": slippage_est,
            "total_statutory": total_statutory,
            "total_charges": total_charges_with_slippage
        }

    def validate_trade_signal(self, signal: DecisionSignal) -> RiskValidationResult:
        """
        Executes strict gatekeeper checks before any paper or live order can be authorized.
        """
        self.state = AgentStateEnum.ANALYZING
        rejections = []
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        portfolio = db.get_portfolio()
        open_positions = db.get_open_positions()

        # 1. Kill Switch Check
        if self.is_kill_switch_active or portfolio.get("is_kill_switch_active", 0) == 1:
            rejections.append("DAILY KILL SWITCH IS ACTIVE: Trading halted for the remainder of the session.")

        # 2. Daily Loss Limit Check
        realized_loss = portfolio.get("realized_daily_pnl", 0.0)
        unrealized_loss = sum(pos.get("unrealized_pnl", 0.0) for pos in open_positions)
        total_current_loss = realized_loss + unrealized_loss
        if total_current_loss <= -config.DAILY_MAX_LOSS:
            self.trip_kill_switch(
                f"Daily loss limit breached: Current loss ₹{abs(total_current_loss)} >= max ₹{config.DAILY_MAX_LOSS}"
            )
            rejections.append(f"DAILY MAX LOSS BREACHED (Current Loss: ₹{abs(total_current_loss):.2f})")

        # 3. Maximum Trades Per Day Limit
        total_trades_today = portfolio.get("total_trades_today", 0)
        if total_trades_today >= config.MAX_TRADES_PER_DAY:
            rejections.append(
                f"MAX DAILY TRADES LIMIT REACHED: {total_trades_today}/{config.MAX_TRADES_PER_DAY} trades completed."
            )

        # 4. Maximum Open Positions Limit
        if len(open_positions) >= config.MAX_OPEN_POSITIONS:
            rejections.append(
                f"MAX POSITIONS LIMIT REACHED: {len(open_positions)}/{config.MAX_OPEN_POSITIONS} active."
            )

        # 5. Duplicate Trade Check
        for pos in open_positions:
            if pos["symbol"] == signal.symbol:
                rejections.append(f"DUPLICATE POSITION DETECTED: Position already open for {signal.symbol}.")

        # 6. Price and Stop-Loss Mechanics
        entry_price = signal.entry_reference_price
        stop_loss = signal.suggested_stop_loss
        target = signal.suggested_target
        per_share_risk = entry_price - stop_loss

        if per_share_risk <= 0:
            rejections.append(f"INVALID STOP LOSS: Entry (₹{entry_price}) must be higher than SL (₹{stop_loss}).")
            per_share_risk = 0.01

        # 7. Risk-to-Reward Ratio Check
        per_share_reward = target - entry_price
        rr_ratio = round(per_share_reward / per_share_risk, 2)
        if rr_ratio < config.MIN_RISK_REWARD_RATIO:
            rejections.append(
                f"UNFAVORABLE RISK/REWARD: {rr_ratio:.2f} is below mandatory minimum {config.MIN_RISK_REWARD_RATIO}."
            )

        # 8. Capital & Position Sizing
        available_capital = portfolio.get("available_capital", config.INITIAL_CAPITAL)
        # Max capital allocation per trade (e.g. 90% of available capital)
        max_capital_for_trade = available_capital * config.MAX_CAPITAL_ALLOCATION_PCT

        # Position Sizing: Risk per trade / per_share_risk
        desired_quantity = math.floor(config.RISK_PER_TRADE / per_share_risk)
        
        # Check against available capital (NO LEVERAGE)
        max_quantity_by_capital = math.floor(max_capital_for_trade / entry_price)
        final_quantity = min(desired_quantity, max_quantity_by_capital)

        if final_quantity < 1:
            rejections.append(
                f"INSUFFICIENT CAPITAL / POSITION SIZING: Calculated quantity is {final_quantity}. "
                f"(Required capital ₹{entry_price:.2f} vs allocated ₹{max_capital_for_trade:.2f})"
            )
            final_quantity = 0

        # Calculate charges
        charges = self.calculate_statutory_charges(
            quantity=max(1, final_quantity),
            entry_price=entry_price,
            exit_price=target
        )

        is_approved = len(rejections) == 0

        if not is_approved:
            self.total_violations_today += 1
            # Log risk event
            conn = db.get_connection()
            conn.execute("""
            INSERT INTO risk_events (event_type, symbol, attempted_action, reason, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (
                "RISK_VIOLATION_REJECTED", signal.symbol, "BUY",
                "; ".join(rejections), str(charges), now_str
            ))
            conn.commit()
            conn.close()
            logger.warning(f"RiskManager rejected {signal.symbol}: {'; '.join(rejections)}")

        result = RiskValidationResult(
            is_approved=is_approved,
            rejection_reasons=rejections,
            calculated_quantity=final_quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            risk_amount=round(final_quantity * per_share_risk, 2),
            estimated_brokerage=charges["brokerage"],
            estimated_stt=charges["stt"],
            estimated_taxes=charges["gst"] + charges["nse_charges"] + charges["sebi_charges"] + charges["stamp_duty"],
            estimated_slippage=charges["slippage"],
            total_estimated_charges=charges["total_charges"]
        )

        self.last_validation_result = result
        self.last_update = now_str
        self.state = AgentStateEnum.IDLE
        return result

    def trip_kill_switch(self, reason: str):
        self.is_kill_switch_active = True
        db.update_portfolio({"is_kill_switch_active": 1})
        db.log_agent_event(self.name, "CRITICAL", f"KILL SWITCH TRIPPED: {reason}")
        logger.critical(f"EMERGENCY KILL SWITCH TRIPPED: {reason}")

    def reset_kill_switch(self):
        self.is_kill_switch_active = False
        db.update_portfolio({"is_kill_switch_active": 0})
        db.log_agent_event(self.name, "INFO", "Kill switch manually reset by authorized operator.")
        logger.info("Kill switch reset.")

risk_manager_agent = RiskManagerAgent()
