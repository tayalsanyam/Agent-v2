"""
Main Orchestrator - Decision Hub
Coordinates all agents, manages memory, and makes final trading decisions
"""

import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import os

from agents.base_agent import BaseAgent
from agents.sentiment_agent import MarketSentimentAgent
from agents.indicator_agent import IndicatorAnalyserAgent
from agents.price_agent import PriceAnalyserAgent
from agents.trade_evaluation_agent import TradeEvaluationAgent
from trade_manager import TradeManager


class TradingOrchestrator:
    """
    Main orchestrator that coordinates all agents and makes trading decisions
    """

    def __init__(self,
                 api_key: str,
                 trade_manager: TradeManager,
                 config: Dict[str, Any]):
        """
        Initialize the orchestrator

        Args:
            api_key: Anthropic API key
            trade_manager: Trade manager instance
            config: Configuration dictionary
        """
        self.api_key = api_key
        self.trade_manager = trade_manager
        self.config = config

        # Setup logging EARLY (used by state loader)
        self.logger = logging.getLogger("Orchestrator")

        # Initialize agents
        self.sentiment_agent = MarketSentimentAgent(api_key)
        self.indicator_agent = IndicatorAnalyserAgent(api_key)
        self.price_agent = PriceAnalyserAgent(api_key)
        self.trade_evaluation_agent = TradeEvaluationAgent(api_key)

        # Agent weights
        self.sentiment_weight = config.get("sentiment_weight", 0.25)
        self.indicator_weight = config.get("indicator_weight", 0.25)
        self.price_action_weight = config.get("price_action_weight", 0.25)
        self.trade_evaluation_weight = config.get("trade_evaluation_weight", 0.25)

        # Decision threshold
        self.min_confidence_threshold = config.get("min_confidence_threshold", 0.65)
        self.min_hold_confidence = config.get("min_hold_confidence", 0.45)

        # Memory: Track recent trades and state
        self.trade_history: List[Dict[str, Any]] = []
        self.daily_trades = 0
        self.win_streak = 0
        self.loss_streak = 0
        self.total_wins = 0
        self.total_losses = 0
        self.daily_pnl = 0.0
        self.last_trade_result = None

        # Store trade evaluation recommendations
        self.current_target_points = 25  # Default minimum
        self.current_sl_points = 20
        self.peak_pnl_percent = 0.0  # Track peak profit for trailing SL

        # State file
        self.state_file = config.get("state_file", "data/agent_state.json")
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

        # Load state if exists
        self._load_state()

        self.logger.info("Trading Orchestrator initialized")

    def analyze_market(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coordinate all agents to analyze market

        Args:
            market_data: Market data dictionary containing:
                - price_data: Current price, candles, etc.
                - indicator_data: RSI, EMA, Supertrend, etc.
                - sentiment_data: Volatility, trend, etc.

        Returns:
            Combined analysis from all agents
        """
        try:
            self.logger.info("=== Starting Market Analysis ===")

            # Extract data for each agent
            sentiment_data = market_data.get("sentiment_data", {})
            indicator_data = market_data.get("indicator_data", {})
            price_data = market_data.get("price_data", {})
            trade_evaluation_data = market_data.get("trade_evaluation_data", {})

            # Add context from recent trades
            context = self._build_context()

            # Run agents in parallel (conceptually - could use threading)
            self.logger.info("Running Sentiment Agent...")
            sentiment_result = self.sentiment_agent.analyze(sentiment_data, context)

            self.logger.info("Running Indicator Agent...")
            indicator_result = self.indicator_agent.analyze(indicator_data, context)

            self.logger.info("Running Price Action Agent...")
            price_result = self.price_agent.analyze(price_data, context)

            self.logger.info("Running Trade Evaluation Agent...")
            trade_evaluation_result = self.trade_evaluation_agent.analyze(trade_evaluation_data, context)

            # Combine results
            combined_analysis = {
                "sentiment": sentiment_result,
                "indicators": indicator_result,
                "price_action": price_result,
                "trade_evaluation": trade_evaluation_result,
                "timestamp": datetime.now().isoformat()
            }

            self.logger.info("=== Market Analysis Complete ===")

            return combined_analysis

        except Exception as e:
            self.logger.error(f"Market analysis error: {str(e)}")
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def make_decision(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make trading decision based on combined analysis

        Args:
            analysis: Combined analysis from all agents

        Returns:
            Trading decision
        """
        try:
            self.logger.info("=== Making Trading Decision ===")

            # Extract agent results
            sentiment = analysis.get("sentiment", {})
            indicators = analysis.get("indicators", {})
            price_action = analysis.get("price_action", {})
            trade_evaluation = analysis.get("trade_evaluation", {})

            # Check for errors
            if sentiment.get("error") or indicators.get("error") or price_action.get("error") or trade_evaluation.get("error"):
                self.logger.warning("One or more agents returned errors")
                return {
                    "action": "WAIT",
                    "reason": "Insufficient or erroneous data from agents"
                }

            # Calculate weighted score for CALL
            call_score = 0.0
            put_score = 0.0

            # Sentiment contribution
            sentiment_bias = sentiment.get("trading_bias", "NEUTRAL")
            sentiment_conf = sentiment.get("confidence", 0.5)

            if sentiment_bias == "CALLS":
                call_score += self.sentiment_weight * sentiment_conf
            elif sentiment_bias == "PUTS":
                put_score += self.sentiment_weight * sentiment_conf
            else:
                call_score += self.sentiment_weight * 0.5
                put_score += self.sentiment_weight * 0.5

            # Indicator contribution
            indicator_signal = indicators.get("signal", "NEUTRAL")
            indicator_conf = indicators.get("confidence", 0.5)

            if "CALL" in indicator_signal:
                call_score += self.indicator_weight * indicator_conf
            elif "PUT" in indicator_signal:
                put_score += self.indicator_weight * indicator_conf
            else:
                call_score += self.indicator_weight * 0.5
                put_score += self.indicator_weight * 0.5

            # Price action contribution
            price_bias = price_action.get("price_action_bias", "NEUTRAL")
            price_conf = price_action.get("confidence", 0.5)

            if price_bias == "BULLISH":
                call_score += self.price_action_weight * price_conf
            elif price_bias == "BEARISH":
                put_score += self.price_action_weight * price_conf
            else:
                call_score += self.price_action_weight * 0.5
                put_score += self.price_action_weight * 0.5

            # Trade evaluation contribution
            trade_direction = trade_evaluation.get("trade_direction", "NEUTRAL")
            trade_conf = trade_evaluation.get("confidence", 0.5)

            if trade_direction == "CALL":
                call_score += self.trade_evaluation_weight * trade_conf
            elif trade_direction == "PUT":
                put_score += self.trade_evaluation_weight * trade_conf
            else:
                call_score += self.trade_evaluation_weight * 0.5
                put_score += self.trade_evaluation_weight * 0.5

            # Store target and SL recommendations from trade evaluation agent
            self.current_target_points = trade_evaluation.get("target_points", 25)
            self.current_sl_points = trade_evaluation.get("stop_loss_points", 20)

            # Normalize scores (should already sum to ~1.0 but ensure)
            total_score = call_score + put_score
            if total_score > 0:
                call_score = call_score / total_score
                put_score = put_score / total_score

            # Determine action
            if call_score > self.min_confidence_threshold:
                action = "BUY_CALL"
                confidence = call_score
                reasoning = self._build_reasoning(sentiment, indicators, price_action, trade_evaluation, "CALL")
            elif put_score > self.min_confidence_threshold:
                action = "BUY_PUT"
                confidence = put_score
                reasoning = self._build_reasoning(sentiment, indicators, price_action, trade_evaluation, "PUT")
            else:
                action = "WAIT"
                confidence = max(call_score, put_score)
                reasoning = f"Insufficient confidence (CALL: {call_score:.2f}, PUT: {put_score:.2f})"

            decision = {
                "action": action,
                "confidence": confidence,
                "call_score": call_score,
                "put_score": put_score,
                "reasoning": reasoning,
                "timestamp": datetime.now().isoformat(),
                "target_points": self.current_target_points,
                "sl_points": self.current_sl_points,
                "agent_summary": {
                    "sentiment": f"{sentiment_bias} ({sentiment_conf:.2f})",
                    "indicators": f"{indicator_signal} ({indicator_conf:.2f})",
                    "price_action": f"{price_bias} ({price_conf:.2f})",
                    "trade_evaluation": f"{trade_direction} ({trade_conf:.2f}) T:{self.current_target_points}pts SL:{self.current_sl_points}pts"
                }
            }

            self.logger.info(f"Decision: {action} (Confidence: {confidence:.2f})")
            self.logger.info(f"Reasoning: {reasoning}")

            return decision

        except Exception as e:
            self.logger.error(f"Decision making error: {str(e)}")
            return {
                "action": "WAIT",
                "reason": f"Error: {str(e)}"
            }

    def execute_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute trading decision

        Args:
            decision: Decision dictionary

        Returns:
            Execution result
        """
        try:
            action = decision.get("action")

            if action == "WAIT":
                return {
                    "executed": False,
                    "reason": decision.get("reasoning", "No action")
                }

            # Check if we already have a position
            if self.trade_manager.has_active_position():
                return {
                    "executed": False,
                    "reason": "Active position exists"
                }

            # Check daily limits
            if not self._check_trading_limits():
                return {
                    "executed": False,
                    "reason": "Daily trading limits reached"
                }

            # Calculate position multiplier based on streak
            position_multiplier = self._calculate_position_multiplier()

            # Execute trade
            if action == "BUY_CALL":
                result = self.trade_manager.place_order("CALL", position_multiplier)
            elif action == "BUY_PUT":
                result = self.trade_manager.place_order("PUT", position_multiplier)
            else:
                return {
                    "executed": False,
                    "reason": f"Unknown action: {action}"
                }

            if result.get("success"):
                self.daily_trades += 1
                self.peak_pnl_percent = 0.0  # Reset peak tracker for new position
                self.logger.info(f"Trade executed: {action} | Target: {self.current_target_points}pts | SL: {self.current_sl_points}pts")

            return {
                "executed": result.get("success", False),
                "result": result,
                "position_multiplier": position_multiplier
            }

        except Exception as e:
            self.logger.error(f"Execution error: {str(e)}")
            return {
                "executed": False,
                "error": str(e)
            }

    def check_exit_conditions(self) -> Optional[str]:
        """
        Check if active position should be exited using dynamic target/SL
        and smart trailing stop logic

        Returns:
            Exit reason or None
        """
        if not self.trade_manager.has_active_position():
            return None

        try:
            # Get current P&L
            pnl_info = self.trade_manager.get_current_pnl()

            if not pnl_info.get("has_position"):
                return None

            pnl_percent = pnl_info.get("pnl_percent", 0)
            current_price = pnl_info.get("current_price", 0)
            entry_price = pnl_info.get("entry_price", 0)

            # Calculate points gained/lost
            if entry_price > 0:
                pnl_points = abs(current_price - entry_price)
            else:
                pnl_points = 0

            # Update peak P&L for trailing
            if pnl_percent > self.peak_pnl_percent:
                self.peak_pnl_percent = pnl_percent
                self.logger.info(f"New peak P&L: {self.peak_pnl_percent:.2f}%")

            # Check stop loss using agent's recommendation
            # Convert points to percentage for comparison
            sl_threshold_percent = -(self.current_sl_points / entry_price * 100) if entry_price > 0 else -3.0

            if pnl_percent <= sl_threshold_percent:
                self.logger.info(f"Stop Loss hit: {pnl_percent:.2f}% <= {sl_threshold_percent:.2f}%")
                return "STOP_LOSS"

            # Check target profit using agent's recommendation
            target_threshold_percent = (self.current_target_points / entry_price * 100) if entry_price > 0 else 3.0

            if pnl_percent >= target_threshold_percent:
                self.logger.info(f"Target hit: {pnl_percent:.2f}% >= {target_threshold_percent:.2f}%")
                return "TARGET"

            # Smart Dynamic Trailing Stop Logic
            # Only activate if we've made significant profit
            if self.peak_pnl_percent > 0.5:  # At least 0.5% profit achieved
                # Calculate trailing distance based on profit magnitude
                # More profit = tighter trail to protect gains
                if self.peak_pnl_percent >= 3.0:
                    # High profit: Trail tightly (allow 20% giveback)
                    trailing_threshold = self.peak_pnl_percent * 0.80
                elif self.peak_pnl_percent >= 2.0:
                    # Good profit: Trail moderately (allow 25% giveback)
                    trailing_threshold = self.peak_pnl_percent * 0.75
                elif self.peak_pnl_percent >= 1.0:
                    # Decent profit: Trail loosely (allow 30% giveback)
                    trailing_threshold = self.peak_pnl_percent * 0.70
                else:
                    # Small profit: Trail very loosely (allow 40% giveback)
                    trailing_threshold = self.peak_pnl_percent * 0.60

                if pnl_percent < trailing_threshold:
                    self.logger.info(f"Trailing Stop hit: Current {pnl_percent:.2f}% < Threshold {trailing_threshold:.2f}% "
                                   f"(Peak was {self.peak_pnl_percent:.2f}%)")
                    return "TRAILING_STOP"

            return None

        except Exception as e:
            self.logger.error(f"Exit check error: {str(e)}")
            return None

    def evaluate_ongoing_position(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Re-evaluate ongoing position using all agents to determine if we should continue holding

        This method runs all agents with context about the current position and calculates
        a "hold confidence" score. If the market conditions have changed and agents now
        favor the opposite direction or neutral, it recommends exiting the position.

        Args:
            market_data: Current market data dictionary

        Returns:
            Dictionary with hold recommendation:
            {
                "hold_recommendation": "HOLD" or "EXIT",
                "confidence": float (0.0-1.0),
                "reasoning": str,
                "agent_scores": dict,
                "call_score": float,
                "put_score": float
            }
        """
        if not self.trade_manager.has_active_position():
            return {
                "hold_recommendation": "HOLD",
                "confidence": 0.0,
                "reasoning": "No active position"
            }

        try:
            self.logger.info("=== Re-evaluating Active Position ===")

            # Get current position info
            position_info = self.trade_manager.get_position_info()
            pnl_info = self.trade_manager.get_current_pnl()

            position_direction = position_info.get("direction", "UNKNOWN")
            current_pnl_percent = pnl_info.get("pnl_percent", 0)

            # Build context with position details
            position_context = self._build_position_context(position_info, pnl_info)

            # Run market analysis with position context
            analysis = self.analyze_market(market_data)

            # Extract agent results
            sentiment = analysis.get("sentiment", {})
            indicators = analysis.get("indicators", {})
            price_action = analysis.get("price_action", {})
            trade_evaluation = analysis.get("trade_evaluation", {})

            # Calculate weighted scores (same as make_decision)
            call_score = 0.0
            put_score = 0.0

            # Sentiment contribution
            sentiment_bias = sentiment.get("trading_bias", "NEUTRAL")
            sentiment_conf = sentiment.get("confidence", 0.5)

            if sentiment_bias == "CALLS":
                call_score += self.sentiment_weight * sentiment_conf
            elif sentiment_bias == "PUTS":
                put_score += self.sentiment_weight * sentiment_conf
            else:
                call_score += self.sentiment_weight * 0.5
                put_score += self.sentiment_weight * 0.5

            # Indicator contribution
            indicator_signal = indicators.get("signal", "NEUTRAL")
            indicator_conf = indicators.get("confidence", 0.5)

            if "CALL" in indicator_signal:
                call_score += self.indicator_weight * indicator_conf
            elif "PUT" in indicator_signal:
                put_score += self.indicator_weight * indicator_conf
            else:
                call_score += self.indicator_weight * 0.5
                put_score += self.indicator_weight * 0.5

            # Price action contribution
            price_bias = price_action.get("price_action_bias", "NEUTRAL")
            price_conf = price_action.get("confidence", 0.5)

            if price_bias == "BULLISH":
                call_score += self.price_action_weight * price_conf
            elif price_bias == "BEARISH":
                put_score += self.price_action_weight * price_conf
            else:
                call_score += self.price_action_weight * 0.5
                put_score += self.price_action_weight * 0.5

            # Trade evaluation contribution
            trade_direction = trade_evaluation.get("trade_direction", "NEUTRAL")
            trade_conf = trade_evaluation.get("confidence", 0.5)

            if trade_direction == "CALL":
                call_score += self.trade_evaluation_weight * trade_conf
            elif trade_direction == "PUT":
                put_score += self.trade_evaluation_weight * trade_conf
            else:
                call_score += self.trade_evaluation_weight * 0.5
                put_score += self.trade_evaluation_weight * 0.5

            # Normalize scores
            total_score = call_score + put_score
            if total_score > 0:
                call_score = call_score / total_score
                put_score = put_score / total_score

            # Determine hold confidence based on position direction
            if position_direction == "CALL":
                hold_confidence = call_score
                opposing_score = put_score
            elif position_direction == "PUT":
                hold_confidence = put_score
                opposing_score = call_score
            else:
                hold_confidence = 0.5
                opposing_score = 0.5

            # Build reasoning
            reasoning_parts = []
            reasoning_parts.append(f"Position: {position_direction} (P&L: {current_pnl_percent:+.2f}%)")
            reasoning_parts.append(f"Current sentiment: {sentiment_bias} ({sentiment_conf:.2f})")
            reasoning_parts.append(f"Indicators: {indicator_signal} ({indicator_conf:.2f})")
            reasoning_parts.append(f"Price action: {price_bias} ({price_conf:.2f})")
            reasoning_parts.append(f"Hold confidence: {hold_confidence:.2f}")

            # Determine recommendation
            if hold_confidence < self.min_hold_confidence:
                recommendation = "EXIT"
                reasoning_parts.append(f"BELOW threshold {self.min_hold_confidence:.2f} - Agents suggest exit")
            else:
                recommendation = "HOLD"
                reasoning_parts.append(f"ABOVE threshold {self.min_hold_confidence:.2f} - Continue holding")

            reasoning = " | ".join(reasoning_parts)

            self.logger.info(f"Hold Evaluation: {recommendation} (Confidence: {hold_confidence:.2f})")
            self.logger.info(f"Agent Scores - CALL: {call_score:.2f}, PUT: {put_score:.2f}")

            return {
                "hold_recommendation": recommendation,
                "confidence": hold_confidence,
                "reasoning": reasoning,
                "agent_scores": {
                    "sentiment": f"{sentiment_bias} ({sentiment_conf:.2f})",
                    "indicators": f"{indicator_signal} ({indicator_conf:.2f})",
                    "price_action": f"{price_bias} ({price_conf:.2f})",
                    "trade_evaluation": f"{trade_direction} ({trade_conf:.2f})"
                },
                "call_score": call_score,
                "put_score": put_score,
                "opposing_score": opposing_score
            }

        except Exception as e:
            self.logger.error(f"Error evaluating ongoing position: {str(e)}")
            return {
                "hold_recommendation": "HOLD",
                "confidence": 0.5,
                "reasoning": f"Error during evaluation: {str(e)}",
                "error": str(e)
            }

    def _build_position_context(self, position_info: Dict[str, Any], pnl_info: Dict[str, Any]) -> str:
        """Build context string describing current position"""
        direction = position_info.get("direction", "UNKNOWN")
        entry_price = position_info.get("entry_price", 0)
        current_pnl = pnl_info.get("pnl", 0)
        pnl_percent = pnl_info.get("pnl_percent", 0)

        entry_time = position_info.get("entry_time")
        if entry_time:
            holding_duration = (datetime.now() - entry_time).total_seconds() / 60
            duration_str = f"{holding_duration:.0f} minutes"
        else:
            duration_str = "unknown duration"

        context = f"\n=== ACTIVE POSITION CONTEXT ===\n"
        context += f"Direction: {direction}\n"
        context += f"Entry Price: Rs.{entry_price:.2f}\n"
        context += f"Current P&L: Rs.{current_pnl:.2f} ({pnl_percent:+.2f}%)\n"
        context += f"Holding Duration: {duration_str}\n"
        context += f"Question: Should we continue holding this {direction} position or exit now?\n"
        context += "=== END POSITION CONTEXT ===\n"

        return context

    def close_position_and_update(self, exit_reason: str) -> Dict[str, Any]:
        """
        Close position and update statistics

        Args:
            exit_reason: Reason for exit

        Returns:
            Trade result
        """
        try:
            # Close position
            result = self.trade_manager.close_position(exit_reason)

            if not result.get("success"):
                return result

            # Update statistics
            pnl = result.get("pnl", 0)
            pnl_percent = result.get("pnl_percent", 0)

            is_win = pnl > 0

            if is_win:
                self.total_wins += 1
                self.win_streak += 1
                self.loss_streak = 0
            else:
                self.total_losses += 1
                self.loss_streak += 1
                self.win_streak = 0

            self.daily_pnl += pnl
            self.last_trade_result = "WIN" if is_win else "LOSS"

            # Reset peak tracker for next trade
            self.peak_pnl_percent = 0.0

            # Add to trade history
            trade_record = {
                "timestamp": datetime.now().isoformat(),
                "symbol": result.get("symbol"),
                "direction": result.get("direction"),
                "entry_price": result.get("entry_price"),
                "exit_price": result.get("exit_price"),
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "exit_reason": exit_reason,
                "result": "WIN" if is_win else "LOSS"
            }

            self.trade_history.append(trade_record)

            # Save state
            self._save_state()

            self.logger.info(f"Trade closed: {trade_record['result']} "
                           f"(P&L: ₹{pnl:.2f}, {pnl_percent:+.2f}%)")
            self.logger.info(f"Win Streak: {self.win_streak}, "
                           f"Total Wins: {self.total_wins}, "
                           f"Total Losses: {self.total_losses}")

            return result

        except Exception as e:
            self.logger.error(f"Close position error: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_statistics(self) -> Dict[str, Any]:
        """Get current trading statistics"""
        total_trades = self.total_wins + self.total_losses
        win_rate = (self.total_wins / total_trades * 100) if total_trades > 0 else 0

        return {
            "daily_trades": self.daily_trades,
            "total_wins": self.total_wins,
            "total_losses": self.total_losses,
            "win_streak": self.win_streak,
            "loss_streak": self.loss_streak,
            "win_rate": win_rate,
            "daily_pnl": self.daily_pnl,
            "current_capital": self.trade_manager.current_capital,
            "last_trade": self.last_trade_result
        }

    def _calculate_position_multiplier(self) -> float:
        """Calculate position size multiplier based on streak"""
        base_multiplier = self.config.get("base_position_multiplier", 1.0)
        win_streak_multiplier = self.config.get("win_streak_multiplier", 1.2)
        loss_reduction_multiplier = self.config.get("loss_reduction_multiplier", 0.5)

        # Increase size on win streak (up to 3 wins)
        if self.win_streak > 0:
            streak_bonus = min(self.win_streak, 3) * 0.1
            return base_multiplier * (1.0 + streak_bonus)

        # Decrease size on loss streak
        if self.loss_streak > 0:
            return base_multiplier * loss_reduction_multiplier

        return base_multiplier

    def _check_trading_limits(self) -> bool:
        """
        Check if trading limits are reached
        NOTE: Trade limits are DISABLED as per user request for unlimited trading
        """
        # ALL LIMITS DISABLED - UNLIMITED TRADING MODE
        # Trade limits commented out but kept for reference

        # # Check daily trade limit
        # max_trades = self.config.get("max_daily_trades", 50)
        # if self.daily_trades >= max_trades:
        #     self.logger.warning(f"Daily trade limit reached: {self.daily_trades}/{max_trades}")
        #     return False

        # # Check daily win target
        # daily_win_target = self.config.get("daily_win_target", 10)
        # if self.win_streak >= daily_win_target:
        #     self.logger.info(f"Daily win target achieved: {self.win_streak} consecutive wins!")
        #     return False

        # # Check max consecutive losses
        # max_losses = self.config.get("max_consecutive_losses", 3)
        # if self.loss_streak >= max_losses:
        #     self.logger.warning(f"Max consecutive losses reached: {self.loss_streak}")
        #     return False

        # # Check daily P&L limits
        # loss_limit = self.config.get("daily_loss_limit", -5.0)
        # profit_limit = self.config.get("daily_profit_limit", 12.0)

        # pnl_percent = (self.daily_pnl / self.trade_manager.initial_capital) * 100

        # if pnl_percent <= loss_limit:
        #     self.logger.warning(f"Daily loss limit reached: {pnl_percent:.2f}%")
        #     return False

        # if pnl_percent >= profit_limit:
        #     self.logger.info(f"Daily profit target achieved: {pnl_percent:.2f}%")
        #     return False

        # No limits - always allow trading
        return True

    def _build_context(self) -> str:
        """Build context from recent trades"""
        if len(self.trade_history) == 0:
            return "No previous trades today."

        recent_trades = self.trade_history[-5:]  # Last 5 trades
        lines = [f"\nRecent Trading Context:"]
        lines.append(f"Win Streak: {self.win_streak}, Loss Streak: {self.loss_streak}")
        lines.append(f"Daily P&L: ₹{self.daily_pnl:.2f}")
        lines.append(f"Last {len(recent_trades)} trades:")

        for trade in recent_trades:
            lines.append(f"  - {trade['direction']}: {trade['result']} "
                        f"({trade['pnl_percent']:+.2f}%)")

        return "\n".join(lines)

    def _build_reasoning(self,
                        sentiment: Dict,
                        indicators: Dict,
                        price_action: Dict,
                        trade_evaluation: Dict,
                        direction: str) -> str:
        """Build reasoning for decision"""
        reasons = []

        # Sentiment
        sentiment_bias = sentiment.get("trading_bias", "NEUTRAL")
        if direction == "CALL" and sentiment_bias == "CALLS":
            reasons.append(f"Bullish sentiment ({sentiment.get('sentiment')})")
        elif direction == "PUT" and sentiment_bias == "PUTS":
            reasons.append(f"Bearish sentiment ({sentiment.get('sentiment')})")

        # Indicators
        signal = indicators.get("signal", "")
        if direction in signal:
            key_indicators = indicators.get("key_indicators", [])
            if key_indicators:
                reasons.append(f"Technical: {key_indicators[0]}")

        # Price action
        price_bias = price_action.get("price_action_bias", "NEUTRAL")
        pattern = price_action.get("pattern_detected", "NONE")
        if (direction == "CALL" and price_bias == "BULLISH") or \
           (direction == "PUT" and price_bias == "BEARISH"):
            reasons.append(f"Price action: {pattern}")

        # Trade evaluation
        trade_direction = trade_evaluation.get("trade_direction", "NEUTRAL")
        if trade_direction == direction:
            trend_alignment = trade_evaluation.get("trend_alignment", "UNKNOWN")
            entry_quality = trade_evaluation.get("entry_quality", "UNKNOWN")
            reasons.append(f"Setup: {entry_quality} ({trend_alignment})")

        return " | ".join(reasons) if reasons else "Multiple factors aligned"

    def _save_state(self):
        """Save orchestrator state to file"""
        try:
            state = {
                "win_streak": self.win_streak,
                "loss_streak": self.loss_streak,
                "total_wins": self.total_wins,
                "total_losses": self.total_losses,
                "daily_pnl": self.daily_pnl,
                "daily_trades": self.daily_trades,
                "last_trade_result": self.last_trade_result,
                "trade_history": self.trade_history[-50:],  # Last 50 trades
                "timestamp": datetime.now().isoformat()
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

        except Exception as e:
            self.logger.error(f"Failed to save state: {str(e)}")

    def _load_state(self):
        """Load orchestrator state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                self.win_streak = state.get("win_streak", 0)
                self.loss_streak = state.get("loss_streak", 0)
                self.total_wins = state.get("total_wins", 0)
                self.total_losses = state.get("total_losses", 0)
                self.daily_pnl = state.get("daily_pnl", 0.0)
                self.daily_trades = state.get("daily_trades", 0)
                self.last_trade_result = state.get("last_trade_result")
                self.trade_history = state.get("trade_history", [])

                self.logger.info("State loaded from file")

        except Exception as e:
            self.logger.error(f"Failed to load state: {str(e)}")
