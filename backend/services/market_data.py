"""
Groww AI Trading Agent - Market Data Hub & Cache
Manages in-memory market quote caching, time-series data freshness,
unusual volume / volatility detection, and controlled batch scanning.
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.models.schemas import MarketQuote
from backend.services.groww_service import groww_service

IST = pytz.timezone(config.MARKET_TIMEZONE)

class MarketDataHub:
    def __init__(self):
        self._quotes: Dict[str, MarketQuote] = {}
        self._last_updated: Dict[str, datetime] = {}
        self._volume_history: Dict[str, List[int]] = {}

    def update_quote(self, quote: MarketQuote):
        self._quotes[quote.symbol] = quote
        self._last_updated[quote.symbol] = datetime.now(IST)
        
        # Track volume for relative volume (RVOL) calculation
        if quote.symbol not in self._volume_history:
            self._volume_history[quote.symbol] = []
        self._volume_history[quote.symbol].append(quote.volume)
        if len(self._volume_history[quote.symbol]) > 50:
            self._volume_history[quote.symbol].pop(0)

    def get_quote(self, symbol: str) -> Optional[MarketQuote]:
        return self._quotes.get(symbol)

    def get_all_quotes(self) -> List[MarketQuote]:
        return list(self._quotes.values())

    def is_data_fresh(self, symbol: str, max_age_seconds: int = 45) -> bool:
        """Flags stale data if price quote has not refreshed within acceptable threshold."""
        last_time = self._last_updated.get(symbol)
        if not last_time:
            return False
        age = (datetime.now(IST) - last_time).total_seconds()
        return age <= max_age_seconds

    def calculate_rvol(self, symbol: str) -> float:
        """
        Calculates Relative Volume (RVOL) = current volume / average volume.
        """
        history = self._volume_history.get(symbol, [])
        if len(history) < 2:
            return 1.0
        avg_vol = sum(history[:-1]) / len(history[:-1])
        if avg_vol <= 0:
            return 1.0
        return round(history[-1] / avg_vol, 2)

    def detect_unusual_volume(self, symbol: str) -> bool:
        rvol = self.calculate_rvol(symbol)
        return rvol >= config.UNUSUAL_VOLUME_MULTIPLIER

    async def fetch_batch_quotes(self, symbols: List[str]) -> List[MarketQuote]:
        """
        Fetches quotes in controlled batches to strictly respect API rate limits.
        """
        results = []
        batch_size = config.SCANNER_BATCH_SIZE
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            tasks = [groww_service.fetch_quote(s) for s in batch]
            quotes = await asyncio.gather(*tasks, return_exceptions=True)
            for q in quotes:
                if isinstance(q, MarketQuote):
                    self.update_quote(q)
                    results.append(q)
            # Gentle pacing between batches
            await asyncio.sleep(0.1)
        return results

market_data_hub = MarketDataHub()
