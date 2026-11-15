"""
Groww AI Trading Agent - Database Entity Models
Defines dataclasses / models representing table schemas for clean mapping.
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class InstrumentEntity:
    symbol: str
    name: str
    exchange: str = "NSE"
    segment: str = "EQUITY"
    lot_size: int = 1
    tick_size: float = 0.05
    is_tradable: int = 1
    updated_at: Optional[str] = None

@dataclass
class MarketDataEntity:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None

@dataclass
class IndicatorEntity:
    symbol: str
    timestamp: str
    ema_9: float
    ema_21: float
    ema_50: float
    ema_200: float
    rsi_14: float
    macd: float
    macd_signal: float
    macd_hist: float
    vwap: float
    atr: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
