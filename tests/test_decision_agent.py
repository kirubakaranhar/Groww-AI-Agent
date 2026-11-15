"""
Unit Tests for Decision Agent Scoring Engine
"""

import pytest
from backend.models.schemas import TechnicalAnalysisReport, IndicatorValues, DecisionTypeEnum, MarketQuote
from backend.agents.decision_agent import decision_agent
from backend.services.market_data import market_data_hub

@pytest.fixture
def dummy_analysis():
    ind = IndicatorValues(
        ema_9=1020.0,
        ema_21=1010.0,
        ema_50=1000.0,
        ema_200=980.0,
        rsi_14=62.0,
        macd=5.2,
        macd_signal=3.1,
        macd_hist=2.1,
        vwap=1012.0,
        atr_14=12.0,
        bb_upper=1035.0,
        bb_middle=1015.0,
        bb_lower=995.0,
        rvol=1.8,
        pdh=1018.0,
        pdl=995.0,
        or_high=1015.0,
        or_low=1002.0
    )
    return TechnicalAnalysisReport(
        symbol="SBIN",
        indicators=ind,
        trend_score=24.0,
        momentum_score=18.0,
        volume_score=18.0,
        price_action_score=16.0,
        regime_score=8.5,
        data_quality_score=5.0,
        total_score=89.5,
        key_findings=["Strong bullish breakout"],
        support_level=995.0,
        resistance_level=1018.0,
        timestamp="2026-11-15 10:15:00"
    )

def test_decision_agent_generates_buy_for_high_score(dummy_analysis):
    market_data_hub.update_quote(MarketQuote(
        symbol="SBIN",
        ltp=1022.0,
        open=1005.0,
        high=1025.0,
        low=1002.0,
        close=1022.0,
        volume=800000,
        vwap=1012.0,
        change_pct=1.69,
        timestamp="2026-11-15 10:15:00"
    ))
    signal = decision_agent.evaluate_candidate(dummy_analysis, market_regime_suitable=True)
    assert signal.decision == DecisionTypeEnum.BUY
    assert signal.total_score >= 70.0
    assert signal.suggested_stop_loss < signal.entry_reference_price
    assert signal.suggested_target > signal.entry_reference_price

def test_decision_agent_rejects_when_regime_unsuitable(dummy_analysis):
    signal = decision_agent.evaluate_candidate(dummy_analysis, market_regime_suitable=False)
    assert signal.decision == DecisionTypeEnum.NO_TRADE
    assert any("regime is unsuitable" in r.lower() for r in signal.reasons)

def test_decision_agent_rejects_low_score(dummy_analysis):
    dummy_analysis.total_score = 45.0  # Below 70 threshold
    signal = decision_agent.evaluate_candidate(dummy_analysis, market_regime_suitable=True)
    assert signal.decision == DecisionTypeEnum.NO_TRADE
    assert any("below configured threshold" in r.lower() for r in signal.reasons)
