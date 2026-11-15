"""
Groww AI Trading Agent - Master Supervisor Agent
The central intelligence coordinator of the multi-agent system:
- Orchestrates and schedules all 8 subagents
- Enforces the autonomous trading pipeline
- Maintains the authoritative global state
- Authorizes paper orders ONLY after risk manager approval
- Handles agent restarts, pause, resume, and emergency shutdown
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
import pytz

from backend.core.config import config
from backend.core.logger import logger
from backend.core.scheduler import MarketScheduler
from backend.database.db import db
from backend.models.schemas import (
    AgentStateEnum, AgentStatus, DecisionTypeEnum, SystemOverview
)

# Import subagents
from backend.agents.market_watcher import market_watcher_agent
from backend.agents.stock_analyst import stock_analyst_agent
from backend.agents.market_regime import market_regime_agent
from backend.agents.decision_agent import decision_agent
from backend.agents.risk_manager import risk_manager_agent
from backend.agents.execution_agent import execution_agent
from backend.agents.position_monitor import position_monitor_agent
from backend.agents.reporting_agent import reporting_agent
from backend.services.groww_service import groww_service

IST = pytz.timezone(config.MARKET_TIMEZONE)

class MasterSupervisorAgent:
    def __init__(self):
        self.name = "MasterSupervisorAgent"
        self.state = AgentStateEnum.IDLE
        self.is_running = False
        self.is_paused = False
        self._loop_task: Optional[asyncio.Task] = None
        self.cycle_count = 0
        self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    def get_all_agent_statuses(self) -> Dict[str, AgentStatus]:
        return {
            "master_agent": AgentStatus(
                name=self.name,
                state=self.state,
                last_heartbeat=self.last_update,
                message=f"Cycles: {self.cycle_count} | Status: {'Running' if self.is_running else 'Stopped'}"
            ),
            "market_watcher": market_watcher_agent.get_status(),
            "stock_analyst": stock_analyst_agent.get_status(),
            "market_regime": market_regime_agent.get_status(),
            "decision_agent": decision_agent.get_status(),
            "risk_manager": risk_manager_agent.get_status(),
            "execution_agent": execution_agent.get_status(),
            "position_monitor": position_monitor_agent.get_status(),
            "reporting_agent": reporting_agent.get_status(),
        }

    def get_system_overview(self) -> SystemOverview:
        portfolio = db.get_portfolio()
        open_positions = db.get_open_positions()
        session = MarketScheduler.get_session_state()

        return SystemOverview(
            is_running=self.is_running,
            is_paused=self.is_paused,
            mode="PAPER" if not config.LIVE_TRADING_ENABLED else "LIVE",
            market_session=session,
            master_state=self.state,
            agents=self.get_all_agent_statuses(),
            portfolio=portfolio,
            active_positions_count=len(open_positions),
            trades_today_count=portfolio.get("total_trades_today", 0)
        )

    async def start(self) -> Dict[str, Any]:
        """Starts the entire multi-agent system."""
        if self.is_running:
            return {"status": "already_running"}

        logger.info("Starting Master Supervisor Agent and initializing subagents...")
        self.is_running = True
        self.is_paused = False
        self.state = AgentStateEnum.SCANNING

        # Step 1: Groww API authentication
        auth_success, auth_msg = await groww_service.authenticate()
        db.log_agent_event(self.name, "INFO", f"Groww Authentication: {auth_msg}")

        # Step 2: Initialize NSE instrument master
        inst_count = await market_watcher_agent.initialize_universe()
        db.log_agent_event(self.name, "INFO", f"Loaded {inst_count} instruments for monitoring.")

        # Step 3: Spawn autonomous cycle background task
        self._loop_task = asyncio.create_task(self._autonomous_trading_loop())
        db.log_agent_event(self.name, "INFO", "Master autonomous trading loop spawned successfully.")

        self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        return {"status": "started", "instruments_count": inst_count, "auth_message": auth_msg}

    def pause(self):
        """Pauses scanning and new trade evaluations while keeping position monitoring active."""
        self.is_paused = True
        self.state = AgentStateEnum.PAUSED
        db.log_agent_event(self.name, "WARNING", "System paused by operator. Position monitoring remains active.")
        logger.warning("Master Supervisor Agent PAUSED.")

    def resume(self):
        """Resumes active scanning and decision operations."""
        self.is_paused = False
        self.state = AgentStateEnum.IDLE
        db.log_agent_event(self.name, "INFO", "System resumed by operator.")
        logger.info("Master Supervisor Agent RESUMED.")

    async def stop(self):
        """Safely stops all agents."""
        logger.info("Stopping Master Supervisor Agent...")
        self.is_running = False
        self.is_paused = False
        self.state = AgentStateEnum.STOPPED
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        db.log_agent_event(self.name, "INFO", "System stopped safely.")

    def emergency_shutdown(self) -> Dict[str, Any]:
        """
        Immediately trips kill switch, cancels pending orders, and stops the system.
        """
        logger.critical("EMERGENCY SHUTDOWN INITIATED!")
        risk_manager_agent.trip_kill_switch("EMERGENCY SHUTDOWN TRIGGERED BY OPERATOR")
        self.is_running = False
        self.state = AgentStateEnum.STOPPED
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        db.log_agent_event(self.name, "CRITICAL", "EMERGENCY SHUTDOWN EXECUTED.")
        return {"status": "emergency_shutdown_completed"}

    async def _autonomous_trading_loop(self):
        """
        The continuous autonomous workflow running during NSE trading sessions.
        """
        logger.info("Master autonomous loop running...")
        while self.is_running:
            try:
                self.cycle_count += 1
                self.last_update = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

                # Step 1: Check Market Timing
                session = MarketScheduler.get_session_state()

                # Step 2: Always Monitor Existing Open Positions (even if paused or square-off zone)
                try:
                    await position_monitor_agent.monitor_positions()
                except Exception as pe:
                    logger.error(f"Position monitor error: {pe}")

                # If outside trading hours or paused or kill switch tripped, wait and continue
                if not session["is_trading_allowed"] or self.is_paused or risk_manager_agent.is_kill_switch_active:
                    # Outside hours: Run end-of-day reporting once if needed
                    if session["phase"] == "POST_MARKET" and reporting_agent.last_generated_report_date != datetime.now(IST).strftime("%Y-%m-%d"):
                        reporting_agent.generate_daily_report()
                    await asyncio.sleep(config.SCAN_INTERVAL_SECONDS)
                    continue

                # Step 3: Scan Market Universe
                self.state = AgentStateEnum.SCANNING
                quotes = await market_watcher_agent.scan_market()

                # Step 4: Market Regime Analysis
                regime_data = await market_regime_agent.analyze_regime(quotes)
                is_regime_suitable = regime_data.get("is_trading_suitable", True)
                regime_score = regime_data.get("regime_score", 5.0)

                # Step 5: Rank candidate stocks by volume & momentum
                # Prioritize unusual volume stocks or top gainers
                candidates = market_watcher_agent.unusual_volume_candidates
                if not candidates and quotes:
                    # Select top 5 momentum candidates
                    sorted_quotes = sorted(quotes, key=lambda q: q.change_pct, reverse=True)
                    candidates = [q.symbol for q in sorted_quotes[:5]]

                # Step 6: In-depth Technical Analysis of Shortlisted Candidates
                for symbol in candidates:
                    if not self.is_running or self.is_paused:
                        break

                    # Check if already at max open positions
                    open_pos = db.get_open_positions()
                    if len(open_pos) >= config.MAX_OPEN_POSITIONS:
                        break

                    self.state = AgentStateEnum.ANALYZING
                    analysis = await stock_analyst_agent.analyze_stock(symbol, regime_score=regime_score)
                    if not analysis:
                        continue

                    # Step 7: Decision Agent Evaluation
                    self.state = AgentStateEnum.DECIDING
                    signal = decision_agent.evaluate_candidate(analysis, is_regime_suitable)

                    if signal.decision == DecisionTypeEnum.BUY:
                        # Step 8: Strict Deterministic Risk Manager Validation
                        self.state = AgentStateEnum.ANALYZING
                        risk_result = risk_manager_agent.validate_trade_signal(signal)

                        # Step 9: Master Agent Authorization Gate
                        if risk_result.is_approved:
                            logger.info(f"MASTER AGENT AUTHORIZATION: Approved BUY for {symbol}")
                            db.log_agent_event(
                                self.name, "INFO",
                                f"MASTER AUTHORIZATION: Trade approved for {symbol} ({risk_result.calculated_quantity} shares)",
                                {"symbol": symbol, "score": signal.total_score, "quantity": risk_result.calculated_quantity}
                            )

                            # Step 10: Dispatch to Paper Execution Agent
                            self.state = AgentStateEnum.EXECUTING
                            order = execution_agent.execute_paper_buy(
                                symbol=symbol,
                                risk_result=risk_result,
                                strategy_name=signal.strategy_name
                            )
                            # Only 1 position permitted at a time under strict risk rules
                            break
                        else:
                            logger.warning(f"Master Agent rejected {symbol}: Risk Manager vetoed signal.")

                self.state = AgentStateEnum.IDLE
                await asyncio.sleep(config.SCAN_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info("Autonomous trading loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in Master Supervisor loop: {e}", exc_info=True)
                self.state = AgentStateEnum.ERROR
                db.log_agent_event(self.name, "ERROR", f"Supervisor loop error: {str(e)}")
                await asyncio.sleep(5)

master_agent = MasterSupervisorAgent()
