"""
Groww AI Trading Agent - REST API Endpoints
Provides control, monitoring, analytics, and safety configuration endpoints
for the web-based Agent Control Center.
"""

from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, List, Optional
from datetime import datetime
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.core.security import SecurityGate
from backend.core.scheduler import MarketScheduler
from backend.database.db import db
from backend.agents.master_agent import master_agent
from backend.agents.risk_manager import risk_manager_agent
from backend.agents.reporting_agent import reporting_agent
from backend.services.market_data import market_data_hub
from backend.services.groww_service import groww_service
from backend.services.backtesting import backtesting_engine

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

# 3. Trading & Portfolio
@router.get("/trading/orders")
async def get_paper_orders():
    return db.get_paper_orders(limit=50)

@router.get("/trading/positions")
async def get_open_positions():
    return db.get_open_positions()

@router.get("/trading/trades")
async def get_trades():
    return db.get_trades(limit=50)

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
    return report

# 6. Backtesting
@router.post("/backtest/run")
async def run_backtest(payload: Dict[str, Any] = Body(...)):
    symbol = payload.get("symbol", "RELIANCE")
    candles = await groww_service.fetch_historical_candles(symbol, interval="5m", limit=150)
    result = backtesting_engine.run_backtest(symbol=symbol, candles=candles)
    return result

# 7. Settings & Safety Gate
@router.get("/settings")
async def get_settings():
    return config.mask_credentials()

@router.post("/settings/update")
async def update_settings(payload: Dict[str, Any] = Body(...)):
    # Update financial and runtime settings
    if "RISK_PER_TRADE" in payload:
        config.RISK_PER_TRADE = float(payload["RISK_PER_TRADE"])
    if "DAILY_MAX_LOSS" in payload:
        config.DAILY_MAX_LOSS = float(payload["DAILY_MAX_LOSS"])
    if "MAX_OPEN_POSITIONS" in payload:
        config.MAX_OPEN_POSITIONS = int(payload["MAX_OPEN_POSITIONS"])
    if "MAX_TRADES_PER_DAY" in payload:
        config.MAX_TRADES_PER_DAY = int(payload["MAX_TRADES_PER_DAY"])
    if "SIMULATE_MARKET_HOURS" in payload:
        config.SIMULATE_MARKET_HOURS = bool(payload["SIMULATE_MARKET_HOURS"])
    return {"status": "updated", "config": config.mask_credentials()}

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
