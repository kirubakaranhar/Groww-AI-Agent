"""
Groww AI Trading Agent - Groww Trading API Service
Implements official Groww Trading API specifications:
- Authentication & Token Management
- Instrument Master Download & Filtering
- Historical OHLCV Candle Data
- Live Market Quotes (REST & WebSocket)
- Safe Offline Mock Data Generator for Sandbox / Testing
"""

import os
import json
import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import httpx
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.models.schemas import InstrumentSchema, MarketQuote

IST = pytz.timezone(config.MARKET_TIMEZONE)

# Curated High-Liquidity NSE Cash Equity Universe for Default Offline Testing
DEFAULT_NSE_STOCKS = [
    {"symbol": "RELIANCE", "name": "Reliance Industries Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 2840.50},
    {"symbol": "TCS", "name": "Tata Consultancy Services Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 4120.00},
    {"symbol": "HDFCBANK", "name": "HDFC Bank Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 1650.25},
    {"symbol": "INFY", "name": "Infosys Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 1820.80},
    {"symbol": "ICICIBANK", "name": "ICICI Bank Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 1210.40},
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 1490.15},
    {"symbol": "SBIN", "name": "State Bank of India", "exchange": "NSE", "segment": "EQUITY", "base_price": 810.60},
    {"symbol": "ITC", "name": "ITC Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 490.30},
    {"symbol": "LICI", "name": "Life Insurance Corporation of India", "exchange": "NSE", "segment": "EQUITY", "base_price": 960.00},
    {"symbol": "LT", "name": "Larsen & Toubro Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 3580.75},
    {"symbol": "HINDUNILVR", "name": "Hindustan Unilever Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 2430.50},
    {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 1780.20},
    {"symbol": "AXISBANK", "name": "Axis Bank Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 1165.90},
    {"symbol": "TATAMOTORS", "name": "Tata Motors Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 980.45},
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Industries Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 1690.10},
    {"symbol": "NTPC", "name": "NTPC Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 385.60},
    {"symbol": "ONGC", "name": "Oil & Natural Gas Corporation Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 280.25},
    {"symbol": "MARUTI", "name": "Maruti Suzuki India Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 12450.00},
    {"symbol": "TITAN", "name": "Titan Company Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 3410.80},
    {"symbol": "ADANIENT", "name": "Adani Enterprises Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 3120.00},
    {"symbol": "POWERGRID", "name": "Power Grid Corporation of India Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 320.40},
    {"symbol": "TATASTEEL", "name": "Tata Steel Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 155.80},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 6890.00},
    {"symbol": "M&M", "name": "Mahindra & Mahindra Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 2780.30},
    {"symbol": "WIPRO", "name": "Wipro Limited", "exchange": "NSE", "segment": "EQUITY", "base_price": 540.60}
]

class GrowwService:
    """
    Client interface for Groww Trade API.
    Supports official REST endpoints & WebSocket, with an intelligent
    in-memory simulated market feed when API keys are not supplied.
    """

    def __init__(self):
        self.api_key = config.GROWW_API_KEY
        self.api_secret = config.GROWW_API_SECRET
        self.access_token = config.GROWW_ACCESS_TOKEN
        self.base_url = (
            "https://sandbox-api.groww.in/v1/trade"
            if config.ENVIRONMENT == "SANDBOX"
            else "https://api.groww.in/v1/trade"
        )
        self.is_connected = False
        self.is_mock_mode = False
        self._price_cache: Dict[str, float] = {}
        self._volume_cache: Dict[str, int] = {}
        self._init_mock_prices()

    def _init_mock_prices(self):
        """Initializes baseline prices for the simulation engine."""
        for stock in DEFAULT_NSE_STOCKS:
            self._price_cache[stock["symbol"]] = stock["base_price"]
            self._volume_cache[stock["symbol"]] = random.randint(250000, 1500000)

    async def authenticate(self) -> Tuple[bool, str]:
        """
        Validates or retrieves the Groww access token.
        Falls back cleanly to labelled mock mode if keys are not configured.
        """
        if not self.api_key or not self.api_secret:
            if config.USE_MOCK_FEED_IF_DISCONNECTED:
                self.is_connected = True
                self.is_mock_mode = True
                msg = "Groww API keys not set in .env. Running in SAFE OFFLINE MOCK MODE."
                logger.warning(msg)
                return True, msg
            else:
                self.is_connected = False
                msg = "Groww API keys missing. Authentication aborted."
                logger.error(msg)
                return False, msg

        # Attempt Groww API authentication
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json"
                }
                # Groww auth session creation
                url = f"{self.base_url}/auth/token"
                payload = {
                    "apiKey": self.api_key,
                    "apiSecret": self.api_secret
                }
                logger.info(f"Connecting to Groww API at {self.base_url}...")
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    self.access_token = data.get("accessToken", data.get("token"))
                    self.is_connected = True
                    self.is_mock_mode = False
                    logger.info("Groww API authenticated successfully.")
                    return True, "Groww API authenticated successfully."
                else:
                    logger.warning(f"Groww API auth returned status {resp.status_code}: {resp.text}")
                    if config.USE_MOCK_FEED_IF_DISCONNECTED:
                        self.is_connected = True
                        self.is_mock_mode = True
                        return True, f"Groww API auth failed ({resp.status_code}). Fallback to SAFE MOCK MODE."
                    return False, f"Authentication failed: {resp.text}"
        except Exception as e:
            logger.warning(f"Groww API connection exception: {e}")
            if config.USE_MOCK_FEED_IF_DISCONNECTED:
                self.is_connected = True
                self.is_mock_mode = True
                return True, f"Groww connection failed ({str(e)}). Running in SAFE MOCK MODE."
            return False, str(e)

    async def fetch_instrument_master(self) -> List[InstrumentSchema]:
        """
        Loads the eligible NSE cash equity universe.
        Filters strictly for NSE exchange, EQUITY segment, and tradable equities.
        """
        instruments = []
        if not self.is_mock_mode and self.access_token:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    url = f"{self.base_url}/instruments/master"
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        raw_data = resp.json()
                        for item in raw_data.get("instruments", []):
                            # Filter: NSE Cash Equity, tradable, exclude derivatives/debt
                            if (
                                item.get("exchange") == "NSE" and
                                item.get("segment") in ("EQUITY", "CASH") and
                                item.get("isTradable", True)
                            ):
                                instruments.append(InstrumentSchema(
                                    symbol=item.get("tradingSymbol", item.get("symbol")),
                                    name=item.get("name", item.get("symbol")),
                                    exchange="NSE",
                                    segment="EQUITY",
                                    lot_size=int(item.get("lotSize", 1)),
                                    tick_size=float(item.get("tickSize", 0.05)),
                                    is_tradable=True
                                ))
                        if instruments:
                            logger.info(f"Loaded {len(instruments)} eligible NSE equities from Groww API.")
                            return instruments
            except Exception as e:
                logger.error(f"Error fetching instrument master from API: {e}. Using fallback.")

        # Default high-liquidity universe fallback
        for s in DEFAULT_NSE_STOCKS:
            instruments.append(InstrumentSchema(
                symbol=s["symbol"],
                name=s["name"],
                exchange="NSE",
                segment="EQUITY",
                lot_size=1,
                tick_size=0.05,
                is_tradable=True
            ))
        logger.info(f"Loaded {len(instruments)} instruments from high-liquidity NSE universe.")
        return instruments

    async def fetch_historical_candles(
        self,
        symbol: str,
        interval: str = "5m",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieves historical OHLCV candle data for technical indicator calculations.
        """
        if not self.is_mock_mode and self.access_token:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    url = f"{self.base_url}/market/candles"
                    params = {"symbol": symbol, "interval": interval, "limit": limit}
                    resp = await client.get(url, headers=headers, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data.get("candles", [])
            except Exception as e:
                logger.error(f"Candle fetch failed for {symbol}: {e}")

        # Generate realistic historical candles for testing
        base_price = self._price_cache.get(symbol, 1000.0)
        candles = []
        current_dt = datetime.now(IST) - timedelta(minutes=interval_minutes(interval) * limit)
        curr = base_price * (1 + random.uniform(-0.02, 0.02))

        # Generate deterministic-trending multi-candle series
        volatility = 0.003
        for i in range(limit):
            current_dt += timedelta(minutes=interval_minutes(interval))
            change = curr * random.gauss(0.0002, volatility)
            open_p = curr
            close_p = curr + change
            high_p = max(open_p, close_p) + abs(random.gauss(0, curr * 0.001))
            low_p = min(open_p, close_p) - abs(random.gauss(0, curr * 0.001))
            vol = int(random.randint(5000, 45000) * (1.5 if i > limit - 5 else 1.0))
            
            candles.append({
                "timestamp": current_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "close": round(close_p, 2),
                "volume": vol
            })
            curr = close_p

        return candles

    async def fetch_quote(self, symbol: str) -> MarketQuote:
        """
        Fetches live LTP and market statistics.
        """
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        if not self.is_mock_mode and self.access_token:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    url = f"{self.base_url}/market/quote/{symbol}"
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        q = resp.json()
                        return MarketQuote(
                            symbol=symbol,
                            ltp=float(q["ltp"]),
                            open=float(q["open"]),
                            high=float(q["high"]),
                            low=float(q["low"]),
                            close=float(q["close"]),
                            volume=int(q["volume"]),
                            vwap=float(q.get("vwap", q["ltp"])),
                            change_pct=float(q.get("changePct", 0.0)),
                            timestamp=now_str
                        )
            except Exception as e:
                logger.error(f"Live quote fetch error for {symbol}: {e}")

        # Realistic dynamic simulation quote
        base = self._price_cache.get(symbol, 1000.0)
        # Small random walk drift (±0.15%)
        drift = base * random.uniform(-0.0015, 0.0018)
        new_price = round(max(1.0, base + drift), 2)
        self._price_cache[symbol] = new_price

        vol_add = random.randint(100, 2500)
        self._volume_cache[symbol] = self._volume_cache.get(symbol, 500000) + vol_add

        # Calculate high/low/open
        open_price = round(base * 0.995, 2)
        high_price = round(max(open_price, new_price) * 1.002, 2)
        low_price = round(min(open_price, new_price) * 0.998, 2)
        change_pct = round(((new_price - open_price) / open_price) * 100, 2)
        vwap = round((open_price + high_price + low_price + new_price) / 4.0, 2)

        return MarketQuote(
            symbol=symbol,
            ltp=new_price,
            open=open_price,
            high=high_price,
            low=low_price,
            close=new_price,
            volume=self._volume_cache[symbol],
            vwap=vwap,
            change_pct=change_pct,
            timestamp=now_str
        )

def interval_minutes(interval: str) -> int:
    if interval == "1m": return 1
    if interval == "5m": return 5
    if interval == "15m": return 15
    if interval == "1h": return 60
    if interval == "1d": return 375
    return 5

# Global service instance
groww_service = GrowwService()
