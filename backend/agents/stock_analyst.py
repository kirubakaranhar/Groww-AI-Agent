"""
Groww AI Trading Agent - Stock Analyst Agent
Performs in-depth technical analysis for shortlisted candidate stocks.
Calculates all required indicators and compiles an explainable technical report.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.database.db import db
from backend.models.schemas import TechnicalAnalysisReport, AgentStateEnum, AgentStatus
from backend.services.groww_service import groww_service
from backend.services.strategy_engine import strategy_engine
from backend.services.market_data import market_data_hub

IST = pytz.timezone(config.MARKET_TIMEZONE)

class StockAnalystAgent:
    def __init__(self):
        self.name = "StockAnalystAgent"
        self.state = AgentStateEnum.IDLE
        self.last_analyzed_symbol = ""
        self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    def get_status(self) -> AgentStatus:
        return AgentStatus(
            name=self.name,
            state=self.state,
            last_heartbeat=self.last_update,
            message=f"Last analyzed: {self.last_analyzed_symbol or 'None'}"
        )

    async def analyze_stock(self, symbol: str, regime_score: float = 8.0) -> Optional[TechnicalAnalysisReport]:
        """
        Gathers historical candles, computes indicators, and calculates component scores.
        """
        self.state = AgentStateEnum.ANALYZING
        self.last_analyzed_symbol = symbol
        try:
            # 1. Fetch candles
            candles = await groww_service.fetch_historical_candles(symbol, interval="5m", limit=100)
            if not candles or len(candles) < 25:
                self.state = AgentStateEnum.IDLE
                return None

            # 2. Compute technical indicators
            ind = strategy_engine.calculate_indicators(candles)
            if not ind:
                self.state = AgentStateEnum.IDLE
                return None

            quote = market_data_hub.get_quote(symbol)
            current_price = quote.ltp if quote else candles[-1]["close"]

            # 3. Factor Scoring Engine (Transparent breakdown out of 100)
            # A. Trend Strength (Max 25 points)
            trend_score = 0.0
            if ind.ema_9 > ind.ema_21:
                trend_score += 10.0
            if ind.ema_21 > ind.ema_50:
                trend_score += 8.0
            if current_price > ind.ema_200:
                trend_score += 7.0

            # B. Momentum (Max 20 points)
            momentum_score = 0.0
            if 50.0 <= ind.rsi_14 <= 70.0:
                momentum_score += 10.0
            elif 45.0 <= ind.rsi_14 < 50.0:
                momentum_score += 5.0
            if ind.macd > ind.macd_signal:
                momentum_score += 5.0
            if ind.macd_hist > 0:
                momentum_score += 5.0

            # C. Volume Confirmation (Max 20 points)
            volume_score = 0.0
            if ind.rvol >= 2.0:
                volume_score += 20.0
            elif ind.rvol >= 1.5:
                volume_score += 15.0
            elif ind.rvol >= 1.2:
                volume_score += 10.0
            else:
                volume_score += 5.0

            # D. Price Action (Max 20 points)
            price_action_score = 0.0
            if current_price > ind.vwap:
                price_action_score += 8.0
            if current_price > ind.bb_middle:
                price_action_score += 4.0
            if current_price > ind.pdh:
                price_action_score += 4.0  # Above yesterday's high
            if current_price > ind.or_high:
                price_action_score += 4.0  # Above opening range

            # E. Market Regime (Max 10 points)
            regime_points = min(10.0, max(0.0, regime_score))

            # F. Data Quality (Max 5 points)
            data_quality_score = 5.0 if market_data_hub.is_data_fresh(symbol) else 2.5

            total_score = round(
                trend_score + momentum_score + volume_score + price_action_score + regime_points + data_quality_score,
                1
            )

            # Key findings log
            findings = []
            if current_price > ind.vwap:
                findings.append(f"Price ₹{current_price} holding comfortably above VWAP ₹{ind.vwap}")
            if ind.ema_9 > ind.ema_21:
                findings.append("Bullish short-term EMA 9/21 alignment")
            if ind.rvol >= 1.3:
                findings.append(f"Strong relative volume: {ind.rvol}x 20-period average")
            if ind.rsi_14 > 55:
                findings.append(f"RSI 14 at {ind.rsi_14} confirms upward momentum")

            report = TechnicalAnalysisReport(
                symbol=symbol,
                indicators=ind,
                trend_score=trend_score,
                momentum_score=momentum_score,
                volume_score=volume_score,
                price_action_score=price_action_score,
                regime_score=regime_points,
                data_quality_score=data_quality_score,
                total_score=total_score,
                key_findings=findings,
                support_level=ind.pdl,
                resistance_level=ind.pdh,
                timestamp=datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
            )

            # Save in database
            conn = db.get_connection()
            conn.execute("""
            INSERT INTO stock_analysis (
                symbol, timestamp, score, trend_score, momentum_score,
                volume_score, price_action_score, regime_score, data_quality_score, analysis_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                symbol, report.timestamp, total_score, trend_score, momentum_score,
                volume_score, price_action_score, regime_points, data_quality_score,
                report.model_dump_json()
            ))
            conn.commit()
            conn.close()

            self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
            self.state = AgentStateEnum.IDLE
            return report

        except Exception as e:
            self.state = AgentStateEnum.ERROR
            logger.error(f"StockAnalystAgent failed for {symbol}: {e}")
            db.log_agent_event(self.name, "ERROR", f"Stock analysis error for {symbol}: {str(e)}")
            return None

stock_analyst_agent = StockAnalystAgent()
