"""
Market Data Module
Fetches and processes market data from Fyers API
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from fyers_apiv3 import fyersModel
import pandas as pd
import numpy as np


class MarketDataProvider:
    """
    Provides market data and technical indicators
    """

    def __init__(self, fyers_client: fyersModel.FyersModel, index: str = "NIFTY"):
        """
        Initialize market data provider

        Args:
            fyers_client: Initialized Fyers API client
            index: Trading index (NIFTY or SENSEX)
        """
        self.fyers = fyers_client
        self.index = index

        # Symbol mapping
        self.index_symbol = "NSE:NIFTY50-INDEX" if index == "NIFTY" else "BSE:SENSEX-INDEX"

        self.logger = logging.getLogger("MarketData")

    def get_current_price(self) -> float:
        """Get current spot price"""
        try:
            response = self.fyers.quotes({"symbols": self.index_symbol})

            if response and response.get("s") == "ok":
                data = response.get("d", [])
                if data and len(data) > 0:
                    return float(data[0].get("v", {}).get("lp", 0))

            return 0.0

        except Exception as e:
            self.logger.error(f"Error fetching price: {str(e)}")
            return 0.0




    def get_historical_candles(self, timeframe: str = "1", candles: int = 100) -> List[Dict]:
        
        #Get historical candle data

        #Args:
         #   timeframe: Timeframe ("1" for 1-min, "5" for 5-min, etc.)
          #  candles: Number of candles

        #Returns:
         #   List of candle dictionaries
        
        try:
            # Calculate date range
            to_date = datetime.now()
            from_date = to_date - timedelta(days=2)  # 2 days should be enough

            # Format dates
            from_date_str = from_date.strftime("%Y-%m-%d")
            to_date_str = to_date.strftime("%Y-%m-%d")

            # Fetch data
            data = {
                "symbol": self.index_symbol,
                "resolution": timeframe,
                "date_format": "1",  # Unix timestamp
                "range_from": from_date_str,
                "range_to": to_date_str,
                "cont_flag": "1"
            }

            response = self.fyers.history(data=data)

            if response and response.get("s") == "ok":
                candles_data = response.get("candles", [])

                # Convert to list of dicts
                candle_list = []
                for candle in candles_data:
                    if len(candle) >= 5:
                        candle_list.append({
                            "timestamp": candle[0],
                            "open": float(candle[1]),
                            "high": float(candle[2]),
                            "low": float(candle[3]),
                            "close": float(candle[4]),
                            "volume": int(candle[5]) if len(candle) > 5 else 0
                        })

                return candle_list[-candles:]  # Return last N candles

            return []

        except Exception as e:
            self.logger.error(f"Error fetching candles: {str(e)}")
            return []
        


    def calculate_rsi(self, candles: List[Dict], period: int = 6) -> float:
        """Calculate RSI"""
        try:
            if len(candles) < period + 1:
                return 50.0  # Neutral RSI

            closes = [c["close"] for c in candles]

            # Calculate price changes
            deltas = np.diff(closes)

            # Separate gains and losses
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)

            # Calculate average gain/loss
            avg_gain = np.mean(gains[-period:])
            avg_loss = np.mean(losses[-period:])

            if avg_loss == 0:
                return 100.0

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            return float(rsi)

        except Exception as e:
            self.logger.error(f"RSI calculation error: {str(e)}")
            return 50.0

    def calculate_ema(self, candles: List[Dict], period: int = 13) -> float:
        """Calculate EMA"""
        try:
            if len(candles) < period:
                return 0.0

            closes = [c["close"] for c in candles]

            # Calculate EMA
            ema = closes[0]
            multiplier = 2 / (period + 1)

            for close in closes[1:]:
                ema = (close * multiplier) + (ema * (1 - multiplier))

            return float(ema)

        except Exception as e:
            self.logger.error(f"EMA calculation error: {str(e)}")
            return 0.0

    def calculate_atr(self, candles: List[Dict], period: int = 10) -> float:
        """Calculate ATR (Average True Range)"""
        try:
            if len(candles) < period + 1:
                return 0.0

            true_ranges = []
            for i in range(1, len(candles)):
                high = candles[i]["high"]
                low = candles[i]["low"]
                prev_close = candles[i - 1]["close"]

                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)

            atr = np.mean(true_ranges[-period:])
            return float(atr)

        except Exception as e:
            self.logger.error(f"ATR calculation error: {str(e)}")
            return 0.0

    def calculate_supertrend(self,
                           candles: List[Dict],
                           period: int = 10,
                           multiplier: float = 3.0) -> Dict[str, Any]:
        """Calculate Supertrend"""
        try:
            if len(candles) < period + 1:
                return {"value": 0.0, "direction": "NEUTRAL"}

            # Calculate ATR
            atr = self.calculate_atr(candles, period)

            # Get last candle
            last_candle = candles[-1]
            hl_avg = (last_candle["high"] + last_candle["low"]) / 2

            # Basic Supertrend calculation
            basic_upper = hl_avg + (multiplier * atr)
            basic_lower = hl_avg - (multiplier * atr)

            # Determine trend
            close = last_candle["close"]

            if close > basic_upper:
                direction = "UP"
                value = basic_lower
            elif close < basic_lower:
                direction = "DOWN"
                value = basic_upper
            else:
                direction = "NEUTRAL"
                value = hl_avg

            return {
                "value": float(value),
                "direction": direction,
                "upper": float(basic_upper),
                "lower": float(basic_lower)
            }

        except Exception as e:
            self.logger.error(f"Supertrend calculation error: {str(e)}")
            return {"value": 0.0, "direction": "NEUTRAL"}

    def get_market_data(self) -> Dict[str, Any]:
        """
        Get complete market data package for agents

        Returns:
            Dictionary containing all market data
        """
        try:
            self.logger.info("Fetching market data...")

            # Get current price
            current_price = self.get_current_price()

            # Get historical candles - 1 minute
            candles_1min = self.get_historical_candles(timeframe="1", candles=100)

            if len(candles_1min) == 0:
                self.logger.error("No candle data available")
                return {}

            # Get historical candles - 5 minute
            candles_5min = self.get_historical_candles(timeframe="5", candles=100)

            # Calculate indicators from 1-min data
            rsi = self.calculate_rsi(candles_1min, period=6)
            ema13 = self.calculate_ema(candles_1min, period=13)
            atr = self.calculate_atr(candles_1min, period=10)
            supertrend = self.calculate_supertrend(candles_1min, period=10, multiplier=3.0)

            # Calculate 5-min indicators
            rsi_5min = self.calculate_rsi(candles_5min, period=6) if len(candles_5min) > 0 else rsi
            atr_5min = self.calculate_atr(candles_5min, period=10) if len(candles_5min) > 0 else atr

            # Get price changes
            first_candle = candles_1min[0]
            last_candle = candles_1min[-1]

            price_change = last_candle["close"] - first_candle["open"]
            price_change_percent = (price_change / first_candle["open"]) * 100

            # Determine trend from 1-min
            if supertrend["direction"] == "UP":
                trend = "UPTREND"
            elif supertrend["direction"] == "DOWN":
                trend = "DOWNTREND"
            else:
                trend = "RANGING"

            # Build data package
            market_data = {
                "sentiment_data": {
                    "current_price": current_price,
                    "price_change": price_change,
                    "price_change_percent": price_change_percent,
                    "volatility": atr,
                    "candles": candles_1min[-10:],  # Last 10 candles
                    "trend": trend,
                    "rsi": rsi
                },
                "indicator_data": {
                    "price": current_price,
                    "rsi": rsi,
                    "ema": {"ema13": ema13},
                    "supertrend": supertrend,
                    "atr": atr
                },
                "price_data": {
                    "current_price": current_price,
                    "candles": candles_1min[-20:],  # Last 20 candles
                    "high_of_day": max([c["high"] for c in candles_1min]),
                    "low_of_day": min([c["low"] for c in candles_1min]),
                    "prev_close": candles_1min[-2]["close"] if len(candles_1min) > 1 else current_price,
                    "trend": trend
                },
                "trade_evaluation_data": {
                    "current_price": current_price,
                    "spot_price": current_price,
                    "candles_1min": candles_1min[-100:],  # Last 100 1-min candles
                    "candles_5min": candles_5min[-100:] if len(candles_5min) > 0 else [],  # Last 100 5-min candles
                    "atr": atr,
                    "atr_5min": atr_5min,
                    "indicators": {
                        "rsi": rsi,
                        "rsi_5min": rsi_5min,
                        "ema": {"ema13": ema13}
                    }
                }
            }

            self.logger.info(f"Market data collected: Price={current_price:.2f}, "
                           f"RSI={rsi:.2f}, Trend={trend}, "
                           f"5min candles: {len(candles_5min)}")

            return market_data

        except Exception as e:
            self.logger.error(f"Error getting market data: {str(e)}")
            return {}
