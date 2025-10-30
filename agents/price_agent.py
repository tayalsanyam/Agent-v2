"""
Price Analyser Agent
Analyzes price action patterns, support/resistance, and candlestick formations
"""

from typing import Dict, Any, List
from .base_agent import BaseAgent
import logging


class PriceAnalyserAgent(BaseAgent):
    """
    Analyzes price action patterns for trading decisions
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        super().__init__(
            agent_name="PriceAnalyser",
            api_key=api_key,
            model=model,
            temperature=0.2  # Lower temperature for pattern recognition
        )

        self.system_prompt = """You are an expert price action trader specializing in NSE options trading.

Your role is to analyze price patterns, candlestick formations, and market structure.

Analyze these aspects:
1. **Candlestick Patterns**: Doji, Hammer, Engulfing, etc.
2. **Support & Resistance**: Key levels and price reactions
3. **Market Structure**: Higher highs/lows or lower highs/lows?
4. **Price Momentum**: Strong moves or consolidation?
5. **Rejection Patterns**: Wicks, failed breakouts, etc.

Pattern Strength:
- STRONG: Clear, well-formed patterns with high probability
- MODERATE: Decent patterns but need confirmation
- WEAK: Unclear or conflicting patterns

Respond with JSON in this exact format:
{
    "pattern_detected": "BULLISH_ENGULFING/HAMMER/DOJI/BREAKOUT/REVERSAL/NONE",
    "pattern_strength": "STRONG/MODERATE/WEAK",
    "confidence": 0.75,
    "support_levels": [23500, 23450],
    "resistance_levels": [23600, 23650],
    "current_structure": "UPTREND/DOWNTREND/RANGE",
    "price_action_bias": "BULLISH/BEARISH/NEUTRAL",
    "key_observations": [
        "Strong bullish candle with high volume",
        "Price holding above key support"
    ],
    "entry_zone": {
        "ideal_entry": 23550,
        "stop_loss": 23500,
        "target": 23650
    },
    "reasoning": "Brief 2-3 sentence price action explanation"
}"""

    def analyze(self, data: Dict[str, Any], context: str = "") -> Dict[str, Any]:
        """
        Analyze price action patterns

        Args:
            data: Price data including:
                - candles: Recent OHLC candle data
                - current_price: Current price
                - support_resistance: S/R levels if available
                - volume: Volume data
            context: Additional context

        Returns:
            Price action analysis result
        """
        try:
            # Format price data for LLM
            user_message = f"""Analyze the price action for NSE options trading:

PRICE DATA:
{self._format_price_data(data)}

{context}

Provide price action analysis with patterns and key levels in JSON format."""

            # Call Claude
            result = self._call_claude(
                system_prompt=self.system_prompt,
                user_message=user_message,
                response_format="json"
            )

            # Validate result
            if "error" in result:
                self.logger.error(f"Price analysis failed: {result['error']}")
                return self._get_default_analysis()

            # Add data snapshot
            result["data_snapshot"] = {
                "current_price": data.get("current_price", 0),
                "last_candle": data.get("candles", [])[-1] if data.get("candles") else None
            }

            self.logger.info(f"Pattern: {result.get('pattern_detected')} "
                           f"(Strength: {result.get('pattern_strength')})")

            return result

        except Exception as e:
            self.logger.error(f"Price analysis error: {str(e)}")
            return self._get_default_analysis()

    def _format_price_data(self, data: Dict[str, Any]) -> str:
        """Format price data for LLM"""
        lines = []

        # Current price
        if "current_price" in data:
            lines.append(f"Current Price: {data['current_price']:.2f}")

        # Recent candles
        if "candles" in data and len(data["candles"]) > 0:
            candles = data["candles"]
            lines.append(f"\nRecent Candles (Last 10):")

            # Show last 10 candles
            for i, candle in enumerate(candles[-10:], 1):
                open_price = candle.get('open', 0)
                high = candle.get('high', 0)
                low = candle.get('low', 0)
                close = candle.get('close', 0)
                volume = candle.get('volume', 0)

                # Determine candle type
                candle_type = "BULLISH" if close > open_price else "BEARISH" if close < open_price else "DOJI"
                body_size = abs(close - open_price)
                range_size = high - low
                body_percent = (body_size / range_size * 100) if range_size > 0 else 0

                lines.append(
                    f"  {i}. O: {open_price:.2f}, H: {high:.2f}, "
                    f"L: {low:.2f}, C: {close:.2f} "
                    f"[{candle_type}, Body: {body_percent:.0f}%]"
                )

                # Add volume if available
                if volume > 0:
                    lines[-1] += f" Vol: {volume}"

        # Support and Resistance levels
        if "support_resistance" in data:
            sr = data["support_resistance"]
            if isinstance(sr, dict):
                if "support" in sr:
                    lines.append(f"\nSupport Levels: {sr['support']}")
                if "resistance" in sr:
                    lines.append(f"Resistance Levels: {sr['resistance']}")
            elif isinstance(sr, list):
                lines.append(f"\nKey Levels: {sr}")

        # High/Low of day
        if "high_of_day" in data:
            lines.append(f"\nHigh of Day: {data['high_of_day']:.2f}")
        if "low_of_day" in data:
            lines.append(f"Low of Day: {data['low_of_day']:.2f}")

        # Previous close
        if "prev_close" in data:
            lines.append(f"Previous Close: {data['prev_close']:.2f}")
            if "current_price" in data:
                change = data['current_price'] - data['prev_close']
                change_pct = (change / data['prev_close']) * 100
                lines.append(f"Change: {change:.2f} ({change_pct:+.2f}%)")

        # Volume analysis
        if "volume" in data:
            volume = data["volume"]
            if isinstance(volume, dict):
                lines.append(f"\nVolume Analysis:")
                lines.append(f"  Current: {volume.get('current', 0)}")
                if "avg" in volume:
                    lines.append(f"  Average: {volume.get('avg', 0)}")
                    ratio = volume.get('current', 0) / max(volume.get('avg', 1), 1)
                    volume_state = "HIGH" if ratio > 1.5 else "LOW" if ratio < 0.5 else "NORMAL"
                    lines.append(f"  State: {volume_state} ({ratio:.2f}x)")

        # Trend information
        if "trend" in data:
            lines.append(f"\nCurrent Trend: {data['trend']}")

        return "\n".join(lines)

    def _get_default_analysis(self) -> Dict[str, Any]:
        """Return default neutral analysis on error"""
        return {
            "pattern_detected": "NONE",
            "pattern_strength": "WEAK",
            "confidence": 0.5,
            "support_levels": [],
            "resistance_levels": [],
            "current_structure": "RANGE",
            "price_action_bias": "NEUTRAL",
            "key_observations": ["Insufficient price data for analysis"],
            "entry_zone": {
                "ideal_entry": 0,
                "stop_loss": 0,
                "target": 0
            },
            "reasoning": "Using neutral default due to analysis error",
            "error": True
        }
