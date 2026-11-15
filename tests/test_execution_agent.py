"""
Unit Tests for Paper Execution Agent
Verifies realistic slippage modeling, order persistence, position updates, and P&L closing.
"""

import pytest
from backend.models.schemas import RiskValidationResult, OrderStatusEnum
from backend.agents.execution_agent import execution_agent
from backend.database.db import db

@pytest.fixture(autouse=True)
def clean_db():
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
        losing_trades_today = 0
    WHERE id = 1;
    """)
    conn.commit()
    conn.close()

def test_paper_buy_execution():
    risk_res = RiskValidationResult(
        is_approved=True,
        rejection_reasons=[],
        calculated_quantity=2,
        entry_price=1000.0,
        stop_loss=985.0,
        target=1030.0,
        risk_amount=30.0,
        estimated_brokerage=2.0,
        estimated_stt=0.5,
        estimated_taxes=1.0,
        estimated_slippage=1.0,
        total_estimated_charges=4.5
    )

    order = execution_agent.execute_paper_buy("INFY", risk_res, "EMA Strategy")
    assert order is not None
    assert order.status == OrderStatusEnum.FILLED
    # Slippage check: buy execution price must be slightly above reference
    assert order.executed_price >= order.reference_price

    # Verify open position exists
    open_positions = db.get_open_positions()
    assert len(open_positions) == 1
    assert open_positions[0]["symbol"] == "INFY"
    assert open_positions[0]["quantity"] == 2

def test_paper_sell_closing_position():
    # First buy
    risk_res = RiskValidationResult(
        is_approved=True,
        rejection_reasons=[],
        calculated_quantity=2,
        entry_price=1000.0,
        stop_loss=985.0,
        target=1030.0,
        risk_amount=30.0,
        estimated_brokerage=2.0,
        estimated_stt=0.5,
        estimated_taxes=1.0,
        estimated_slippage=1.0,
        total_estimated_charges=4.5
    )
    execution_agent.execute_paper_buy("TCS", risk_res, "Test")
    pos = db.get_open_positions()[0]

    # Now sell at target price ₹1030
    sell_res = execution_agent.execute_paper_sell(
        position_id=pos["position_id"],
        symbol="TCS",
        quantity=2,
        entry_price=pos["entry_price"],
        exit_reference_price=1030.0,
        exit_reason="TARGET_ACHIEVED"
    )

    assert sell_res["symbol"] == "TCS"
    assert sell_res["exit_price"] <= 1030.0  # Sell slippage executed below reference
    # Net PnL must be positive on profitable trade
    assert sell_res["net_pnl"] > 0

    # Ensure no open positions remain
    assert len(db.get_open_positions()) == 0
    # Ensure completed trade was recorded
    assert len(db.get_trades()) == 1
