"""
Groww AI Trading Agent - Historical Quantitative Backtesting & Strategy Tuning Engine
Provides:
- High-fidelity intraday simulation over historical candles
- Realistic execution modeling with slippage (0.05%) & trailing stop-loss
- Full Indian statutory charges (Brokerage, STT, NSE txn, SEBI fee, Stamp duty, GST)
- Walk-forward In-Sample / Out-of-Sample split validation
- Multi-Stock Universe Backtesting
- Walk-Forward Grid-Search Strategy Parameter Optimizer (anti-overfitting OOS validation)
- Comprehensive risk metrics: Win Rate, Profit Factor, Max Drawdown, Sharpe Ratio, Equity Curve
"""

import math
from itertools import product
from typing import Dict, Any, List, Optional
import numpy as np

from backend.core.config import config
from backend.models.schemas import IndicatorValues
from backend.services.strategy_engine import strategy_engine
from backend.agents.risk_manager import risk_manager_agent


class BacktestingEngine:
    def __init__(self, initial_capital: float = None):
        self.initial_capital = initial_capital or config.INITIAL_CAPITAL

    def _precompute_indicators(self, candles: List[Dict[str, Any]], window_size: int = 25) -> List[Optional[IndicatorValues]]:
        """Pre-calculates rolling indicators once so grid-search sweeps run rapidly."""
        ind_series: List[Optional[IndicatorValues]] = [None] * len(candles)
        for i in range(window_size, len(candles)):
            window = candles[max(0, i - 100): i + 1]
            ind_series[i] = strategy_engine.calculate_indicators(window)
        return ind_series

    def run_backtest(
        self,
        symbol: str,
        candles: List[Dict[str, Any]],
        split_ratio: float = 0.7,
        params: Optional[Dict[str, Any]] = None
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

        in_sample_results = self._simulate_strategy(symbol, in_sample_candles, params=params)
        out_sample_results = self._simulate_strategy(symbol, out_sample_candles, params=params)
        total_results = self._simulate_strategy(symbol, candles, params=params)

        active_params = {
            "min_confirmations": int((params or {}).get("min_confirmations", config.STRATEGY_MIN_CONFIRMATIONS)),
            "atr_sl_multiplier": float((params or {}).get("atr_sl_multiplier", config.STRATEGY_ATR_SL_MULTIPLIER)),
            "rr_ratio": float((params or {}).get("rr_ratio", config.MIN_RISK_REWARD_RATIO)),
            "min_rvol": float((params or {}).get("min_rvol", config.STRATEGY_MIN_RVOL)),
            "rsi_min": float((params or {}).get("rsi_min", config.STRATEGY_RSI_MIN)),
            "rsi_max": float((params or {}).get("rsi_max", config.STRATEGY_RSI_MAX)),
        }

        return {
            "symbol": symbol,
            "parameters_used": active_params,
            "total_candles": len(candles),
            "in_sample_candles": len(in_sample_candles),
            "out_of_sample_candles": len(out_sample_candles),
            "overall_performance": total_results,
            "in_sample_performance": in_sample_results,
            "out_of_sample_validation": out_sample_results
        }

    def run_universe_backtest(
        self,
        symbols_candles: Dict[str, List[Dict[str, Any]]],
        split_ratio: float = 0.7,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Runs walk-forward backtesting across multiple NSE stocks and aggregates results."""
        per_stock = {}
        total_trades = 0
        total_wins = 0
        total_losses = 0
        total_net_pnl = 0.0
        total_gross_pnl = 0.0
        total_charges = 0.0
        max_dd = 0.0

        for sym, candles in symbols_candles.items():
            if not candles or len(candles) < 40:
                continue
            res = self.run_backtest(sym, candles, split_ratio=split_ratio, params=params)
            if "error" in res:
                continue
            perf = res["overall_performance"]
            per_stock[sym] = {
                "total_trades": perf["total_trades"],
                "win_rate_pct": perf["win_rate_pct"],
                "net_profit_inr": perf["net_profit_inr"],
                "profit_factor": perf["profit_factor"],
                "max_drawdown_inr": perf["max_drawdown_inr"],
                "oos_trades": res["out_of_sample_validation"]["total_trades"],
                "oos_net_pnl": res["out_of_sample_validation"]["net_profit_inr"],
            }
            total_trades += perf["total_trades"]
            total_wins += perf["winning_trades"]
            total_losses += perf["losing_trades"]
            total_net_pnl += perf["net_profit_inr"]
            total_gross_pnl += perf["gross_profit_inr"]
            total_charges += perf["total_statutory_charges"]
            max_dd = max(max_dd, perf["max_drawdown_inr"])

        win_rate = round((total_wins / total_trades) * 100, 2) if total_trades > 0 else 0.0

        return {
            "stocks_tested": len(per_stock),
            "aggregate": {
                "total_trades": total_trades,
                "winning_trades": total_wins,
                "losing_trades": total_losses,
                "win_rate_pct": win_rate,
                "net_profit_inr": round(total_net_pnl, 2),
                "gross_profit_inr": round(total_gross_pnl, 2),
                "total_statutory_charges": round(total_charges, 2),
                "worst_stock_drawdown_inr": round(max_dd, 2),
            },
            "per_stock": per_stock
        }

    def optimize_strategy(
        self,
        symbols_candles: Dict[str, List[Dict[str, Any]]],
        split_ratio: float = 0.7
    ) -> Dict[str, Any]:
        """
        Walk-Forward Grid Search Parameter Optimizer:
        1. Pre-computes rolling technical indicators on In-Sample (70%) and Out-of-Sample (30%) windows.
        2. Evaluates parameter combinations strictly on In-Sample data.
        3. Validates top candidates on Out-of-Sample unseen candles to prevent overfitting.
        4. Recommends balanced parameters + suggested Decision Score threshold.
        """
        # Filter usable stocks with enough candles
        valid_stocks = {
            sym: candles for sym, candles in symbols_candles.items()
            if candles and len(candles) >= 60
        }
        if not valid_stocks:
            return {"error": "Insufficient historical candle data across universe (need >= 60 candles per stock)."}

        # Precompute indicators once for speed
        in_sample_data = {}
        out_sample_data = {}
        for sym, candles in valid_stocks.items():
            split_idx = int(len(candles) * split_ratio)
            is_candles = candles[:split_idx]
            oos_candles = candles[split_idx:]
            if len(is_candles) >= 35 and len(oos_candles) >= 30:
                in_sample_data[sym] = (is_candles, self._precompute_indicators(is_candles))
                out_sample_data[sym] = (oos_candles, self._precompute_indicators(oos_candles))

        if not in_sample_data:
            return {"error": "Not enough candles to construct In-Sample and Out-of-Sample splits."}

        # Parameter grid
        grid_min_conf = [3, 4, 5]
        grid_atr_mult = [1.2, 1.5, 2.0]
        grid_rr = [1.5, 2.0, 2.5]
        grid_rvol = [1.1, 1.2, 1.4]

        evaluated = []
        for min_conf, atr_mult, rr, min_rvol in product(grid_min_conf, grid_atr_mult, grid_rr, grid_rvol):
            params = {
                "min_confirmations": min_conf,
                "atr_sl_multiplier": atr_mult,
                "rr_ratio": rr,
                "min_rvol": min_rvol,
                "rsi_min": config.STRATEGY_RSI_MIN,
                "rsi_max": config.STRATEGY_RSI_MAX,
            }

            is_trades = 0
            is_wins = 0
            is_net_pnl = 0.0
            is_gross_wins = 0.0
            is_gross_losses = 0.0
            is_max_dd = 0.0

            for sym, (candles, ind_series) in in_sample_data.items():
                res = self._simulate_strategy(sym, candles, params=params, precomputed_indicators=ind_series)
                is_trades += res["total_trades"]
                is_wins += res["winning_trades"]
                is_net_pnl += res["net_profit_inr"]
                is_max_dd = max(is_max_dd, res["max_drawdown_inr"])
                for t in res["all_trades"]:
                    if t["gross_pnl"] > 0:
                        is_gross_wins += t["gross_pnl"]
                    elif t["gross_pnl"] < 0:
                        is_gross_losses += abs(t["gross_pnl"])

            is_win_rate = round((is_wins / is_trades) * 100, 2) if is_trades > 0 else 0.0
            is_pf = round(is_gross_wins / max(0.01, is_gross_losses), 2) if is_gross_losses > 0 else (
                round(min(9.99, is_gross_wins), 2) if is_gross_wins > 0 else 0.0
            )

            # Risk-adjusted objective score (penalizes 0 trades & excessive drawdown)
            if is_trades == 0:
                objective_score = -999.0
            else:
                trade_bonus = min(10.0, is_trades * 0.5)
                dd_penalty = is_max_dd * 0.4
                objective_score = round(is_net_pnl + (is_pf * 8.0) + (is_win_rate * 0.15) + trade_bonus - dd_penalty, 2)

            evaluated.append({
                "params": params,
                "in_sample": {
                    "total_trades": is_trades,
                    "winning_trades": is_wins,
                    "win_rate_pct": is_win_rate,
                    "net_profit_inr": round(is_net_pnl, 2),
                    "profit_factor": is_pf,
                    "max_drawdown_inr": round(is_max_dd, 2),
                },
                "objective_score": objective_score
            })

        # Sort by In-Sample objective score descending
        evaluated.sort(key=lambda x: x["objective_score"], reverse=True)
        top_candidates = evaluated[:5]

        # Validate Top 5 on unseen Out-of-Sample data
        for cand in top_candidates:
            oos_trades = 0
            oos_wins = 0
            oos_net_pnl = 0.0
            oos_gross_wins = 0.0
            oos_gross_losses = 0.0
            oos_max_dd = 0.0

            for sym, (candles, ind_series) in out_sample_data.items():
                res = self._simulate_strategy(sym, candles, params=cand["params"], precomputed_indicators=ind_series)
                oos_trades += res["total_trades"]
                oos_wins += res["winning_trades"]
                oos_net_pnl += res["net_profit_inr"]
                oos_max_dd = max(oos_max_dd, res["max_drawdown_inr"])
                for t in res["all_trades"]:
                    if t["gross_pnl"] > 0:
                        oos_gross_wins += t["gross_pnl"]
                    elif t["gross_pnl"] < 0:
                        oos_gross_losses += abs(t["gross_pnl"])

            oos_win_rate = round((oos_wins / oos_trades) * 100, 2) if oos_trades > 0 else 0.0
            oos_pf = round(oos_gross_wins / max(0.01, oos_gross_losses), 2) if oos_gross_losses > 0 else (
                round(min(9.99, oos_gross_wins), 2) if oos_gross_wins > 0 else 0.0
            )
            cand["out_of_sample"] = {
                "total_trades": oos_trades,
                "winning_trades": oos_wins,
                "win_rate_pct": oos_win_rate,
                "net_profit_inr": round(oos_net_pnl, 2),
                "profit_factor": oos_pf,
                "max_drawdown_inr": round(oos_max_dd, 2),
            }

        # Pick best candidate that also holds up Out-of-Sample
        best = max(
            top_candidates,
            key=lambda c: (c["out_of_sample"]["net_profit_inr"] * 0.6 + c["in_sample"]["net_profit_inr"] * 0.4)
            if c["in_sample"]["total_trades"] > 0 else -9999.0
        )

        # Recommend Decision Score Threshold matching confirmation strictness
        conf = best["params"]["min_confirmations"]
        suggested_score_threshold = 65.0 if conf == 3 else (70.0 if conf == 4 else 75.0)
        best["params"]["decision_min_score_threshold"] = suggested_score_threshold

        # Baseline (current config) comparison
        baseline_params = {
            "min_confirmations": config.STRATEGY_MIN_CONFIRMATIONS,
            "atr_sl_multiplier": config.STRATEGY_ATR_SL_MULTIPLIER,
            "rr_ratio": config.MIN_RISK_REWARD_RATIO,
            "min_rvol": config.STRATEGY_MIN_RVOL,
            "rsi_min": config.STRATEGY_RSI_MIN,
            "rsi_max": config.STRATEGY_RSI_MAX,
        }
        base_is_pnl = 0.0
        base_is_trades = 0
        base_oos_pnl = 0.0
        base_oos_trades = 0
        for sym, (candles, ind_series) in in_sample_data.items():
            r = self._simulate_strategy(sym, candles, params=baseline_params, precomputed_indicators=ind_series)
            base_is_pnl += r["net_profit_inr"]
            base_is_trades += r["total_trades"]
        for sym, (candles, ind_series) in out_sample_data.items():
            r = self._simulate_strategy(sym, candles, params=baseline_params, precomputed_indicators=ind_series)
            base_oos_pnl += r["net_profit_inr"]
            base_oos_trades += r["total_trades"]

        return {
            "stocks_evaluated": list(in_sample_data.keys()),
            "combinations_tested": len(evaluated),
            "baseline": {
                "params": baseline_params,
                "in_sample_trades": base_is_trades,
                "in_sample_net_pnl": round(base_is_pnl, 2),
                "out_of_sample_trades": base_oos_trades,
                "out_of_sample_net_pnl": round(base_oos_pnl, 2),
            },
            "recommended": best,
            "top_candidates": top_candidates,
            "note": (
                "Walk-forward grid search evaluates combinations on In-Sample (70%) candles and validates "
                "the top 5 on unseen Out-of-Sample (30%) candles. Past simulated performance does not guarantee future live returns."
            )
        }

    def _simulate_strategy(
        self,
        symbol: str,
        candles: List[Dict[str, Any]],
        params: Optional[Dict[str, Any]] = None,
        precomputed_indicators: Optional[List[Optional[IndicatorValues]]] = None
    ) -> Dict[str, Any]:
        capital = self.initial_capital
        peak_capital = capital
        max_drawdown = 0.0
        trades = []
        equity_curve = [{"trade_num": 0, "capital": round(capital, 2)}]
        open_position = None

        window_size = 25
        for i in range(window_size, len(candles)):
            current_candle = candles[i]
            current_price = current_candle["close"]

            # 1. Manage Open Position if exists
            if open_position:
                entry_p = open_position["entry_price"]
                sl = open_position["stop_loss"]
                target = open_position["target"]
                qty = open_position["quantity"]
                initial_risk = open_position["initial_risk"]

                # Trailing Stop Loss activation at 1R profit (matching PositionMonitorAgent)
                if config.TRAILING_STOP_LOSS_ENABLED and not open_position["trailing_active"]:
                    if current_candle["high"] >= entry_p + (initial_risk * config.TRAILING_STOP_LOSS_ACTIVATION_R):
                        open_position["stop_loss"] = max(sl, round(entry_p, 2))
                        open_position["trailing_active"] = True
                        sl = open_position["stop_loss"]

                exit_price = None
                exit_reason = None

                # Check SL hit (conservative: check SL before target within same candle)
                if current_candle["low"] <= sl:
                    exit_price = sl
                    exit_reason = "TRAILING_SL_HIT" if open_position["trailing_active"] else "STOP_LOSS_HIT"
                # Check Target hit
                elif current_candle["high"] >= target:
                    exit_price = target
                    exit_reason = "TARGET_HIT"
                # End of session exit
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
                    equity_curve.append({"trade_num": len(trades), "capital": round(capital, 2)})
                    open_position = None
                    continue

            # 2. Look for New Entry Signal if no open position
            if not open_position:
                if precomputed_indicators is not None:
                    ind = precomputed_indicators[i]
                else:
                    window = candles[max(0, i - 100): i + 1]
                    ind = strategy_engine.calculate_indicators(window)

                if not ind:
                    continue

                eval_result = strategy_engine.evaluate_strategy_confirmation(
                    current_price=current_price,
                    ind=ind,
                    market_regime_bullish=True,
                    params=params
                )

                if eval_result["is_confirmed"]:
                    per_share_risk = current_price - eval_result["stop_loss"]
                    if per_share_risk <= 0:
                        continue

                    # Sizing strictly honoring ₹25 risk per trade & 90% capital cap
                    desired_qty = math.floor(config.RISK_PER_TRADE / per_share_risk)
                    max_qty = math.floor((capital * config.MAX_CAPITAL_ALLOCATION_PCT) / current_price)
                    qty = min(desired_qty, max_qty)

                    if qty >= 1:
                        entry_executed = round(current_price * (1.0 + config.SLIPPAGE_PCT), 2)
                        open_position = {
                            "entry_price": entry_executed,
                            "stop_loss": eval_result["stop_loss"],
                            "target": eval_result["target"],
                            "quantity": qty,
                            "initial_risk": per_share_risk,
                            "trailing_active": False
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
        if gross_losses > 0:
            profit_factor = round(gross_wins / gross_losses, 2)
        elif gross_wins > 0:
            profit_factor = round(min(9.99, gross_wins), 2)
        else:
            profit_factor = 0.0

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
            "equity_curve": equity_curve,
            "trades_sample": trades[:10],
            "all_trades": trades
        }


backtesting_engine = BacktestingEngine()
