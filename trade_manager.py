"""
Trade Manager
Handles position management, order placement, and risk management
Interfaces with Fyers API for live trading
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, time
from fyers_apiv3 import fyersModel
import time as time_module


class TradeManager:
    """
    Manages trade execution, position tracking, and risk management
    """

    def __init__(self,
                 fyers_client: fyersModel.FyersModel,
                 index: str = "NIFTY",
                 lot_size: int = 75,
                 expiry_date: str = "2025-11-04",
                 initial_capital: float = 150000,
                 is_simulation: bool = True):
        """
        Initialize Trade Manager

        Args:
            fyers_client: Initialized Fyers API client
            index: Trading index (NIFTY or SENSEX)
            lot_size: Lot size for options
            expiry_date: Option expiry date (YYYY-MM-DD)
            initial_capital: Starting capital
            is_simulation: Simulation mode flag
        """
        self.fyers = fyers_client
        self.index = index
        self.lot_size = lot_size
        self.expiry_date = expiry_date
        self.initial_capital = initial_capital
        self.is_simulation = is_simulation

        # Position tracking
        self.active_position = None
        self.position_entry_price = 0.0
        self.position_quantity = 0
        self.position_type = None  # "CALL" or "PUT"
        self.position_symbol = None
        self.entry_time = None

        # Capital tracking
        self.current_capital = initial_capital
        self.available_balance = initial_capital

        # Setup logging
        self.logger = logging.getLogger("TradeManager")

        # Strike gap based on index
        self.strike_gap = 50 if index == "NIFTY" else 100

        # Symbol format
        self.index_symbol = "NSE:NIFTY50-INDEX" if index == "NIFTY" else "BSE:SENSEX-INDEX"

        self.logger.info(f"TradeManager initialized for {index} "
                        f"(Simulation: {is_simulation})")

    def get_index_spot_price(self) -> float:
        """
        Get current spot price of index

        Returns:
            Current spot price
        """
        try:
            response = self.fyers.quotes({"symbols": self.index_symbol})

            if response and response.get("s") == "ok":
                data = response.get("d", [])
                if data and len(data) > 0:
                    ltp = data[0].get("v", {}).get("lp", 0)
                    return float(ltp)

            self.logger.error(f"Failed to fetch spot price: {response}")
            return 0.0

        except Exception as e:
            self.logger.error(f"Error fetching spot price: {str(e)}")
            return 0.0

    def get_atm_strike(self, spot_price: float) -> int:
        """
        Calculate ATM (At The Money) strike price

        Args:
            spot_price: Current spot price

        Returns:
            ATM strike price
        """
        return round(spot_price / self.strike_gap) * self.strike_gap

    def build_option_symbol(self, strike: int, option_type: str) -> str:
        """
        Build option symbol for Fyers

        Args:
            strike: Strike price
            option_type: "CE" for Call or "PE" for Put

        Returns:
            Option symbol string
        """
        # Parse expiry date
        expiry = datetime.strptime(self.expiry_date, "%Y-%m-%d")
        year = expiry.strftime("%y")
        month_map = {1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
                     7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"}
        month = month_map[expiry.month][0]  # First letter
        day = expiry.strftime("%d")

        if self.index == "NIFTY":
            # Format: NSE:NIFTY25N0423500CE
            symbol = f"NSE:NIFTY{year}{month}{day}{strike}{option_type}"
        else:
            # Format: BSE:SENSEX25N84000CE
            symbol = f"BSE:SENSEX{year}{month}{strike}{option_type}"

        return symbol

    def get_option_ltp(self, symbol: str) -> float:
        """
        Get LTP (Last Traded Price) of option

        Args:
            symbol: Option symbol

        Returns:
            LTP value
        """
        try:
            response = self.fyers.quotes({"symbols": symbol})

            if response and response.get("s") == "ok":
                data = response.get("d", [])
                if data and len(data) > 0:
                    ltp = data[0].get("v", {}).get("lp", 0)
                    return float(ltp)

            return 0.0

        except Exception as e:
            self.logger.error(f"Error fetching LTP for {symbol}: {str(e)}")
            return 0.0

    def calculate_position_size(self,
                                ltp: float,
                                available_capital: float,
                                position_multiplier: float = 1.0) -> int:
        """
        Calculate position size based on available capital

        Args:
            ltp: Last traded price
            available_capital: Available capital
            position_multiplier: Multiplier for position sizing (streak-based)

        Returns:
            Quantity in lots
        """
        if ltp <= 0:
            return 0

        # Calculate usable capital (with multiplier)
        usable_capital = available_capital * position_multiplier

        # Max quantity by capital
        max_qty_by_capital = int(usable_capital / ltp)

        # Convert to lots
        quantity_in_lots = max(1, max_qty_by_capital // self.lot_size)
        quantity = quantity_in_lots * self.lot_size

        return quantity

    def place_order(self,
                   direction: str,
                   position_multiplier: float = 1.0,
                   funds_percent: float = 0.90) -> Dict[str, Any]:
        """
        Place a new order

        Args:
            direction: "CALL" or "PUT"
            position_multiplier: Position size multiplier (streak-based)
            funds_percent: Percentage of funds to use

        Returns:
            Order result dictionary
        """
        try:
            # Check if we already have an active position
            if self.active_position:
                return {
                    "success": False,
                    "error": "Active position already exists"
                }

            # Get spot price
            spot_price = self.get_index_spot_price()
            if spot_price <= 0:
                return {
                    "success": False,
                    "error": "Failed to fetch spot price"
                }

            # Get ATM strike
            atm_strike = self.get_atm_strike(spot_price)

            # Build option symbol
            option_type = "CE" if direction == "CALL" else "PE"
            option_symbol = self.build_option_symbol(atm_strike, option_type)

            # Get option LTP
            ltp = self.get_option_ltp(option_symbol)
            if ltp <= 0:
                return {
                    "success": False,
                    "error": "Failed to fetch option LTP"
                }

            # Calculate position size
            available_capital = self.available_balance * funds_percent
            quantity = self.calculate_position_size(
                ltp,
                available_capital,
                position_multiplier
            )

            if quantity <= 0:
                return {
                    "success": False,
                    "error": "Insufficient capital for trade"
                }

            # Prepare order data
            order_data = {
                "symbol": option_symbol,
                "qty": quantity,
                "type": 2,  # Market order
                "side": 1,  # Buy
                "productType": "INTRADAY",
                "limitPrice": 0,
                "stopPrice": 0,
                "validity": "DAY",
                "disclosedQty": 0,
                "offlineOrder": False,
                "stopLoss": 0,
                "takeProfit": 0
            }

            # Place order (skip if simulation)
            if not self.is_simulation:
                response = self.fyers.place_order(data=order_data)

                if response and response.get("s") == "ok":
                    order_id = response.get("id", "")
                    self.logger.info(f"Order placed: {order_id}")
                else:
                    return {
                        "success": False,
                        "error": f"Order placement failed: {response}"
                    }
            else:
                order_id = f"SIM_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                self.logger.info(f"Simulation order: {order_id}")

            # Update position tracking
            self.active_position = {
                "symbol": option_symbol,
                "quantity": quantity,
                "entry_price": ltp,
                "direction": direction,
                "order_id": order_id,
                "entry_time": datetime.now(),
                "strike": atm_strike,
                "spot_price": spot_price
            }

            self.position_entry_price = ltp
            self.position_quantity = quantity
            self.position_type = direction
            self.position_symbol = option_symbol
            self.entry_time = datetime.now()

            return {
                "success": True,
                "order_id": order_id,
                "symbol": option_symbol,
                "quantity": quantity,
                "entry_price": ltp,
                "direction": direction
            }

        except Exception as e:
            self.logger.error(f"Error placing order: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def close_position(self, exit_reason: str = "Manual") -> Dict[str, Any]:
        """
        Close the active position

        Args:
            exit_reason: Reason for exit

        Returns:
            Exit result dictionary
        """
        try:
            if not self.active_position:
                return {
                    "success": False,
                    "error": "No active position to close"
                }

            # Get current LTP
            current_ltp = self.get_option_ltp(self.position_symbol)
            if current_ltp <= 0:
                self.logger.warning("Failed to fetch current LTP, using last known price")
                current_ltp = self.position_entry_price

            # Calculate P&L
            entry_value = self.position_entry_price * self.position_quantity
            exit_value = current_ltp * self.position_quantity
            pnl = exit_value - entry_value
            pnl_percent = (pnl / entry_value) * 100 if entry_value > 0 else 0

            # Prepare exit order
            order_data = {
                "symbol": self.position_symbol,
                "qty": self.position_quantity,
                "type": 2,  # Market order
                "side": -1,  # Sell
                "productType": "INTRADAY",
                "limitPrice": 0,
                "stopPrice": 0,
                "validity": "DAY",
                "disclosedQty": 0,
                "offlineOrder": False
            }

            # Place exit order (skip if simulation)
            if not self.is_simulation:
                response = self.fyers.place_order(data=order_data)

                if response and response.get("s") == "ok":
                    exit_order_id = response.get("id", "")
                    self.logger.info(f"Exit order placed: {exit_order_id}")
                else:
                    return {
                        "success": False,
                        "error": f"Exit order failed: {response}"
                    }
            else:
                exit_order_id = f"SIM_EXIT_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                self.logger.info(f"Simulation exit: {exit_order_id}")

            # Update capital
            self.current_capital += pnl
            self.available_balance = self.current_capital

            # Store trade info before clearing
            trade_info = {
                "success": True,
                "symbol": self.position_symbol,
                "direction": self.position_type,
                "quantity": self.position_quantity,
                "entry_price": self.position_entry_price,
                "exit_price": current_ltp,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "exit_reason": exit_reason,
                "exit_order_id": exit_order_id,
                "holding_duration": (datetime.now() - self.entry_time).total_seconds() / 10
            }

            # Clear position
            self.active_position = None
            self.position_entry_price = 0.0
            self.position_quantity = 0
            self.position_type = None
            self.position_symbol = None
            self.entry_time = None

            self.logger.info(f"Position closed: P&L = ₹{pnl:.2f} ({pnl_percent:+.2f}%)")

            return trade_info

        except Exception as e:
            self.logger.error(f"Error closing position: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_current_pnl(self) -> Dict[str, Any]:
        """
        Get current P&L of active position

        Returns:
            P&L information
        """
        if not self.active_position:
            return {
                "has_position": False,
                "pnl": 0.0,
                "pnl_percent": 0.0
            }

        try:
            # Get current LTP
            current_ltp = self.get_option_ltp(self.position_symbol)
            if current_ltp <= 0:
                return {
                    "has_position": True,
                    "error": "Failed to fetch current LTP"
                }

            # Calculate P&L
            entry_value = self.position_entry_price * self.position_quantity
            current_value = current_ltp * self.position_quantity
            pnl = current_value - entry_value
            pnl_percent = (pnl / entry_value) * 100 if entry_value > 0 else 0

            return {
                "has_position": True,
                "current_price": current_ltp,
                "entry_price": self.position_entry_price,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "quantity": self.position_quantity,
                "symbol": self.position_symbol
            }

        except Exception as e:
            self.logger.error(f"Error calculating P&L: {str(e)}")
            return {
                "has_position": True,
                "error": str(e)
            }

    def has_active_position(self) -> bool:
        """Check if there's an active position"""
        return self.active_position is not None

    def get_position_info(self) -> Optional[Dict[str, Any]]:
        """Get active position information"""
        return self.active_position
