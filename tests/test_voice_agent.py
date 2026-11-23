"""
Tests for Voice Agent briefing text generation and Voice API endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.agents.voice_agent import VoiceAgent


def _mock_agents():
    return {
        "master_agent":    {"state": "RUNNING", "message": "Cycles: 42"},
        "market_watcher":  {"state": "SCANNING", "message": "25 instruments active"},
        "stock_analyst":   {"state": "ANALYZING", "message": "Processed 12 stocks"},
        "market_regime":   {"state": "IDLE", "message": "Regime: BULLISH"},
        "decision_agent":  {"state": "DECIDING", "message": "Evaluating candidates"},
        "risk_manager":    {"state": "IDLE", "message": "Kill switch: INACTIVE"},
        "execution_agent": {"state": "IDLE", "message": "0 orders today"},
        "position_monitor":{"state": "MONITORING", "message": "1 open position"},
        "reporting_agent": {"state": "IDLE", "message": "Report ready"},
    }

def _mock_portfolio(pnl=33.5, trades=1, kill=False):
    return {
        "total_capital": 5000.0,
        "available_capital": 4700.0,
        "realized_daily_pnl": pnl,
        "total_trades_today": trades,
        "is_kill_switch_active": kill,
    }

def _mock_session(open=True):
    return {
        "status": "OPEN" if open else "CLOSED",
        "phase": "NORMAL_TRADING" if open else "POST_MARKET",
        "is_trading_allowed": open,
        "reason": "NSE regular intraday trading active" if open else "Market closed"
    }


class TestVoiceAgentBriefings:

    def test_assembly_briefing_contains_all_agents(self):
        va = VoiceAgent()
        result = va.generate_assembly_briefing(
            agents=_mock_agents(),
            portfolio=_mock_portfolio(),
            market_session=_mock_session(open=True),
            open_positions=[{"symbol": "NTPC"}],
            active_signals=2
        )
        text = result["text"]
        assert result["type"] == "ASSEMBLY"
        assert "Master Supervisor" in text
        assert "Market Watcher" in text
        assert "Stock Analyst" in text
        assert "Decision Agent" in text
        assert "Risk Manager" in text
        assert "Position Monitor" in text
        assert "Reporting Agent" in text
        assert "NTPC" in text
        assert "₹" in text
        assert result["word_count"] > 50

    def test_trade_briefing(self):
        va = VoiceAgent()
        result = va.generate_trade_briefing({
            "symbol": "NTPC", "side": "BUY",
            "quantity": 6, "executed_price": 387.5,
            "stop_loss": 383.0, "target": 393.0
        })
        assert result["type"] == "TRADE"
        assert "NTPC" in result["text"]
        assert "387.50" in result["text"]
        assert "Stop loss" in result["text"] or "stop loss" in result["text"]

    def test_exit_briefing_target_hit(self):
        va = VoiceAgent()
        result = va.generate_exit_briefing({
            "symbol": "NTPC", "net_pnl": 33.73,
            "exit_reason": "TARGET_HIT", "exit_price": 393.0
        })
        assert result["type"] == "EXIT"
        assert "TARGET_HIT" not in result["text"]  # human-readable, not raw enum
        assert "Target reached" in result["text"]
        assert "profit" in result["text"]
        assert "33.73" in result["text"]

    def test_kill_switch_briefing_is_urgent(self):
        va = VoiceAgent()
        result = va.generate_kill_switch_briefing(daily_loss=-52.0)
        assert result["type"] == "KILL"
        assert result["urgent"] is True
        assert "52.00" in result["text"]
        assert "ACTIVE" in result["text"]

    def test_heartbeat_briefing_market_open(self):
        va = VoiceAgent()
        result = va.generate_heartbeat_briefing(
            portfolio=_mock_portfolio(pnl=20.0, trades=1),
            market_session=_mock_session(open=True),
            open_positions=[{"symbol": "SBIN"}]
        )
        assert result["type"] == "HEARTBEAT"
        assert "1 open position" in result["text"]
        assert "up" in result["text"]

    def test_session_open_announcement(self):
        va = VoiceAgent()
        result = va.generate_session_briefing(is_open=True, reason="")
        assert "OPEN" in result["text"]
        assert "Market Watcher" in result["text"]

    def test_last_briefing_persists(self):
        va = VoiceAgent()
        va.generate_heartbeat_briefing(
            portfolio=_mock_portfolio(),
            market_session=_mock_session(),
            open_positions=[]
        )
        last = va.get_last_briefing()
        assert last["type"] == "HEARTBEAT"
        assert len(last["text"]) > 10


class TestVoiceAPIEndpoints:

    def test_assembly_endpoint(self):
        client = TestClient(app)
        r = client.get("/api/voice/assembly")
        assert r.status_code == 200
        d = r.json()
        assert d["type"] == "ASSEMBLY"
        assert len(d["text"]) > 50
        assert d["word_count"] > 10

    def test_heartbeat_endpoint(self):
        client = TestClient(app)
        r = client.get("/api/voice/heartbeat")
        assert r.status_code == 200
        d = r.json()
        assert d["type"] == "HEARTBEAT"
        assert len(d["text"]) > 10

    def test_trade_endpoint(self):
        client = TestClient(app)
        r = client.post("/api/voice/trade", json={
            "symbol": "ITC", "side": "BUY",
            "quantity": 10, "executed_price": 491.5,
            "stop_loss": 487.0, "target": 498.5
        })
        assert r.status_code == 200
        assert "ITC" in r.json()["text"]

    def test_exit_endpoint(self):
        client = TestClient(app)
        r = client.post("/api/voice/exit", json={
            "symbol": "ITC", "net_pnl": 45.0,
            "exit_reason": "TARGET_HIT", "exit_price": 498.5
        })
        assert r.status_code == 200
        assert "Target reached" in r.json()["text"]

    def test_last_briefing_endpoint(self):
        client = TestClient(app)
        # Trigger a briefing first
        client.get("/api/voice/heartbeat")
        r = client.get("/api/voice/last")
        assert r.status_code == 200
        d = r.json()
        assert "text" in d
        assert "type" in d

    def test_session_endpoint(self):
        client = TestClient(app)
        r = client.get("/api/voice/session")
        assert r.status_code == 200
        d = r.json()
        assert d["type"] == "SESSION"
        assert len(d["text"]) > 10
