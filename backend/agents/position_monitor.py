"""
Groww AI Trading Agent - Position Monitor Agent
Continuously monitors open paper positions:
- Live LTP tracking
- Stop Loss breach detection
- Target achievement detection
- Trailing Stop Loss mechanics (1R profit moves SL to breakeven or trails)
- Mandatory 15:15 IST intraday auto square-off enforcement
- Unrealized P&L calculation
- Safe dispatch to ExecutionAgent
"""

from typing import Dict, Any, List
from datetime import datetime, time
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.database.db import db
from backend.models.schemas import AgentStateEnum, AgentStatus
from backend.services.market_data import market_data_hub
from backend.agents.execution_agent import execution_agent

IST = pytz.timezone(config.MARKET_TIMEZONE)

class PositionMonitorAgent:
    def __init__(self):
        self.name = "PositionMonitorAgent"
        self.state = AgentStateEnum.IDLE
        self.monitored_positions_count = 0
        self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    def get_status(self) -> AgentStatus:
        return AgentStatus(
            name=self.name,
            state=self.state,
            last_heartbeat=self.last_update,
            message=f"Monitoring {self.monitored_positions_count} open position(s)"
        )

    async def monitor_positions(self) -> List[Dict[str, Any]]:
        """
        Inspects all open positions, updates live prices and unrealized P&L,
        and triggers stop-loss, target, or intraday square-off exits.
        """
        self.state = AgentStateEnum.MONITORING
        exits = []
        now_dt = datetime.now(IST)
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        current_time = now_dt.time()
        square_off_time = time(15, 15)

        is_square_off_cutoff = (
            current_time >= square_off_time
            if not config.SIMULATE_MARKET_HOURS
            else False
        )

        open_positions = db.get_open_positions()
        self.monitored_positions_count = len(open_positions)

        for pos in open_positions:
            pos_id = pos["position_id"]
            symbol = pos["symbol"]
            qty = pos["quantity"]
            entry_p = pos["entry_price"]
            sl = pos["stop_loss"]
            target = pos["target"]
            trailing_sl = pos["trailing_sl"] or sl
            trailing_active = bool(pos["trailing_activated"])

            # 1. Fetch current price
            quote = market_data_hub.get_quote(symbol)
            if not quote:
                continue

            current_p = quote.ltp

            # 2. Update Unrealized P&L
            unrealized = round((current_p - entry_p) * qty, 2)
            pnl_pct = round(((current_p - entry_p) / entry_p) * 100, 2)

            # 3. Trailing Stop Loss Logic (if enabled)
            per_share_risk = entry_p - sl
            if config.TRAILING_STOP_LOSS_ENABLED and per_share_risk > 0:
                profit_distance = current_p - entry_p
                # If price reached 1R profit, move SL to breakeven or higher
                if profit_distance >= per_share_risk:
                    candidate_trailing_sl = round(entry_p + (profit_distance * 0.5), 2)
                    if candidate_trailing_sl > trailing_sl:
                        trailing_sl = candidate_trailing_sl
                        trailing_active = True
                        logger.info(f"Trailing SL updated for {symbol}: ₹{trailing_sl}")

            # Persist updated status
            conn = db.get_connection()
            conn.execute("""
            UPDATE positions SET
                current_price = ?,
                trailing_sl = ?,
                trailing_activated = ?,
                unrealized_pnl = ?,
                pnl_pct = ?
            WHERE position_id = ?;
            """, (current_p, trailing_sl, 1 if trailing_active else 0, unrealized, pnl_pct, pos_id))
            conn.commit()
            conn.close()

            # 4. Check Exit Conditions
            exit_reason = None
            if current_p <= trailing_sl:
                exit_reason = f"STOP_LOSS_TRIGGERED (LTP ₹{current_p} <= SL ₹{trailing_sl})"
            elif current_p >= target:
                exit_reason = f"TARGET_ACHIEVED (LTP ₹{current_p} >= TGT ₹{target})"
            elif is_square_off_cutoff:
                exit_reason = "INTRADAY_AUTO_SQUARE_OFF (15:15 IST Cutoff)"

            if exit_reason:
                logger.info(f"Exit condition met for {symbol}: {exit_reason}")
                exit_res = execution_agent.execute_paper_sell(
                    position_id=pos_id,
                    symbol=symbol,
                    quantity=qty,
                    entry_price=entry_p,
                    exit_reference_price=current_p,
                    exit_reason=exit_reason
                )
                exits.append(exit_res)

        self.last_update = now_str
        self.state = AgentStateEnum.IDLE
        return exits

position_monitor_agent = PositionMonitorAgent()
