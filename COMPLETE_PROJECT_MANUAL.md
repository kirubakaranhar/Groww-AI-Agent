# 🚀 GROWW AUTONOMOUS AI TRADING AGENT (v1.0)
## Complete Project Manual & Architectural Specification

---

### 1. Project Summary & Core Configuration

- **Project Name:** Groww Autonomous AI Trading Agent
- **Target Market:** Indian Stock Market (NSE Cash Equity Intraday)
- **Broker Interface:** Groww Trading API (with Graceful Offline Simulation Fallback)
- **Initial Mode:** Paper Trading (Safe Default; Live trading locked by multi-step compliance gate)
- **Capital Constraints:**
  - Starting Capital: ₹5,000.00
  - Risk Per Trade: ₹25.00 (Max 0.5% - 5% per trade)
  - Daily Maximum Loss: ₹50.00 (Deterministic Kill Switch)
  - Max Open Positions: 1
  - Max Daily Trades: 2
  - Leverage / F&O: Strictly Disabled

---

### 2. Multi-Agent Fleet Architecture (9 Agents + Voice Agent)

```
                       +-------------------------------+
                       |    Master Supervisor Agent    |
                       +---------------+---------------+
                                       |
    +-------------------+--------------+--------------+--------------------+
    |                   |                             |                    |
+---v-------------+ +---v-----------+           +-----v----------+   +---------v------+
| Market Watcher  | | Stock Analyst |           | Market Regime  |   | Decision Agent |
| (NSE Batch Scan)| | (100-pt Score)|           | (Adv/Dec Ratio)|   | (Rule Scoring) |
+-----------------+ +---------------+           +----------------+   +--------+-------+
                                                                              |
                               +----------------------------------------------+
                               |
                        +------v------+
                        | Risk Manager| (Non-Bypassable: Capital, Sizing, Statutory Charges)
                        +------+------+
                               |
                        +------v------+
                        |  Execution  | (Paper BUY/SELL with 0.05% realistic slippage)
                        +------+------+
                               |
                        +------v------+
                        |   Position  | (Trailing SL @ 1R, 15:15 IST Auto Square-off)
                        |   Monitor   |
                        +------+------+
                               |
         +---------------------+---------------------+
         |                                           |
+--------v-------+                         +---------v--------+
| Reporting Agent|                         |   Voice Agent    |
| (Audit Reports)|                         | (Web Speech TTS) |
+----------------+                         +------------------+
```

1. **Master Supervisor Agent** (`backend/agents/master_agent.py`):
   Central orchestrator running an asynchronous event loop. Schedules market scans, monitors health, enforces risk gates, authorizes executions, and handles emergency shutdowns.

2. **Market Watcher Agent** (`backend/agents/market_watcher.py`):
   Loads eligible tradable instruments from the official NSE universe. Monitors live LTP, volumes, and detects relative volume (RVOL) spikes in controlled batches.

3. **Stock Analyst Agent** (`backend/agents/stock_analyst.py`):
   Computes quantitative indicators: EMA (9, 21, 50, 200), RSI 14, MACD (12, 26, 9), VWAP, ATR 14, Bollinger Bands, and Opening Range Breakout (ORB). Outputs a transparent 100-point score report.

4. **Market Regime Agent** (`backend/agents/market_regime.py`):
   Evaluates macro market sentiment (Advance/Decline ratio, index bias). Prevents fresh long entries during adverse macro conditions.

5. **Decision Agent** (`backend/agents/decision_agent.py`):
   Evaluates multi-factor confirmations against configurable thresholds (Score >= 70, Confirmations >= 4). Emits BUY or NO_TRADE decisions with full audit explanations.

6. **Risk Manager Agent** (`backend/agents/risk_manager.py`):
   Deterministic, non-bypassable risk engine. Enforces capital checks, ATR-based position sizing, Indian statutory fees (Brokerage, STT, NSE turnover, SEBI fee, Stamp Duty, GST), Risk:Reward >= 1.5, and activates daily kill-switch at ₹50 loss.

7. **Execution Agent** (`backend/agents/execution_agent.py`):
   Simulates paper order execution with realistic 0.05% slippage, records all fills, and atomically updates available capital and portfolios.

8. **Position Monitor Agent** (`backend/agents/position_monitor.py`):
   Continuously monitors open positions for Target hit, Stop Loss hit, Trailing SL activation (at 1R profit), and executes mandatory 15:15 IST intraday square-offs.

9. **Reporting Agent** (`backend/agents/reporting_agent.py`):
   Compiles comprehensive daily audit summaries (Win Rate, Profit Factor, Gross/Net P&L, Drawdown, Brokerage charges) in JSON and Markdown formats under `reports/`.

10. **Voice Agent** (`backend/agents/voice_agent.py`):
    Generates natural language audio briefings for multi-agent roll-calls, executed trades, profit exits, and emergency alerts using the browser's native Web Speech API (zero external dependencies).

---

### 3. File & Directory Structure

```
c:\Users\ASUS\OneDrive\Desktop\Groww AI Agent\
├── .env.example                     # Sample configuration
├── .env                             # Environment settings & secrets
├── .gitignore                       # Git exclusions (credentials, venv, logs, db)
├── requirements.txt                 # Python dependencies
├── README.md                        # Quickstart documentation
├── run.bat                          # One-click Windows runner
├── run.ps1                          # PowerShell runner
├── start_agent.bat                  # Smart automated startup (with calendar check)
├── stop_agent.bat                   # Graceful shutdown script
├── setup_autostartup.ps1            # Windows Task Scheduler registration script
├── Groww_AI_Trading_Agent_v1.0.zip  # Single-file distributable archive
│
├── backend/
│   ├── main.py                      # FastAPI app entry point & WebSocket server
│   ├── core/
│   │   ├── config.py                # Pydantic v2 settings & credential masking
│   │   ├── logger.py                # Structured IST-aware logger
│   │   ├── scheduler.py             # NSE market hours calendar & 2026 holidays
│   │   └── security.py              # Live trading compliance verification gate
│   ├── models/
│   │   └── schemas.py               # Pydantic schemas for data exchange
│   ├── database/
│   │   ├── db.py                    # SQLite database interface (WAL mode)
│   │   └── models.py                # Database schemas & dataclasses
│   ├── services/
│   │   ├── groww_service.py         # Groww API client & 25-stock simulation engine
│   │   ├── market_data.py           # Real-time MarketDataHub & RVOL tracker
│   │   ├── strategy_engine.py       # Technical indicator computations
│   │   └── backtesting.py           # Walk-forward backtest & grid optimizer
│   ├── agents/                      # 9 Autonomous Agents + Voice Agent
│   └── api/
│       ├── routes.py                # REST endpoints
│       └── websocket.py             # WebSocket telemetry broadcast
│
├── frontend/
│   ├── index.html                   # Dark-themed AI Command Center
│   ├── css/styles.css               # Styling, animations, layout & indicators
│   └── js/app.js                    # HTML5 canvas chart, Web Audio, Voice Agent TTS
│
├── tests/                           # 33 Unit & Integration Tests (100% Pass)
│   ├── test_indicators.py           # Technical indicators validation
│   ├── test_decision_agent.py       # Decision scoring tests
│   ├── test_risk_manager.py         # Risk rules & statutory charges
│   ├── test_execution_agent.py      # Paper buy/sell & slippage
│   ├── test_master_agent.py         # Orchestration & lifecycle
│   ├── test_api_upgrades.py         # Candles, square-off, CSV export
│   ├── test_backtesting_tuning.py   # Backtest & strategy tuning API
│   └── test_voice_agent.py          # Voice briefings & Web Speech endpoints
│
└── reports/                         # Audit reports & performance logs
```

---

### 4. How to Run the Application

#### Option A: Quick Start via Script
Double-click `run.bat` or run in PowerShell:
```powershell
.\run.ps1
```

#### Option B: Manual Terminal Execution
```powershell
cd "c:\Users\ASUS\OneDrive\Desktop\Groww AI Agent"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open your browser and navigate to:
👉 **http://127.0.0.1:8000**

---

### 5. Running the Complete Automated Test Suite (33 Tests)

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```
All 33 tests will execute and pass:
- Indicator calculations & EMA crossovers
- Decision agent scoring & regime filters
- Statutory charges calculation (STT, GST, Stamp Duty, Brokerage)
- Daily kill-switch trigger on ₹50 loss
- Manual square-off & CSV trade export
- Walk-forward backtester & grid-search optimizer
- Voice agent assembly briefings & speech API endpoints

---

### 6. Windows Market-Hours Auto-Startup Setup

To automatically start the agent at 09:00 IST and gracefully shut it down at 15:35 IST every weekday:
1. Open PowerShell as **Administrator**.
2. Run:
```powershell
cd "c:\Users\ASUS\OneDrive\Desktop\Groww AI Agent"
powershell -ExecutionPolicy Bypass -File setup_autostartup.ps1
```
This registers `GrowwAI_MarketOpen` and `GrowwAI_MarketClose` in Windows Task Scheduler.

---

### 7. Key REST API Endpoints

- `GET  /api/system/overview` — Full system status and 9-agent telemetry
- `POST /api/system/start` — Start autonomous multi-agent surveillance
- `POST /api/system/pause` / `resume` / `stop` — Fleet lifecycle controls
- `POST /api/system/emergency-shutdown` — Immediate kill-switch & halt
- `GET  /api/market/quotes` — Real-time quotes for tracked NSE universe
- `GET  /api/market/candles/{symbol}` — OHLCV candles with EMA 9/21 and VWAP overlays
- `GET  /api/trading/positions` — Active open paper positions
- `POST /api/trading/positions/{id}/close` — 1-Click manual position square-off
- `GET  /api/trading/trades/export` — Download trades as CSV
- `POST /api/backtest/run` — Run walk-forward backtest for a specific stock
- `POST /api/backtest/optimize` — Run 81-combination Grid Search optimizer
- `GET  /api/voice/assembly` — Generate complete 9-agent Voice Assembly Briefing
- `GET  /api/voice/heartbeat` — Generate periodic 1-sentence audio heartbeat
- `POST /api/settings/update` — Adjust risk, capital limits, and strategy parameters
- `POST /api/safety-gate/verify-live` — Compliance gate verification for Live mode

---
*Generated for Groww Autonomous AI Trading Agent v1.0. All code, tests, and configuration are self-contained.*
