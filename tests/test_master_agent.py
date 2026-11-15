"""
Integration Tests for Master Supervisor Agent and Backtesting Engine
"""

import pytest
import asyncio
from backend.agents.master_agent import master_agent
from backend.services.backtesting import backtesting_engine

@pytest.mark.asyncio
async def test_master_agent_lifecycle():
    # Start
    start_res = await master_agent.start()
    assert start_res["status"] in ("started", "already_running")
    assert master_agent.is_running is True

    # Pause
    master_agent.pause()
    assert master_agent.is_paused is True

    # Resume
    master_agent.resume()
    assert master_agent.is_paused is False

    # Stop
    await master_agent.stop()
    assert master_agent.is_running is False

def test_backtesting_walk_forward_engine():
    # Generate 60 test candles
    candles = []
    base_p = 500.0
    for i in range(60):
        candles.append({
            "timestamp": f"2026-11-15 09:{i:02d}:00",
            "open": base_p + (i * 0.5),
            "high": base_p + (i * 0.5) + 2.0,
            "low": base_p + (i * 0.5) - 1.0,
            "close": base_p + (i * 0.5) + 1.2,
            "volume": 25000 + (i * 200)
        })

    res = backtesting_engine.run_backtest(symbol="TEST_STOCK", candles=candles)
    assert "overall_performance" in res
    assert "out_of_sample_validation" in res
    assert res["symbol"] == "TEST_STOCK"
    assert res["total_candles"] == 60
    assert "win_rate_pct" in res["overall_performance"]
    assert "profit_factor" in res["overall_performance"]
