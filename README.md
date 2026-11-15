# Groww Autonomous AI Trading Agent
### Version 1.0 – Multi-Agent Quantitative Autonomous System for NSE Cash Equities

---

## 1. Project Overview

**Groww AI Trading Agent** is a full-featured, continuously operating multi-agent quantitative trading system built specifically for the Indian stock market (NSE cash equity segment) utilizing the Groww Trading API.

Unlike conventional dashboards or simple wrappers, this system is an **autonomous algorithmic trading system**:
- A **Master Supervisor Agent** coordinates 8 specialized autonomous agents.
- Continuously scans eligible NSE equities, calculates technical indicators, identifies market regimes, scores opportunities using explainable rules, enforces deterministic non-bypassable risk controls, executes realistic paper orders, monitors trailing stop-losses, and generates end-of-day audit reports.
- Runs independently on the Python backend with persistent SQLite storage and an event-driven WebSocket pipeline.
- Features a desktop-first **Dark AI Command Center** control interface (HTML5, CSS3, Vanilla JavaScript).
- **Default Execution Mode:** Paper Trading (Safe Default). Live trading remains locked behind a multi-step SEBI/NSE compliance safety gate.

---

## 2. Multi-Agent Architecture

```
                               +-----------------------------+
                               |   MASTER SUPERVISOR AGENT   |
                               +--------------+--------------+
                                              |
      +-------------------+-------------------+-------------------+-------------------+
      |                   |                   |                   |                   |
+-----v-------+     +-----v-------+     +-----v-------+     +-----v-------+     +-----v-------+
|   MARKET    |     |    STOCK    |     |   MARKET    |     |  DECISION   |     |    RISK     |
|   WATCHER   |     |   ANALYST   |     |   REGIME    |     |    AGENT    |     |   MANAGER   |
+-------------+     +-------------+     +-------------+     +-------------+     +------+------+
                                                                                       |
                                                          +----------------------------+
                                                          | Authorizes only if risk approved
                                                    +-----v-------+     +-------------+
                                                    |  EXECUTION  | --> |  POSITION   |
                                                    |    AGENT    |     |   MONITOR   |
                                                    +-------------+     +------+------+
                                                                               |
                                                                        +------v------+
                                                                        |  REPORTING  |
                                                                        |    AGENT    |
                                                                        +-------------+
```

| Agent Name | Core Responsibilities |
| :--- | :--- |
| **1. Master Supervisor Agent** | Central coordinator. Orchestrates agent loops, resolves conflicts, maintains authoritative state, and authorizes paper orders only after risk approval. |
| **2. Market Watcher Agent** | Loads official NSE cash instrument universe, maintains real-time LTP/volume feeds, detects unusual volume surges (RVOL ≥ 1.5), and handles rate-limited batch scanning. |
| **3. Stock Analyst Agent** | Computes mathematical indicators (EMA 9/21/50/200, RSI 14, MACD, VWAP, ATR 14, Bollinger Bands, ORB, PDH/PDL) and produces transparent analysis reports. |
| **4. Market Regime Agent** | Evaluates NIFTY 50 benchmark health, Advance/Decline ratio, and market volatility to determine if macro conditions suit fresh long entries. |
| **5. Decision Agent** | Transparent 100-point multi-factor scoring engine (Trend 25, Momentum 20, Volume 20, Price Action 20, Regime 10, Data 5). Enforces minimum threshold (default 70). |
| **6. Risk Manager Agent** | Deterministic non-bypassable gatekeeper. Validates available capital, position sizing, exact Indian statutory charges & slippage, R:R ≥ 1.5, daily max loss (₹50), max positions (1), and daily trades limit (2). |
| **7. Execution Agent** | Paper Trading simulator. Models realistic slippage (0.05%) and statutory charges, assigns unique order IDs, and updates the SQLite database. |
| **8. Position Monitor Agent** | Tracks open paper positions against Stop Loss and Target, manages trailing stop-loss (1R profit moves SL to breakeven/trails), and enforces mandatory 15:15 IST auto square-off. |
| **9. Reporting Agent** | Computes Win Rate, Profit Factor, Max Drawdown, and Net P&L. Generates daily JSON and Markdown reports in `reports/`. |

---

## 3. Directory Structure

```
Groww AI Agent/
├── .env.example                # Configuration template
├── .env                        # Active local configuration (git-ignored)
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Python dependencies
├── README.md                   # Complete architectural guide
├── backend/
│   ├── main.py                 # FastAPI application and WebSocket server
│   ├── core/
│   │   ├── config.py           # Pydantic settings & validation
│   │   ├── logger.py           # Structured IST logger with credential masking
│   │   ├── scheduler.py        # NSE market calendar, hours, & holidays
│   │   └── security.py         # Live trading compliance gate & credential protection
│   ├── models/
│   │   └── schemas.py          # Pydantic schemas for quotes, signals, & reports
│   ├── database/
│   │   ├── db.py               # SQLite engine, tables initialization, & queries
│   │   └── models.py           # Database entities
│   ├── services/
│   │   ├── groww_service.py    # Official Groww API client & safe offline mock engine
│   │   ├── market_data.py      # Market data cache, freshness, & RVOL detector
│   │   ├── strategy_engine.py  # Technical indicator math & confirmation rules
│   │   └── backtesting.py      # Walk-forward historical backtesting engine
│   ├── agents/
│   │   ├── master_agent.py     # Master Supervisor Agent
│   │   ├── market_watcher.py   # Market Watcher Agent
│   │   ├── stock_analyst.py    # Stock Analyst Agent
│   │   ├── market_regime.py    # Market Regime Agent
│   │   ├── decision_agent.py   # Decision Agent
│   │   ├── risk_manager.py     # Risk Manager Agent
│   │   ├── execution_agent.py  # Paper Execution Agent
│   │   ├── position_monitor.py # Position Monitor Agent
│   │   └── reporting_agent.py  # Reporting Agent
│   └── api/
│       ├── routes.py           # REST endpoints
│       └── websocket.py        # WebSocket connection manager
├── frontend/
│   ├── index.html              # Desktop-first dark AI Command Center
│   ├── css/
│   │   └── styles.css          # Cybernetic trading terminal design
│   └── js/
│       └── app.js              # Real-time WebSocket controller & UI updater
├── tests/
│   ├── test_indicators.py      # Quantitative indicators tests
│   ├── test_risk_manager.py    # Deterministic risk engine & kill switch tests
│   ├── test_decision_agent.py  # Multi-factor scoring tests
│   ├── test_execution_agent.py # Paper execution & charges tests
│   └── test_master_agent.py    # Master Agent lifecycle & backtest tests
└── reports/                    # Generated trading reports
```

---

## 4. Installation & Setup

### Prerequisites
- Python 3.10+ (Tested on Python 3.12)
- Windows, macOS, or Linux

### 1. Initialize Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

---

## 5. How to Connect Groww API

1. Open your `.env` file.
2. Enter your credentials obtained from the Groww Developer Console:
```ini
GROWW_API_KEY=your_groww_api_key_here
GROWW_API_SECRET=your_groww_api_secret_here
GROWW_ENVIRONMENT=SANDBOX   # or PRODUCTION
```
3. **Safe Offline / Sandbox Mode**: If API keys are not supplied or Groww servers are unreachable, the system automatically falls back to **SAFE OFFLINE MOCK MODE**. This loads real NSE equities (RELIANCE, TCS, INFY, HDFCBANK, etc.) and generates realistic time-series quotes, allowing 100% safe testing without network errors.

---

## 6. How to Start the Trading Agent

Run the backend server using the virtual environment:
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open your browser and navigate to:
```
http://127.0.0.1:8000
```

---

## 7. How to Test Paper Trading

1. In the browser command center, click **"⚙ Settings"**.
2. If testing outside NSE trading hours (09:15 - 15:30 IST) or on weekends, set **Simulate Market Hours** to `True` and click **"Save Settings"**.
3. Click **"▶ Start All Agents"** in the top navigation bar.
4. The Master Supervisor will initialize the universe, scan quotes, compute technical indicators, and evaluate candidate stocks.
5. Watch the **Stock Analyst & Decision Engine** card calculate scores. When a candidate reaches ≥ 70 points with full strategy confirmations:
   - The Risk Manager validates capital and position sizing.
   - The Master Agent authorizes execution.
   - A paper BUY order is executed with realistic slippage and statutory charges.
   - The position appears in **"Active Paper Positions"**.
   - The Position Monitor manages trailing stop-loss and exits at target or SL.
6. Click **"🚨 Emergency Shutdown"** at any time to test the kill switch.

---

## 8. Running Automated Tests

Run the complete test suite:
```powershell
.\.venv\Scripts\pytest.exe -v
```

All 15 unit and integration tests verify:
- Indicator calculations (EMA, RSI, MACD, VWAP, ATR, BB)
- Deterministic risk engine rules (Capital allocation, R:R ≥ 1.5, Max loss kill switch, Max daily trades)
- Scoring engine logic (Regime rejection, low score rejection, BUY trigger)
- Paper execution slippage and full Indian regulatory fee accounting
- Master Supervisor lifecycle and backtesting walk-forward validation

---

## 9. Risk & Regulatory Disclaimers

- **Paper Trading Default:** The system runs in paper trading simulation mode by default.
- **Explainable Rules:** All AI decisions are grounded in deterministic quantitative rules. The system makes no claim of predicting future stock prices with certainty.
- **SEBI / NSE Compliance:** Live trading execution is locked behind a strict multi-step compliance gate requiring verified Groww authentication, statutory algo acknowledgments, static IP verification, and explicit passphrase confirmation.
