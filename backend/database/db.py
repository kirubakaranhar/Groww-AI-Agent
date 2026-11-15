"""
Groww AI Trading Agent - Database Layer (SQLite)
Provides robust, thread-safe asynchronous and synchronous database access,
schema management, migrations, and operations.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import pytz
from backend.core.config import config
from backend.core.logger import logger

IST = pytz.timezone(config.MARKET_TIMEZONE)

def get_ist_now_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DATABASE_PATH
        # Ensure database directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for concurrent read/write performance
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def init_db(self):
        """Initializes all required database tables matching prompt specification."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # 1. instruments
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS instruments (
            symbol TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            exchange TEXT DEFAULT 'NSE',
            segment TEXT DEFAULT 'EQUITY',
            lot_size INTEGER DEFAULT 1,
            tick_size REAL DEFAULT 0.05,
            is_tradable INTEGER DEFAULT 1,
            updated_at TEXT
        );
        """)

        # 2. market_data
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume INTEGER NOT NULL,
            vwap REAL,
            UNIQUE(symbol, timestamp)
        );
        """)

        # 3. indicators
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            ema_9 REAL,
            ema_21 REAL,
            ema_50 REAL,
            ema_200 REAL,
            rsi_14 REAL,
            macd REAL,
            macd_signal REAL,
            macd_hist REAL,
            vwap REAL,
            atr REAL,
            bb_upper REAL,
            bb_middle REAL,
            bb_lower REAL,
            UNIQUE(symbol, timestamp)
        );
        """)

        # 4. stock_analysis
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            score REAL NOT NULL,
            trend_score REAL,
            momentum_score REAL,
            volume_score REAL,
            price_action_score REAL,
            regime_score REAL,
            data_quality_score REAL,
            analysis_json TEXT NOT NULL
        );
        """)

        # 5. trading_signals
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trading_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            entry_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            target REAL NOT NULL,
            score REAL NOT NULL,
            status TEXT DEFAULT 'PENDING',
            explanation TEXT,
            created_at TEXT NOT NULL
        );
        """)

        # 6. agent_events
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            details_json TEXT,
            timestamp TEXT NOT NULL
        );
        """)

        # 7. paper_orders
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_orders (
            order_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            order_type TEXT DEFAULT 'MARKET',
            reference_price REAL NOT NULL,
            executed_price REAL,
            slippage REAL DEFAULT 0.0,
            brokerage REAL DEFAULT 0.0,
            stt REAL DEFAULT 0.0,
            other_charges REAL DEFAULT 0.0,
            total_charges REAL DEFAULT 0.0,
            status TEXT NOT NULL,
            rejection_reason TEXT,
            placed_at TEXT NOT NULL,
            executed_at TEXT
        );
        """)

        # 8. trades
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            trade_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            gross_pnl REAL NOT NULL,
            net_pnl REAL NOT NULL,
            total_charges REAL NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT NOT NULL,
            exit_reason TEXT NOT NULL
        );
        """)

        # 9. positions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            position_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            target REAL NOT NULL,
            trailing_sl REAL,
            trailing_activated INTEGER DEFAULT 0,
            unrealized_pnl REAL DEFAULT 0.0,
            pnl_pct REAL DEFAULT 0.0,
            is_open INTEGER DEFAULT 1,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            exit_price REAL,
            exit_reason TEXT
        );
        """)

        # 10. portfolio
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY,
            total_capital REAL NOT NULL,
            available_capital REAL NOT NULL,
            invested_capital REAL DEFAULT 0.0,
            realized_daily_pnl REAL DEFAULT 0.0,
            unrealized_pnl REAL DEFAULT 0.0,
            total_trades_today INTEGER DEFAULT 0,
            winning_trades_today INTEGER DEFAULT 0,
            losing_trades_today INTEGER DEFAULT 0,
            daily_drawdown REAL DEFAULT 0.0,
            is_kill_switch_active INTEGER DEFAULT 0,
            last_updated TEXT NOT NULL
        );
        """)

        # 11. risk_events
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            symbol TEXT,
            attempted_action TEXT NOT NULL,
            reason TEXT NOT NULL,
            details_json TEXT,
            created_at TEXT NOT NULL
        );
        """)

        # 12. daily_reports
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_reports (
            report_date TEXT PRIMARY KEY,
            total_trades INTEGER NOT NULL,
            winning_trades INTEGER NOT NULL,
            losing_trades INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            gross_pnl REAL NOT NULL,
            net_pnl REAL NOT NULL,
            total_charges REAL NOT NULL,
            max_drawdown REAL NOT NULL,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)

        # 13. system_settings
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)

        # Initialize portfolio record if none exists
        cursor.execute("SELECT COUNT(*) as count FROM portfolio WHERE id = 1;")
        if cursor.fetchone()["count"] == 0:
            cursor.execute("""
            INSERT INTO portfolio (
                id, total_capital, available_capital, invested_capital,
                realized_daily_pnl, unrealized_pnl, total_trades_today,
                winning_trades_today, losing_trades_today, daily_drawdown,
                is_kill_switch_active, last_updated
            ) VALUES (1, ?, ?, 0.0, 0.0, 0.0, 0, 0, 0, 0.0, 0, ?);
            """, (config.INITIAL_CAPITAL, config.INITIAL_CAPITAL, get_ist_now_str()))

        conn.commit()
        conn.close()
        logger.info(f"Database schema initialized at {self.db_path}")

    # Helper operations
    def log_agent_event(self, agent_name: str, level: str, message: str, details: Optional[Dict[str, Any]] = None):
        try:
            conn = self.get_connection()
            conn.execute("""
            INSERT INTO agent_events (agent_name, level, message, details_json, timestamp)
            VALUES (?, ?, ?, ?, ?);
            """, (agent_name, level, message, json.dumps(details or {}), get_ist_now_str()))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error logging agent event: {e}")

    def get_recent_agent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, agent_name, level, message, details_json, timestamp
        FROM agent_events ORDER BY id DESC LIMIT ?;
        """, (limit,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def get_portfolio(self) -> Dict[str, Any]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM portfolio WHERE id = 1;")
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return {
            "total_capital": config.INITIAL_CAPITAL,
            "available_capital": config.INITIAL_CAPITAL,
            "invested_capital": 0.0,
            "realized_daily_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "total_trades_today": 0,
            "winning_trades_today": 0,
            "losing_trades_today": 0,
            "daily_drawdown": 0.0,
            "is_kill_switch_active": 0,
            "last_updated": get_ist_now_str()
        }

    def update_portfolio(self, data: Dict[str, Any]):
        conn = self.get_connection()
        data["last_updated"] = get_ist_now_str()
        set_clauses = [f"{k} = ?" for k in data.keys()]
        values = list(data.values())
        query = f"UPDATE portfolio SET {', '.join(set_clauses)} WHERE id = 1;"
        conn.execute(query, values)
        conn.commit()
        conn.close()

    def get_open_positions(self) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM positions WHERE is_open = 1;")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def get_paper_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM paper_orders ORDER BY placed_at DESC LIMIT ?;", (limit,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def get_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades ORDER BY exit_time DESC LIMIT ?;", (limit,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def get_risk_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM risk_events ORDER BY created_at DESC LIMIT ?;", (limit,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

# Global database instance
db = Database()
