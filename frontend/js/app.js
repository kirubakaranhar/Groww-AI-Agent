/**
 * Groww Autonomous AI Trading Agent - Command Center Controller (v1.0 - 100% UI)
 * Pure Vanilla JavaScript Client managing:
 * - Real-time WebSocket telemetry & 9-agent neural status
 * - High-DPI Interactive Candlestick Chart with EMA 9, EMA 21, VWAP & Volume overlays
 * - 1-Click Manual Paper Position Square-Off
 * - Web Audio API Sound Alerts (Trade Chime & Kill Switch Alarm)
 * - 1-Click CSV Export for Completed Trades
 * - Toast Notification Engine & Compliance Safety Gate
 * - Voice Agent: Web Speech API Assembly Briefing & Auto-Announce (Zero CDN)
 */

// State
let ws = null;
let systemState = null;
let currentCandidate = null;
let selectedChartSymbol = "RELIANCE";
let chartCandles = [];
let chartHoverIdx = -1;
let soundEnabled = localStorage.getItem("groww_sound_enabled") !== "false";
let lastKnownTradesCount = null;
let lastKnownKillSwitch = false;
let audioCtx = null;

// ---- Voice Agent State ----
let voiceEnabled = localStorage.getItem("groww_voice_enabled") === "true";
let isSpeaking = false;
let voiceHeartbeatTimer = null;
let lastSpokenTradeCount = null;
let lastSpokenKillSwitch = false;
const VOICE_HEARTBEAT_INTERVAL_MS = 90000; // Auto-read every 90 seconds when enabled

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

const chartSymbolSelect = document.getElementById("chartSymbolSelect");
const chartLiveLtp = document.getElementById("chartLiveLtp");
const chartTooltip = document.getElementById("chartTooltip");
const candlestickCanvas = document.getElementById("candlestickCanvas");
const btnToggleSound = document.getElementById("btnToggleSound");
const toastContainer = document.getElementById("toastContainer");

// Initialize application
document.addEventListener("DOMContentLoaded", () => {
  updateSoundButtonUI();
  setupEventListeners();
  setupChartInteractions();
  setupVoiceAgent();           // ← Voice Agent init
  connectWebSocket();
  startClock();
  fetchInitialData();
  loadCandlestickChart(selectedChartSymbol);

  // Periodically refresh active chart every 10 seconds
  setInterval(() => loadCandlestickChart(selectedChartSymbol, true), 10000);
});

// ============================================================================
// AUDIO ALERTS ENGINE (Web Audio API - Zero External Dependencies)
// ============================================================================
function getAudioContext() {
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) audioCtx = new AudioContextClass();
  }
  if (audioCtx && audioCtx.state === "suspended") {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

function playTradeChime() {
  if (!soundEnabled) return;
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    const now = ctx.currentTime;
    const notes = [587.33, 880.0]; // D5 -> A5 crisp upward chime
    notes.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, now + i * 0.11);
      gain.gain.setValueAtTime(0.001, now + i * 0.11);
      gain.gain.exponentialRampToValueAtTime(0.14, now + i * 0.11 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.11 + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + i * 0.11);
      osc.stop(now + i * 0.11 + 0.26);
    });
  } catch (e) {
    console.debug("Audio playback skipped:", e);
  }
}

function playAlertTone() {
  if (!soundEnabled) return;
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    const now = ctx.currentTime;
    [260, 220].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(freq, now + i * 0.18);
      gain.gain.setValueAtTime(0.16, now + i * 0.18);
      gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.18 + 0.16);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + i * 0.18);
      osc.stop(now + i * 0.18 + 0.17);
    });
  } catch (e) {
    console.debug("Alert tone skipped:", e);
  }
}

function updateSoundButtonUI() {
  if (!btnToggleSound) return;
  if (soundEnabled) {
    btnToggleSound.textContent = "🔊 Sound ON";
    btnToggleSound.classList.add("btn-sound-on");
  } else {
    btnToggleSound.textContent = "🔇 Muted";
    btnToggleSound.classList.remove("btn-sound-on");
  }
}

// ============================================================================
// TOAST NOTIFICATIONS
// ============================================================================
function showToast(message, type = "info") {
  if (!toastContainer) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4200);
}

// ============================================================================
// INTERACTIVE CANDLESTICK CHART (High-DPI HTML5 Canvas)
// ============================================================================
async function loadCandlestickChart(symbol, silent = false) {
  selectedChartSymbol = symbol;
  if (chartSymbolSelect && chartSymbolSelect.value !== symbol) {
    // Add option if missing
    let exists = Array.from(chartSymbolSelect.options).some(o => o.value === symbol);
    if (!exists) {
      const opt = document.createElement("option");
      opt.value = symbol;
      opt.textContent = symbol;
      chartSymbolSelect.appendChild(opt);
    }
    chartSymbolSelect.value = symbol;
  }

  try {
    const res = await fetch(`/api/market/candles/${encodeURIComponent(symbol)}?interval=5m&limit=70`);
    if (!res.ok) return;
    const data = await res.json();
    chartCandles = data.candles || [];
    if (chartLiveLtp && data.ltp) {
      chartLiveLtp.textContent = `${data.symbol} LTP: ₹${Number(data.ltp).toFixed(2)}`;
    }
    drawCandlestickChart();
    if (!silent) {
      updateChartTooltip(chartCandles.length - 1);
    }
  } catch (err) {
    console.error("Failed to load candlestick chart:", err);
  }
}

function setupChartInteractions() {
  if (!candlestickCanvas) return;

  candlestickCanvas.addEventListener("mousemove", (e) => {
    if (!chartCandles.length) return;
    const rect = candlestickCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const padLeft = 14;
    const padRight = 66;
    const plotWidth = rect.width - padLeft - padRight;
    if (x < padLeft || x > rect.width - padRight) {
      chartHoverIdx = -1;
      drawCandlestickChart();
      return;
    }
    const idx = Math.min(
      chartCandles.length - 1,
      Math.max(0, Math.floor(((x - padLeft) / plotWidth) * chartCandles.length))
    );
    chartHoverIdx = idx;
    updateChartTooltip(idx);
    drawCandlestickChart();
  });

  candlestickCanvas.addEventListener("mouseleave", () => {
    chartHoverIdx = -1;
    if (chartCandles.length) updateChartTooltip(chartCandles.length - 1);
    drawCandlestickChart();
  });

  window.addEventListener("resize", () => drawCandlestickChart());
}

function updateChartTooltip(idx) {
  if (!chartTooltip || idx < 0 || idx >= chartCandles.length) return;
  const c = chartCandles[idx];
  const color = c.close >= c.open ? "#10b981" : "#ef4444";
  const timePart = c.timestamp ? c.timestamp.split(" ")[1] || c.timestamp : "";
  chartTooltip.innerHTML = `
    <span style="color:#94a3b8;">${selectedChartSymbol} ${timePart}</span>
    <span>O: <strong style="color:${color}">₹${c.open.toFixed(2)}</strong></span>
    <span>H: <strong style="color:${color}">₹${c.high.toFixed(2)}</strong></span>
    <span>L: <strong style="color:${color}">₹${c.low.toFixed(2)}</strong></span>
    <span>C: <strong style="color:${color}">₹${c.close.toFixed(2)}</strong></span>
    <span style="color:#06b6d4;">EMA9: ₹${c.ema_9.toFixed(2)}</span>
    <span style="color:#f59e0b;">EMA21: ₹${c.ema_21.toFixed(2)}</span>
    <span style="color:#a855f7;">VWAP: ₹${c.vwap.toFixed(2)}</span>
    <span style="color:#94a3b8;">Vol: ${(c.volume / 1000).toFixed(1)}k</span>
  `;
}

function drawCandlestickChart() {
  if (!candlestickCanvas || !chartCandles.length) return;
  const ctx = candlestickCanvas.getContext("2d");
  const rect = candlestickCanvas.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return;

  const dpr = window.devicePixelRatio || 1;
  candlestickCanvas.width = Math.floor(rect.width * dpr);
  candlestickCanvas.height = Math.floor(rect.height * dpr);
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;
  const padTop = 36;
  const padBottom = 26;
  const padLeft = 14;
  const padRight = 66;
  const plotW = w - padLeft - padRight;
  const plotH = h - padTop - padBottom;
  const priceAreaH = plotH * 0.80;
  const volAreaTop = padTop + priceAreaH + 6;
  const volAreaH = plotH * 0.17;

  // Clear background
  ctx.fillStyle = "#060a12";
  ctx.fillRect(0, 0, w, h);

  // Price bounds
  let minP = Infinity;
  let maxP = -Infinity;
  let maxVol = 1;
  chartCandles.forEach(c => {
    minP = Math.min(minP, c.low, c.ema_9, c.ema_21, c.vwap);
    maxP = Math.max(maxP, c.high, c.ema_9, c.ema_21, c.vwap);
    maxVol = Math.max(maxVol, c.volume);
  });
  const range = Math.max(0.01, maxP - minP);
  minP -= range * 0.06;
  maxP += range * 0.06;

  const yForPrice = (p) => padTop + ((maxP - p) / (maxP - minP)) * priceAreaH;
  const stepX = plotW / chartCandles.length;
  const candleW = Math.max(2, stepX * 0.62);

  // Horizontal Grid & Right Price Axis
  ctx.strokeStyle = "rgba(148, 163, 184, 0.12)";
  ctx.fillStyle = "#64748b";
  ctx.font = "10px 'JetBrains Mono', monospace";
  ctx.lineWidth = 1;

  const gridLines = 5;
  for (let i = 0; i <= gridLines; i++) {
    const ratio = i / gridLines;
    const y = padTop + ratio * priceAreaH;
    const priceVal = maxP - ratio * (maxP - minP);
    ctx.beginPath();
    ctx.setLineDash([3, 3]);
    ctx.moveTo(padLeft, y);
    ctx.lineTo(w - padRight, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillText(`₹${priceVal.toFixed(1)}`, w - padRight + 6, y + 3);
  }

  // Volume Bars + Candlesticks
  chartCandles.forEach((c, i) => {
    const cx = padLeft + i * stepX + stepX / 2;
    const isBull = c.close >= c.open;
    const color = isBull ? "#10b981" : "#ef4444";

    // Volume bar
    const vH = (c.volume / maxVol) * volAreaH;
    ctx.fillStyle = isBull ? "rgba(16, 185, 129, 0.25)" : "rgba(239, 68, 68, 0.25)";
    ctx.fillRect(cx - candleW / 2, volAreaTop + volAreaH - vH, candleW, vH);

    // Wick
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(cx, yForPrice(c.high));
    ctx.lineTo(cx, yForPrice(c.low));
    ctx.stroke();

    // Candle Body
    const openY = yForPrice(c.open);
    const closeY = yForPrice(c.close);
    const bodyTop = Math.min(openY, closeY);
    const bodyH = Math.max(1.5, Math.abs(closeY - openY));
    ctx.fillStyle = color;
    ctx.fillRect(cx - candleW / 2, bodyTop, candleW, bodyH);
  });

  // Helper to draw overlay line
  const drawOverlay = (key, color, dashed = false) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6;
    if (dashed) ctx.setLineDash([5, 4]);
    ctx.beginPath();
    chartCandles.forEach((c, i) => {
      const cx = padLeft + i * stepX + stepX / 2;
      const cy = yForPrice(c[key]);
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    });
    ctx.stroke();
    ctx.setLineDash([]);
  };

  drawOverlay("ema_9", "#06b6d4", false);   // EMA 9 Cyan
  drawOverlay("ema_21", "#f59e0b", false);  // EMA 21 Amber
  drawOverlay("vwap", "#a855f7", true);     // VWAP Dashed Purple

  // Hover Crosshair
  if (chartHoverIdx >= 0 && chartHoverIdx < chartCandles.length) {
    const c = chartCandles[chartHoverIdx];
    const cx = padLeft + chartHoverIdx * stepX + stepX / 2;
    const cy = yForPrice(c.close);

    ctx.strokeStyle = "rgba(248, 250, 252, 0.35)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(cx, padTop);
    ctx.lineTo(cx, h - padBottom);
    ctx.moveTo(padLeft, cy);
    ctx.lineTo(w - padRight, cy);
    ctx.stroke();
    ctx.setLineDash([]);

    // Highlight Price Tag on Axis
    ctx.fillStyle = "#06b6d4";
    ctx.fillRect(w - padRight + 2, cy - 8, 60, 16);
    ctx.fillStyle = "#060a12";
    ctx.font = "bold 10px 'JetBrains Mono', monospace";
    ctx.fillText(`₹${c.close.toFixed(1)}`, w - padRight + 5, cy + 3);
  }

  // Time Labels along Bottom
  ctx.fillStyle = "#64748b";
  ctx.font = "10px 'JetBrains Mono', monospace";
  const labelStep = Math.max(1, Math.floor(chartCandles.length / 6));
  for (let i = 0; i < chartCandles.length; i += labelStep) {
    const cx = padLeft + i * stepX;
    const ts = chartCandles[i].timestamp || "";
    const hhmm = ts.includes(" ") ? ts.split(" ")[1].slice(0, 5) : ts;
    ctx.fillText(hhmm, cx, h - 8);
  }
}

// ============================================================================
// CLOCK & WEBSOCKET TELEMETRY
// ============================================================================
function startClock() {
  setInterval(() => {
    const now = new Date();
    const istOffset = 5.5 * 60 * 60 * 1000;
    const istTime = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + istOffset);
    istClock.textContent = istTime.toTimeString().split(" ")[0] + " IST";
  }, 1000);
}

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

// ============================================================================
// UI STATE UPDATES
// ============================================================================
function updateUI(data) {
  if (!data) return;
  systemState = data;

  // ---- Voice Agent: auto-announce trade events ----
  checkVoiceAutoAnnounce(data);

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

  // 2. Portfolio Metrics & Real-Time Audio Triggers
  if (data.portfolio) {
    const p = data.portfolio;

    // Detect new executed trade -> play chime & toast
    if (lastKnownTradesCount !== null && p.total_trades_today > lastKnownTradesCount) {
      playTradeChime();
      showToast(`⚡ New Paper Trade Executed! Daily trades: ${p.total_trades_today}`, "profit");
    }
    lastKnownTradesCount = p.total_trades_today;

    // Detect Kill Switch trip -> play warning tone & toast
    const ksActive = Boolean(p.is_kill_switch_active);
    if (ksActive && !lastKnownKillSwitch) {
      playAlertTone();
      showToast("🚨 DAILY KILL SWITCH ACTIVATED! Trading halted for safety.", "loss");
    }
    lastKnownKillSwitch = ksActive;

    valInitialCapital.textContent = `₹${(p.total_capital - p.realized_daily_pnl).toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
    valAvailCapital.textContent = `₹${p.available_capital.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
    valInvestedCapital.textContent = `Invested: ₹${p.invested_capital.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;

    valRealizedPnl.textContent = `₹${p.realized_daily_pnl.toFixed(2)}`;
    valRealizedPnl.className = `metric-value ${p.realized_daily_pnl >= 0 ? 'profit' : 'loss'}`;

    valUnrealizedPnl.textContent = `₹${p.unrealized_pnl.toFixed(2)}`;
    valUnrealizedPnl.className = `metric-value ${p.unrealized_pnl >= 0 ? 'profit' : 'loss'}`;

    valTradesCount.textContent = `${p.total_trades_today} / 2`;

    const headroom = Math.max(0, 50.0 + p.realized_daily_pnl);
    valLossHeadroom.textContent = `₹${headroom.toFixed(2)}`;

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
  Object.keys(agents).forEach((key) => {
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

// ============================================================================
// NSE SCANNER & CLICK-TO-CHART
// ============================================================================
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
      tr.className = `scanner-row ${q.symbol === selectedChartSymbol ? "active" : ""}`;
      tr.title = `Click to view ${q.symbol} interactive candlestick chart`;
      tr.addEventListener("click", () => {
        loadCandlestickChart(q.symbol);
        showToast(`📈 Chart switched to ${q.symbol}`, "info");
      });

      const chgColor = q.change_pct >= 0 ? "var(--color-profit)" : "var(--color-loss)";
      tr.innerHTML = `
        <td style="font-weight:600; color:#fff;">${q.symbol}</td>
        <td>₹${q.ltp.toFixed(2)}</td>
        <td style="color:${chgColor}; font-weight:600;">${q.change_pct >= 0 ? '+' : ''}${q.change_pct.toFixed(2)}%</td>
        <td>${(q.volume / 100000).toFixed(1)}L</td>
        <td><span class="${q.change_pct > 0.5 ? 'tag-buy' : 'agent-badge'}">${q.change_pct > 0.5 ? 'BULLISH' : 'NEUTRAL'}</span></td>
      `;
      scannerTableBody.appendChild(tr);
    });

    if (quotes.length > 0 && !currentCandidate) {
      renderCandidateAnalysis(quotes[0].symbol);
    }
  } catch (e) {
    console.error("Error fetching quotes:", e);
  }
}

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

// ============================================================================
// OPEN POSITIONS + 1-CLICK MANUAL SQUARE-OFF
// ============================================================================
async function manualSquareOff(positionId, symbol) {
  if (!confirm(`⚡ Square off open paper position for ${symbol} at current LTP?`)) return;
  try {
    const res = await fetch(`/api/trading/positions/${encodeURIComponent(positionId)}/close`, {
      method: "POST"
    });
    if (res.ok) {
      const data = await res.json();
      const trade = data.trade;
      const pnl = Number(trade.net_pnl);
      if (pnl >= 0) {
        playTradeChime();
        showToast(`✅ ${symbol} squared off @ ₹${trade.exit_price} | Net P&L: +₹${pnl.toFixed(2)}`, "profit");
      } else {
        playAlertTone();
        showToast(`⚡ ${symbol} squared off @ ₹${trade.exit_price} | Net P&L: ₹${pnl.toFixed(2)}`, "loss");
      }
      fetchInitialData();
    } else {
      const err = await res.json();
      showToast(`❌ Square-off failed: ${err.detail || "Unknown error"}`, "loss");
    }
  } catch (e) {
    console.error("Square-off error:", e);
    showToast("❌ Network error during square-off.", "loss");
  }
}

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
            <span class="pos-symbol" style="cursor:pointer;" onclick="loadCandlestickChart('${pos.symbol}')">${pos.symbol}</span>
            <span class="tag-buy" style="margin-left:6px;">${pos.side}</span>
            <span style="font-size:11px; color:var(--text-muted); margin-left:6px;">${pos.quantity} Qty</span>
          </div>
          <div style="display:flex; align-items:center; gap:10px;">
            <div class="pos-pnl" style="color:${pnlColor};">
              ${pos.unrealized_pnl >= 0 ? '+' : ''}₹${pos.unrealized_pnl.toFixed(2)} (${pos.pnl_pct.toFixed(2)}%)
            </div>
            <button class="btn-square-off" data-pos-id="${pos.position_id}" data-symbol="${pos.symbol}">⚡ Square Off</button>
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
      const sqBtn = div.querySelector(".btn-square-off");
      if (sqBtn) {
        sqBtn.addEventListener("click", () => manualSquareOff(pos.position_id, pos.symbol));
      }
      positionsContainer.appendChild(div);
    });
  } catch (e) {
    console.error("Error fetching positions:", e);
  }
}

// ============================================================================
// ORDERS, LOGS & CSV EXPORT
// ============================================================================
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

function triggerCsvExport() {
  window.location.href = "/api/trading/trades/export";
  showToast("⬇ Downloading completed trades CSV...", "info");
}

// ============================================================================
// EVENT LISTENERS & MODALS
// ============================================================================
function setupEventListeners() {
  // Sound Toggle
  if (btnToggleSound) {
    btnToggleSound.addEventListener("click", () => {
      soundEnabled = !soundEnabled;
      localStorage.setItem("groww_sound_enabled", soundEnabled ? "true" : "false");
      updateSoundButtonUI();
      if (soundEnabled) {
        playTradeChime();
        showToast("🔊 Audio Alerts Enabled", "info");
      } else {
        showToast("🔇 Audio Alerts Muted", "warning");
      }
    });
  }

  // Chart Symbol Dropdown & Refresh
  if (chartSymbolSelect) {
    chartSymbolSelect.addEventListener("change", (e) => {
      loadCandlestickChart(e.target.value);
    });
  }
  const btnRefreshChart = document.getElementById("btnRefreshChart");
  if (btnRefreshChart) {
    btnRefreshChart.addEventListener("click", () => {
      loadCandlestickChart(selectedChartSymbol);
      showToast(`↻ Refreshed ${selectedChartSymbol} candles`, "info");
    });
  }

  // Export CSV buttons
  const btnExportCsv = document.getElementById("btnExportCsv");
  if (btnExportCsv) btnExportCsv.addEventListener("click", triggerCsvExport);
  const btnExportReportCsv = document.getElementById("btnExportReportCsv");
  if (btnExportReportCsv) btnExportReportCsv.addEventListener("click", triggerCsvExport);

  // Master Control buttons
  document.getElementById("btnStartAll").addEventListener("click", async () => {
    const res = await fetch("/api/system/start", { method: "POST" });
    const data = await res.json();
    playTradeChime();
    showToast(`▶ Master Supervisor Started (${data.instruments_count || 25} NSE stocks)`, "profit");
    fetchInitialData();
  });

  document.getElementById("btnPauseAll").addEventListener("click", async () => {
    await fetch("/api/system/pause", { method: "POST" });
    showToast("⏸ Agents Paused (Position Monitor still active)", "warning");
    fetchInitialData();
  });

  document.getElementById("btnStopAll").addEventListener("click", async () => {
    await fetch("/api/system/stop", { method: "POST" });
    showToast("⏹ All Agents Stopped safely", "info");
    fetchInitialData();
  });

  document.getElementById("btnEmergencyShutdown").addEventListener("click", async () => {
    if (confirm("🚨 INITIATE EMERGENCY SHUTDOWN? This will immediately trip the kill switch and halt all agents.")) {
      await fetch("/api/system/emergency-shutdown", { method: "POST" });
      playAlertTone();
      showToast("🚨 EMERGENCY SHUTDOWN EXECUTED. Kill Switch Engaged.", "loss");
      fetchInitialData();
    }
  });

  document.getElementById("btnResetKillSwitch").addEventListener("click", async () => {
    await fetch("/api/system/reset-kill-switch", { method: "POST" });
    showToast("✅ Kill Switch Reset by operator", "profit");
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
      if (document.getElementById("cfgMinScore")) {
        document.getElementById("cfgMinScore").value = cfg.DECISION_MIN_SCORE_THRESHOLD ?? 70;
        document.getElementById("cfgMinConfirmations").value = cfg.STRATEGY_MIN_CONFIRMATIONS ?? 4;
        document.getElementById("cfgAtrSlMult").value = cfg.STRATEGY_ATR_SL_MULTIPLIER ?? 1.5;
        document.getElementById("cfgRrRatio").value = cfg.MIN_RISK_REWARD_RATIO ?? 1.5;
        document.getElementById("cfgMinRvol").value = cfg.STRATEGY_MIN_RVOL ?? 1.2;
      }
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
    if (document.getElementById("cfgMinScore")) {
      payload.DECISION_MIN_SCORE_THRESHOLD = parseFloat(document.getElementById("cfgMinScore").value);
      payload.STRATEGY_MIN_CONFIRMATIONS = parseInt(document.getElementById("cfgMinConfirmations").value);
      payload.STRATEGY_ATR_SL_MULTIPLIER = parseFloat(document.getElementById("cfgAtrSlMult").value);
      payload.MIN_RISK_REWARD_RATIO = parseFloat(document.getElementById("cfgRrRatio").value);
      payload.STRATEGY_MIN_RVOL = parseFloat(document.getElementById("cfgMinRvol").value);
    }
    const res = await fetch("/api/settings/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast("⚙ Trading & Strategy Configuration saved", "profit");
      settingsModal.style.display = "none";
      fetchInitialData();
    } else {
      const err = await res.json();
      showToast(`❌ Failed to save: ${err.detail || "Invalid value"}`, "loss");
    }
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
      playTradeChime();
      showToast("✅ Compliance checks passed in sandbox!", "profit");
    } else {
      playAlertTone();
      showToast(`❌ Live Trading Blocked: ${result.message}`, "loss");
    }
  });

  // Backtest & Strategy Tuning Lab Modal
  const backtestModal = document.getElementById("backtestModal");
  document.getElementById("btnOpenBacktest").addEventListener("click", () => {
    backtestModal.style.display = "flex";
  });
  document.getElementById("btnCloseBacktest").addEventListener("click", () => {
    backtestModal.style.display = "none";
  });

  // Capital-friendly quick preset buttons
  document.querySelectorAll(".bt-preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById("txtBacktestSymbol").value = btn.dataset.sym;
    });
  });

  document.getElementById("btnRunBacktest").addEventListener("click", async () => {
    const symbol = document.getElementById("txtBacktestSymbol").value.toUpperCase().trim() || "NTPC";
    const container = document.getElementById("backtestResultsContainer");
    container.innerHTML = `<div style="text-align:center; padding:30px; color:var(--color-cyan);">Running walk-forward backtest (250 candles) for ${symbol}...</div>`;

    const res = await fetch("/api/backtest/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, limit: 250 })
    });

    if (res.ok) {
      const b = await res.json();
      if (b.error) {
        container.innerHTML = `<div style="color:var(--color-loss); text-align:center; padding:20px;">${b.error}</div>`;
        return;
      }
      const perf = b.overall_performance;
      const ins = b.in_sample_performance;
      const oos = b.out_of_sample_validation;
      const p = b.parameters_used || {};

      container.innerHTML = `
        <div style="background:var(--bg-card); padding:16px; border-radius:6px; font-family:var(--font-mono); font-size:12px;">
          <h4 style="color:#fff; margin-bottom:8px;">${symbol} Walk-Forward Backtest Results (Trailing SL Enabled)</h4>
          <div style="font-size:11px; color:var(--text-muted); margin-bottom:12px;">
            Params: Confirmations ≥ ${p.min_confirmations} | ATR SL: ${p.atr_sl_multiplier}x | R:R: ${p.rr_ratio} | RVOL ≥ ${p.min_rvol}
          </div>
          <div style="display:grid; grid-template-columns: repeat(2, 1fr); gap:8px;">
            <div>Total Candles: <strong>${b.total_candles}</strong></div>
            <div>Total Trades: <strong>${perf.total_trades}</strong> (W: ${perf.winning_trades} / L: ${perf.losing_trades})</div>
            <div>Win Rate: <strong style="color:var(--color-profit);">${perf.win_rate_pct}%</strong></div>
            <div>Net Profit: <strong style="color:${perf.net_profit_inr >= 0 ? 'var(--color-profit)' : 'var(--color-loss)'};">₹${perf.net_profit_inr}</strong></div>
            <div>Statutory Charges: <strong>₹${perf.total_statutory_charges}</strong></div>
            <div>Profit Factor: <strong>${perf.profit_factor}</strong></div>
            <div>Max Drawdown: <strong style="color:var(--color-loss);">₹${perf.max_drawdown_inr} (${perf.max_drawdown_pct}%)</strong></div>
            <div>Estimated Sharpe: <strong>${perf.sharpe_ratio}</strong></div>
          </div>

          <div style="margin-top:14px; border-top:1px solid var(--border-subtle); padding-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:10px;">
            <div>
              <strong style="color:var(--color-cyan);">In-Sample (70%):</strong>
              <div>Trades: ${ins.total_trades} | Win: ${ins.win_rate_pct}% | Net: ₹${ins.net_profit_inr}</div>
            </div>
            <div>
              <strong style="color:var(--color-profit);">Out-of-Sample (30%):</strong>
              <div>Trades: ${oos.total_trades} | Win: ${oos.win_rate_pct}% | Net: ₹${oos.net_profit_inr}</div>
            </div>
          </div>
        </div>
      `;
    } else {
      container.innerHTML = `<div style="color:var(--color-loss); text-align:center; padding:20px;">Backtest execution failed.</div>`;
    }
  });

  // Auto-Optimize Strategy (Walk-Forward Grid Search)
  const btnOptimize = document.getElementById("btnOptimizeStrategy");
  if (btnOptimize) {
    btnOptimize.addEventListener("click", async () => {
      const container = document.getElementById("backtestResultsContainer");
      container.innerHTML = `
        <div style="text-align:center; padding:30px; color:var(--color-cyan);">
          🔬 Running Walk-Forward Grid Search (81 parameter combos × 9 NSE stocks)...<br>
          <span style="font-size:11px; color:var(--text-muted);">Optimizing on In-Sample (70%) and validating on unseen Out-of-Sample (30%)</span>
        </div>`;

      const res = await fetch("/api/backtest/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: 250 })
      });

      if (!res.ok) {
        container.innerHTML = `<div style="color:var(--color-loss); text-align:center; padding:20px;">Strategy optimization failed.</div>`;
        return;
      }

      const opt = await res.json();
      if (opt.error) {
        container.innerHTML = `<div style="color:var(--color-loss); text-align:center; padding:20px;">${opt.error}</div>`;
        return;
      }

      const rec = opt.recommended;
      const rp = rec.params;
      const base = opt.baseline;

      let rowsHtml = "";
      opt.top_candidates.forEach((c, idx) => {
        const cp = c.params;
        const isBest = idx === 0;
        rowsHtml += `
          <tr style="${isBest ? 'background:rgba(16,185,129,0.08);' : ''}">
            <td>#${idx + 1}</td>
            <td>≥${cp.min_confirmations}</td>
            <td>${cp.atr_sl_multiplier}x</td>
            <td>1:${cp.rr_ratio}</td>
            <td>≥${cp.min_rvol}x</td>
            <td>${c.in_sample.total_trades} (${c.in_sample.win_rate_pct}%)</td>
            <td style="color:${c.in_sample.net_profit_inr >= 0 ? 'var(--color-profit)' : 'var(--color-loss)'};">₹${c.in_sample.net_profit_inr}</td>
            <td>${c.out_of_sample.total_trades} (${c.out_of_sample.win_rate_pct}%)</td>
            <td style="color:${c.out_of_sample.net_profit_inr >= 0 ? 'var(--color-profit)' : 'var(--color-loss)'};">₹${c.out_of_sample.net_profit_inr}</td>
          </tr>`;
      });

      container.innerHTML = `
        <div style="background:var(--bg-card); padding:16px; border-radius:6px; font-family:var(--font-mono); font-size:12px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
            <div>
              <h4 style="color:#fff; margin:0;">🔬 Walk-Forward Grid Search Complete</h4>
              <div style="font-size:11px; color:var(--text-muted);">${opt.combinations_tested} combos tested across ${opt.stocks_evaluated.length} NSE equities</div>
            </div>
            <button class="btn btn-start" id="btnApplyTunedParams" style="padding:6px 12px; font-size:11px;">
              ✅ Apply Recommended Parameters
            </button>
          </div>

          <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:14px;">
            <div style="background:rgba(255,255,255,0.03); padding:10px; border-radius:4px; border:1px solid var(--border-subtle);">
              <div style="font-size:10px; color:var(--text-muted);">CURRENT BASELINE</div>
              <div>Conf ≥ ${base.params.min_confirmations} | ATR ${base.params.atr_sl_multiplier}x | R:R 1:${base.params.rr_ratio} | RVOL ≥ ${base.params.min_rvol}</div>
              <div style="margin-top:4px;">In-Sample: <strong>₹${base.in_sample_net_pnl}</strong> (${base.in_sample_trades} trades)</div>
              <div>Out-of-Sample: <strong>₹${base.out_of_sample_net_pnl}</strong> (${base.out_of_sample_trades} trades)</div>
            </div>
            <div style="background:rgba(16,185,129,0.08); padding:10px; border-radius:4px; border:1px solid rgba(16,185,129,0.4);">
              <div style="font-size:10px; color:var(--color-profit); font-weight:700;">RECOMMENDED TUNED CONFIG</div>
              <div>Conf ≥ <strong>${rp.min_confirmations}</strong> | ATR <strong>${rp.atr_sl_multiplier}x</strong> | R:R <strong>1:${rp.rr_ratio}</strong> | RVOL ≥ <strong>${rp.min_rvol}</strong> | Score ≥ <strong>${rp.decision_min_score_threshold}</strong></div>
              <div style="margin-top:4px;">In-Sample: <strong style="color:var(--color-profit);">₹${rec.in_sample.net_profit_inr}</strong> (WR ${rec.in_sample.win_rate_pct}%, PF ${rec.in_sample.profit_factor})</div>
              <div>Out-of-Sample: <strong style="color:${rec.out_of_sample.net_profit_inr >= 0 ? 'var(--color-profit)' : 'var(--color-loss)'};">₹${rec.out_of_sample.net_profit_inr}</strong> (WR ${rec.out_of_sample.win_rate_pct}%)</div>
            </div>
          </div>

          <div style="overflow-x:auto;">
            <table class="data-table" style="font-size:11px;">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Conf</th>
                  <th>ATR SL</th>
                  <th>R:R</th>
                  <th>RVOL</th>
                  <th>IS Trades (WR)</th>
                  <th>IS Net</th>
                  <th>OOS Trades (WR)</th>
                  <th>OOS Net</th>
                </tr>
              </thead>
              <tbody>${rowsHtml}</tbody>
            </table>
          </div>

          <div style="margin-top:10px; font-size:10px; color:var(--text-muted);">
            ℹ ${opt.note}
          </div>
        </div>
      `;

      const applyBtn = document.getElementById("btnApplyTunedParams");
      if (applyBtn) {
        applyBtn.addEventListener("click", async () => {
          const updateRes = await fetch("/api/settings/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              STRATEGY_MIN_CONFIRMATIONS: rp.min_confirmations,
              STRATEGY_ATR_SL_MULTIPLIER: rp.atr_sl_multiplier,
              MIN_RISK_REWARD_RATIO: rp.rr_ratio,
              STRATEGY_MIN_RVOL: rp.min_rvol,
              DECISION_MIN_SCORE_THRESHOLD: rp.decision_min_score_threshold
            })
          });
          if (updateRes.ok) {
            playTradeChime();
            showToast(`✅ Tuned parameters applied! (Score≥${rp.decision_min_score_threshold}, Conf≥${rp.min_confirmations}, R:R 1:${rp.rr_ratio})`, "profit");
          } else {
            showToast("❌ Failed to apply tuned parameters.", "loss");
          }
        });
      }
    });
  }

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


// ============================================================================
// VOICE AGENT ENGINE (Web Speech API - Zero CDN, Zero Install)
// ============================================================================

// Stored Voice Configuration (persisted across sessions)
let voiceConfig = {
  voiceURI: "",
  rate: 1.05,
  pitch: 1.0,
  volume: 1.0,
  persona: "anchor",
  announceTrades: true,
  announceExits: true,
  announceAlerts: true
};

try {
  const saved = localStorage.getItem("groww_voice_settings");
  if (saved) voiceConfig = Object.assign(voiceConfig, JSON.parse(saved));
} catch (e) {
  console.warn("Could not load voice config:", e);
}

function setupVoiceAgent() {
  if (!window.speechSynthesis) {
    console.warn("[VoiceAgent] Web Speech API not supported in this browser.");
    return;
  }

  updateVoiceButtonUI();
  initVoiceModalControls();

  // Assembly Briefing button
  const btnAssembly = document.getElementById("btnAssemblyBriefing");
  if (btnAssembly) {
    btnAssembly.addEventListener("click", () => triggerAssemblyBriefing());
  }

  // Toggle Voice ON/OFF
  const btnToggle = document.getElementById("btnToggleVoice");
  if (btnToggle) {
    btnToggle.addEventListener("click", () => {
      voiceEnabled = !voiceEnabled;
      localStorage.setItem("groww_voice_enabled", voiceEnabled ? "true" : "false");
      updateVoiceButtonUI();
      if (voiceEnabled) {
        showToast("🔈 Voice Agent ENABLED — auto-briefings every 90s", "info");
        startVoiceHeartbeat();
        // Welcome announcement
        speak("Voice Agent is now active. I will read out agent status and trade alerts automatically.", "INFO");
      } else {
        stopVoiceHeartbeat();
        window.speechSynthesis.cancel();
        setVoiceTicker("Voice Agent disabled.", false);
        showToast("🔇 Voice Agent DISABLED", "warning");
      }
    });
  }

  // Repeat last briefing
  const btnRepeat = document.getElementById("btnRepeatBriefing");
  if (btnRepeat) {
    btnRepeat.addEventListener("click", async () => {
      try {
        const res = await fetch("/api/voice/last");
        if (res.ok) {
          const d = await res.json();
          if (d.text) {
            speak(d.text, d.type || "INFO");
            showToast("↺ Repeating last briefing", "info");
          } else {
            showToast("No previous briefing found.", "warning");
          }
        }
      } catch (e) {
        console.error("[VoiceAgent] Repeat error:", e);
      }
    });
  }

  // Stop speech
  const btnStop = document.getElementById("btnStopSpeech");
  if (btnStop) {
    btnStop.addEventListener("click", () => {
      window.speechSynthesis.cancel();
      isSpeaking = false;
      setVoiceTicker("Speech stopped.", false);
    });
  }

  // Start heartbeat if already enabled from previous session
  if (voiceEnabled) {
    startVoiceHeartbeat();
  }
}

// ---- Voice Model & Settings Modal Controls ----
function initVoiceModalControls() {
  const voiceModal = document.getElementById("voiceModal");
  const openModal = () => {
    populateVoiceDropdown();
    syncVoiceModalUI();
    if (voiceModal) voiceModal.style.display = "flex";
  };
  const closeModal = () => {
    if (voiceModal) voiceModal.style.display = "none";
  };

  const btnHeader = document.getElementById("btnHeaderVoiceModal");
  if (btnHeader) btnHeader.addEventListener("click", openModal);

  const btnTicker = document.getElementById("btnOpenVoiceModal");
  if (btnTicker) btnTicker.addEventListener("click", openModal);

  const btnClose = document.getElementById("btnCloseVoiceModal");
  if (btnClose) btnClose.addEventListener("click", closeModal);

  const btnCancel = document.getElementById("btnCancelVoiceModal");
  if (btnCancel) btnCancel.addEventListener("click", closeModal);

  // Sliders real-time feedback
  const rRate = document.getElementById("rangeVoiceRate");
  const valRate = document.getElementById("valVoiceRate");
  if (rRate && valRate) {
    rRate.addEventListener("input", (e) => {
      valRate.textContent = `${parseFloat(e.target.value).toFixed(2)}x`;
    });
  }

  const rPitch = document.getElementById("rangeVoicePitch");
  const valPitch = document.getElementById("valVoicePitch");
  if (rPitch && valPitch) {
    rPitch.addEventListener("input", (e) => {
      valPitch.textContent = parseFloat(e.target.value).toFixed(2);
    });
  }

  const rVol = document.getElementById("rangeVoiceVolume");
  const valVol = document.getElementById("valVoiceVolume");
  if (rVol && valVol) {
    rVol.addEventListener("input", (e) => {
      valVol.textContent = `${Math.round(parseFloat(e.target.value) * 100)}%`;
    });
  }

  // Persona Presets
  const personaCards = document.querySelectorAll(".voice-persona-card");
  personaCards.forEach(card => {
    card.addEventListener("click", () => {
      personaCards.forEach(c => c.classList.remove("active"));
      card.classList.add("active");
      const persona = card.dataset.persona;
      applyPersonaSettings(persona);
    });
  });

  // Test Voice Model button
  const btnTest = document.getElementById("btnTestVoiceModel");
  if (btnTest) {
    btnTest.addEventListener("click", () => {
      testSelectedVoice();
    });
  }

  // Save Voice Model button
  const btnSave = document.getElementById("btnSaveVoiceModel");
  if (btnSave) {
    btnSave.addEventListener("click", () => {
      saveVoiceSettings();
      closeModal();
      showToast("🎙 AI Voice Model & Audio Settings saved!", "profit");
    });
  }

  // Populate voice dropdown when speech synthesis loads voices
  if (window.speechSynthesis.onvoiceschanged !== undefined) {
    window.speechSynthesis.onvoiceschanged = () => {
      populateVoiceDropdown();
    };
  }
  // Also try immediately
  populateVoiceDropdown();
}

function populateVoiceDropdown() {
  const select = document.getElementById("selectVoiceModel");
  const countLbl = document.getElementById("lblVoiceCount");
  if (!select) return;

  const voices = window.speechSynthesis.getVoices();
  if (!voices || voices.length === 0) return;

  const currentSelection = voiceConfig.voiceURI || select.value;
  select.innerHTML = "";

  // Group English voices first, then others
  const enVoices = voices.filter(v => v.lang.startsWith("en"));
  const otherVoices = voices.filter(v => !v.lang.startsWith("en"));

  const addGroup = (label, list) => {
    if (list.length === 0) return;
    const group = document.createElement("optgroup");
    group.label = label;
    list.forEach(v => {
      const opt = document.createElement("option");
      opt.value = v.voiceURI;
      opt.textContent = `${v.name} (${v.lang})${v.default ? " [Default]" : ""}`;
      if (v.voiceURI === currentSelection) opt.selected = true;
      group.appendChild(opt);
    });
    select.appendChild(group);
  };

  addGroup("English Neural & System Voices", enVoices);
  addGroup("Other Languages", otherVoices);

  if (countLbl) countLbl.textContent = `${voices.length} voices ready`;
}

function syncVoiceModalUI() {
  const rRate = document.getElementById("rangeVoiceRate");
  const valRate = document.getElementById("valVoiceRate");
  if (rRate) rRate.value = voiceConfig.rate;
  if (valRate) valRate.textContent = `${voiceConfig.rate.toFixed(2)}x`;

  const rPitch = document.getElementById("rangeVoicePitch");
  const valPitch = document.getElementById("valVoicePitch");
  if (rPitch) rPitch.value = voiceConfig.pitch;
  if (valPitch) valPitch.textContent = voiceConfig.pitch.toFixed(2);

  const rVol = document.getElementById("rangeVoiceVolume");
  const valVol = document.getElementById("valVoiceVolume");
  if (rVol) rVol.value = voiceConfig.volume;
  if (valVol) valVol.textContent = `${Math.round(voiceConfig.volume * 100)}%`;

  const chkTrades = document.getElementById("chkVoxTrades");
  if (chkTrades) chkTrades.checked = voiceConfig.announceTrades !== false;
  const chkExits = document.getElementById("chkVoxExits");
  if (chkExits) chkExits.checked = voiceConfig.announceExits !== false;
  const chkAlerts = document.getElementById("chkVoxAlerts");
  if (chkAlerts) chkAlerts.checked = voiceConfig.announceAlerts !== false;

  // Highlight persona card if matching
  document.querySelectorAll(".voice-persona-card").forEach(c => {
    c.classList.toggle("active", c.dataset.persona === voiceConfig.persona);
  });
}

function applyPersonaSettings(persona) {
  const rRate = document.getElementById("rangeVoiceRate");
  const rPitch = document.getElementById("rangeVoicePitch");
  const select = document.getElementById("selectVoiceModel");
  const voices = window.speechSynthesis.getVoices();

  let rate = 1.05;
  let pitch = 1.0;

  if (persona === "anchor") {
    rate = 1.05;
    pitch = 1.0;
  } else if (persona === "scalper") {
    rate = 1.25;
    pitch = 1.1;
  } else if (persona === "risk") {
    rate = 0.95;
    pitch = 0.9;
  } else if (persona === "cyber") {
    rate = 1.15;
    pitch = 1.25;
  } else if (persona === "india") {
    rate = 1.0;
    pitch = 1.0;
    // Prefer en-IN voice if present
    const inVoice = voices.find(v => v.lang === "en-IN" || v.lang.startsWith("en_IN") || v.name.includes("India") || v.name.includes("Ravi") || v.name.includes("Heera"));
    if (inVoice && select) select.value = inVoice.voiceURI;
  }

  if (rRate) {
    rRate.value = rate;
    const l = document.getElementById("valVoiceRate");
    if (l) l.textContent = `${rate.toFixed(2)}x`;
  }
  if (rPitch) {
    rPitch.value = pitch;
    const l = document.getElementById("valVoicePitch");
    if (l) l.textContent = pitch.toFixed(2);
  }
}

function testSelectedVoice() {
  if (!window.speechSynthesis) return;
  const select = document.getElementById("selectVoiceModel");
  const rate = parseFloat(document.getElementById("rangeVoiceRate")?.value || 1.05);
  const pitch = parseFloat(document.getElementById("rangeVoicePitch")?.value || 1.0);
  const volume = parseFloat(document.getElementById("rangeVoiceVolume")?.value || 1.0);
  const voiceURI = select ? select.value : "";

  window.speechSynthesis.cancel();
  const testPhrase = "Groww AI Voice Agent online. Master Supervisor and Risk Manager are operational on NSE.";
  const utter = new SpeechSynthesisUtterance(testPhrase);

  const voices = window.speechSynthesis.getVoices();
  const matched = voices.find(v => v.voiceURI === voiceURI);
  if (matched) utter.voice = matched;

  utter.rate = rate;
  utter.pitch = pitch;
  utter.volume = volume;

  setVoiceTicker("Testing selected voice model...", true);
  utter.onend = () => setVoiceTicker("Done testing voice.", false);
  utter.onerror = () => setVoiceTicker("Voice test error.", false);

  window.speechSynthesis.speak(utter);
}

function saveVoiceSettings() {
  const select = document.getElementById("selectVoiceModel");
  const rRate = document.getElementById("rangeVoiceRate");
  const rPitch = document.getElementById("rangeVoicePitch");
  const rVol = document.getElementById("rangeVoiceVolume");
  const activePersona = document.querySelector(".voice-persona-card.active");

  voiceConfig.voiceURI = select ? select.value : "";
  voiceConfig.rate = rRate ? parseFloat(rRate.value) : 1.05;
  voiceConfig.pitch = rPitch ? parseFloat(rPitch.value) : 1.0;
  voiceConfig.volume = rVol ? parseFloat(rVol.value) : 1.0;
  voiceConfig.persona = activePersona ? activePersona.dataset.persona : "custom";
  voiceConfig.announceTrades = Boolean(document.getElementById("chkVoxTrades")?.checked);
  voiceConfig.announceExits = Boolean(document.getElementById("chkVoxExits")?.checked);
  voiceConfig.announceAlerts = Boolean(document.getElementById("chkVoxAlerts")?.checked);

  try {
    localStorage.setItem("groww_voice_settings", JSON.stringify(voiceConfig));
  } catch (e) {
    console.error("Failed to save voice config:", e);
  }
}

// ---- Core speak() function ----
function speak(text, type = "INFO") {
  if (!window.speechSynthesis) return;
  if (!text || text.trim().length === 0) return;

  // Cancel any ongoing speech first
  window.speechSynthesis.cancel();

  const utter = new SpeechSynthesisUtterance(text);
  const voices = window.speechSynthesis.getVoices();

  // Match the user's selected voice model if configured
  if (voiceConfig.voiceURI) {
    const customVoice = voices.find(v => v.voiceURI === voiceConfig.voiceURI);
    if (customVoice) utter.voice = customVoice;
  }

  // Fallback if no custom voice selected or available
  if (!utter.voice) {
    const preferred = voices.find(v =>
      v.lang.startsWith("en") && (
        v.name.includes("Google") ||
        v.name.includes("Microsoft") ||
        v.name.includes("Samantha") ||
        v.name.includes("Daniel") ||
        v.lang === "en-IN"
      )
    );
    if (preferred) utter.voice = preferred;
  }

  // Base adjustments from user configuration
  let rateMultiplier = voiceConfig.rate || 1.05;
  let basePitch = voiceConfig.pitch || 1.0;
  let baseVol = voiceConfig.volume || 1.0;

  // Dynamic context modulation by notification severity
  switch (type) {
    case "KILL":
      utter.rate = rateMultiplier * 0.95;
      utter.pitch = Math.max(0.6, basePitch * 0.85);
      utter.volume = 1.0;
      break;
    case "TRADE":
    case "EXIT":
      utter.rate = rateMultiplier;
      utter.pitch = Math.min(1.4, basePitch * 1.08);
      utter.volume = baseVol;
      break;
    case "ASSEMBLY":
      utter.rate = rateMultiplier;
      utter.pitch = basePitch;
      utter.volume = baseVol;
      break;
    default:
      utter.rate = rateMultiplier;
      utter.pitch = basePitch;
      utter.volume = baseVol;
  }

  utter.onstart = () => {
    isSpeaking = true;
    setVoiceTicker(text, true);
  };
  utter.onend = () => {
    isSpeaking = false;
    setVoiceTicker("Done speaking.", false);
  };
  utter.onerror = (e) => {
    isSpeaking = false;
    console.warn("[VoiceAgent] Speech error:", e.error);
    setVoiceTicker("Voice playback error. Try again.", false);
  };

  window.speechSynthesis.speak(utter);
}

// ---- Assembly Briefing (all 9 agents + portfolio) ----
async function triggerAssemblyBriefing() {
  const btnAssembly = document.getElementById("btnAssemblyBriefing");
  if (btnAssembly) {
    btnAssembly.textContent = "🎙 Loading...";
    btnAssembly.disabled = true;
  }
  try {
    const res = await fetch("/api/voice/assembly");
    if (res.ok) {
      const data = await res.json();
      speak(data.text, "ASSEMBLY");
      showToast(`🎙 Assembly Briefing — ${data.word_count} words`, "info");
    } else {
      showToast("❌ Assembly briefing failed.", "loss");
    }
  } catch (e) {
    console.error("[VoiceAgent] Assembly fetch error:", e);
    showToast("❌ Could not reach voice endpoint.", "loss");
  } finally {
    if (btnAssembly) {
      btnAssembly.textContent = "🎙 Assembly Briefing";
      btnAssembly.disabled = false;
    }
  }
}

// ---- Heartbeat (periodic concise auto-read) ----
function startVoiceHeartbeat() {
  stopVoiceHeartbeat();
  voiceHeartbeatTimer = setInterval(async () => {
    if (!voiceEnabled || isSpeaking) return;
    try {
      const res = await fetch("/api/voice/heartbeat");
      if (res.ok) {
        const data = await res.json();
        speak(data.text, "HEARTBEAT");
      }
    } catch (e) {
      console.warn("[VoiceAgent] Heartbeat error:", e);
    }
  }, VOICE_HEARTBEAT_INTERVAL_MS);
}

function stopVoiceHeartbeat() {
  if (voiceHeartbeatTimer) {
    clearInterval(voiceHeartbeatTimer);
    voiceHeartbeatTimer = null;
  }
}

// ---- Auto-announce trade events detected via UI state polling ----
function checkVoiceAutoAnnounce(data) {
  if (!voiceEnabled || !data) return;
  const portfolio = data.portfolio || {};
  const trades = portfolio.total_trades_today || 0;
  const killSwitch = Boolean(portfolio.is_kill_switch_active);

  // New trade executed
  if (lastSpokenTradeCount !== null && trades > lastSpokenTradeCount && voiceConfig.announceTrades !== false) {
    // Fetch the latest trade info and announce it
    fetch("/api/trading/orders")
      .then(r => r.json())
      .then(orders => {
        if (orders && orders.length > 0) {
          const latest = orders[0];
          fetch("/api/voice/trade", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              symbol: latest.symbol,
              side: latest.side,
              quantity: latest.quantity,
              executed_price: latest.executed_price || latest.reference_price,
              stop_loss: latest.stop_loss || 0,
              target: latest.target || 0
            })
          }).then(r => r.json()).then(d => {
            if (!isSpeaking) speak(d.text, "TRADE");
          });
        }
      })
      .catch(() => {});
  }
  lastSpokenTradeCount = trades;

  // Kill switch triggered
  if (killSwitch && !lastSpokenKillSwitch && voiceConfig.announceAlerts !== false) {
    const dailyLoss = portfolio.realized_daily_pnl || 0;
    fetch("/api/voice/last")
      .then(r => r.json())
      .then(() => {
        const killText = `ALERT! Daily loss limit reached. Kill switch is now ACTIVE. All new order generation is suspended.`;
        if (!isSpeaking) speak(killText, "KILL");
      });
  }
  lastSpokenKillSwitch = killSwitch;
}

// ---- Ticker Strip UI ----
function setVoiceTicker(text, speaking) {
  const ticker = document.getElementById("voiceTickerText");
  const strip = document.getElementById("voiceTicker");
  if (!ticker || !strip) return;

  ticker.innerHTML = speaking
    ? `${text.substring(0, 120)}${text.length > 120 ? "..." : ""}
       <span class="voice-wave">
         <span></span><span></span><span></span><span></span><span></span>
       </span>`
    : text.substring(0, 160);

  if (speaking) {
    strip.classList.add("speaking");
  } else {
    strip.classList.remove("speaking");
  }
}

// ---- Voice button UI ----
function updateVoiceButtonUI() {
  const btn = document.getElementById("btnToggleVoice");
  if (!btn) return;
  if (voiceEnabled) {
    btn.textContent = "🔈 Voice ON";
    btn.classList.add("voice-active");
  } else {
    btn.textContent = "🔈 Voice OFF";
    btn.classList.remove("voice-active");
  }
}
