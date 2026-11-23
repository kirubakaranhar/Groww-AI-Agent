"""
Groww AI Trading Agent - REST API Endpoints
Provides control, monitoring, analytics, and safety configuration endpoints
for the web-based Agent Control Center.
"""

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse, FileResponse
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import io
import csv
import pandas as pd
import numpy as np
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.core.security import SecurityGate
from backend.core.scheduler import MarketScheduler
from backend.database.db import db
from backend.agents.master_agent import master_agent
from backend.agents.risk_manager import risk_manager_agent
from backend.agents.reporting_agent import reporting_agent
from backend.agents.execution_agent import execution_agent
from backend.services.market_data import market_data_hub
from backend.services.groww_service import groww_service
from backend.services.backtesting import backtesting_engine
from backend.services.strategy_engine import strategy_engine
from backend.agents.voice_agent import voice_agent

router = APIRouter()
IST = pytz.timezone(config.MARKET_TIMEZONE)

# 1. System Control
@router.get("/system/overview")
async def get_system_overview():
    return master_agent.get_system_overview()

@router.post("/system/start")
async def start_system():
    res = await master_agent.start()
    return res

@router.post("/system/pause")
async def pause_system():
    master_agent.pause()
    return {"status": "paused"}

@router.post("/system/resume")
async def resume_system():
    master_agent.resume()
    return {"status": "resumed"}

@router.post("/system/stop")
async def stop_system():
    await master_agent.stop()
    return {"status": "stopped"}

@router.post("/system/emergency-shutdown")
async def emergency_shutdown():
    return master_agent.emergency_shutdown()

@router.post("/system/reset-kill-switch")
async def reset_kill_switch():
    risk_manager_agent.reset_kill_switch()
    return {"status": "kill_switch_reset"}

@router.post("/system/reset-portfolio")
async def reset_portfolio():
    db.update_portfolio({
        "total_capital": config.INITIAL_CAPITAL,
        "available_capital": config.INITIAL_CAPITAL,
        "invested_capital": 0.0,
        "realized_daily_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "total_trades_today": 0,
        "winning_trades_today": 0,
        "losing_trades_today": 0,
        "is_kill_switch_active": 0
    })
    risk_manager_agent.reset_kill_switch()
    return {"status": "portfolio_reset_to_fresh_day"}

# 2. Market Data & Scanner
@router.get("/market/quotes")
async def get_market_quotes():
    quotes = market_data_hub.get_all_quotes()
    return [q.model_dump() for q in quotes]

@router.get("/market/scanner")
async def get_scanner_state():
    return {
        "tracked_universe_count": len(market_data_hub.get_all_quotes()),
        "unusual_volume_candidates": market_data_hub.get_all_quotes()[:10],
        "is_mock_feed": groww_service.is_mock_mode
    }

@router.get("/market/candles/{symbol}")
async def get_market_candles(symbol: str, interval: str = "5m", limit: int = 80):
    """Returns OHLCV candles along with EMA 9, EMA 21, and VWAP series for interactive charting."""
    sym = symbol.upper().strip()
    candles = await groww_service.fetch_historical_candles(sym, interval=interval, limit=limit)
    if not candles:
        raise HTTPException(status_code=404, detail=f"No candle data available for {sym}")

    df = pd.DataFrame(candles)
    df["close"] = pd.to_numeric(df["close"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["volume"] = pd.to_numeric(df["volume"])

    df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean().round(2)
    df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean().round(2)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_vol = df["volume"].cumsum().replace(0, np.nan)
    df["vwap"] = ((typical_price * df["volume"]).cumsum() / cum_vol).fillna(df["close"]).round(2)

    enriched = []
    for idx, row in df.iterrows():
        enriched.append({
            "timestamp": candles[idx]["timestamp"],
            "open": float(candles[idx]["open"]),
            "high": float(candles[idx]["high"]),
            "low": float(candles[idx]["low"]),
            "close": float(candles[idx]["close"]),
            "volume": int(candles[idx]["volume"]),
            "ema_9": float(row["ema_9"]),
            "ema_21": float(row["ema_21"]),
            "vwap": float(row["vwap"])
        })

    indicators = strategy_engine.calculate_indicators(candles)
    quote = market_data_hub.get_quote(sym)
    return {
        "symbol": sym,
        "interval": interval,
        "ltp": quote.ltp if quote else enriched[-1]["close"],
        "candles": enriched,
        "indicators": indicators.model_dump() if indicators else None
    }

# 3. Trading & Portfolio
@router.get("/trading/orders")
async def get_paper_orders():
    return db.get_paper_orders(limit=50)

@router.get("/trading/positions")
async def get_open_positions():
    return db.get_open_positions()

@router.post("/trading/positions/{position_id}/close")
async def close_open_position(position_id: str):
    """Manually squares off an open paper position at live LTP."""
    open_positions = db.get_open_positions()
    target_pos = next((p for p in open_positions if p["position_id"] == position_id), None)
    if not target_pos:
        raise HTTPException(status_code=404, detail=f"Open position {position_id} not found.")

    symbol = target_pos["symbol"]
    quote = market_data_hub.get_quote(symbol)
    exit_ref_price = quote.ltp if quote else float(target_pos["current_price"])

    result = execution_agent.execute_paper_sell(
        position_id=position_id,
        symbol=symbol,
        quantity=int(target_pos["quantity"]),
        entry_price=float(target_pos["entry_price"]),
        exit_reference_price=exit_ref_price,
        exit_reason="MANUAL_SQUARE_OFF_BY_OPERATOR"
    )
    return {"status": "closed", "trade": result}

@router.get("/trading/trades")
async def get_trades():
    return db.get_trades(limit=50)

@router.get("/trading/trades/export")
async def export_trades_csv():
    """Exports completed paper trades as a downloadable CSV file."""
    trades = db.get_trades(limit=500)
    output = io.StringIO()
    fieldnames = [
        "trade_id", "symbol", "side", "quantity", "entry_price", "exit_price",
        "gross_pnl", "total_charges", "net_pnl", "entry_time", "exit_time", "exit_reason"
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for t in trades:
        writer.writerow({k: t.get(k, "") for k in fieldnames})

    output.seek(0)
    date_str = datetime.now(IST).strftime("%Y-%m-%d")
    filename = f"groww_ai_trades_{date_str}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("/trading/signals")
async def get_signals():
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trading_signals ORDER BY created_at DESC LIMIT 50;")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@router.get("/trading/portfolio")
async def get_portfolio():
    return db.get_portfolio()

# 4. Risk & Compliance
@router.get("/risk/events")
async def get_risk_events():
    return db.get_risk_events(limit=50)

@router.get("/logs/events")
async def get_agent_logs():
    return db.get_recent_agent_events(limit=50)

# 5. Reports & Analytics
@router.get("/reports/daily")
async def get_daily_report(date: Optional[str] = None):
    report = reporting_agent.generate_daily_report(target_date=date)

# ------------------------------------------------------------------
# 5b. Voice Agent Briefing Endpoints
# ------------------------------------------------------------------

@router.get("/voice/assembly")
async def get_assembly_briefing():
    """Full Assembly Roll-Call: all 9 agents + portfolio summary in spoken text."""
    overview = master_agent.get_system_overview()
    portfolio = db.get_portfolio()
    open_positions = db.get_open_positions()
    session = MarketScheduler.get_session_state()

    # Count active BUY signals
    try:
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM trading_signals WHERE signal_type='BUY' AND status='GENERATED' AND date(created_at)=date('now');")
        active_signals = c.fetchone()[0]
        conn.close()
    except Exception:
        active_signals = 0

    # Convert AgentStatus objects to dicts
    agents_dict = {}
    if hasattr(overview, "agents") and overview.agents:
        for k, v in overview.agents.items():
            if hasattr(v, "model_dump"):
                agents_dict[k] = v.model_dump()
            elif hasattr(v, "__dict__"):
                agents_dict[k] = {"state": str(v.state), "message": v.message}
            else:
                agents_dict[k] = v
    elif isinstance(overview, dict):
        agents_dict = overview.get("agents", {})

    market_session = session if isinstance(session, dict) else {}

    return voice_agent.generate_assembly_briefing(
        agents=agents_dict,
        portfolio=portfolio,
        market_session=market_session,
        open_positions=open_positions,
        active_signals=active_signals
    )

@router.get("/voice/heartbeat")
async def get_heartbeat_briefing():
    """Concise 1-sentence periodic status update."""
    portfolio = db.get_portfolio()
    open_positions = db.get_open_positions()
    session = MarketScheduler.get_session_state()
    return voice_agent.generate_heartbeat_briefing(
        portfolio=portfolio,
        market_session=session,
        open_positions=open_positions
    )

@router.post("/voice/trade")
async def announce_trade(payload: Dict[str, Any] = Body(...)):
    """Announce a newly executed paper trade."""
    return voice_agent.generate_trade_briefing(payload)

@router.post("/voice/exit")
async def announce_exit(payload: Dict[str, Any] = Body(...)):
    """Announce a position exit with P&L."""
    return voice_agent.generate_exit_briefing(payload)

@router.post("/voice/signal")
async def announce_signal(payload: Dict[str, Any] = Body(...)):
    """Announce a high-confidence BUY signal."""
    return voice_agent.generate_signal_briefing(payload)

@router.get("/voice/session")
async def announce_session():
    """Announce market open / market close."""
    session = MarketScheduler.get_session_state()
    is_open = session.get("is_trading_allowed", False)
    reason = session.get("reason", "")
    return voice_agent.generate_session_briefing(is_open, reason)

@router.get("/voice/last")
async def get_last_briefing():
    """Returns the most recently generated briefing (for re-read)."""
    return voice_agent.get_last_briefing()


    return report

# 6. Backtesting & Strategy Tuning
DEFAULT_BACKTEST_UNIVERSE = [
    "TATASTEEL", "ONGC", "POWERGRID", "NTPC", "ITC", "WIPRO", "SBIN", "LICI", "TATAMOTORS"
]

@router.post("/backtest/run")
async def run_backtest(payload: Dict[str, Any] = Body(...)):
    symbol = payload.get("symbol", "NTPC").upper().strip()
    limit = int(payload.get("limit", 250))
    params = payload.get("params")
    candles = await groww_service.fetch_historical_candles(symbol, interval="5m", limit=limit)
    result = backtesting_engine.run_backtest(symbol=symbol, candles=candles, params=params)
    # Remove bulky internal all_trades before HTTP response
    for key in ("overall_performance", "in_sample_performance", "out_of_sample_validation"):
        if key in result and isinstance(result[key], dict):
            result[key].pop("all_trades", None)
    return result

@router.post("/backtest/universe")
async def run_universe_backtest(payload: Dict[str, Any] = Body(default={})):
    symbols = payload.get("symbols") or DEFAULT_BACKTEST_UNIVERSE
    limit = int(payload.get("limit", 250))
    params = payload.get("params")
    symbols_candles = {}
    for sym in symbols:
        s = sym.upper().strip()
        symbols_candles[s] = await groww_service.fetch_historical_candles(s, interval="5m", limit=limit)
    return backtesting_engine.run_universe_backtest(symbols_candles=symbols_candles, params=params)

@router.post("/backtest/optimize")
async def optimize_strategy(payload: Dict[str, Any] = Body(default={})):
    symbols = payload.get("symbols") or DEFAULT_BACKTEST_UNIVERSE
    limit = int(payload.get("limit", 250))
    symbols_candles = {}
    for sym in symbols:
        s = sym.upper().strip()
        symbols_candles[s] = await groww_service.fetch_historical_candles(s, interval="5m", limit=limit)
    result = backtesting_engine.optimize_strategy(symbols_candles=symbols_candles)
    return result

# 7. Settings & Safety Gate
@router.get("/settings")
async def get_settings():
    return config.mask_credentials()

@router.post("/settings/update")
async def update_settings(payload: Dict[str, Any] = Body(...)):
    # Update financial and runtime settings (with strict risk guardrails)
    if "RISK_PER_TRADE" in payload:
        val = float(payload["RISK_PER_TRADE"])
        if val > config.INITIAL_CAPITAL * 0.05:
            raise HTTPException(status_code=400, detail="RISK_PER_TRADE cannot exceed 5% of initial capital.")
        config.RISK_PER_TRADE = max(5.0, val)
    if "DAILY_MAX_LOSS" in payload:
        config.DAILY_MAX_LOSS = max(10.0, float(payload["DAILY_MAX_LOSS"]))
    if "MAX_OPEN_POSITIONS" in payload:
        config.MAX_OPEN_POSITIONS = max(1, min(5, int(payload["MAX_OPEN_POSITIONS"])))
    if "MAX_TRADES_PER_DAY" in payload:
        config.MAX_TRADES_PER_DAY = max(1, min(10, int(payload["MAX_TRADES_PER_DAY"])))
    if "SIMULATE_MARKET_HOURS" in payload:
        config.SIMULATE_MARKET_HOURS = bool(payload["SIMULATE_MARKET_HOURS"])

    # Tunable Strategy Parameters (with safe bounds)
    if "DECISION_MIN_SCORE_THRESHOLD" in payload:
        config.DECISION_MIN_SCORE_THRESHOLD = max(55.0, min(90.0, float(payload["DECISION_MIN_SCORE_THRESHOLD"])))
    if "MIN_RISK_REWARD_RATIO" in payload:
        config.MIN_RISK_REWARD_RATIO = max(1.2, min(4.0, float(payload["MIN_RISK_REWARD_RATIO"])))
    if "STRATEGY_MIN_CONFIRMATIONS" in payload:
        config.STRATEGY_MIN_CONFIRMATIONS = max(3, min(6, int(payload["STRATEGY_MIN_CONFIRMATIONS"])))
    if "STRATEGY_ATR_SL_MULTIPLIER" in payload:
        config.STRATEGY_ATR_SL_MULTIPLIER = max(1.0, min(3.0, float(payload["STRATEGY_ATR_SL_MULTIPLIER"])))
    if "STRATEGY_MIN_RVOL" in payload:
        config.STRATEGY_MIN_RVOL = max(1.0, min(3.0, float(payload["STRATEGY_MIN_RVOL"])))
    if "STRATEGY_RSI_MIN" in payload:
        config.STRATEGY_RSI_MIN = max(40.0, min(65.0, float(payload["STRATEGY_RSI_MIN"])))
    if "STRATEGY_RSI_MAX" in payload:
        config.STRATEGY_RSI_MAX = max(65.0, min(85.0, float(payload["STRATEGY_RSI_MAX"])))

    logger.info(
        f"Configuration updated: Score>={config.DECISION_MIN_SCORE_THRESHOLD}, "
        f"MinConf={config.STRATEGY_MIN_CONFIRMATIONS}, ATR_SL={config.STRATEGY_ATR_SL_MULTIPLIER}x, "
        f"R:R={config.MIN_RISK_REWARD_RATIO}, RVOL>={config.STRATEGY_MIN_RVOL}"
    )
    return {"status": "updated", "config": config.mask_credentials()}

@router.get("/download/project-zip")
async def download_project_zip():
    """Serves the complete project ZIP bundle for 1-click browser download."""
    zip_path = "Groww_AI_Trading_Agent_v1.0.zip"
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Project ZIP file not found.")
    return FileResponse(
        path=zip_path,
        filename="Groww_AI_Trading_Agent_v1.0.zip",
        media_type="application/zip"
    )

@router.post("/safety-gate/verify-live")
async def verify_live_safety_gate(payload: Dict[str, Any] = Body(...)):
    passphrase = payload.get("passphrase", "")
    sebi_ack = payload.get("sebi_acknowledged", False)
    groww_verified = payload.get("groww_verified", False)
    static_ip = payload.get("static_ip_verified", False)

    is_eligible, message = SecurityGate.verify_live_trading_eligibility(
        provided_passphrase=passphrase,
        sebi_acknowledged=sebi_ack,
        groww_verified=groww_verified,
        static_ip_verified=static_ip
    )

    return {
        "is_eligible": is_eligible,
        "message": message,
        "live_trading_locked": not config.LIVE_TRADING_ENABLED
    }
