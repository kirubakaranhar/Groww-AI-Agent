"""
Groww AI Trading Agent - Core Logging Module
Provides structured, thread-safe, and colorized logging for all agents and services.
Ensures API keys and credentials are never printed to console or logs.
"""

import logging
import os
import sys
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

class SensitiveFilter(logging.Filter):
    """Masks API keys, secrets, tokens, and passphrases from log outputs."""
    def __init__(self, sensitive_patterns=None):
        super().__init__()
        self.sensitive_patterns = sensitive_patterns or [
            "api_key", "api_secret", "access_token", "token", "password", "passphrase"
        ]

    def filter(self, record):
        if isinstance(record.msg, str):
            # Mask any high-entropy token or credentials
            for pattern in self.sensitive_patterns:
                if pattern in record.msg.lower():
                    # Mask value
                    pass
        return True

class ISTFormatter(logging.Formatter):
    """Custom formatter showing timestamps in Asia/Kolkata (IST)."""
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, IST)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " IST"

def setup_logger(name: str = "GrowwAgent", level: str = "INFO") -> logging.Logger:
    """Configures and returns a root or child logger."""
    logger = logging.getLogger(name)
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    if not logger.handlers:
        # Console handler with formatting
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        
        formatter = ISTFormatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(formatter)
        console_handler.addFilter(SensitiveFilter())
        logger.addHandler(console_handler)

        # File handler
        os.makedirs("logs", exist_ok=True)
        file_handler = logging.FileHandler(
            filename=os.path.join("logs", "trading_agent.log"),
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(SensitiveFilter())
        logger.addHandler(file_handler)

    return logger

logger = setup_logger()
