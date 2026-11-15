"""
Unit Tests for Quantitative Indicators & Strategy Confirmation Engine
"""

import pytest
import numpy as np
from backend.services.strategy_engine import strategy_engine

@pytest.fixture
def sample_candles():
    """Generates 50 synthetic candles for indicator verification."""
    candles = []
    base_price = 1000.0
    for i in range(50):
        # Create an upward trending price series
        open_p = base_price + (i * 2.5)
        close_p = open_p + 1.8
        high_p = close_p + 1.2
        low_p = open_p - 0.8
        vol = 10000 + (i * 500)
        candles.append({
            "timestamp": f"2026-11-15 09:{i:02d}:00",
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": vol
        })
    return candles

def test_calculate_indicators_structure(sample_candles):
    ind = strategy_engine.calculate_indicators(sample_candles)
    assert ind is not None
    # Verify indicator fields exist and are positive
    assert ind.ema_9 > 0
    assert ind.ema_21 > 0
    assert ind.ema_50 > 0
    assert ind.vwap > 0
    assert ind.atr_14 > 0
    assert 0 <= ind.rsi_14 <= 100
    assert ind.bb_upper >= ind.bb_middle >= ind.bb_lower

def test_ema_alignment_in_uptrend(sample_candles):
    ind = strategy_engine.calculate_indicators(sample_candles)
    # In an established uptrend, shorter EMA should be above longer EMA
    assert ind.ema_9 > ind.ema_21

def test_strategy_confirmation(sample_candles):
    ind = strategy_engine.calculate_indicators(sample_candles)
    current_price = sample_candles[-1]["close"]
    res = strategy_engine.evaluate_strategy_confirmation(
        current_price=current_price,
        ind=ind,
        market_regime_bullish=True
    )
    assert "confirmations_count" in res
    assert "stop_loss" in res
    assert "target" in res
    assert res["stop_loss"] < current_price < res["target"]
    assert res["risk_reward_ratio"] >= 1.5
