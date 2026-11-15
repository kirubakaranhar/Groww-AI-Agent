"""
Groww AI Trading Agent - Market Scheduler & Calendar
Enforces NSE trading hours (09:15 - 15:30 IST), pre-market,
square-off cutoff (15:15 IST), holidays, and market state transitions.
"""

from datetime import datetime, time, date
import pytz
from typing import Dict, Any, Tuple
from backend.core.config import config
from backend.core.logger import logger

IST = pytz.timezone(config.MARKET_TIMEZONE)

# Standard NSE Trading Holidays (Format: YYYY-MM-DD)
NSE_HOLIDAYS_2026 = {
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-20": "Id-Ul-Fitr",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-27": "Bakri Id",
    "2026-08-15": "Independence Day",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan",
    "2026-11-10": "Diwali Balipratipada",
    "2026-11-24": "Gurunanak Jayanti",
    "2026-12-25": "Christmas",
}

class MarketScheduler:
    """Provides market timing validation and session status."""

    @staticmethod
    def get_current_ist_time() -> datetime:
        return datetime.now(IST)

    @classmethod
    def get_session_state(cls) -> Dict[str, Any]:
        """
        Calculates the current market session status.
        """
        now = cls.get_current_ist_time()
        today_str = now.strftime("%Y-%m-%d")
        current_time = now.time()

        # If user explicitly enables simulation mode, allow OPEN status anytime
        if config.SIMULATE_MARKET_HOURS:
            return {
                "status": "OPEN",
                "phase": "SIMULATED_HOURS",
                "is_trading_allowed": True,
                "is_square_off_time": False,
                "reason": "Market simulation override is active for testing",
                "ist_time": now.strftime("%Y-%m-%d %H:%M:%S IST")
            }

        # Check weekend
        if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
            day_name = "Saturday" if now.weekday() == 5 else "Sunday"
            return {
                "status": "CLOSED",
                "phase": "WEEKEND",
                "is_trading_allowed": False,
                "is_square_off_time": False,
                "reason": f"NSE closed on {day_name}",
                "ist_time": now.strftime("%Y-%m-%d %H:%M:%S IST")
            }

        # Check holiday
        if today_str in NSE_HOLIDAYS_2026:
            holiday_name = NSE_HOLIDAYS_2026[today_str]
            return {
                "status": "CLOSED",
                "phase": "HOLIDAY",
                "is_trading_allowed": False,
                "is_square_off_time": False,
                "reason": f"NSE Holiday: {holiday_name}",
                "ist_time": now.strftime("%Y-%m-%d %H:%M:%S IST")
            }

        # Market timings
        pre_market_start = time(9, 0)
        market_open = time(9, 15)
        square_off_cutoff = time(15, 15)
        market_close = time(15, 30)

        if current_time < pre_market_start:
            return {
                "status": "CLOSED",
                "phase": "EARLY_MORNING",
                "is_trading_allowed": False,
                "is_square_off_time": False,
                "reason": "Market opens at 09:15 IST",
                "ist_time": now.strftime("%Y-%m-%d %H:%M:%S IST")
            }
        elif pre_market_start <= current_time < market_open:
            return {
                "status": "PRE_MARKET",
                "phase": "ORDER_COLLECTION",
                "is_trading_allowed": False,
                "is_square_off_time": False,
                "reason": "Pre-market session (09:00 - 09:15 IST)",
                "ist_time": now.strftime("%Y-%m-%d %H:%M:%S IST")
            }
        elif market_open <= current_time < square_off_cutoff:
            return {
                "status": "OPEN",
                "phase": "NORMAL_TRADING",
                "is_trading_allowed": True,
                "is_square_off_time": False,
                "reason": "NSE regular intraday trading active",
                "ist_time": now.strftime("%Y-%m-%d %H:%M:%S IST")
            }
        elif square_off_cutoff <= current_time < market_close:
            return {
                "status": "OPEN",
                "phase": "SQUARE_OFF_ZONE",
                "is_trading_allowed": False,
                "is_square_off_time": True,
                "reason": "Intraday square-off cutoff in effect (15:15 - 15:30 IST)",
                "ist_time": now.strftime("%Y-%m-%d %H:%M:%S IST")
            }
        else:
            return {
                "status": "CLOSED",
                "phase": "POST_MARKET",
                "is_trading_allowed": False,
                "is_square_off_time": False,
                "reason": "Market closed at 15:30 IST. Reconciliation mode.",
                "ist_time": now.strftime("%Y-%m-%d %H:%M:%S IST")
            }

    @classmethod
    def can_open_new_positions(cls) -> Tuple[bool, str]:
        state = cls.get_session_state()
        if not state["is_trading_allowed"]:
            return False, state["reason"]
        return True, "Trading session is currently active."
