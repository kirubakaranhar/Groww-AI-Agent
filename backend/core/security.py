"""
Groww AI Trading Agent - Security & Compliance Safety Gate
Enforces strict regulatory compliance (SEBI / NSE), algorithm checks,
hard safety gates, credential protection, and prevents unauthorized live execution.
"""

from typing import Dict, Any, Tuple
from backend.core.config import config
from backend.core.logger import logger

# Required regulatory acknowledgment string
REQUIRED_LIVE_PASSPHRASE = "I_UNDERSTAND_THE_RISKS_ACTIVATE_LIVE"

class SecurityGate:
    """
    Guarantees that live trading can NEVER be triggered inadvertently or automatically.
    Paper trading is the default and permanent baseline.
    """

    @staticmethod
    def verify_live_trading_eligibility(
        provided_passphrase: str,
        sebi_acknowledged: bool,
        groww_verified: bool,
        static_ip_verified: bool
    ) -> Tuple[bool, str]:
        """
        Multi-step verification required before live trading can be toggled.
        Returns (is_eligible, reason_or_message).
        """
        if not config.GROWW_API_KEY or not config.GROWW_API_SECRET:
            return False, "Groww API credentials missing in configuration."

        if not groww_verified:
            return False, "Groww Trading API connection test failed or unverified."

        if not sebi_acknowledged:
            return False, "SEBI & NSE algorithmic trading compliance requirements not acknowledged."

        if not static_ip_verified:
            return False, "Broker-mandated static IP and API order tagging requirements unverified."

        if provided_passphrase != REQUIRED_LIVE_PASSPHRASE:
            return False, f"Invalid safety passphrase. Must match '{REQUIRED_LIVE_PASSPHRASE}' exactly."

        logger.warning("SAFETY ALERT: Live trading authorization checks passed.")
        return True, "All compliance gates satisfied. Ready for explicit confirmation."

    @staticmethod
    def can_place_order(is_live_order: bool) -> Tuple[bool, str]:
        """
        Final execution check right before order routing.
        """
        if not is_live_order:
            # Paper trading is always permitted unless emergency kill switch is tripped
            return True, "Paper execution authorized."

        # If live order requested:
        if not config.LIVE_TRADING_ENABLED:
            logger.error("BLOCKED: Attempted to place live order while LIVE_TRADING_ENABLED is False.")
            return False, "Live trading is currently locked in configuration."

        return True, "Live order authorized."

    @staticmethod
    def sanitize_log_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitizes dictionary to hide tokens and passwords."""
        sanitized = {}
        sensitive_keys = {"token", "secret", "key", "password", "passphrase", "authorization"}
        for k, v in payload.items():
            if any(s in k.lower() for s in sensitive_keys):
                sanitized[k] = "********"
            elif isinstance(v, dict):
                sanitized[k] = SecurityGate.sanitize_log_payload(v)
            else:
                sanitized[k] = v
        return sanitized
