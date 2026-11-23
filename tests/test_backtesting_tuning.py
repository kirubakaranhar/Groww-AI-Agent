"""
Tests for Walk-Forward Backtesting, Trailing SL Simulation, Universe Backtest,
Grid-Search Strategy Optimizer, and Strategy Tuning Settings API.
"""

import random
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import config
from backend.services.backtesting import BacktestingEngine


def _generate_trending_candles(base_price: float = 380.0, count: int = 160, seed: int = 42):
    """Generates deterministic intraday 5m candles with realistic swings and volume bursts."""
    rng = random.Random(seed)
    candles = []
    price = base_price
    for i in range(count):
        # Mild upward wave + volatility so EMA/VWAP/RSI setups trigger naturally
        drift = 0.0008 if (i % 30) < 20 else -0.0005
        change = price * (drift + rng.gauss(0, 0.0035))
        open_p = price
        close_p = max(10.0, price + change)
        high_p = max(open_p, close_p) + abs(rng.gauss(0, price * 0.0015))
        low_p = min(open_p, close_p) - abs(rng.gauss(0, price * 0.0015))
        vol = int(rng.randint(10000, 35000) * (1.8 if (i % 7 == 0) else 1.0))
        candles.append({
            "timestamp": f"2026-11-18 09:{15 + (i % 45):02d}:00",
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": vol
        })
        price = close_p
    return candles


def test_single_stock_walk_forward_backtest_with_custom_params():
    engine = BacktestingEngine(initial_capital=5000.0)
    candles = _generate_trending_candles(base_price=385.0, count=180, seed=101)

    res = engine.run_backtest(
        symbol="NTPC",
        candles=candles,
        params={"min_confirmations": 3, "atr_sl_multiplier": 1.2, "rr_ratio": 1.5, "min_rvol": 1.1}
    )

    assert "error" not in res
    assert res["symbol"] == "NTPC"
    assert res["parameters_used"]["min_confirmations"] == 3
    assert res["in_sample_candles"] + res["out_of_sample_candles"] == 180
    assert "equity_curve" in res["overall_performance"]
    assert res["overall_performance"]["equity_curve"][0]["capital"] == 5000.0
    assert res["overall_performance"]["total_trades"] >= 1


def test_universe_backtest_and_grid_search_optimizer():
    engine = BacktestingEngine(initial_capital=5000.0)
    universe = {
        "NTPC": _generate_trending_candles(385.0, 160, seed=11),
        "TATASTEEL": _generate_trending_candles(155.0, 160, seed=22),
        "ONGC": _generate_trending_candles(280.0, 160, seed=33),
    }

    uni_res = engine.run_universe_backtest(universe)
    assert uni_res["stocks_tested"] == 3
    assert "aggregate" in uni_res
    assert set(uni_res["per_stock"].keys()) == {"NTPC", "TATASTEEL", "ONGC"}

    opt_res = engine.optimize_strategy(universe)
    assert "error" not in opt_res
    assert opt_res["combinations_tested"] == 81  # 3 x 3 x 3 x 3 grid
    assert len(opt_res["top_candidates"]) == 5
    assert "recommended" in opt_res
    assert "out_of_sample" in opt_res["recommended"]
    assert "decision_min_score_threshold" in opt_res["recommended"]["params"]


def test_backtest_optimize_and_settings_tuning_api():
    client = TestClient(app)

    # Save original config values to restore after test
    orig_score = config.DECISION_MIN_SCORE_THRESHOLD
    orig_conf = config.STRATEGY_MIN_CONFIRMATIONS
    orig_atr = config.STRATEGY_ATR_SL_MULTIPLIER
    orig_rr = config.MIN_RISK_REWARD_RATIO
    orig_rvol = config.STRATEGY_MIN_RVOL

    try:
        # 1. Single backtest endpoint
        r1 = client.post("/api/backtest/run", json={"symbol": "NTPC", "limit": 120})
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["symbol"] == "NTPC"
        assert "overall_performance" in d1
        assert "all_trades" not in d1["overall_performance"]

        # 2. Optimize endpoint (small subset for fast test)
        r2 = client.post("/api/backtest/optimize", json={"symbols": ["NTPC", "TATASTEEL"], "limit": 120})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["combinations_tested"] == 81
        assert "recommended" in d2

        # 3. Settings update with strategy parameters
        r3 = client.post("/api/settings/update", json={
            "DECISION_MIN_SCORE_THRESHOLD": 68.0,
            "STRATEGY_MIN_CONFIRMATIONS": 3,
            "STRATEGY_ATR_SL_MULTIPLIER": 1.2,
            "MIN_RISK_REWARD_RATIO": 2.0,
            "STRATEGY_MIN_RVOL": 1.1
        })
        assert r3.status_code == 200
        cfg = r3.json()["config"]
        assert cfg["DECISION_MIN_SCORE_THRESHOLD"] == 68.0
        assert cfg["STRATEGY_MIN_CONFIRMATIONS"] == 3
        assert cfg["STRATEGY_ATR_SL_MULTIPLIER"] == 1.2
        assert cfg["MIN_RISK_REWARD_RATIO"] == 2.0
        assert cfg["STRATEGY_MIN_RVOL"] == 1.1

        # 4. Guardrail check: rejecting RISK_PER_TRADE > 5% of initial capital
        r4 = client.post("/api/settings/update", json={"RISK_PER_TRADE": 500.0})
        assert r4.status_code == 400
    finally:
        config.DECISION_MIN_SCORE_THRESHOLD = orig_score
        config.STRATEGY_MIN_CONFIRMATIONS = orig_conf
        config.STRATEGY_ATR_SL_MULTIPLIER = orig_atr
        config.MIN_RISK_REWARD_RATIO = orig_rr
        config.STRATEGY_MIN_RVOL = orig_rvol
