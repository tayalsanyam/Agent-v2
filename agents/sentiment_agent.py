"""
Market Sentiment Agent
Analyzes NSE market mood using volatility, trend, and market behavior
"""

from typing import Dict, Any
from .base_agent import BaseAgent
import logging


class MarketSentimentAgent(BaseAgent):
    """
    Analyzes market sentiment and mood for NSE trading
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        super().__init__(
            agent_name="MarketSentiment",
            api_key=api_key,
            model=model,
            temperature=0.3
        )

        self.system_prompt = """You are an expert NSE market sentiment analyst with deep knowledge of Indian stock markets.

Your role is to analyze market data and determine the overall market mood/sentiment.

Analyze the following aspects:
1. **Volatility Analysis**: Is volatility high or low? What does it indicate?
2. **Price Momentum**: Is the market trending or ranging?
3. **Market Breadth**: Are most stocks moving in the same direction?
4. **Intraday Behavior**: How has the market behaved in the current session?

Provide a sentiment assessment with:
- Overall sentiment: BULLISH, BEARISH, or NEUTRAL
- Confidence score: 0.0 to 1.0
- Key factors driving the sentiment
- Risk level: LOW, MEDIUM, or HIGH

Respond with JSON in this exact format:
{
    "sentiment": "BULLISH/BEARISH/NEUTRAL",
    "confidence": 0.75,
    "risk_level": "LOW/MEDIUM/HIGH",
    "key_factors": [
        "Factor 1 explanation",
        "Factor 2 explanation"
    ],
    "trading_bias": "CALLS/PUTS/NEUTRAL",
    "volatility_state": "HIGH/MODERATE/LOW",
    "reasoning": "Brief 2-3 sentence explanation"
}"""

    def analyze(self, data: Dict[str, Any], context: str = "") -> Dict[str, Any]:
        """
        Analyze market sentiment

        Args:
            data: Market data including:
                - current_price: Current index price
                - price_change: Change from open
                - price_change_percent: Percentage change
                - volatility: Current volatility (ATR or similar)
                - candles: Recent candle data
                - volume: Recent volume data
            context: Additional context

        Returns:
            Sentiment analysis result
        """
        try:
            # Format market data for LLM
            user_message = f"""Analyze the current NSE market sentiment:

CURRENT MARKET DATA:
{self._format_market_data(data)}

{context}

Provide sentiment analysis in JSON format."""

            # Call Claude
            result = self._call_claude(
                system_prompt=self.system_prompt,
                user_message=user_message,
                response_format="json"
            )

            # Validate result
            if "error" in result:
                self.logger.error(f"Sentiment analysis failed: {result['error']}")
                return self._get_default_sentiment()

            # Add data snapshot
            result["data_snapshot"] = {
                "price": data.get("current_price", 0),
                "change_percent": data.get("price_change_percent", 0),
                "volatility": data.get("volatility", 0)
            }

            self.logger.info(f"Sentiment: {result.get('sentiment')} "
                           f"(Confidence: {result.get('confidence', 0):.2f})")

            return result

        except Exception as e:
            self.logger.error(f"Sentiment analysis error: {str(e)}")
            return self._get_default_sentiment()

    def _format_market_data(self, data: Dict[str, Any]) -> str:
        """Format market data for LLM"""
        lines = [
            f"Current Price: {data.get('current_price', 0):.2f}",
            f"Change: {data.get('price_change', 0):.2f} "
            f"({data.get('price_change_percent', 0):.2f}%)",
            f"Volatility (ATR): {data.get('volatility', 0):.2f}",
        ]

        # Add candle data if available
        if "candles" in data and len(data["candles"]) > 0:
            recent_candles = data["candles"][-5:]  # Last 5 candles
            lines.append("\nRecent Candles (Last 5):")
            for i, candle in enumerate(recent_candles, 1):
                lines.append(
                    f"  {i}. Open: {candle.get('open', 0):.2f}, "
                    f"High: {candle.get('high', 0):.2f}, "
                    f"Low: {candle.get('low', 0):.2f}, "
                    f"Close: {candle.get('close', 0):.2f}"
                )

        # Add trend data if available
        if "trend" in data:
            lines.append(f"\nTrend Direction: {data['trend']}")

        if "rsi" in data:
            lines.append(f"RSI: {data['rsi']:.2f}")

        if "volume_trend" in data:
            lines.append(f"Volume Trend: {data['volume_trend']}")

        return "\n".join(lines)

    def _get_default_sentiment(self) -> Dict[str, Any]:
        """Return default neutral sentiment on error"""
        return {
            "sentiment": "NEUTRAL",
            "confidence": 0.5,
            "risk_level": "MEDIUM",
            "key_factors": ["Insufficient data for analysis"],
            "trading_bias": "NEUTRAL",
            "volatility_state": "MODERATE",
            "reasoning": "Using neutral default due to analysis error",
            "error": True
        }
