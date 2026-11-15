"""
Groww AI Trading Agent - Historical Quantitative Backtesting Engine
Provides:
- High-fidelity intraday simulation over historical candles
- Realistic execution modeling with slippage (0.05%)
- Full Indian statutory charges (Brokerage, STT, NSE txn, SEBI fee, Stamp duty, GST)
- Walk-forward and out-of-sample split validation
- Comprehensive risk metrics: Win Rate, Profit Factor, Max Drawdown, Sharpe Ratio
"""

import math
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from backend.core.config import config
from backend.models.schemas import IndicatorValues
from backend.services.strategy_engine import strategy_engine
from backend.agents.risk_manager import risk_manager_agent

class BacktestingEngine:
    def __init__(self, initial_capital: float = None):
        self.initial_capital = initial_capital or config.INITIAL_CAPITAL

    def run_backtest(
        self,
        symbol: str,
        candles: List[Dict[str, Any]],
        split_ratio: float = 0.7
    ) -> Dict[str, Any]:
        """
        Runs walk-forward backtest splitting into In-Sample (train/calibration)
        and Out-Of-Sample (test/validation) windows.
        """
        if not candles or len(candles) < 40:
            return {"error": "Insufficient candle data for backtesting (minimum 40 required)."}

        split_idx = int(len(candles) * split_ratio)
        in_sample_candles = candles[:split_idx]
        out_sample_candles = candles[split_idx:]

        in_sample_results = self._simulate_strategy(symbol, in_sample_candles)
        out_sample_results = self._simulate_strategy(symbol, out_sample_candles)

        total_results = self._simulate_strategy(symbol, candles)

        return {
            "symbol": symbol,
            "total_candles": len(candles),
            "in_sample_candles": len(in_sample_candles),
            "out_of_sample_candles": len(out_sample_candles),
            "overall_performance": total_results,
            "in_sample_performance": in_sample_results,
            "out_of_sample_validation": out_sample_results
        }

    def _simulate_strategy(self, symbol: str, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        capital = self.initial_capital
        peak_capital = capital
        max_drawdown = 0.0
        trades = []
        open_position = None

        # Rolling window for indicator calculations
        window_size = 25
        for i in range(window_size, len(candles)):
            window = candles[max(0, i - 100) : i + 1]
            current_candle = candles[i]
            current_price = current_candle["close"]

            # 1. Manage Open Position if exists
            if open_position:
                entry_p = open_position["entry_price"]
                sl = open_position["stop_loss"]
                target = open_position["target"]
                qty = open_position["quantity"]

                exit_price = None
                exit_reason = None

                # Check SL hit
                if current_candle["low"] <= sl:
                    exit_price = sl
                    exit_reason = "STOP_LOSS_HIT"
                # Check Target hit
                elif current_candle["high"] >= target:
                    exit_price = target
                    exit_reason = "TARGET_HIT"
                # End of day / session exit
                elif i == len(candles) - 1:
                    exit_price = current_price
                    exit_reason = "SESSION_CLOSE"

                if exit_price:
                    # Deduct slippage on exit
                    exit_executed = round(exit_price * (1.0 - config.SLIPPAGE_PCT), 2)
                    gross_pnl = round((exit_executed - entry_p) * qty, 2)
                    charges = risk_manager_agent.calculate_statutory_charges(qty, entry_p, exit_executed)
                    net_pnl = round(gross_pnl - charges["total_charges"], 2)

                    capital += net_pnl
                    if capital > peak_capital:
                        peak_capital = capital
                    dd = peak_capital - capital
                    if dd > max_drawdown:
                        max_drawdown = dd

                    trades.append({
                        "entry_price": entry_p,
                        "exit_price": exit_executed,
                        "quantity": qty,
                        "gross_pnl": gross_pnl,
                        "charges": charges["total_charges"],
                        "net_pnl": net_pnl,
                        "exit_reason": exit_reason
                    })
                    open_position = None
                    continue

            # 2. Look for New Entry Signal if no open position
            if not open_position:
                ind = strategy_engine.calculate_indicators(window)
                if not ind:
                    continue

                eval_result = strategy_engine.evaluate_strategy_confirmation(
                    current_price=current_price,
                    ind=ind,
                    market_regime_bullish=True
                )

                if eval_result["is_confirmed"]:
                    per_share_risk = current_price - eval_result["stop_loss"]
                    if per_share_risk <= 0:
                        continue

                    # Sizing
                    desired_qty = math.floor(config.RISK_PER_TRADE / per_share_risk)
                    max_qty = math.floor((capital * config.MAX_CAPITAL_ALLOCATION_PCT) / current_price)
                    qty = min(desired_qty, max_qty)

                    if qty >= 1:
                        # Entry slippage
                        entry_executed = round(current_price * (1.0 + config.SLIPPAGE_PCT), 2)
                        open_position = {
                            "entry_price": entry_executed,
                            "stop_loss": eval_result["stop_loss"],
                            "target": eval_result["target"],
                            "quantity": qty
                        }

        # Calculate metrics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t["net_pnl"] > 0)
        losing_trades = sum(1 for t in trades if t["net_pnl"] <= 0)
        win_rate = round((winning_trades / total_trades * 100), 2) if total_trades > 0 else 0.0

        net_profit = round(capital - self.initial_capital, 2)
        total_charges = round(sum(t["charges"] for t in trades), 2)
        gross_profit = round(sum(t["gross_pnl"] for t in trades), 2)

        gross_wins = sum(t["gross_pnl"] for t in trades if t["gross_pnl"] > 0)
        gross_losses = abs(sum(t["gross_pnl"] for t in trades if t["gross_pnl"] < 0))
        profit_factor = round(gross_wins / max(0.01, gross_losses), 2) if gross_losses > 0 else 1.0

        # Sharpe ratio estimate
        returns = [t["net_pnl"] / self.initial_capital for t in trades]
        sharpe = round(float(np.mean(returns) / (np.std(returns) + 1e-6) * np.sqrt(252)), 2) if len(returns) > 2 else 0.0

        return {
            "initial_capital": self.initial_capital,
            "final_capital": round(capital, 2),
            "net_profit_inr": net_profit,
            "gross_profit_inr": gross_profit,
            "total_statutory_charges": total_charges,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate_pct": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_inr": round(max_drawdown, 2),
            "max_drawdown_pct": round((max_drawdown / self.initial_capital) * 100, 2),
            "sharpe_ratio": sharpe,
            "trades_sample": trades[:10]
        }

backtesting_engine = BacktestingEngine()
