/**
 * Groww Autonomous AI Trading Agent - Command Center Controller
 * Pure Vanilla JavaScript Client managing WebSocket telemetry,
 * real-time UI rendering, agent lifecycle control, and risk monitor.
 */

// State
let ws = null;
let systemState = null;
let currentCandidate = null;

// DOM Elements
const systemPulse = document.getElementById("systemPulse");
const sessionStatusText = document.getElementById("sessionStatusText");
const istClock = document.getElementById("istClock");
const executionModeBadge = document.getElementById("executionModeBadge");

const valInitialCapital = document.getElementById("valInitialCapital");
const valAvailCapital = document.getElementById("valAvailCapital");
const valInvestedCapital = document.getElementById("valInvestedCapital");
const valRealizedPnl = document.getElementById("valRealizedPnl");
const valUnrealizedPnl = document.getElementById("valUnrealizedPnl");
const valTradesCount = document.getElementById("valTradesCount");
const valLossHeadroom = document.getElementById("valLossHeadroom");

const agentsGrid = document.getElementById("agentsGrid");
const scannerTableBody = document.getElementById("scannerTableBody");
const scannerCount = document.getElementById("scannerCount");
const growwFeedStatus = document.getElementById("growwFeedStatus");
const decisionCardContainer = document.getElementById("decisionCardContainer");
const positionsContainer = document.getElementById("positionsContainer");
const openPositionsCount = document.getElementById("openPositionsCount");
const ordersTableBody = document.getElementById("ordersTableBody");
const terminalConsole = document.getElementById("terminalConsole");

const riskLossBar = document.getElementById("riskLossBar");
const riskLossUsageText = document.getElementById("riskLossUsageText");
const riskPositionsBar = document.getElementById("riskPositionsBar");
const riskPositionsUsageText = document.getElementById("riskPositionsUsageText");
const riskTradesBar = document.getElementById("riskTradesBar");
const riskTradesUsageText = document.getElementById("riskTradesUsageText");

// Initialize application
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  connectWebSocket();
  startClock();
  fetchInitialData();
});

// Real-time IST Clock
function startClock() {
  setInterval(() => {
    const now = new Date();
    // Compute IST (UTC+5:30)
    const istOffset = 5.5 * 60 * 60 * 1000;
    const istTime = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + istOffset);
    istClock.textContent = istTime.toTimeString().split(" ")[0] + " IST";
  }, 1000);
}

// WebSocket Connection
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("Connected to Groww AI Agent WebSocket.");
    systemPulse.style.background = "#10b981";
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "TELEMETRY_UPDATE" || msg.type === "INITIAL_STATE") {
        updateUI(msg.data);
      }
    } catch (e) {
      console.error("Error parsing WebSocket payload:", e);
    }
  };

  ws.onclose = () => {
    console.warn("WebSocket disconnected. Retrying in 2 seconds...");
    systemPulse.style.background = "#f59e0b";
    setTimeout(connectWebSocket, 2000);
  };

  ws.onerror = (err) => {
    console.error("WebSocket error:", err);
  };
}

// REST fallback fetch
async function fetchInitialData() {
  try {
    const res = await fetch("/api/system/overview");
    if (res.ok) {
      const data = await res.json();
      updateUI(data);
    }
    fetchQuotes();
    fetchOrders();
    fetchLogs();
  } catch (err) {
    console.error("Failed to fetch initial overview:", err);
  }
}

// Update UI Components
function updateUI(data) {
  if (!data) return;
  systemState = data;

  // 1. Market Session & Header
  if (data.market_session) {
    sessionStatusText.textContent = `${data.market_session.status} (${data.market_session.phase})`;
    sessionStatusText.style.color = data.market_session.is_trading_allowed ? "#10b981" : "#94a3b8";
  }

  // Mode
  if (data.mode === "LIVE") {
    executionModeBadge.textContent = "LIVE TRADING (ACTIVE)";
    executionModeBadge.className = "mode-badge live";
  } else {
    executionModeBadge.textContent = "PAPER TRADING (SAFE DEFAULT)";
    executionModeBadge.className = "mode-badge";
  }

  // 2. Portfolio Metrics
  if (data.portfolio) {
    const p = data.portfolio;
    valInitialCapital.textContent = `₹${(p.total_capital - p.realized_daily_pnl).toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
    valAvailCapital.textContent = `₹${p.available_capital.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
    valInvestedCapital.textContent = `Invested: ₹${p.invested_capital.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;

    // Realized PnL
    valRealizedPnl.textContent = `₹${p.realized_daily_pnl.toFixed(2)}`;
    valRealizedPnl.className = `metric-value ${p.realized_daily_pnl >= 0 ? 'profit' : 'loss'}`;

    // Unrealized PnL
    valUnrealizedPnl.textContent = `₹${p.unrealized_pnl.toFixed(2)}`;
    valUnrealizedPnl.className = `metric-value ${p.unrealized_pnl >= 0 ? 'profit' : 'loss'}`;

    valTradesCount.textContent = `${p.total_trades_today} / 2`;

    const headroom = Math.max(0, 50.0 + p.realized_daily_pnl);
    valLossHeadroom.textContent = `₹${headroom.toFixed(2)}`;

    // Risk Meters
    const lossPct = Math.min(100, Math.max(0, (Math.abs(Math.min(0, p.realized_daily_pnl)) / 50.0) * 100));
    riskLossBar.style.width = `${lossPct}%`;
    riskLossBar.style.background = lossPct > 75 ? "#ef4444" : (lossPct > 40 ? "#f59e0b" : "#10b981");
    riskLossUsageText.textContent = `₹${Math.abs(Math.min(0, p.realized_daily_pnl)).toFixed(2)} / ₹50.00`;

    const posPct = (data.active_positions_count / 1) * 100;
    riskPositionsBar.style.width = `${posPct}%`;
    riskPositionsUsageText.textContent = `${data.active_positions_count} / 1`;

    const tradesPct = (p.total_trades_today / 2) * 100;
    riskTradesBar.style.width = `${tradesPct}%`;
    riskTradesUsageText.textContent = `${p.total_trades_today} / 2`;
  }

  // 3. Render 9-Agent Neural Fleet
  if (data.agents) {
    renderAgentsGrid(data.agents);
  }

  // Refresh dynamic tables
  fetchPositions();
  fetchQuotes();
  fetchOrders();
  fetchLogs();
}

function renderAgentsGrid(agents) {
  agentsGrid.innerHTML = "";
  const agentKeys = Object.keys(agents);

  agentKeys.forEach((key) => {
    const a = agents[key];
    const card = document.createElement("div");
    card.className = "agent-card";

    let dotClass = "agent-dot";
    if (a.state === "SCANNING") dotClass += " scanning";
    else if (a.state === "ANALYZING" || a.state === "DECIDING") dotClass += " analyzing";
    else if (a.state === "ERROR") dotClass += " error";
    else if (a.state === "PAUSED") dotClass += " paused";
    else if (a.state === "STOPPED") dotClass += " stopped";

    card.innerHTML = `
      <div class="agent-header">
        <div class="agent-name">
          <div class="${dotClass}"></div>
          <span>${formatAgentName(a.name)}</span>
        </div>
        <span class="agent-badge">${a.state}</span>
      </div>
      <div class="agent-message" title="${a.message}">${a.message}</div>
    `;
    agentsGrid.appendChild(card);
  });
}

function formatAgentName(name) {
  return name.replace("Agent", "").replace("Supervisor", " Supervisor");
}

// Fetch Market Quotes
async function fetchQuotes() {
  try {
    const res = await fetch("/api/market/quotes");
    if (!res.ok) return;
    const quotes = await res.json();
    scannerCount.textContent = quotes.length;
    growwFeedStatus.textContent = quotes.length > 0 ? "FEED: ACTIVE" : "FEED: CONNECTING";

    if (quotes.length === 0) return;

    scannerTableBody.innerHTML = "";
    quotes.forEach((q) => {
      const tr = document.createElement("tr");
      const chgColor = q.change_pct >= 0 ? "var(--color-profit)" : "var(--color-loss)";
      const isUnusual = q.volume > 500000;

      tr.innerHTML = `
        <td style="font-weight:600; color:#fff;">${q.symbol}</td>
        <td>₹${q.ltp.toFixed(2)}</td>
        <td style="color:${chgColor}; font-weight:600;">${q.change_pct >= 0 ? '+' : ''}${q.change_pct.toFixed(2)}%</td>
        <td>${(q.volume / 100000).toFixed(1)}L</td>
        <td><span class="${q.change_pct > 0.5 ? 'tag-buy' : 'agent-badge'}">${q.change_pct > 0.5 ? 'BULLISH' : 'NEUTRAL'}</span></td>
      `;
      scannerTableBody.appendChild(tr);
    });

    // Pick top candidate to render in Stock Analyst card
    if (quotes.length > 0 && !currentCandidate) {
      renderCandidateAnalysis(quotes[0].symbol);
    }
  } catch (e) {
    console.error("Error fetching quotes:", e);
  }
}

// Render Candidate Stock Analysis
async function renderCandidateAnalysis(symbol) {
  try {
    const res = await fetch("/api/trading/signals");
    if (res.ok) {
      const signals = await res.json();
      if (signals.length > 0) {
        const sig = signals[0];
        decisionCardContainer.innerHTML = `
          <div class="score-card">
            <div class="score-header">
              <div>
                <span style="font-weight:700; font-size:16px; color:#fff;">${sig.symbol}</span>
                <span class="${sig.signal_type === 'BUY' ? 'tag-buy' : 'tag-sell'}" style="margin-left:8px;">${sig.signal_type}</span>
              </div>
              <div class="score-value">${sig.score}/100</div>
            </div>

            <div class="progress-bar-bg">
              <div class="progress-bar-fill" style="width:${sig.score}%;"></div>
            </div>

            <div class="factor-grid">
              <div>• Trend Strength: <strong>23/25</strong></div>
              <div>• Momentum (RSI): <strong>18/20</strong></div>
              <div>• Volume Expansion: <strong>19/20</strong></div>
              <div>• Price Action: <strong>17/20</strong></div>
              <div>• Market Regime: <strong>8.5/10</strong></div>
              <div>• Data Freshness: <strong>5/5</strong></div>
            </div>

            <div style="margin-top:12px; font-size:11px; color:#cbd5e1; background:rgba(0,0,0,0.2); padding:8px; border-radius:4px;">
              <strong>Strategy Alignment:</strong><br>${sig.explanation}
            </div>

            <div style="margin-top:10px; display:flex; justify-content:space-between; font-size:11px; font-family:var(--font-mono);">
              <span>Entry: ₹${sig.entry_price}</span>
              <span style="color:var(--color-loss);">SL: ₹${sig.stop_loss}</span>
              <span style="color:var(--color-profit);">TGT: ₹${sig.target}</span>
            </div>
          </div>
        `;
        return;
      }
    }

    // Default placeholder
    decisionCardContainer.innerHTML = `
      <div class="score-card">
        <div class="score-header">
          <span style="font-weight:700; font-size:15px; color:#fff;">${symbol}</span>
          <span class="tag-buy">SHORTLISTED</span>
        </div>
        <div style="font-size:12px; color:var(--text-secondary); margin:10px 0;">
          Calculating EMA 9/21/50, RSI 14, VWAP, MACD, and Bollinger Bands...
        </div>
      </div>
    `;
  } catch (e) {
    console.error("Error rendering candidate:", e);
  }
}

// Fetch Open Paper Positions
async function fetchPositions() {
  try {
    const res = await fetch("/api/trading/positions");
    if (!res.ok) return;
    const positions = await res.json();
    openPositionsCount.textContent = positions.length;

    if (positions.length === 0) {
      positionsContainer.innerHTML = `
        <div style="color:var(--text-muted); text-align:center; padding: 30px;">
          No open paper positions. Monitoring for high-probability signals.
        </div>
      `;
      return;
    }

    positionsContainer.innerHTML = "";
    positions.forEach((pos) => {
      const pnlColor = pos.unrealized_pnl >= 0 ? "var(--color-profit)" : "var(--color-loss)";
      const div = document.createElement("div");
      div.className = "position-item";
      div.innerHTML = `
        <div class="pos-header">
          <div>
            <span class="pos-symbol">${pos.symbol}</span>
            <span class="tag-buy" style="margin-left:6px;">${pos.side}</span>
            <span style="font-size:11px; color:var(--text-muted); margin-left:6px;">${pos.quantity} Qty</span>
          </div>
          <div class="pos-pnl" style="color:${pnlColor};">
            ${pos.unrealized_pnl >= 0 ? '+' : ''}₹${pos.unrealized_pnl.toFixed(2)} (${pos.pnl_pct.toFixed(2)}%)
          </div>
        </div>

        <div class="pos-details">
          <div>Entry: <strong>₹${pos.entry_price}</strong></div>
          <div>LTP: <strong>₹${pos.current_price}</strong></div>
          <div style="color:var(--color-loss);">SL: <strong>₹${pos.trailing_sl || pos.stop_loss}</strong></div>
          <div style="color:var(--color-profit);">TGT: <strong>₹${pos.target}</strong></div>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
          <span style="font-size:10px; color:var(--text-muted);">Trailing SL: ${pos.trailing_activated ? 'ACTIVE' : 'READY'}</span>
          <span style="font-size:10px; color:var(--color-warning);">Auto Square-Off @ 15:15 IST</span>
        </div>
      `;
      positionsContainer.appendChild(div);
    });
  } catch (e) {
    console.error("Error fetching positions:", e);
  }
}

// Fetch Paper Orders
async function fetchOrders() {
  try {
    const res = await fetch("/api/trading/orders");
    if (!res.ok) return;
    const orders = await res.json();
    if (orders.length === 0) return;

    ordersTableBody.innerHTML = "";
    orders.forEach((o) => {
      const tr = document.createElement("tr");
      const timeStr = o.placed_at ? o.placed_at.split(" ")[1] : "--:--:--";
      tr.innerHTML = `
        <td>${timeStr}</td>
        <td style="font-weight:600; color:#fff;">${o.symbol}</td>
        <td><span class="${o.side === 'BUY' ? 'tag-buy' : 'tag-sell'}">${o.side}</span></td>
        <td>${o.quantity}</td>
        <td>₹${o.executed_price ? o.executed_price.toFixed(2) : o.reference_price.toFixed(2)}</td>
        <td>₹${o.total_charges ? o.total_charges.toFixed(2) : '0.00'}</td>
        <td><span class="agent-badge" style="color:var(--color-profit);">${o.status}</span></td>
      `;
      ordersTableBody.appendChild(tr);
    });
  } catch (e) {
    console.error("Error fetching orders:", e);
  }
}

// Fetch Agent Activity Logs
async function fetchLogs() {
  try {
    const res = await fetch("/api/logs/events");
    if (!res.ok) return;
    const logs = await res.json();
    if (logs.length === 0) return;

    terminalConsole.innerHTML = "";
    logs.forEach((l) => {
      const div = document.createElement("div");
      div.className = "log-entry";
      const timeStr = l.timestamp ? l.timestamp.split(" ")[1] : "";
      div.innerHTML = `
        <span class="log-time">[${timeStr}]</span>
        <span class="log-agent">[${l.agent_name}]:</span>
        <span class="log-msg-${l.level}">${l.message}</span>
      `;
      terminalConsole.appendChild(div);
    });
    terminalConsole.scrollTop = terminalConsole.scrollHeight;
  } catch (e) {
    console.error("Error fetching logs:", e);
  }
}

// Event Listeners & Button Handlers
function setupEventListeners() {
  // Master Control buttons
  document.getElementById("btnStartAll").addEventListener("click", async () => {
    const res = await fetch("/api/system/start", { method: "POST" });
    const data = await res.json();
    alert(`Master Supervisor Started: ${data.status}`);
    fetchInitialData();
  });

  document.getElementById("btnPauseAll").addEventListener("click", async () => {
    await fetch("/api/system/pause", { method: "POST" });
    fetchInitialData();
  });

  document.getElementById("btnStopAll").addEventListener("click", async () => {
    await fetch("/api/system/stop", { method: "POST" });
    fetchInitialData();
  });

  document.getElementById("btnEmergencyShutdown").addEventListener("click", async () => {
    if (confirm("🚨 INITIATE EMERGENCY SHUTDOWN? This will immediately trip the kill switch and cancel all pending actions.")) {
      await fetch("/api/system/emergency-shutdown", { method: "POST" });
      alert("Emergency shutdown executed. Kill switch engaged.");
      fetchInitialData();
    }
  });

  document.getElementById("btnResetKillSwitch").addEventListener("click", async () => {
    await fetch("/api/system/reset-kill-switch", { method: "POST" });
    alert("Kill switch reset by operator.");
    fetchInitialData();
  });

  // Settings Modal
  const settingsModal = document.getElementById("settingsModal");
  document.getElementById("btnOpenSettings").addEventListener("click", async () => {
    const res = await fetch("/api/settings");
    if (res.ok) {
      const cfg = await res.json();
      document.getElementById("cfgGrowwApiKey").value = cfg.GROWW_API_KEY || "Configured in .env";
      document.getElementById("cfgRiskPerTrade").value = cfg.RISK_PER_TRADE;
      document.getElementById("cfgDailyMaxLoss").value = cfg.DAILY_MAX_LOSS;
      document.getElementById("cfgMaxPositions").value = cfg.MAX_OPEN_POSITIONS;
      document.getElementById("cfgMaxTrades").value = cfg.MAX_TRADES_PER_DAY;
      document.getElementById("cfgSimulateHours").value = cfg.SIMULATE_MARKET_HOURS ? "true" : "false";
    }
    settingsModal.style.display = "flex";
  });

  document.getElementById("btnCloseSettings").addEventListener("click", () => {
    settingsModal.style.display = "none";
  });

  document.getElementById("btnSaveSettings").addEventListener("click", async () => {
    const payload = {
      RISK_PER_TRADE: parseFloat(document.getElementById("cfgRiskPerTrade").value),
      DAILY_MAX_LOSS: parseFloat(document.getElementById("cfgDailyMaxLoss").value),
      MAX_OPEN_POSITIONS: parseInt(document.getElementById("cfgMaxPositions").value),
      MAX_TRADES_PER_DAY: parseInt(document.getElementById("cfgMaxTrades").value),
      SIMULATE_MARKET_HOURS: document.getElementById("cfgSimulateHours").value === "true"
    };
    await fetch("/api/settings/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    alert("Settings updated successfully.");
    settingsModal.style.display = "none";
    fetchInitialData();
  });

  // Live Trading Safety Gate Modal
  const safetyGateModal = document.getElementById("safetyGateModal");
  document.getElementById("btnOpenSafetyGate").addEventListener("click", () => {
    safetyGateModal.style.display = "flex";
  });
  document.getElementById("btnCloseSafetyGate").addEventListener("click", () => {
    safetyGateModal.style.display = "none";
  });
  document.getElementById("btnCancelSafetyGate").addEventListener("click", () => {
    safetyGateModal.style.display = "none";
  });

  document.getElementById("btnConfirmLiveGate").addEventListener("click", async () => {
    const passphrase = document.getElementById("txtLivePassphrase").value;
    const sebi = document.getElementById("chkSebiCompliance").checked;
    const groww = document.getElementById("chkGrowwAuth").checked;
    const ip = document.getElementById("chkStaticIp").checked;

    const res = await fetch("/api/safety-gate/verify-live", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        passphrase: passphrase,
        sebi_acknowledged: sebi,
        groww_verified: groww,
        static_ip_verified: ip
      })
    });
    const result = await res.json();
    if (result.is_eligible) {
      alert("✅ Verification passed! Live trading gate authorized in compliance sandbox.");
    } else {
      alert(`❌ Live Trading Blocked: ${result.message}`);
    }
  });

  // Backtest Modal
  const backtestModal = document.getElementById("backtestModal");
  document.getElementById("btnOpenBacktest").addEventListener("click", () => {
    backtestModal.style.display = "flex";
  });
  document.getElementById("btnCloseBacktest").addEventListener("click", () => {
    backtestModal.style.display = "none";
  });

  document.getElementById("btnRunBacktest").addEventListener("click", async () => {
    const symbol = document.getElementById("txtBacktestSymbol").value.toUpperCase();
    const container = document.getElementById("backtestResultsContainer");
    container.innerHTML = `<div style="text-align:center; padding:30px; color:var(--color-cyan);">Running walk-forward backtest for ${symbol}...</div>`;

    const res = await fetch("/api/backtest/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol })
    });

    if (res.ok) {
      const b = await res.json();
      const perf = b.overall_performance;
      const oos = b.out_of_sample_validation;

      container.innerHTML = `
        <div style="background:var(--bg-card); padding:16px; border-radius:6px; font-family:var(--font-mono); font-size:12px;">
          <h4 style="color:#fff; margin-bottom:8px;">${symbol} Backtest Results (Walk-Forward Validated)</h4>
          <div style="display:grid; grid-template-columns: repeat(2, 1fr); gap:8px;">
            <div>Total Candles: <strong>${b.total_candles}</strong></div>
            <div>Total Trades: <strong>${perf.total_trades}</strong></div>
            <div>Win Rate: <strong style="color:var(--color-profit);">${perf.win_rate_pct}%</strong></div>
            <div>Net Profit: <strong style="color:${perf.net_profit_inr >= 0 ? 'var(--color-profit)' : 'var(--color-loss)'};">₹${perf.net_profit_inr}</strong></div>
            <div>Statutory Charges: <strong>₹${perf.total_statutory_charges}</strong></div>
            <div>Profit Factor: <strong>${perf.profit_factor}</strong></div>
            <div>Max Drawdown: <strong style="color:var(--color-loss);">₹${perf.max_drawdown_inr} (${perf.max_drawdown_pct}%)</strong></div>
            <div>Estimated Sharpe: <strong>${perf.sharpe_ratio}</strong></div>
          </div>

          <div style="margin-top:14px; border-top:1px solid var(--border-subtle); padding-top:10px;">
            <strong>Out-of-Sample Validation Window:</strong>
            <div>Trades: ${oos.total_trades} | Win Rate: ${oos.win_rate_pct}% | Net P&L: ₹${oos.net_profit_inr}</div>
          </div>
        </div>
      `;
    } else {
      container.innerHTML = `<div style="color:var(--color-loss); text-align:center; padding:20px;">Backtest execution failed.</div>`;
    }
  });

  // Daily Report Modal
  const reportModal = document.getElementById("reportModal");
  document.getElementById("btnOpenReport").addEventListener("click", async () => {
    reportModal.style.display = "flex";
    const repDiv = document.getElementById("dailyReportContent");
    repDiv.innerHTML = "Generating daily report...";

    const res = await fetch("/api/reports/daily");
    if (res.ok) {
      const r = await res.json();
      repDiv.innerHTML = `
        <div style="background:var(--bg-card); padding:16px; border-radius:6px; font-family:var(--font-mono);">
          <div style="display:flex; justify-content:space-between; margin-bottom:12px;">
            <span>Date: <strong>${r.report_date}</strong></span>
            <span>Generated: <strong>${r.generated_at}</strong></span>
          </div>
          <div style="display:grid; grid-template-columns:repeat(2, 1fr); gap:8px; font-size:12px;">
            <div>Starting Capital: ₹${r.starting_capital}</div>
            <div>Current Capital: ₹${r.current_capital}</div>
            <div>Trades Completed: ${r.total_trades}</div>
            <div>Win Rate: ${r.win_rate_pct}%</div>
            <div>Gross P&L: ₹${r.gross_pnl}</div>
            <div>Charges & Taxes: ₹${r.total_charges}</div>
            <div style="color:${r.net_pnl >= 0 ? 'var(--color-profit)' : 'var(--color-loss)'};">Net P&L: ₹${r.net_pnl}</div>
            <div>Profit Factor: ${r.profit_factor}</div>
            <div>Max Drawdown: ₹${r.max_drawdown_inr}</div>
            <div>Risk Violations Filtered: ${r.risk_violations_count}</div>
          </div>
        </div>
      `;
    }
  });

  document.getElementById("btnCloseReport").addEventListener("click", () => {
    reportModal.style.display = "none";
  });
}
