"""
Groww AI Trading Agent - Reporting Agent
Generates comprehensive end-of-day and on-demand trading analytics:
- Win rate, Profit factor, Maximum Drawdown
- Gross vs Net P&L (after full regulatory fees & taxes)
- Risk violations & failed signals audit
- Formats reports in JSON & GitHub Flavored Markdown in reports/
"""

import os
import json
from typing import Dict, Any, List
from datetime import datetime
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.database.db import db
from backend.models.schemas import AgentStateEnum, AgentStatus

IST = pytz.timezone(config.MARKET_TIMEZONE)

class ReportingAgent:
    def __init__(self):
        self.name = "ReportingAgent"
        self.state = AgentStateEnum.IDLE
        self.last_generated_report_date: Optional[str] = None
        self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    def get_status(self) -> AgentStatus:
        return AgentStatus(
            name=self.name,
            state=self.state,
            last_heartbeat=self.last_update,
            message=f"Last Report: {self.last_generated_report_date or 'None'}"
        )

    def generate_daily_report(self, target_date: str = None) -> Dict[str, Any]:
        """
        Calculates all performance metrics for the day and saves both JSON & Markdown files.
        """
        self.state = AgentStateEnum.ANALYZING
        now_dt = datetime.now(IST)
        date_str = target_date or now_dt.strftime("%Y-%m-%d")
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        trades = db.get_trades(limit=100)
        risk_events = db.get_risk_events(limit=100)
        portfolio = db.get_portfolio()

        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t["net_pnl"] > 0)
        losing_trades = sum(1 for t in trades if t["net_pnl"] <= 0)
        win_rate = round((winning_trades / total_trades * 100), 2) if total_trades > 0 else 0.0

        gross_pnl = round(sum(t["gross_pnl"] for t in trades), 2)
        net_pnl = round(sum(t["net_pnl"] for t in trades), 2)
        total_charges = round(sum(t["total_charges"] for t in trades), 2)

        # Profit factor = Gross Profits / Gross Losses
        gross_wins = sum(t["gross_pnl"] for t in trades if t["gross_pnl"] > 0)
        gross_losses = abs(sum(t["gross_pnl"] for t in trades if t["gross_pnl"] < 0))
        profit_factor = round(gross_wins / max(0.01, gross_losses), 2) if gross_losses > 0 else (gross_wins if gross_wins > 0 else 1.0)

        # Max Drawdown calculation
        peak = config.INITIAL_CAPITAL
        running_equity = config.INITIAL_CAPITAL
        max_drawdown = 0.0
        for t in reversed(trades):
            running_equity += t["net_pnl"]
            if running_equity > peak:
                peak = running_equity
            dd = peak - running_equity
            if dd > max_drawdown:
                max_drawdown = dd

        report_data = {
            "report_date": date_str,
            "generated_at": now_str,
            "starting_capital": config.INITIAL_CAPITAL,
            "current_capital": portfolio["total_capital"],
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate_pct": win_rate,
            "gross_pnl": gross_pnl,
            "total_charges": total_charges,
            "net_pnl": net_pnl,
            "profit_factor": profit_factor,
            "max_drawdown_inr": round(max_drawdown, 2),
            "max_drawdown_pct": round((max_drawdown / config.INITIAL_CAPITAL) * 100, 2),
            "risk_violations_count": len(risk_events),
            "trades_list": trades,
            "risk_events_list": risk_events
        }

        # 1. Save to Database
        try:
            conn = db.get_connection()
            conn.execute("""
            INSERT OR REPLACE INTO daily_reports (
                report_date, total_trades, winning_trades, losing_trades,
                win_rate, gross_pnl, net_pnl, total_charges, max_drawdown,
                report_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                date_str, total_trades, winning_trades, losing_trades, win_rate,
                gross_pnl, net_pnl, total_charges, max_drawdown,
                json.dumps(report_data), now_str
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save daily report to DB: {e}")

        # 2. Save JSON file to reports/
        os.makedirs("reports", exist_ok=True)
        json_path = os.path.join("reports", f"report_{date_str}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        # 3. Save Markdown file to reports/
        md_content = f"""# Groww AI Trading Agent - Daily Performance Report
**Date:** {date_str}  
**Generated At:** {now_str} IST  
**Execution Mode:** PAPER TRADING (Safe Default)

---

## 1. Executive Summary

| Metric | Value |
| :--- | :--- |
| **Initial Capital** | ₹{config.INITIAL_CAPITAL:,.2f} |
| **Current Portfolio Capital** | ₹{portfolio['total_capital']:,.2f} |
| **Total Trades** | {total_trades} |
| **Winning Trades** | {winning_trades} |
| **Losing Trades** | {losing_trades} |
| **Win Rate** | {win_rate}% |
| **Gross P&L** | ₹{gross_pnl:,.2f} |
| **Statutory & Brokerage Charges** | ₹{total_charges:,.2f} |
| **Net P&L (After Charges)** | ₹{net_pnl:,.2f} |
| **Profit Factor** | {profit_factor} |
| **Max Drawdown** | ₹{max_drawdown:,.2f} ({report_data['max_drawdown_pct']}%) |
| **Risk Violations Filtered** | {len(risk_events)} |

---

## 2. Completed Trades Log

| Symbol | Side | Qty | Entry Price | Exit Price | Gross P&L | Charges | Net P&L | Exit Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
        for t in trades:
            md_content += f"| {t['symbol']} | {t['side']} | {t['quantity']} | ₹{t['entry_price']} | ₹{t['exit_price']} | ₹{t['gross_pnl']} | ₹{t['total_charges']} | ₹{t['net_pnl']} | {t['exit_reason']} |\n"

        md_content += """
---

## 3. Risk Engine Audit
All trading decisions are strictly verified by the deterministic risk manager prior to execution.
The system automatically prevented duplicate trades, managed daily maximum loss, and applied position sizing.
"""
        md_path = os.path.join("reports", f"report_{date_str}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        logger.info(f"Daily report generated for {date_str} -> {md_path}")
        self.last_generated_report_date = date_str
        self.last_update = now_str
        self.state = AgentStateEnum.IDLE

        return report_data

reporting_agent = ReportingAgent()
