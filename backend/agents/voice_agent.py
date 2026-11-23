"""
Groww AI Trading Agent - Voice Agent (Assembly Briefing Engine)
Generates natural language status briefings for all 9 agents and
key trading events. The frontend's Web Speech API (SpeechSynthesis)
reads these briefings aloud with zero external dependencies.

Briefing types:
  - ASSEMBLY  : Full multi-agent roll-call status report
  - TRADE     : New paper trade executed
  - EXIT      : Position exited (Target / SL / Square-off)
  - KILL      : Daily kill-switch activated
  - SIGNAL    : Strong BUY signal generated
  - SESSION   : Market open / market close announcement
  - HEARTBEAT : Concise 10-second interval summary
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.core.scheduler import MarketScheduler
from backend.database.db import db

IST = pytz.timezone(config.MARKET_TIMEZONE)

# Map of raw agent-state values → human-readable voice phrases
STATE_PHRASES: Dict[str, str] = {
    "IDLE":      "is standing by",
    "RUNNING":   "is active and running",
    "SCANNING":  "is scanning the market",
    "ANALYZING": "is analyzing stocks",
    "DECIDING":  "is evaluating candidates",
    "EXECUTING": "is executing a paper order",
    "MONITORING":"is monitoring open positions",
    "REPORTING": "is generating the daily report",
    "PAUSED":    "is paused",
    "STOPPED":   "has been stopped",
    "ERROR":     "has encountered an error",
}

# Human-friendly names for each agent key
AGENT_NAMES: Dict[str, str] = {
    "master_agent":    "Master Supervisor",
    "market_watcher":  "Market Watcher",
    "stock_analyst":   "Stock Analyst",
    "market_regime":   "Market Regime",
    "decision_agent":  "Decision Agent",
    "risk_manager":    "Risk Manager",
    "execution_agent": "Execution Agent",
    "position_monitor":"Position Monitor",
    "reporting_agent": "Reporting Agent",
}


class VoiceAgent:
    """
    Builds spoken-language briefings from live system state.
    Does NOT synthesize audio itself — returns text strings for the
    browser's native window.speechSynthesis API.
    """

    def __init__(self):
        self.name = "VoiceAgent"
        self._last_briefing_text: str = ""
        self._last_briefing_type: str = ""
        self._last_briefed_at: str = ""

    # ------------------------------------------------------------------
    # PUBLIC: Generate briefings
    # ------------------------------------------------------------------

    def generate_assembly_briefing(
        self,
        agents: Dict[str, Any],
        portfolio: Dict[str, Any],
        market_session: Dict[str, Any],
        open_positions: List[Dict[str, Any]],
        active_signals: int = 0
    ) -> Dict[str, Any]:
        """
        Full Assembly Roll-Call: reads every agent's state aloud in order,
        followed by a portfolio summary.
        """
        now = datetime.now(IST).strftime("%I:%M %p")
        session_phase = market_session.get("phase", "UNKNOWN").replace("_", " ").title()
        is_open = market_session.get("is_trading_allowed", False)

        lines: List[str] = []

        # Intro
        if is_open:
            lines.append(
                f"Groww AI Trading Agent, Assembly Briefing at {now}. Market is OPEN. "
                f"All systems are live."
            )
        else:
            lines.append(
                f"Groww AI Trading Agent, Assembly Briefing at {now}. "
                f"Market session is {session_phase}."
            )

        # Agent Roll-Call
        lines.append("Agent Status Report:")
        for key, display_name in AGENT_NAMES.items():
            agent_data = agents.get(key)
            if not agent_data:
                continue
            # agent_data may be AgentStatus object or dict
            if isinstance(agent_data, dict):
                state = agent_data.get("state", "IDLE")
                message = agent_data.get("message", "")
            else:
                state = str(agent_data.state) if hasattr(agent_data, "state") else "IDLE"
                message = agent_data.message if hasattr(agent_data, "message") else ""

            phrase = STATE_PHRASES.get(state, f"is in state {state}")
            line = f"{display_name} {phrase}."

            # Add key detail from agent message if meaningful
            if message and len(message) < 80 and ":" in message:
                # e.g. "Regime: BULLISH" or "Cycles: 42"
                line = line.rstrip(".") + f". {message}."
            lines.append(line)

        # Portfolio Summary
        total_cap = portfolio.get("total_capital", config.INITIAL_CAPITAL)
        realized = portfolio.get("realized_daily_pnl", 0.0)
        trades_today = portfolio.get("total_trades_today", 0)
        kill_switch = portfolio.get("is_kill_switch_active", False)

        pnl_word = "profit" if realized >= 0 else "loss"
        pnl_abs = abs(realized)

        lines.append(
            f"Portfolio update: Available capital ₹{portfolio.get('available_capital', total_cap):.2f}. "
            f"Today's realized {pnl_word}: ₹{pnl_abs:.2f}. "
            f"Trades completed today: {trades_today}."
        )

        if open_positions:
            pos_names = ", ".join(p["symbol"] for p in open_positions[:3])
            lines.append(
                f"Open paper positions: {len(open_positions)} — {pos_names}."
            )
        else:
            lines.append("No open paper positions at this time.")

        if active_signals > 0:
            lines.append(f"Active trading signals in queue: {active_signals}.")

        if kill_switch:
            lines.append(
                "WARNING: The daily kill switch is ACTIVE. No new trades will be opened until it is reset."
            )

        # Closing
        lines.append(
            "End of assembly briefing. Agents continue autonomous surveillance."
        )

        full_text = " ".join(lines)
        self._save(full_text, "ASSEMBLY")
        return self._wrap(full_text, "ASSEMBLY")

    def generate_trade_briefing(self, trade_info: Dict[str, Any]) -> Dict[str, Any]:
        """Announces a newly executed paper trade."""
        sym = trade_info.get("symbol", "UNKNOWN")
        side = trade_info.get("side", "BUY")
        qty = trade_info.get("quantity", 0)
        price = trade_info.get("executed_price", trade_info.get("reference_price", 0))
        sl = trade_info.get("stop_loss", 0)
        tgt = trade_info.get("target", 0)

        text = (
            f"Paper {side} order executed. {sym}, {qty} shares at ₹{price:.2f}. "
            f"Stop loss set at ₹{sl:.2f}. Target at ₹{tgt:.2f}. "
            f"Position Monitor is now tracking this trade."
        )
        self._save(text, "TRADE")
        return self._wrap(text, "TRADE")

    def generate_exit_briefing(self, trade_info: Dict[str, Any]) -> Dict[str, Any]:
        """Announces position exit with P&L."""
        sym = trade_info.get("symbol", "UNKNOWN")
        net_pnl = float(trade_info.get("net_pnl", 0))
        exit_reason = trade_info.get("exit_reason", "EXIT")
        exit_price = trade_info.get("exit_price", 0)

        reason_map = {
            "TARGET_HIT": "Target reached",
            "STOP_LOSS_HIT": "Stop loss triggered",
            "TRAILING_SL_HIT": "Trailing stop activated",
            "SESSION_CLOSE": "Intraday session close",
            "MANUAL_SQUARE_OFF_BY_OPERATOR": "Manual square-off by operator",
        }
        reason_text = reason_map.get(exit_reason, exit_reason.replace("_", " ").title())
        pnl_word = "profit" if net_pnl >= 0 else "loss"

        text = (
            f"{sym} position closed. {reason_text} at ₹{exit_price:.2f}. "
            f"Net {pnl_word}: ₹{abs(net_pnl):.2f} after all statutory charges."
        )
        self._save(text, "EXIT")
        return self._wrap(text, "EXIT")

    def generate_signal_briefing(self, signal_info: Dict[str, Any]) -> Dict[str, Any]:
        """Announces a high-confidence BUY signal."""
        sym = signal_info.get("symbol", "UNKNOWN")
        score = signal_info.get("score", 0)
        entry = signal_info.get("entry_price", 0)
        confirmations = signal_info.get("confirmations_count", 0)

        text = (
            f"High-confidence signal generated for {sym}. "
            f"Composite score: {score} out of 100. "
            f"{confirmations} strategy confirmations aligned. "
            f"Reference entry at ₹{entry:.2f}. Risk Manager is now validating."
        )
        self._save(text, "SIGNAL")
        return self._wrap(text, "SIGNAL")

    def generate_kill_switch_briefing(self, daily_loss: float) -> Dict[str, Any]:
        """Urgent announcement when daily kill switch is tripped."""
        text = (
            f"ALERT! Daily loss limit reached at ₹{abs(daily_loss):.2f}. "
            f"Kill switch is now ACTIVE. "
            f"All new order generation is suspended for the remainder of the session. "
            f"Open positions are being monitored for safe exit."
        )
        self._save(text, "KILL")
        return self._wrap(text, "KILL", urgent=True)

    def generate_session_briefing(self, is_open: bool, reason: str) -> Dict[str, Any]:
        """Market open or market close announcement."""
        if is_open:
            text = (
                "NSE market is now OPEN. Groww AI Trading Agent is live. "
                "Market Watcher is loading instruments. "
                "All agents are commencing autonomous surveillance. Good luck!"
            )
        else:
            text = (
                f"NSE market session has ended. {reason}. "
                "Position Monitor is completing final square-off. "
                "Reporting Agent is generating the daily trading report."
            )
        self._save(text, "SESSION")
        return self._wrap(text, "SESSION")

    def generate_heartbeat_briefing(
        self,
        portfolio: Dict[str, Any],
        market_session: Dict[str, Any],
        open_positions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Concise 1-sentence status check for periodic auto-read (every ~60 seconds).
        """
        trades = portfolio.get("total_trades_today", 0)
        realized = portfolio.get("realized_daily_pnl", 0.0)
        pnl_word = "up" if realized >= 0 else "down"
        is_open = market_session.get("is_trading_allowed", False)
        pos_count = len(open_positions)

        if is_open:
            text = (
                f"System heartbeat: {trades} trades today, "
                f"{pnl_word} ₹{abs(realized):.2f}, "
                f"{pos_count} open position{'s' if pos_count != 1 else ''}. "
                f"All agents active."
            )
        else:
            phase = market_session.get("phase", "").replace("_", " ").title()
            text = f"System heartbeat: Market {phase}. {trades} trades completed today."

        self._save(text, "HEARTBEAT")
        return self._wrap(text, "HEARTBEAT")

    def get_last_briefing(self) -> Dict[str, Any]:
        """Returns the most recent briefing generated."""
        return {
            "text": self._last_briefing_text,
            "type": self._last_briefing_type,
            "generated_at": self._last_briefed_at,
        }

    # ------------------------------------------------------------------
    # PRIVATE
    # ------------------------------------------------------------------

    def _save(self, text: str, btype: str):
        self._last_briefing_text = text
        self._last_briefing_type = btype
        self._last_briefed_at = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[VoiceAgent] Briefing({btype}): {text[:80]}...")

    @staticmethod
    def _wrap(text: str, btype: str, urgent: bool = False) -> Dict[str, Any]:
        return {
            "type": btype,
            "text": text,
            "word_count": len(text.split()),
            "urgent": urgent,
            "generated_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        }


# Singleton
voice_agent = VoiceAgent()
