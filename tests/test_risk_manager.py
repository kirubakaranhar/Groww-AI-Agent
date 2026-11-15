"""
Unit and Safety Gate Tests for Deterministic Risk Manager Agent
"""

import pytest
from backend.core.config import config
from backend.models.schemas import DecisionSignal, DecisionTypeEnum
from backend.agents.risk_manager import risk_manager_agent
from backend.database.db import db

@pytest.fixture(autouse=True)
def setup_test_db():
    """Resets portfolio and kill switch state before tests."""
    risk_manager_agent.reset_kill_switch()
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

def test_statutory_charges_calculation():
    charges = risk_manager_agent.calculate_statutory_charges(
        quantity=10,
        entry_price=1000.0,
        exit_price=1020.0
    )
    # Check that individual statutory charges are positive numbers
    assert charges["brokerage"] > 0
    assert charges["stt"] > 0
    assert charges["nse_charges"] > 0
    assert charges["sebi_charges"] > 0
    assert charges["stamp_duty"] > 0
    assert charges["gst"] > 0
    assert charges["slippage"] > 0
    assert charges["total_charges"] > charges["total_statutory"]

def test_risk_manager_approves_valid_signal():
    signal = DecisionSignal(
        symbol="INFY",
        decision=DecisionTypeEnum.BUY,
        total_score=82.0,
        score_breakdown={"trend": 20, "momentum": 18},
        entry_reference_price=1800.0,
        suggested_stop_loss=1780.0,  # ₹20 risk per share
        suggested_target=1840.0,    # ₹40 reward (1:2 R:R)
        risk_reward_ratio=2.0,
        strategy_name="EMA & VWAP Breakout",
        reasons=["Bullish alignment"],
        timestamp="2026-11-15 10:00:00",
        explanation="Valid test signal"
    )

    result = risk_manager_agent.validate_trade_signal(signal)
    assert result.is_approved is True
    assert result.calculated_quantity >= 1
    assert len(result.rejection_reasons) == 0

def test_risk_manager_rejects_unfavorable_risk_reward():
    signal = DecisionSignal(
        symbol="TCS",
        decision=DecisionTypeEnum.BUY,
        total_score=75.0,
        score_breakdown={},
        entry_reference_price=4000.0,
        suggested_stop_loss=3950.0,  # ₹50 risk
        suggested_target=4020.0,    # ₹20 reward (0.4 R:R, below 1.5 min)
        risk_reward_ratio=0.4,
        strategy_name="Test",
        reasons=[],
        timestamp="2026-11-15 10:00:00",
        explanation="Poor R:R signal"
    )

    result = risk_manager_agent.validate_trade_signal(signal)
    assert result.is_approved is False
    assert any("UNFAVORABLE RISK/REWARD" in r for r in result.rejection_reasons)

def test_risk_manager_rejects_when_daily_trades_exceeded():
    # Set trades today to 2 (limit is 2)
    conn = db.get_connection()
    conn.execute("UPDATE portfolio SET total_trades_today = 2 WHERE id = 1;")
    conn.commit()
    conn.close()

    signal = DecisionSignal(
        symbol="RELIANCE",
        decision=DecisionTypeEnum.BUY,
        total_score=85.0,
        score_breakdown={},
        entry_reference_price=2800.0,
        suggested_stop_loss=2770.0,
        suggested_target=2860.0,
        risk_reward_ratio=2.0,
        strategy_name="Test",
        reasons=[],
        timestamp="2026-11-15 10:00:00",
        explanation="Exceeded trades test"
    )

    result = risk_manager_agent.validate_trade_signal(signal)
    assert result.is_approved is False
    assert any("MAX DAILY TRADES LIMIT REACHED" in r for r in result.rejection_reasons)

def test_risk_manager_trips_kill_switch_on_max_loss():
    # Simulate a realized loss of ₹55 (exceeds ₹50 limit)
    conn = db.get_connection()
    conn.execute("UPDATE portfolio SET realized_daily_pnl = -55.0 WHERE id = 1;")
    conn.commit()
    conn.close()

    signal = DecisionSignal(
        symbol="HDFCBANK",
        decision=DecisionTypeEnum.BUY,
        total_score=85.0,
        score_breakdown={},
        entry_reference_price=1600.0,
        suggested_stop_loss=1580.0,
        suggested_target=1640.0,
        risk_reward_ratio=2.0,
        strategy_name="Test",
        reasons=[],
        timestamp="2026-11-15 10:00:00",
        explanation="Kill switch trigger test"
    )

    result = risk_manager_agent.validate_trade_signal(signal)
    assert result.is_approved is False
    assert risk_manager_agent.is_kill_switch_active is True
