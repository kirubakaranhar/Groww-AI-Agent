"""
Groww AI Trading Agent - Pydantic Data Models & Schemas
Defines structured validation contracts for agents, market data,
orders, positions, risk metrics, and reports.
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class AgentStateEnum(str, Enum):
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    ANALYZING = "ANALYZING"
    DECIDING = "DECIDING"
    EXECUTING = "EXECUTING"
    MONITORING = "MONITORING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    STOPPED = "STOPPED"

class MarketRegimeEnum(str, Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"

class DecisionTypeEnum(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"

class OrderStatusEnum(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

class InstrumentSchema(BaseModel):
    symbol: str
    name: str
    exchange: str = "NSE"
    segment: str = "EQUITY"
    lot_size: int = 1
    tick_size: float = 0.05
    is_tradable: bool = True

class MarketQuote(BaseModel):
    symbol: str
    ltp: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float
    change_pct: float
    timestamp: str

class IndicatorValues(BaseModel):
    ema_9: float
    ema_21: float
    ema_50: float
    ema_200: float
    rsi_14: float
    macd: float
    macd_signal: float
    macd_hist: float
    vwap: float
    atr_14: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    rvol: float
    pdh: float
    pdl: float
    or_high: float
    or_low: float

class TechnicalAnalysisReport(BaseModel):
    symbol: str
    indicators: IndicatorValues
    trend_score: float = Field(ge=0, le=25)
    momentum_score: float = Field(ge=0, le=20)
    volume_score: float = Field(ge=0, le=20)
    price_action_score: float = Field(ge=0, le=20)
    regime_score: float = Field(ge=0, le=10)
    data_quality_score: float = Field(ge=0, le=5)
    total_score: float = Field(ge=0, le=100)
    key_findings: List[str]
    support_level: float
    resistance_level: float
    timestamp: str

class DecisionSignal(BaseModel):
    symbol: str
    decision: DecisionTypeEnum
    total_score: float
    score_breakdown: Dict[str, float]
    entry_reference_price: float
    suggested_stop_loss: float
    suggested_target: float
    risk_reward_ratio: float
    strategy_name: str
    reasons: List[str]
    timestamp: str
    explanation: str

class RiskValidationResult(BaseModel):
    is_approved: bool
    rejection_reasons: List[str]
    calculated_quantity: int
    entry_price: float
    stop_loss: float
    target: float
    risk_amount: float
    estimated_brokerage: float
    estimated_stt: float
    estimated_taxes: float
    estimated_slippage: float
    total_estimated_charges: float

class PaperOrder(BaseModel):
    order_id: str
    symbol: str
    side: str  # BUY or SELL
    quantity: int
    order_type: str = "MARKET"
    reference_price: float
    executed_price: Optional[float] = None
    slippage: float = 0.0
    brokerage: float = 0.0
    stt: float = 0.0
    other_charges: float = 0.0
    total_charges: float = 0.0
    status: OrderStatusEnum = OrderStatusEnum.PENDING
    rejection_reason: Optional[str] = None
    placed_at: str
    executed_at: Optional[str] = None

class PaperPosition(BaseModel):
    position_id: str
    symbol: str
    side: str
    quantity: int
    entry_price: float
    current_price: float
    stop_loss: float
    target: float
    trailing_sl: Optional[float] = None
    trailing_activated: bool = False
    unrealized_pnl: float
    pnl_pct: float
    is_open: bool = True
    opened_at: str
    closed_at: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None

class ClosedTrade(BaseModel):
    trade_id: str
    symbol: str
    side: str
    quantity: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    net_pnl: float
    total_charges: float
    entry_time: str
    exit_time: str
    exit_reason: str

class PortfolioState(BaseModel):
    total_capital: float
    available_capital: float
    invested_capital: float
    realized_daily_pnl: float
    unrealized_pnl: float
    total_trades_today: int
    winning_trades_today: int
    losing_trades_today: int
    daily_drawdown: float
    is_kill_switch_active: bool
    mode: str = "PAPER"
    last_updated: str

class AgentStatus(BaseModel):
    name: str
    state: AgentStateEnum
    last_heartbeat: str
    error_count: int = 0
    message: str = "Initialized"

class SystemOverview(BaseModel):
    is_running: bool
    is_paused: bool
    mode: str
    market_session: Dict[str, Any]
    master_state: AgentStateEnum
    agents: Dict[str, AgentStatus]
    portfolio: PortfolioState
    active_positions_count: int
    trades_today_count: int
