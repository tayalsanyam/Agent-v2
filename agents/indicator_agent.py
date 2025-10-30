"""
Indicator Analyser Agent
Analyzes technical indicators (RSI, EMA, Supertrend, etc.) for trading signals
"""

from typing import Dict, Any
from .base_agent import BaseAgent
import logging


class IndicatorAnalyserAgent(BaseAgent):
    """
    Analyzes technical indicators for trading signals
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        super().__init__(
            agent_name="IndicatorAnalyser",
            api_key=api_key,
            model=model,
            temperature=0.2  # Lower temperature for technical analysis
        )

        self.system_prompt = """You are an expert technical analyst specializing in NSE options trading.

Your role is to analyze technical indicators and generate actionable trading signals.

Analyze these key indicators:
1. **RSI (Relative Strength Index)**: Overbought (>70) or Oversold (<30)?
2. **EMA (Exponential Moving Average)**: Price above or below EMA? Trend direction?
3. **Supertrend**: Is the trend UP or DOWN? Price position relative to Supertrend?
4. **ATR (Average True Range)**: Volatility level?
5. **Volume**: Is volume confirming the move?

Signal Guidelines:
- STRONG_BUY_CALL: Oversold RSI + bullish trend + price above key EMAs
- STRONG_BUY_PUT: Overbought RSI + bearish trend + price below key EMAs
- WEAK_BUY_CALL/PUT: Partial confirmation from indicators
- NEUTRAL: Conflicting signals or choppy conditions

Respond with JSON in this exact format:
{
    "signal": "STRONG_BUY_CALL/STRONG_BUY_PUT/WEAK_BUY_CALL/WEAK_BUY_PUT/NEUTRAL",
    "confidence": 0.80,
    "indicator_scores": {
        "rsi": 0.75,
        "ema": 0.85,
        "supertrend": 0.90,
        "volume": 0.70
    },
    "key_indicators": [
        "RSI at 28 - Oversold",
        "Price above EMA13",
        "Supertrend bullish"
    ],
    "entry_recommendation": "IMMEDIATE/WAIT/AVOID",
    "risk_reward_ratio": 2.5,
    "reasoning": "Brief 2-3 sentence technical explanation"
}"""

    def analyze(self, data: Dict[str, Any], context: str = "") -> Dict[str, Any]:
        """
        Analyze technical indicators

        Args:
            data: Indicator data including:
                - rsi: RSI value
                - ema: EMA values
                - supertrend: Supertrend values
                - atr: ATR value
                - price: Current price
                - volume: Volume data
            context: Additional context

        Returns:
            Indicator analysis result
        """
        try:
            # Format indicator data for LLM
            user_message = f"""Analyze these technical indicators for NSE options trading:

INDICATOR DATA:
{self._format_indicator_data(data)}

{context}

Provide technical analysis and trading signal in JSON format."""

            # Call Claude
            result = self._call_claude(
                system_prompt=self.system_prompt,
                user_message=user_message,
                response_format="json"
            )

            # Validate result
            if "error" in result:
                self.logger.error(f"Indicator analysis failed: {result['error']}")
                return self._get_default_signal()

            # Add data snapshot
            result["data_snapshot"] = {
                "rsi": data.get("rsi", 0),
                "price": data.get("price", 0),
                "supertrend": data.get("supertrend", {})
            }

            self.logger.info(f"Signal: {result.get('signal')} "
                           f"(Confidence: {result.get('confidence', 0):.2f})")

            return result

        except Exception as e:
            self.logger.error(f"Indicator analysis error: {str(e)}")
            return self._get_default_signal()

    def _format_indicator_data(self, data: Dict[str, Any]) -> str:
        """Format indicator data for LLM"""
        lines = []

        # Current price
        if "price" in data:
            lines.append(f"Current Price: {data['price']:.2f}")

        # RSI
        if "rsi" in data:
            rsi = data["rsi"]
            rsi_state = "OVERSOLD" if rsi < 30 else "OVERBOUGHT" if rsi > 70 else "NEUTRAL"
            lines.append(f"\nRSI: {rsi:.2f} ({rsi_state})")

        # EMA
        if "ema" in data:
            ema_data = data["ema"]
            if isinstance(ema_data, dict):
                lines.append("\nEMA Values:")
                for period, value in ema_data.items():
                    position = "above" if data.get("price", 0) > value else "below"
                    lines.append(f"  EMA{period}: {value:.2f} (Price {position})")
            else:
                position = "above" if data.get("price", 0) > ema_data else "below"
                lines.append(f"\nEMA: {ema_data:.2f} (Price {position})")

        # Supertrend
        if "supertrend" in data:
            st = data["supertrend"]
            if isinstance(st, dict):
                lines.append(f"\nSupertrend:")
                lines.append(f"  Value: {st.get('value', 0):.2f}")
                lines.append(f"  Direction: {st.get('direction', 'N/A')}")
                if "price" in data:
                    position = "above" if data["price"] > st.get('value', 0) else "below"
                    lines.append(f"  Price Position: {position}")
            else:
                position = "above" if data.get("price", 0) > st else "below"
                lines.append(f"\nSupertrend: {st:.2f} (Price {position})")

        # ATR (Volatility)
        if "atr" in data:
            lines.append(f"\nATR (Volatility): {data['atr']:.2f}")

        # Volume
        if "volume" in data:
            volume = data["volume"]
            if isinstance(volume, dict):
                lines.append(f"\nVolume: {volume.get('current', 0)}")
                if "avg" in volume:
                    ratio = volume.get('current', 0) / max(volume.get('avg', 1), 1)
                    lines.append(f"  Volume Ratio: {ratio:.2f}x average")
            else:
                lines.append(f"\nVolume: {volume}")

        # MACD
        if "macd" in data:
            macd = data["macd"]
            if isinstance(macd, dict):
                lines.append(f"\nMACD:")
                lines.append(f"  MACD: {macd.get('macd', 0):.2f}")
                lines.append(f"  Signal: {macd.get('signal', 0):.2f}")
                lines.append(f"  Histogram: {macd.get('histogram', 0):.2f}")

        # Bollinger Bands
        if "bollinger" in data:
            bb = data["bollinger"]
            if isinstance(bb, dict):
                lines.append(f"\nBollinger Bands:")
                lines.append(f"  Upper: {bb.get('upper', 0):.2f}")
                lines.append(f"  Middle: {bb.get('middle', 0):.2f}")
                lines.append(f"  Lower: {bb.get('lower', 0):.2f}")
                if "price" in data:
                    price = data["price"]
                    if price > bb.get('upper', 0):
                        lines.append(f"  Price Position: Above upper band")
                    elif price < bb.get('lower', 0):
                        lines.append(f"  Price Position: Below lower band")
                    else:
                        lines.append(f"  Price Position: Within bands")

        return "\n".join(lines)

    def _get_default_signal(self) -> Dict[str, Any]:
        """Return default neutral signal on error"""
        return {
            "signal": "NEUTRAL",
            "confidence": 0.5,
            "indicator_scores": {
                "rsi": 0.5,
                "ema": 0.5,
                "supertrend": 0.5,
                "volume": 0.5
            },
            "key_indicators": ["Insufficient indicator data"],
            "entry_recommendation": "AVOID",
            "risk_reward_ratio": 0.0,
            "reasoning": "Using neutral default due to analysis error",
            "error": True
        }
