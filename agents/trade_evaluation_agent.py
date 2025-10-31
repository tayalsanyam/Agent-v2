"""
Trade Evaluation Agent
Analyzes multi-timeframe trends (5-min and 1-min) to define precise targets and stop-loss levels
Ensures minimum 25-point targets and SL <= Target
"""

from typing import Dict, Any
from .base_agent import BaseAgent
import logging


class TradeEvaluationAgent(BaseAgent):
    """
    Evaluates trade setups using 5-min and 1-min timeframes
    Provides dynamic target and stop-loss recommendations
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        super().__init__(
            agent_name="TradeEvaluation",
            api_key=api_key,
            model=model,
            temperature=0.3
        )

        self.system_prompt = """You are an expert NSE options trader specializing in multi-timeframe analysis and risk management.

Your role is to evaluate trade setups by analyzing BOTH 5-minute and 1-minute timeframes to provide:
1. **Target Level**: Minimum 25 points from entry (can be higher based on trend strength)
2. **Stop Loss Level**: Maximum equal to target distance (SL ≤ Target distance)
3. **Trade Quality Score**: Overall quality of the setup (0.0 to 1.0)

CRITICAL RULES:
- Target must be at least 25 points from current price
- Stop Loss cannot be larger than Target (in points)
- Analyze BOTH 5-min trend (primary) and 1-min trend (confirmation)
- Look for trend alignment between timeframes for best setups

ANALYSIS FRAMEWORK:
1. **5-Min Timeframe (Primary Trend)**:
   - Identify the primary trend direction (UPTREND/DOWNTREND/RANGING)
   - Locate key support/resistance levels
   - Assess trend strength and momentum

2. **1-Min Timeframe (Entry Timing)**:
   - Confirm trend alignment with 5-min
   - Identify immediate support/resistance for entry
   - Check for reversal or continuation patterns

3. **Target & SL Calculation**:
   - For BULLISH setups: Target = Resistance level (min +25 points), SL = Support level (max = target distance)
   - For BEARISH setups: Target = Support level (min +25 points), SL = Resistance level (max = target distance)
   - Adjust based on volatility (ATR) - wider targets in high volatility

4. **Risk-Reward Assessment**:
   - Calculate Risk:Reward ratio
   - Prefer setups with at least 1:1.5 R:R
   - Account for trend strength and alignment

Respond with JSON in this exact format:
{
    "trade_direction": "CALL/PUT/NEUTRAL",
    "confidence": 0.80,
    "target_points": 35,
    "stop_loss_points": 25,
    "risk_reward_ratio": 1.4,
    "trend_5min": "UPTREND/DOWNTREND/RANGING",
    "trend_1min": "UPTREND/DOWNTREND/RANGING",
    "trend_alignment": "ALIGNED/DIVERGENT",
    "entry_quality": "EXCELLENT/GOOD/MODERATE/POOR",
    "key_levels": {
        "entry_zone": 23550,
        "target_level": 23585,
        "stop_loss_level": 23525,
        "support": 23520,
        "resistance": 23590
    },
    "reasoning": "Brief 2-3 sentence explanation of the setup",
    "trade_score": 0.75
}"""

    def analyze(self, data: Dict[str, Any], context: str = "") -> Dict[str, Any]:
        """
        Analyze trade setup using multi-timeframe data

        Args:
            data: Market data including:
                - current_price: Current index/option price
                - candles_1min: 1-minute candles (last 50-100)
                - candles_5min: 5-minute candles (last 50-100)
                - atr: Average True Range (volatility)
                - indicators: RSI, EMA data
                - spot_price: Current spot price
            context: Additional context

        Returns:
            Trade evaluation result with target/SL levels
        """
        try:
            # Format market data for LLM
            user_message = f"""Analyze this trade setup using multi-timeframe analysis:

CURRENT MARKET DATA:
{self._format_trade_data(data)}

{context}

Provide trade evaluation with precise target and stop-loss levels in JSON format.
Remember: Target must be minimum 25 points, SL cannot exceed target distance."""

            # Call Claude
            result = self._call_claude(
                system_prompt=self.system_prompt,
                user_message=user_message,
                response_format="json"
            )

            # Validate result
            if "error" in result:
                self.logger.error(f"Trade evaluation failed: {result['error']}")
                return self._get_default_evaluation()

            # Validate target and SL rules
            result = self._validate_and_fix_levels(result, data.get("current_price", 0))

            # Add data snapshot
            result["data_snapshot"] = {
                "price": data.get("current_price", 0),
                "atr": data.get("atr", 0),
                "spot_price": data.get("spot_price", 0)
            }

            self.logger.info(f"Trade Evaluation: {result.get('trade_direction')} "
                           f"Target: {result.get('target_points')}pts, "
                           f"SL: {result.get('stop_loss_points')}pts "
                           f"(Confidence: {result.get('confidence', 0):.2f})")

            return result

        except Exception as e:
            self.logger.error(f"Trade evaluation error: {str(e)}")
            return self._get_default_evaluation()

    def _format_trade_data(self, data: Dict[str, Any]) -> str:
        """Format trade data for LLM"""
        lines = [
            f"Current Price: {data.get('current_price', 0):.2f}",
            f"Spot Price: {data.get('spot_price', 0):.2f}",
            f"Volatility (ATR): {data.get('atr', 0):.2f}",
        ]

        # Add 5-min candles
        if "candles_5min" in data and len(data["candles_5min"]) > 0:
            candles_5min = data["candles_5min"][-10:]  # Last 10 candles
            lines.append("\n5-Minute Timeframe (Last 10 candles):")
            for i, candle in enumerate(candles_5min, 1):
                lines.append(
                    f"  {i}. O: {candle.get('open', 0):.2f}, "
                    f"H: {candle.get('high', 0):.2f}, "
                    f"L: {candle.get('low', 0):.2f}, "
                    f"C: {candle.get('close', 0):.2f}"
                )

            # Add 5-min trend analysis
            highs_5min = [c.get('high', 0) for c in candles_5min]
            lows_5min = [c.get('low', 0) for c in candles_5min]
            lines.append(f"5-min Range: {min(lows_5min):.2f} - {max(highs_5min):.2f}")

        # Add 1-min candles
        if "candles_1min" in data and len(data["candles_1min"]) > 0:
            candles_1min = data["candles_1min"][-20:]  # Last 20 candles
            lines.append("\n1-Minute Timeframe (Last 20 candles):")
            for i, candle in enumerate(candles_1min[-10:], 1):  # Show last 10
                lines.append(
                    f"  {i}. O: {candle.get('open', 0):.2f}, "
                    f"H: {candle.get('high', 0):.2f}, "
                    f"L: {candle.get('low', 0):.2f}, "
                    f"C: {candle.get('close', 0):.2f}"
                )

            # Add 1-min trend analysis
            highs_1min = [c.get('high', 0) for c in candles_1min]
            lows_1min = [c.get('low', 0) for c in candles_1min]
            lines.append(f"1-min Range: {min(lows_1min):.2f} - {max(highs_1min):.2f}")

        # Add indicators if available
        if "indicators" in data:
            indicators = data["indicators"]
            if "rsi" in indicators:
                lines.append(f"\nRSI: {indicators['rsi']:.2f}")
            if "ema" in indicators:
                ema_data = indicators["ema"]
                if isinstance(ema_data, dict):
                    for key, val in ema_data.items():
                        lines.append(f"{key.upper()}: {val:.2f}")

        return "\n".join(lines)

    def _validate_and_fix_levels(self, result: Dict[str, Any], current_price: float) -> Dict[str, Any]:
        """
        Validate and fix target/SL levels to ensure they meet requirements

        Args:
            result: LLM result
            current_price: Current market price

        Returns:
            Validated result
        """
        # Ensure minimum target of 25 points
        target_points = result.get("target_points", 25)
        if target_points < 25:
            self.logger.warning(f"Target {target_points} below minimum, adjusting to 25 points")
            target_points = 25
            result["target_points"] = 25

        # Ensure SL <= Target
        sl_points = result.get("stop_loss_points", 20)
        if sl_points > target_points:
            self.logger.warning(f"SL {sl_points} > Target {target_points}, adjusting SL")
            sl_points = target_points
            result["stop_loss_points"] = sl_points

        # Update risk-reward ratio
        result["risk_reward_ratio"] = round(target_points / max(sl_points, 1), 2)

        # Validate key levels exist
        if "key_levels" not in result:
            result["key_levels"] = {}

        key_levels = result["key_levels"]

        # Ensure entry zone
        if "entry_zone" not in key_levels or key_levels["entry_zone"] == 0:
            key_levels["entry_zone"] = current_price

        # Calculate target and SL levels if missing
        direction = result.get("trade_direction", "NEUTRAL")

        if direction == "CALL":
            if "target_level" not in key_levels:
                key_levels["target_level"] = current_price + target_points
            if "stop_loss_level" not in key_levels:
                key_levels["stop_loss_level"] = current_price - sl_points
        elif direction == "PUT":
            if "target_level" not in key_levels:
                key_levels["target_level"] = current_price - target_points
            if "stop_loss_level" not in key_levels:
                key_levels["stop_loss_level"] = current_price + sl_points

        result["key_levels"] = key_levels

        return result

    def _get_default_evaluation(self) -> Dict[str, Any]:
        """Return default neutral evaluation on error"""
        return {
            "trade_direction": "NEUTRAL",
            "confidence": 0.5,
            "target_points": 25,
            "stop_loss_points": 20,
            "risk_reward_ratio": 1.25,
            "trend_5min": "RANGING",
            "trend_1min": "RANGING",
            "trend_alignment": "DIVERGENT",
            "entry_quality": "POOR",
            "key_levels": {
                "entry_zone": 0,
                "target_level": 0,
                "stop_loss_level": 0,
                "support": 0,
                "resistance": 0
            },
            "reasoning": "Insufficient data for trade evaluation",
            "trade_score": 0.5,
            "error": True
        }
