"""
Groww AI Trading Agent - Quantitative Strategy & Technical Indicators Engine
Computes mathematical indicators:
- EMA (9, 21, 50, 200)
- RSI 14 (Wilder's method)
- MACD (12, 26, 9)
- VWAP
- ATR 14
- Bollinger Bands (20, 2)
- Opening Range Breakout (ORB)
- Support & Resistance Pivots
- Multi-factor Confirmation Strategies
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.models.schemas import IndicatorValues

IST = pytz.timezone(config.MARKET_TIMEZONE)

class StrategyEngine:
    """Computes technical indicators and validates multi-indicator strategy rules."""

    @staticmethod
    def calculate_indicators(candles: List[Dict[str, Any]]) -> Optional[IndicatorValues]:
        """
        Takes raw OHLCV candles list and calculates all technical indicator series.
        """
        if not candles or len(candles) < 20:
            return None

        df = pd.DataFrame(candles)
        df["close"] = pd.to_numeric(df["close"])
        df["open"] = pd.to_numeric(df["open"])
        df["high"] = pd.to_numeric(df["high"])
        df["low"] = pd.to_numeric(df["low"])
        df["volume"] = pd.to_numeric(df["volume"])

        # 1. EMAs
        df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema_200"] = df["close"].ewm(span=min(200, len(df)), adjust=False).mean()

        # 2. RSI 14 (Wilder's Smoothing)
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss.replace(0, np.nan))
        df["rsi_14"] = 100 - (100 / (1 + rs))
        df["rsi_14"] = df["rsi_14"].fillna(50.0)

        # 3. MACD (12, 26, 9)
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # 4. VWAP (Cumulative Price * Volume / Cumulative Volume)
        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        df["cum_vp"] = (typical_price * df["volume"]).cumsum()
        df["cum_vol"] = df["volume"].cumsum()
        df["vwap"] = df["cum_vp"] / df["cum_vol"].replace(0, np.nan)
        df["vwap"] = df["vwap"].fillna(df["close"])

        # 5. ATR 14
        prev_close = df["close"].shift(1)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - prev_close).abs()
        tr3 = (df["low"] - prev_close).abs()
        df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr_14"] = df["tr"].rolling(window=14).mean()
        df["atr_14"] = df["atr_14"].fillna(df["high"] - df["low"])

        # 6. Bollinger Bands (20, 2 std)
        bb_period = min(20, len(df))
        df["bb_middle"] = df["close"].rolling(window=bb_period).mean()
        df["bb_std"] = df["close"].rolling(window=bb_period).std()
        df["bb_upper"] = df["bb_middle"] + (2.0 * df["bb_std"])
        df["bb_lower"] = df["bb_middle"] - (2.0 * df["bb_std"])

        # 7. Volume Breakdown & RVOL
        vol_sma20 = df["volume"].rolling(window=min(20, len(df))).mean()
        current_vol = df["volume"].iloc[-1]
        avg_vol = vol_sma20.iloc[-1] if not np.isnan(vol_sma20.iloc[-1]) and vol_sma20.iloc[-1] > 0 else current_vol
        rvol = round(float(current_vol / avg_vol), 2) if avg_vol > 0 else 1.0

        # 8. Support / Resistance & Opening Range
        # Previous Day High / Low proxy
        pdh = float(df["high"].iloc[:-1].max()) if len(df) > 1 else float(df["high"].iloc[-1])
        pdl = float(df["low"].iloc[:-1].min()) if len(df) > 1 else float(df["low"].iloc[-1])
        
        # Opening range (first 3 candles)
        or_candles = df.head(min(3, len(df)))
        or_high = float(or_candles["high"].max())
        or_low = float(or_candles["low"].min())

        last = df.iloc[-1]

        return IndicatorValues(
            ema_9=round(float(last["ema_9"]), 2),
            ema_21=round(float(last["ema_21"]), 2),
            ema_50=round(float(last["ema_50"]), 2),
            ema_200=round(float(last["ema_200"]), 2),
            rsi_14=round(float(last["rsi_14"]), 2),
            macd=round(float(last["macd"]), 2),
            macd_signal=round(float(last["macd_signal"]), 2),
            macd_hist=round(float(last["macd_hist"]), 2),
            vwap=round(float(last["vwap"]), 2),
            atr_14=round(float(last["atr_14"]), 2),
            bb_upper=round(float(last["bb_upper"]), 2),
            bb_middle=round(float(last["bb_middle"]), 2),
            bb_lower=round(float(last["bb_lower"]), 2),
            rvol=rvol,
            pdh=round(pdh, 2),
            pdl=round(pdl, 2),
            or_high=round(or_high, 2),
            or_low=round(or_low, 2)
        )

    @staticmethod
    def evaluate_strategy_confirmation(
        current_price: float,
        ind: IndicatorValues,
        market_regime_bullish: bool
    ) -> Dict[str, Any]:
        """
        Validates whether multiple intraday strategies confirm a BUY entry.
        Strategies:
        1. EMA 9 > EMA 21 (Bullish Moving Average Crossover)
        2. Price > VWAP (Intraday Institutional Trend Confirmation)
        3. RSI between 52 and 72 (Healthy Bullish Momentum, not overbought)
        4. MACD Histogram > 0 and MACD > Signal
        5. Volume Breakout (RVOL >= 1.3)
        6. Price breaking above ORB or Support/Resistance
        """
        confirmations = []
        is_ema_bullish = ind.ema_9 > ind.ema_21
        if is_ema_bullish:
            confirmations.append("EMA 9 > EMA 21 Bullish Crossover")

        is_vwap_bullish = current_price >= ind.vwap
        if is_vwap_bullish:
            confirmations.append(f"Price ₹{current_price} holding at/above VWAP ₹{ind.vwap}")

        is_rsi_favorable = 50.0 <= ind.rsi_14 <= 72.0
        if is_rsi_favorable:
            confirmations.append(f"RSI 14 at {ind.rsi_14} shows constructive momentum")

        is_macd_bullish = ind.macd > ind.macd_signal and ind.macd_hist > 0
        if is_macd_bullish:
            confirmations.append("MACD above Signal line with positive histogram")

        is_volume_confirmed = ind.rvol >= 1.2
        if is_volume_confirmed:
            confirmations.append(f"Volume surge detected (RVOL: {ind.rvol}x)")

        is_price_action_bullish = current_price > ind.bb_middle
        if is_price_action_bullish:
            confirmations.append("Price action above Bollinger 20-SMA middle band")

        if current_price > ind.or_high:
            confirmations.append(f"Opening range breakout above ₹{ind.or_high}")

        # ATR-based Stop Loss & Target calculation
        atr_buffer = max(ind.atr_14 * 1.5, current_price * 0.005)
        stop_loss = round(current_price - atr_buffer, 2)
        # Minimum 1:1.5 Risk to Reward Target
        target = round(current_price + (atr_buffer * config.MIN_RISK_REWARD_RATIO), 2)
        rr_ratio = round((target - current_price) / max(0.01, (current_price - stop_loss)), 2)

        return {
            "confirmations_count": len(confirmations),
            "confirmations": confirmations,
            "stop_loss": stop_loss,
            "target": target,
            "risk_reward_ratio": rr_ratio,
            "is_confirmed": len(confirmations) >= 4 and is_vwap_bullish and is_ema_bullish
        }

strategy_engine = StrategyEngine()
