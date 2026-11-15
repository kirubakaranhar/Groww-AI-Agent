"""
Groww AI Trading Agent - Configuration Engine
Handles all environment variables, trading limits, statutory charges,
and operating parameters with Pydantic validation.
"""

import os
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class SystemConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # 1. Project Info
    PROJECT_NAME: str = "Groww AI Trading Agent"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "SANDBOX"  # SANDBOX or PRODUCTION

    # 2. Groww API Credentials
    GROWW_API_KEY: Optional[str] = Field(default=None)
    GROWW_API_SECRET: Optional[str] = Field(default=None)
    GROWW_ACCESS_TOKEN: Optional[str] = Field(default=None)
    GROWW_ACCOUNT_ID: Optional[str] = Field(default=None)
    USE_MOCK_FEED_IF_DISCONNECTED: bool = True

    # 3. Capital & Risk Limits
    INITIAL_CAPITAL: float = 5000.0
    RISK_PER_TRADE: float = 25.0
    DAILY_MAX_LOSS: float = 50.0
    MAX_OPEN_POSITIONS: int = 1
    MAX_TRADES_PER_DAY: int = 2
    MAX_CAPITAL_ALLOCATION_PCT: float = 0.90
    MIN_RISK_REWARD_RATIO: float = 1.5
    TRAILING_STOP_LOSS_ENABLED: bool = True
    TRAILING_STOP_LOSS_ACTIVATION_R: float = 1.0

    # 4. Indian Equity Intraday Statutory & Brokerage Fees
    BROKERAGE_FLAT_INR: float = 20.0
    BROKERAGE_PCT: float = 0.0005
    STT_SELL_PCT: float = 0.00025
    NSE_TXN_CHARGE_PCT: float = 0.0000297
    SEBI_TURNOVER_PCT: float = 0.000001
    STAMP_DUTY_BUY_PCT: float = 0.00003
    GST_PCT: float = 0.18
    SLIPPAGE_PCT: float = 0.0005

    # 5. Safety & Execution Gates
    PAPER_TRADING_ENABLED: bool = True
    LIVE_TRADING_ENABLED: bool = False
    LIVE_CONFIRMATION_PASSPHRASE: Optional[str] = None

    # 6. Market Timings (Asia/Kolkata)
    MARKET_TIMEZONE: str = "Asia/Kolkata"
    PRE_MARKET_START: str = "09:00"
    MARKET_OPEN_TIME: str = "09:15"
    INTRADAY_SQUARE_OFF_TIME: str = "15:15"
    MARKET_CLOSE_TIME: str = "15:30"
    SIMULATE_MARKET_HOURS: bool = False

    # 7. Scanner & Agent Behavior
    SCANNER_BATCH_SIZE: int = 25
    SCAN_INTERVAL_SECONDS: int = 15
    DECISION_MIN_SCORE_THRESHOLD: float = 70.0
    UNUSUAL_VOLUME_MULTIPLIER: float = 1.5

    # 8. Server & Database
    SERVER_HOST: str = "127.0.0.1"
    SERVER_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    DATABASE_PATH: str = "backend/database/trading_system.db"

    @field_validator("RISK_PER_TRADE")
    @classmethod
    def validate_risk(cls, v, info):
        initial_cap = info.data.get("INITIAL_CAPITAL", 5000.0)
        if v > initial_cap * 0.05:
            # Enforce max 5% single-trade risk constraint
            raise ValueError(f"Risk per trade (₹{v}) exceeds 5% of starting capital (₹{initial_cap})")
        return v

    def mask_credentials(self) -> dict:
        """Returns safe dict with masked credentials for UI & API responses."""
        data = self.model_dump()
        for key in ["GROWW_API_KEY", "GROWW_API_SECRET", "GROWW_ACCESS_TOKEN", "LIVE_CONFIRMATION_PASSPHRASE"]:
            val = data.get(key)
            if val and len(val) > 4:
                data[key] = f"{val[:2]}****{val[-2:]}"
            elif val:
                data[key] = "****"
            else:
                data[key] = None
        return data

# Singleton config instance
config = SystemConfig()
