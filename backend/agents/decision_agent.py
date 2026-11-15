"""
Groww AI Trading Agent - Decision Agent
Evaluates analyzed candidate stocks using an explainable multi-factor scoring engine.
Produces transparent decisions: BUY, SELL, HOLD, NO_TRADE.
Enforces the rule that AI scores do NOT predict prices with certainty.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.database.db import db
from backend.models.schemas import (
    TechnicalAnalysisReport, DecisionSignal, DecisionTypeEnum,
    AgentStateEnum, AgentStatus
)
from backend.services.strategy_engine import strategy_engine
from backend.services.market_data import market_data_hub

IST = pytz.timezone(config.MARKET_TIMEZONE)

class DecisionAgent:
    def __init__(self):
        self.name = "DecisionAgent"
        self.state = AgentStateEnum.IDLE
        self.last_decision: Optional[DecisionSignal] = None
        self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    def get_status(self) -> AgentStatus:
        msg = f"Last Decision: {self.last_decision.decision.value if self.last_decision else 'None'}"
        return AgentStatus(
            name=self.name,
            state=self.state,
            last_heartbeat=self.last_update,
            message=msg
        )

    def evaluate_candidate(
        self,
        analysis: TechnicalAnalysisReport,
        market_regime_suitable: bool
    ) -> DecisionSignal:
        """
        Synthesizes technical analysis and regime to reach a rule-based decision.
        """
        self.state = AgentStateEnum.DECIDING
        symbol = analysis.symbol
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        quote = market_data_hub.get_quote(symbol)
        current_price = quote.ltp if quote else analysis.indicators.vwap

        # Evaluate strategy confirmations
        strat = strategy_engine.evaluate_strategy_confirmation(
            current_price=current_price,
            ind=analysis.indicators,
            market_regime_bullish=market_regime_suitable
        )

        score_breakdown = {
            "trend_strength": analysis.trend_score,
            "momentum": analysis.momentum_score,
            "volume": analysis.volume_score,
            "price_action": analysis.price_action_score,
            "market_regime": analysis.regime_score,
            "data_quality": analysis.data_quality_score,
            "total_score": analysis.total_score
        }

        reasons = []
        decision = DecisionTypeEnum.NO_TRADE

        # Check macro suitability first
        if not market_regime_suitable:
            reasons.append("Broad market regime is unsuitable for intraday long entries.")
            explanation = (
                f"{symbol} scored {analysis.total_score}/100, but general market conditions "
                f"are unfavorable for fresh long positions."
            )
        elif analysis.total_score < config.DECISION_MIN_SCORE_THRESHOLD:
            reasons.append(
                f"Total composite score {analysis.total_score} is below configured threshold {config.DECISION_MIN_SCORE_THRESHOLD}."
            )
            explanation = (
                f"{symbol} did not reach the minimum threshold of {config.DECISION_MIN_SCORE_THRESHOLD} "
                f"(scored {analysis.total_score}). Lacks sufficient quantitative confirmation."
            )
        elif not strat["is_confirmed"]:
            reasons.append("Insufficient strategy confirmations (< 4 criteria met).")
            explanation = (
                f"{symbol} reached score {analysis.total_score}, but failed strict multi-strategy alignment "
                f"(Confirmed: {', '.join(strat['confirmations'])})."
            )
        else:
            # All conditions met for BUY candidate
            decision = DecisionTypeEnum.BUY
            reasons.extend(strat["confirmations"])
            explanation = (
                f"BUY signal generated for {symbol} with strong technical score of {analysis.total_score}/100. "
                f"Confirmations: {'; '.join(strat['confirmations'])}. "
                f"Note: This score indicates strict rule alignment, not a guaranteed price prediction."
            )

        signal = DecisionSignal(
            symbol=symbol,
            decision=decision,
            total_score=analysis.total_score,
            score_breakdown=score_breakdown,
            entry_reference_price=current_price,
            suggested_stop_loss=strat["stop_loss"],
            suggested_target=strat["target"],
            risk_reward_ratio=strat["risk_reward_ratio"],
            strategy_name="Multi-Factor Intraday Trend & VWAP Breakout",
            reasons=reasons,
            timestamp=now_str,
            explanation=explanation
        )

        # Record signal in database
        try:
            conn = db.get_connection()
            conn.execute("""
            INSERT INTO trading_signals (
                symbol, signal_type, entry_price, stop_loss, target, score, status, explanation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                symbol, decision.value, current_price, strat["stop_loss"],
                strat["target"], analysis.total_score, "GENERATED", explanation, now_str
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to record trading signal in DB: {e}")

        self.last_decision = signal
        self.last_update = now_str
        self.state = AgentStateEnum.IDLE

        return signal

decision_agent = DecisionAgent()
