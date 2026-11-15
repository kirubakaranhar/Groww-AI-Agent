"""
Groww AI Trading Agent - Market Watcher Agent
Responsible for:
- Loading the full eligible NSE cash equity universe from Groww API
- Continuously polling / streaming market data
- Batch scanning with rate-limit pacing
- Detecting unusual volume spikes and volatility
- Maintaining market data freshness in MarketDataHub
- Reconnection and error recovery
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.database.db import db
from backend.models.schemas import InstrumentSchema, MarketQuote, AgentStateEnum, AgentStatus
from backend.services.groww_service import groww_service
from backend.services.market_data import market_data_hub

IST = pytz.timezone(config.MARKET_TIMEZONE)

class MarketWatcherAgent:
    def __init__(self):
        self.name = "MarketWatcherAgent"
        self.state = AgentStateEnum.IDLE
        self.instruments: List[InstrumentSchema] = []
        self.symbols: List[str] = []
        self.scanned_count: int = 0
        self.unusual_volume_candidates: List[str] = []
        self.is_connected = False
        self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    def get_status(self) -> AgentStatus:
        return AgentStatus(
            name=self.name,
            state=self.state,
            last_heartbeat=self.last_update,
            message=f"Watching {len(self.symbols)} NSE stocks | Scanned: {self.scanned_count}"
        )

    async def initialize_universe(self) -> int:
        """
        Loads the NSE instrument master, populates the SQLite instruments table,
        and sets up the internal universe.
        """
        self.state = AgentStateEnum.SCANNING
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.instruments = await groww_service.fetch_instrument_master()
            self.symbols = [inst.symbol for inst in self.instruments]

            # Save in database
            conn = db.get_connection()
            for inst in self.instruments:
                conn.execute("""
                INSERT OR REPLACE INTO instruments (
                    symbol, name, exchange, segment, lot_size, tick_size, is_tradable, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    inst.symbol, inst.name, inst.exchange, inst.segment,
                    inst.lot_size, inst.tick_size, 1 if inst.is_tradable else 0, now_str
                ))
            conn.commit()
            conn.close()

            self.is_connected = groww_service.is_connected
            self.last_update = now_str
            self.state = AgentStateEnum.IDLE
            logger.info(f"MarketWatcher initialized universe with {len(self.symbols)} NSE stocks.")
            return len(self.symbols)
        except Exception as e:
            self.state = AgentStateEnum.ERROR
            logger.error(f"Failed to initialize NSE universe: {e}")
            db.log_agent_event(self.name, "ERROR", f"Universe init failure: {str(e)}")
            return 0

    async def scan_market(self) -> List[MarketQuote]:
        """
        Scans all universe symbols in controlled rate-limited batches.
        Detects unusual volume surges (RVOL > threshold).
        """
        if not self.symbols:
            await self.initialize_universe()

        self.state = AgentStateEnum.SCANNING
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        try:
            quotes = await market_data_hub.fetch_batch_quotes(self.symbols)
            self.scanned_count = len(quotes)

            # Detect unusual volume breakouts
            unusual = []
            for q in quotes:
                if market_data_hub.detect_unusual_volume(q.symbol):
                    unusual.append(q.symbol)
            self.unusual_volume_candidates = unusual

            self.last_update = now_str
            self.state = AgentStateEnum.IDLE
            return quotes
        except Exception as e:
            self.state = AgentStateEnum.ERROR
            logger.error(f"Error during market scanning: {e}")
            db.log_agent_event(self.name, "ERROR", f"Scan error: {str(e)}")
            return []

market_watcher_agent = MarketWatcherAgent()
