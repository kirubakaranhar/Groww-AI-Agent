"""
Integration Tests for Frontend 100% Upgrade APIs:
- Live Candles + EMA 9/21/VWAP overlay endpoint
- 1-Click Manual Position Square-Off endpoint
- CSV Export endpoint for completed paper trades
"""

import pytest
import httpx
from backend.main import app
from backend.database.db import db
from backend.models.schemas import RiskValidationResult
from backend.agents.execution_agent import execution_agent

@pytest.fixture(autouse=True)
def reset_state():
    conn = db.get_connection()
    conn.execute("DELETE FROM positions;")
    conn.execute("DELETE FROM paper_orders;")
    conn.execute("DELETE FROM trades;")
    conn.execute("""
    UPDATE portfolio SET
        total_capital = 5000.0,
        available_capital = 5000.0,
        invested_capital = 0.0,
        realized_daily_pnl = 0.0,
        unrealized_pnl = 0.0,
        total_trades_today = 0,
        winning_trades_today = 0,
        losing_trades_today = 0,
        is_kill_switch_active = 0
    WHERE id = 1;
    """)
    conn.commit()
    conn.close()

@pytest.mark.asyncio
async def test_market_candles_with_overlays():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/market/candles/RELIANCE?interval=5m&limit=40")
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == "RELIANCE"
        assert len(data["candles"]) == 40
        sample = data["candles"][-1]
        for key in ["open", "high", "low", "close", "volume", "ema_9", "ema_21", "vwap"]:
            assert key in sample

@pytest.mark.asyncio
async def test_manual_position_square_off_and_csv_export():
    # Open a paper position first
    risk_res = RiskValidationResult(
        is_approved=True,
        rejection_reasons=[],
        calculated_quantity=3,
        entry_price=500.0,
        stop_loss=492.0,
        target=515.0,
        risk_amount=24.0,
        estimated_brokerage=1.5,
        estimated_stt=0.4,
        estimated_taxes=0.6,
        estimated_slippage=0.75,
        total_estimated_charges=3.25
    )
    execution_agent.execute_paper_buy("ITC", risk_res, "EMA Strategy")
    open_positions = db.get_open_positions()
    assert len(open_positions) == 1
    pos_id = open_positions[0]["position_id"]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Manual Square-Off
        close_res = await client.post(f"/api/trading/positions/{pos_id}/close")
        assert close_res.status_code == 200
        body = close_res.json()
        assert body["status"] == "closed"
        assert body["trade"]["symbol"] == "ITC"
        assert body["trade"]["exit_reason"] == "MANUAL_SQUARE_OFF_BY_OPERATOR"
        assert len(db.get_open_positions()) == 0

        # 2. Attempting to close again returns 404
        dup_res = await client.post(f"/api/trading/positions/{pos_id}/close")
        assert dup_res.status_code == 404

        # 3. Export CSV includes the closed ITC trade
        csv_res = await client.get("/api/trading/trades/export")
        assert csv_res.status_code == 200
        assert "text/csv" in csv_res.headers["content-type"]
        assert "trade_id,symbol,side,quantity" in csv_res.text
        assert "ITC,BUY,3" in csv_res.text
