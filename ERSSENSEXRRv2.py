#!/usr/bin/env python3
import asyncio
import configparser
import csv
import functools
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, time as dtime, timedelta
import pandas as pd
import numpy as np
import requests


# Import Fyers API model (ensure fyers_apiv3 is installed and configured)
from fyers_apiv3 import fyersModel
from db_utils import log_status, init_database

requested_symbols = set()

# REMOVED: subscribe_to_websocket_symbol function - not needed with API

# -------------------------
# Logging Setup
# -------------------------
import os

# Create logs directory if it doesn't exist
logs_dir = "logs"
os.makedirs(logs_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(logs_dir, "fyers_renko_channel.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# Trade Journey Logger Setup
# -------------------------
trade_journey_logger = logging.getLogger('trade_journey')
trade_journey_handler = logging.FileHandler(os.path.join(logs_dir, "trade_journey.log"))
trade_journey_formatter = logging.Formatter("%(asctime)s - %(message)s")
trade_journey_handler.setFormatter(trade_journey_formatter)
trade_journey_logger.addHandler(trade_journey_handler)
trade_journey_logger.setLevel(logging.INFO)
trade_journey_logger.propagate = False

SYMBOL = "BSE:SENSEX-INDEX"
EXPIRY_DATE = "2025-10-30"


# -------------------------
# Global Trading Settings
# -------------------------
TRADE_FUNDS_PERCENT = 0.90   # Percentage of available funds to use for trading
MAX_TRADES = 100
LOT_SIZE = 20             # Base lot size for options
LOSS_LIMIT = -5.0          # Stop at 15% loss
PROFIT_LIMIT = 12.0         # Stop at 60% profit
DUMMY_CAPITAL = 150000.0    # Dummy capital for simulation

# -------------------------
# Global variables
# -------------------------
cumulative_pct = 0.0
cumulative_pnl = 0.0
initial_capital = None
last_trend = None
is_simulation = True
simulated_capital = DUMMY_CAPITAL
#ENABLE_NIFTY_SPOT_EXIT = False
#ENABLE_TRAILING_STOP_EXIT = False
#TRAILING_THRESHOLD = 1.5
#TRAILING_DISTANCE = 2.0
ENABLE_TARGET_EXIT = True
TARGET_PROFIT_PERCENT = 5.0
INITIAL_STOP_LOSS_PERCENT = -3.0   # Initial SL at -3%
TRAILING_STOP_DISTANCE = 3.0        # SL trails 3% below highest profit
STRATEGY_START_TIME = dtime(9, 40)
STRATEGY_END_TIME = dtime(14, 50)
ENABLE_FIXED_STOP_LOSS = False
NEGATIVE_TRAILING_THRESHOLD = -2.5  # Activate negative trail at -2.5% loss
NEGATIVE_TRAILING_DISTANCE = 2.0
TARGET_NIFTY_POINTS_CALL = 11
TARGET_NIFTY_POINTS_PUT = 9
ENABLE_NIFTY_POINTS_TARGET = False
subscription_requested = set()
requested_symbols = set()
# -------------------------
# Strategy Indicator Settings
# -------------------------
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 3
EMA_13_PERIOD = 13
RSI_PERIOD = 6
RSI_OVERBOUGHT = 72
RSI_OVERSOLD = 28
MIN_CANDLES_FOR_INDICATORS = 20  # Minimum candles needed for all indicators
# Strategy state tracking
previous_rsi = None
last_candle_timestamp = None  # Track to avoid duplicate signals on same candle


# Global state for trade tracking
trade_count = 0
current_trade = None
current_position = None
option_symbol = None
current_instrument = None
current_quantity = None

# Global variables for Fyers API
ACCESS_TOKEN = None
available_balance = None
index_instrument = None
fyers = None
config = None

# -------------------------
# Retry Decorator
# -------------------------
def retry(exceptions, tries=3, delay=1, backoff=2):
    def decorator_retry(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _tries, _delay = tries, delay
            while _tries > 1:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    logger.warning(f"{func.__name__} failed with {e}. Retrying in {_delay} seconds...")
                    time.sleep(_delay)
                    _tries -= 1
                    _delay *= backoff
            return func(*args, **kwargs)
        return wrapper
    return decorator_retry

# -------------------------
# API Helper Functions - DIRECT API CALLS
# -------------------------
@retry((Exception,), tries=3, delay=1, backoff=2)
def safe_api_call(api_func, *args, **kwargs):
    """Safely call Fyers API with retry logic"""
    result = api_func(*args, **kwargs)
    if isinstance(result, dict):
        if result.get("code") != 200 and result.get("s") != "ok":
            error_msg = result.get("message", "Unknown API error")
            logger.error(f"API Error: {error_msg}")
            raise Exception(f"API call failed: {error_msg}")
    return result

def get_nifty_spot():
    """Get current Nifty/Sensex spot price via API"""
    try:
        quotes_data = {
            "symbols": index_instrument["symbol"]
        }
        result = safe_api_call(fyers.quotes, data=quotes_data)
        
        if result and "d" in result and len(result["d"]) > 0:
            ltp = result["d"][0]["v"]["lp"]
            logger.info(f"Spot price for {index_instrument['symbol']}: {ltp}")
            return float(ltp)
        return None
    except Exception as e:
        logger.error(f"Error fetching spot price via API: {e}")
        return None

def get_ltp(inst):
    """Get Last Traded Price for a symbol via API - NO WEBSOCKET"""
    symbol = inst["symbol"]
    
    try:
        quotes_data = {"symbols": symbol}
        result = safe_api_call(fyers.quotes, data=quotes_data)
        
        if result and "d" in result and len(result["d"]) > 0:
            ltp = result["d"][0]["v"]["lp"]
            logger.info(f"LTP for {symbol}: {ltp} (API)")
            return float(ltp)
        return None
    except Exception as e:
        logger.error(f"Error fetching LTP for {symbol} via API: {e}")
        return None

def get_historical_candle_fyers(symbol, resolution, from_time, to_time):
    """Fetch historical candles via API"""
    try:
        data = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "0",
            "range_from": str(from_time),
            "range_to": str(to_time),
            "cont_flag": "1"
        }
        resp = safe_api_call(fyers.history, data=data)
        return resp if resp else {}
    except Exception as e:
        logger.error(f"Error fetching historical candles via API for {symbol}: {e}")
        return {}

def get_custom_expiry_date():
    """
    Get the expiry date from the hardcoded value.
    Returns the date in YYYY-MM-DD format.
    """
    logging.info(f"Using hardcoded expiry date: {EXPIRY_DATE}")
    return EXPIRY_DATE

def format_symbol(strike, expiry_date, option_type):
    """
    Format the option symbol for BSE SENSEX options
    Example: BSE:SENSEX25O3084000CE
    Format: BSE:SENSEX[YY][M][DD][STRIKE][CE/PE]
    """
    try:
        expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d")
        yy = expiry_dt.strftime("%y")
        month_code_map = {
            1: '1', 2: '2', 3: '3', 4: '4', 5: '5', 6: '6',
            7: '7', 8: '8', 9: '9', 10: 'OCT', 11: 'N', 12: 'D'
        }
        month_code = month_code_map[expiry_dt.month]
        dd = expiry_dt.strftime("%d")
        #symbol = f"BSE:SENSEX{yy}{month_code}{dd}{int(strike)}{option_type}" #week
        symbol = f"BSE:SENSEX{yy}{month_code}{int(strike)}{option_type}" #Month
        logging.info(f"Formatted symbol: {symbol}")
        return symbol
    except Exception as e:
        logging.error(f"Error formatting symbol: {e}")
        return None

def get_atm_options_for_index(expiry_date, spot_price=None, strike_gap=100):
    """
    Finds ATM Call and Put options based on spot price
    """
    if spot_price is None:
        spot_price = get_nifty_spot()
        if spot_price is None:
            logging.error("Could not determine spot price")
            return None, None

    atm_strike = round(spot_price / strike_gap) * strike_gap
    logging.info(f"Spot: {spot_price}, ATM Strike: {atm_strike}")

    call_symbol = format_symbol(atm_strike, expiry_date, "CE")
    put_symbol = format_symbol(atm_strike, expiry_date, "PE")

    if not call_symbol or not put_symbol:
        logging.error("Symbol formatting failed")
        return None, None

    call_inst, put_inst = None, None

    # Fetch LTP data for both options
    call_data = safe_api_call(fyers.quotes, {"symbols": call_symbol})
    put_data = safe_api_call(fyers.quotes, {"symbols": put_symbol})

    # Process call option if valid
    if call_data and call_data.get("d") and len(call_data["d"]) > 0:
        call_ltp = call_data["d"][0].get("v", {}).get("lp")
        if call_ltp:
            call_inst = {
                "exchange": "BSE_FO",
                "symbol": call_symbol,
                "instrument_key": call_symbol,
                "expiry": expiry_date,
                "strike": atm_strike
            }
            logging.info(f"Found valid call option: {call_symbol} with LTP {call_ltp}")
    else:
        logging.error(f"Call option {call_symbol} not found or invalid")

    # Process put option if valid
    if put_data and put_data.get("d") and len(put_data["d"]) > 0:
        put_ltp = put_data["d"][0].get("v", {}).get("lp")
        if put_ltp:
            put_inst = {
                "exchange": "BSE_FO",
                "symbol": put_symbol,
                "instrument_key": put_symbol,
                "expiry": expiry_date,
                "strike": atm_strike
            }
            logging.info(f"Found valid put option: {put_symbol} with LTP {put_ltp}")
    else:
        logging.error(f"Put option {put_symbol} not found or invalid")

    return call_inst, put_inst

# -------------------------
# Order Management Functions
# -------------------------
def place_order(direction, expiry_date, strategy_name, funds_percent=TRADE_FUNDS_PERCENT):
    """
    Place an order for options (Call or Put)
    """
    global option_symbol, is_simulation, available_balance, simulated_capital
    
    try:
        # Get ATM options
        spot_price = get_nifty_spot()
        if spot_price is None:
            logger.error("Failed to get spot price for option selection")
            return None, None, None, None

        call_inst, put_inst = get_atm_options_for_index(expiry_date, spot_price)
        
        if direction == "CALL":
            inst = call_inst
        elif direction == "PUT":
            inst = put_inst
        else:
            logger.error(f"Invalid direction: {direction}")
            return None, None, None, None

        if inst is None:
            logger.error(f"Failed to get {direction} instrument")
            return None, None, None, None

        option_symbol = inst["symbol"]
        
        # Get current LTP
        ltp = get_ltp(inst)
        if ltp is None:
            logger.error(f"Could not fetch LTP for {option_symbol}")
            return None, None, None, None

        # Calculate quantity
        capital = simulated_capital if is_simulation else available_balance
        usable_capital = capital * funds_percent
        
        max_quantity_by_capital = int(usable_capital / ltp)
        quantity_in_lots = max(1, max_quantity_by_capital // LOT_SIZE)
        quantity = quantity_in_lots * LOT_SIZE

        logger.info(f"Order Details: Symbol={option_symbol}, LTP={ltp:.2f}, Qty={quantity}")

        if is_simulation:
            logger.info(f"SIMULATION: Would place BUY order for {quantity} units at {ltp:.2f}")
            return inst, ltp, quantity, None
        else:
            # Place actual order
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
            
            response = safe_api_call(fyers.place_order, data=order_data)
            
            if response and response.get("s") == "ok":
                order_id = response.get("id")
                logger.info(f"Order placed successfully. Order ID: {order_id}")
                return inst, ltp, quantity, order_id
            else:
                logger.error(f"Order placement failed: {response}")
                return None, None, None, None

    except Exception as e:
        logger.error(f"Error in place_order: {e}")
        return None, None, None, None

async def confirm_and_update_entry_price(order_id, expected_entry, instrument):
    """Confirm order and update entry price if needed"""
    try:
        await asyncio.sleep(2)
        
        if is_simulation:
            logger.info("SIMULATION: Order confirmation skipped")
            return

        order_data = {"id": order_id}
        order_status = safe_api_call(fyers.orderbook, data=order_data)

        if order_status and "orderBook" in order_status:
            for order in order_status["orderBook"]:
                if order.get("id") == order_id:
                    status = order.get("status")
                    traded_price = order.get("tradedPrice", expected_entry)
                    
                    if status == 2:  # Filled
                        if current_trade and traded_price != expected_entry:
                            logger.info(f"Entry price updated: {expected_entry:.2f} -> {traded_price:.2f}")
                            current_trade["entry_price"] = traded_price
                    break

    except Exception as e:
        logger.error(f"Error confirming order: {e}")

def close_position(inst, qty, exit_reason="Manual"):
    """Close position"""
    global is_simulation, simulated_capital
    
    try:
        symbol = inst["symbol"]
        ltp = get_ltp(inst)
        
        if ltp is None:
            logger.error(f"Could not fetch LTP for {symbol}")
            return None

        logger.info(f"Closing position: {symbol} x {qty} at {ltp:.2f}")

        if is_simulation:
            logger.info(f"SIMULATION: Would SELL {qty} units of {symbol} at {ltp:.2f}")
            
            if current_trade:
                entry_price = current_trade["entry_price"]
                pnl = (ltp - entry_price) * qty
                pnl_pct = ((ltp - entry_price) / entry_price) * 100
                
                simulated_capital += pnl
                logger.info(f"Simulated P&L: {pnl:.2f} INR ({pnl_pct:.2f}%)")
                logger.info(f"Updated simulated capital: {simulated_capital:.2f}")
            
            return ltp
        else:
            order_data = {
                "symbol": symbol,
                "qty": qty,
                "type": 2,
                "side": -1,
                "productType": "INTRADAY",
                "limitPrice": 0,
                "stopPrice": 0,
                "validity": "DAY",
                "disclosedQty": 0,
                "offlineOrder": False,
                "stopLoss": 0,
                "takeProfit": 0
            }
            
            response = safe_api_call(fyers.place_order, data=order_data)
            
            if response and response.get("s") == "ok":
                logger.info(f"Exit order placed successfully")
                return ltp
            else:
                logger.error(f"Exit order failed: {response}")
                return None

    except Exception as e:
        logger.error(f"Error closing position: {e}")
        return None

def partial_exit(inst, total_qty, exit_percent, exit_reason="Partial Exit"):
    """Exit partial position"""
    exit_qty = int(total_qty * exit_percent)
    
    if exit_qty <= 0:
        logger.warning(f"Invalid partial exit quantity: {exit_qty}")
        return []

    logger.info(f"Partial exit: {exit_percent*100:.0f}% ({exit_qty} units)")
    
    ltp = get_ltp(inst)
    if ltp is None:
        logger.error("Could not fetch LTP for partial exit")
        return []

    responses = []
    remaining = exit_qty

    while remaining > 0:
        qty = min(remaining, 1800)
        
        order_payload = {
            "symbol": inst["symbol"],
            "qty": qty,
            "type": 2,
            "side": -1,
            "productType": "INTRADAY",
            "limitPrice": 0,
            "stopPrice": 0,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
            "stopLoss": 0,
            "takeProfit": 0
        }
        try:
            resp = safe_api_call(fyers.place_order, order_payload)
            responses.append(resp)
            logger.info(f"Partial exit order for {qty} units placed.")
        except Exception as e:
            logger.error(f"Error placing partial exit order: {e}")
        remaining -= qty

    return responses

# -------------------------
# Helper Functions for Data & Indicators
# -------------------------
def structure_candle_df(candles):
    """Convert raw candle data to DataFrame with proper structure"""
    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])

    if not df.empty:
        # Convert timestamp to datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
        # Add date column for compatibility
        df["date"] = df["timestamp"]

        # Ensure numeric types
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Remove any NaN values
        df = df.dropna()

    return df

def sort_df_chronologically(df):
    """Sort dataframe by timestamp"""
    if "timestamp" in df.columns:
        df = df.sort_values(by="timestamp").reset_index(drop=True)
    return df

# -----------------------------
# Helper Functions for Trading Logic
# -----------------------------

def check_nifty_exit_condition(entry_spot_price, current_position):
    """
    Check if Nifty spot has moved to trigger target or stop loss.
    Returns dict with exit information.

    Args:
        entry_spot_price: Nifty spot price at trade entry
        current_position: "CALL" or "PUT"

    Returns:
        dict: {
            'exit_triggered': bool,
            'type': 'target'/'stop_loss',
            'reason': str,
            'spot_movement': float
        }
    """
    try:
        current_spot = get_nifty_spot()
        if current_spot is None:
            logger.warning("Failed to get current Nifty spot price for exit check")
            return {'exit_triggered': False, 'type': None, 'reason': None, 'spot_movement': 0}

        spot_movement = current_spot - entry_spot_price
        logger.info(f"Nifty spot movement from entry: {spot_movement:.2f} points")

        # Define target and stop loss points
        TARGET_POINTS = 11.0  # Or use your TARGET_NIFTY_POINTS_CALL/PUT
        STOP_LOSS_POINTS = 9.0

        if current_position == "CALL":
            # CALL Target: +11 points (profit)
            if spot_movement >= TARGET_POINTS:
                return {
                    'exit_triggered': True,
                    'type': 'target',
                    'reason': f'Nifty moved +{spot_movement:.2f} points (Target: +{TARGET_POINTS})',
                    'spot_movement': spot_movement
                }
            # CALL Stop Loss: -9 points (loss)
            elif spot_movement <= -STOP_LOSS_POINTS:
                return {
                    'exit_triggered': True,
                    'type': 'stop_loss',
                    'reason': f'Nifty moved {spot_movement:.2f} points (Stop: -{STOP_LOSS_POINTS})',
                    'spot_movement': spot_movement
                }

        elif current_position == "PUT":
            # PUT Target: -11 points (profit)
            if spot_movement <= -TARGET_POINTS:
                return {
                    'exit_triggered': True,
                    'type': 'target',
                    'reason': f'Nifty moved {spot_movement:.2f} points (Target: -{TARGET_POINTS})',
                    'spot_movement': spot_movement
                }
            # PUT Stop Loss: +9 points (loss)
            elif spot_movement >= STOP_LOSS_POINTS:
                return {
                    'exit_triggered': True,
                    'type': 'stop_loss',
                    'reason': f'Nifty moved +{spot_movement:.2f} points (Stop: +{STOP_LOSS_POINTS})',
                    'spot_movement': spot_movement
                }

        return {'exit_triggered': False, 'type': None, 'reason': None, 'spot_movement': spot_movement}

    except Exception as e:
        logger.error(f"Error in check_nifty_exit_condition: {e}")
        return {'exit_triggered': False, 'type': None, 'reason': None, 'spot_movement': 0}

TRADE_CSV = os.path.join(logs_dir, "ERSSRRv2.csv")

def record_trade(trade_data, simulated=True):
    """Record trade to CSV"""
    file_exists = os.path.exists(TRADE_CSV)
    trade_record = {
        "timestamp": trade_data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "strategy": "ERSSRRv2",
        "position": trade_data.get("position", ""),
        "entry_time": trade_data.get("entry_time", ""),
        "exit_time": trade_data.get("exit_time", ""),
        "entry_price": trade_data.get("entry_price", 0),
        "exit_price": trade_data.get("exit_price", 0),
        "max_high": trade_data.get("max_high", 0),
        "max_high_pct": trade_data.get("max_high_pct", 0),
        "max_low": trade_data.get("max_low", 0),
        "max_low_pct": trade_data.get("max_low_pct", 0),
        "current_pct": trade_data.get("current_pct", 0),
        "quantity": trade_data.get("quantity", 0),
        "pnl": trade_data.get("pnl", 0),
        "info": trade_data.get("info", ""),
    }
    fieldnames = ["timestamp", "strategy", "position", "entry_time", "exit_time",
                  "entry_price", "exit_price", "max_high", "max_high_pct", "max_low",
                  "max_low_pct", "current_pct", "quantity", "pnl", "info"]
    with open(TRADE_CSV, "a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(trade_record)
    logger.info(f"{'Simulated ' if simulated else ''}Trade recorded: {trade_record}")

# -------------------------
# P&L Limit Check
# -------------------------
def check_pnl_limits():
    global cumulative_pnl, initial_capital, simulated_capital, is_simulation
    capital = simulated_capital if is_simulation else initial_capital
    if capital is None or capital == 0:
        logger.error("Capital not set or zero. Cannot check P&L limits.")
        return
    cumulative_pct = (cumulative_pnl / capital) * 100
    logger.info(f"Cumulative P&L: {cumulative_pnl:.2f} INR ({cumulative_pct:.2f}% of {'simulated' if is_simulation else 'initial'} capital {capital:.2f})")
    if cumulative_pct <= LOSS_LIMIT:
        logger.info(f"Cumulative loss reached {LOSS_LIMIT}% of {'simulated' if is_simulation else 'initial'} capital. Stopping script.")
        exit(0)
    elif cumulative_pct >= PROFIT_LIMIT:
        logger.info(f"Cumulative profit reached {PROFIT_LIMIT}% of {'simulated' if is_simulation else 'initial'} capital. Stopping script.")
        exit(0)

# -------------------------
# Periodic Range Check Function


def get_candle_oc_range(candle_data):
    """Calculate open-close range for a candle"""
    return abs(candle_data['close'] - candle_data['open'])

def get_candle_color(candle_data):
    """Determine candle color"""
    return "GREEN" if candle_data['close'] > candle_data['open'] else "RED"

def is_candle_complete(candle_timestamp):
    """Check if a 1-minute candle is complete (at least 5 seconds past the minute)"""
    current_time = pd.Timestamp.now()
    candle_end_time = pd.Timestamp(candle_timestamp).ceil('1min')
    buffer_time = candle_end_time + pd.Timedelta(seconds=1)
    return current_time >= buffer_time

def calculate_atr(df, period=10):
    """
    Calculate Average True Range for Supertrend

    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        period: ATR period (default 10)

    Returns:
        pandas Series with ATR values
    """
    # Calculate True Range components
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())

    # True Range is the maximum of the three
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    # ATR is the moving average of True Range
    atr = true_range.rolling(window=period).mean()

    return atr

def calculate_supertrend(df, period=10, multiplier=3):
    """
    Calculate Supertrend indicator

    Args:
        df: DataFrame with OHLC data
        period: ATR period (default 10)
        multiplier: ATR multiplier (default 3)

    Returns:
        DataFrame with 'supertrend' and 'supertrend_direction' columns added
        direction: 1 = bullish (price above ST), -1 = bearish (price below ST)
    """
    df = df.copy()

    # Calculate ATR
    atr = calculate_atr(df, period)

    # Calculate basic upper and lower bands
    hl_avg = (df['high'] + df['low']) / 2
    basic_upper = hl_avg + (multiplier * atr)
    basic_lower = hl_avg - (multiplier * atr)

    # Initialize arrays
    final_upper = [0.0] * len(df)
    final_lower = [0.0] * len(df)
    supertrend = [0.0] * len(df)
    direction = [1] * len(df)

    # Calculate Supertrend with proper band adjustment
    for i in range(period, len(df)):
        curr_basic_upper = basic_upper.iloc[i]
        curr_basic_lower = basic_lower.iloc[i]
        prev_close = df['close'].iloc[i-1]
        curr_close = df['close'].iloc[i]

        # Adjust upper band - compare with PREVIOUS FINAL band
        if i == period:
            final_upper[i] = curr_basic_upper
        else:
            if curr_basic_upper < final_upper[i-1] or prev_close > final_upper[i-1]:
                final_upper[i] = curr_basic_upper
            else:
                final_upper[i] = final_upper[i-1]

        # Adjust lower band - compare with PREVIOUS FINAL band
        if i == period:
            final_lower[i] = curr_basic_lower
        else:
            if curr_basic_lower > final_lower[i-1] or prev_close < final_lower[i-1]:
                final_lower[i] = curr_basic_lower
            else:
                final_lower[i] = final_lower[i-1]

        # Determine direction and supertrend value
        if i > period:
            prev_direction = direction[i-1]

            # If previous direction was bullish (1)
            if prev_direction == 1:
                if curr_close <= final_lower[i]:
                    direction[i] = -1
                    supertrend[i] = final_upper[i]
                else:
                    direction[i] = 1
                    supertrend[i] = final_lower[i]
            # If previous direction was bearish (-1)
            else:
                if curr_close >= final_upper[i]:
                    direction[i] = 1
                    supertrend[i] = final_lower[i]
                else:
                    direction[i] = -1
                    supertrend[i] = final_upper[i]
        else:
            # Initial direction based on close vs bands
            if curr_close > final_upper[i]:
                direction[i] = 1
                supertrend[i] = final_lower[i]
            else:
                direction[i] = -1
                supertrend[i] = final_upper[i]

    df['supertrend'] = supertrend
    df['supertrend_direction'] = direction

    return df


def calculate_rsi(df, period=6):
    """Calculate RSI indicator"""
    if len(df) < period + 1:
        return None

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi.iloc[-1]

def calculate_ema(df, period=9):
    """Calculate EMA for the given period"""
    if len(df) < period:
        return None

    # Calculate EMA using pandas
    ema_values = df['close'].ewm(span=period, adjust=False).mean()
    return ema_values.iloc[-1]  # Return the latest EMA value

# ADD this new function (after other helper functions):
def get_ema_direction(current_ema, previous_ema):
    """Determine EMA direction based on Pine Script logic"""
    if current_ema >= previous_ema:
        return "GREEN"
    else:
        return "RED"

# Trading Logic: Renko & Supertrend with Brick Reversal Exit
# Trading Logic: Simplified Trailing Stop System
async def monitor_active_trade():
    """Continuous monitoring for active trades with trailing stop loss system"""
    global current_trade, current_position, current_instrument, current_quantity
    global cumulative_pnl, cumulative_pct, simulated_capital, trade_count, option_symbol

    # Safety check: Ensure all required variables are set
    if current_trade is None or current_instrument is None or current_quantity is None:
        logger.error("Monitor called but trade variables not properly initialized!")
        return

    while current_trade is not None:
        current_price = get_ltp(current_instrument)
        if current_price is None:
            logger.warning("LTP fetch failed. Retrying in 2 seconds...")
            await asyncio.sleep(2)
            continue

        entry_price = current_trade["entry_price"]
        current_pct = ((current_price - entry_price) / entry_price) * 100
        current_trade["current_pct"] = current_pct

        logger.info(f"Current Option Price: {current_price:.2f} ({current_pct:+.2f}%) for {option_symbol}")

        # Log significant price movements
        if not hasattr(current_trade, 'last_logged_pct'):
            current_trade['last_logged_pct'] = 0
            current_trade['last_log_time'] = datetime.now()

        if abs(current_pct - current_trade['last_logged_pct']) >= 0.5 or \
                (datetime.now() - current_trade['last_log_time']).seconds >= 30:
            log_status("ERSSRRv2", "trading", f"Live: {current_price:.2f} ({current_pct:+.1f}%)",
                       {"position": current_position, "price": current_price, "pnl": current_price - entry_price, "pnl_pct": current_pct})
            trade_journey_logger.info(f"  {datetime.now().strftime('%H:%M:%S')} - Price: {current_price:.2f} ({current_pct:+.2f}%)")
            current_trade['last_logged_pct'] = current_pct
            current_trade['last_log_time'] = datetime.now()

        # Update max high and low (for tracking purposes)
        if "max_high" not in current_trade or current_price > current_trade["max_high"]:
            current_trade["max_high"] = current_price
            current_trade["max_high_pct"] = current_pct
            logger.info(f"New Max High: {current_trade['max_high']:.2f} ({current_trade['max_high_pct']:.2f}%)")

        if "max_low" not in current_trade or current_price < current_trade["max_low"]:
            current_trade["max_low"] = current_price
            current_trade["max_low_pct"] = current_pct
            logger.info(f"New Max Low: {current_trade['max_low']:.2f} ({current_trade['max_low_pct']:.2f}%)")

        # ==============================================
        # NEW TRAILING STOP LOSS SYSTEM
        # ==============================================

        # Initialize trailing stop system on first iteration
        if "trailing_stop_loss" not in current_trade:
            current_trade["trailing_stop_loss"] = INITIAL_STOP_LOSS_PERCENT  # -3%
            current_trade["highest_profit_pct"] = 0.0
            logger.info(f"Trailing stop initialized at {current_trade['trailing_stop_loss']:.2f}%")
            trade_journey_logger.info(f"Initial Stop Loss: {current_trade['trailing_stop_loss']:.2f}%")

        # Update trailing stop when new profit high is reached
        if current_pct > current_trade["highest_profit_pct"]:
            old_highest = current_trade["highest_profit_pct"]
            old_stop = current_trade["trailing_stop_loss"]

            current_trade["highest_profit_pct"] = current_pct
            current_trade["trailing_stop_loss"] = current_pct - TRAILING_STOP_DISTANCE

            logger.info(f" NEW HIGH PROFIT: {current_pct:.2f}% (previous: {old_highest:.2f}%)")
            logger.info(f"Stop Loss TRAILED: {old_stop:.2f}% -> {current_trade['trailing_stop_loss']:.2f}%")
            trade_journey_logger.info(f"  Profit High: {current_pct:.2f}% | SL trailed to: {current_trade['trailing_stop_loss']:.2f}%")

        # Exit condition checks
        exit_triggered = False
        exit_reason = ""
        exit_price = current_price

        # Check trailing stop loss
        if current_pct <= current_trade["trailing_stop_loss"]:
            exit_triggered = True
            exit_reason = f"Trailing Stop Hit at {current_pct:.2f}% (SL: {current_trade['trailing_stop_loss']:.2f}%)"
            logger.info(f" {exit_reason}")

        # Optional: Check target profit
        if ENABLE_TARGET_EXIT and current_pct >= current_trade.get("target_profit", TARGET_PROFIT_PERCENT):
            exit_triggered = True
            exit_reason = f"Target Profit Reached: {current_pct:.2f}%"
            logger.info(f" {exit_reason}")

        # Execute exit if triggered
        if exit_triggered:
            logger.info("")
            logger.info("="*80)
            logger.info(f" EXIT SIGNAL: {exit_reason}")
            logger.info("="*80)
            logger.info("")

            # Close position
            exit_price = close_position(current_instrument, current_quantity, exit_reason)

            if exit_price:
                # Calculate final P&L
                pnl = (exit_price - entry_price) * current_quantity
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100

                # Update global P&L
                cumulative_pnl += pnl
                trade_count += 1

                # Log to trade journey
                trade_journey_logger.info("")
                trade_journey_logger.info("="*60)
                trade_journey_logger.info(f"TRADE #{trade_count} - EXIT")
                trade_journey_logger.info(f"Exit Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                trade_journey_logger.info(f"Exit Price: {exit_price:.2f}")
                trade_journey_logger.info(f"Exit Reason: {exit_reason}")
                trade_journey_logger.info(f"Entry Price: {entry_price:.2f}")
                trade_journey_logger.info(f"Max High: {current_trade['max_high']:.2f} ({current_trade['max_high_pct']:.2f}%)")
                trade_journey_logger.info(f"Max Low: {current_trade['max_low']:.2f} ({current_trade['max_low_pct']:.2f}%)")
                trade_journey_logger.info(f"Final P&L: {pnl:.2f} INR ({pnl_pct:.2f}%)")
                trade_journey_logger.info(f"Cumulative P&L: {cumulative_pnl:.2f} INR")
                trade_journey_logger.info("="*60)
                trade_journey_logger.info("")

                # Record trade
                trade_data = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "position": current_position,
                    "entry_time": current_trade["entry_time"],
                    "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "max_high": current_trade.get("max_high", exit_price),
                    "max_high_pct": current_trade.get("max_high_pct", 0),
                    "max_low": current_trade.get("max_low", exit_price),
                    "max_low_pct": current_trade.get("max_low_pct", 0),
                    "current_pct": pnl_pct,
                    "quantity": current_quantity,
                    "pnl": pnl,
                    "info": exit_reason
                }
                record_trade(trade_data, simulated=is_simulation)

                # Update status
                log_status("ERSSRRv2", "waiting",
                           f"Trade closed: {exit_reason}",
                           {"pnl": pnl, "pnl_pct": pnl_pct, "total_pnl": cumulative_pnl})

                # Reset trade variables
                current_trade = None
                current_position = None
                current_instrument = None
                current_quantity = None
                option_symbol = None

                # Check P&L limits
                check_pnl_limits()

                logger.info(f"Trade #{trade_count} complete. Waiting for next signal...")
                logger.info("")
                break

        # Wait before next monitoring iteration
        await asyncio.sleep(2)

async def monitor_and_trade():
    """Main trading loop with Supertrend + EMA + RSI entry signals"""
    global current_trade, current_position, current_instrument, current_quantity
    global option_symbol, trade_count, cumulative_pnl, last_trend, previous_rsi, last_candle_timestamp

    try:
        logger.info("="*80)
        logger.info("Starting SUPERTREND + EMA + RSI REVERSAL Strategy")
        logger.info("="*80)
        logger.info(f"Index: {index_instrument['symbol']}")
        logger.info(f"Supertrend: Period={SUPERTREND_PERIOD}, Multiplier={SUPERTREND_MULTIPLIER}")
        logger.info(f"EMA: Period={EMA_13_PERIOD}")
        logger.info(f"RSI: Period={RSI_PERIOD}, Oversold={RSI_OVERSOLD}, Overbought={RSI_OVERBOUGHT}")
        logger.info(f"Trading Hours: {STRATEGY_START_TIME.strftime('%H:%M')} to {STRATEGY_END_TIME.strftime('%H:%M')}")
        logger.info(f"Initial Stop Loss: {INITIAL_STOP_LOSS_PERCENT}%")
        logger.info(f"Trailing Distance: {TRAILING_STOP_DISTANCE}%")
        logger.info("="*80)
        logger.info("")

        log_status("ERSSRRv2", "starting", "Strategy initialized")

        # Wait for trading hours
        while True:
            now = datetime.now()
            current_time = now.time()

            if current_time < STRATEGY_START_TIME:
                wait_seconds = (datetime.combine(now.date(), STRATEGY_START_TIME) - now).total_seconds()
                logger.info(f"Market opens in {wait_seconds/60:.1f} minutes. Waiting...")
                log_status("ERSSRRv2", "waiting", f"Market opens in {wait_seconds/60:.0f}min")
                await asyncio.sleep(min(wait_seconds, 60))
                continue

            if current_time >= STRATEGY_END_TIME:
                logger.info("Trading hours ended")
                log_status("ERSSRRv2", "stopped", "Trading hours ended")
                break

            # Main trading logic
            if current_trade is None:
                # Fetch candles for index
                symbol = index_instrument["symbol"]
                current_time_unix = int(datetime.now().timestamp())
                from_time = current_time_unix - (60 * 60 * 2)  # 2 hours of data

                candle_resp = get_historical_candle_fyers(symbol, "1", from_time, current_time_unix)

                if not candle_resp or "candles" not in candle_resp or not candle_resp["candles"]:
                    logger.warning(f"No candle data received for {symbol}")
                    await asyncio.sleep(10)
                    continue

                # Structure and sort candles
                df = structure_candle_df(candle_resp["candles"])
                df = sort_df_chronologically(df)

                if len(df) < MIN_CANDLES_FOR_INDICATORS:
                    logger.warning(f"Insufficient candles ({len(df)}) for indicators. Need {MIN_CANDLES_FOR_INDICATORS}")
                    await asyncio.sleep(10)
                    continue

                # Get latest candle info
                latest_candle = df.iloc[-1]
                latest_candle_time = latest_candle['timestamp']
                current_price = latest_candle['close']

                # Skip if we already processed this candle
                if last_candle_timestamp is not None and latest_candle_time == last_candle_timestamp:
                    await asyncio.sleep(2)
                    continue

                # Calculate indicators
                df_with_st = calculate_supertrend(df, SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER)
                current_supertrend = df_with_st['supertrend'].iloc[-1]
                st_direction = df_with_st['supertrend_direction'].iloc[-1]
                st_trend_str = "BULLISH" if st_direction == 1 else "BEARISH"

                current_ema13 = calculate_ema(df, EMA_13_PERIOD)
                current_rsi = calculate_rsi(df, RSI_PERIOD)

                if current_ema13 is None or current_rsi is None:
                    logger.warning("Could not calculate EMA or RSI")
                    await asyncio.sleep(5)
                    continue

                logger.info("")
                logger.info("="*80)
                logger.info(f"ANALYSIS - {latest_candle_time.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"Price: {current_price:.2f}")
                logger.info(f"Supertrend: {current_supertrend:.2f} ({st_trend_str})")
                logger.info(f"EMA13: {current_ema13:.2f}")
                logger.info(f"RSI: {current_rsi:.2f} (Previous: {previous_rsi if previous_rsi else 'N/A'})")
                logger.info("="*80)
                logger.info("")

                # Check for entry signals
                if previous_rsi is not None and trade_count < MAX_TRADES:
                    signal = None
                    trade_valid = False
                    trade_direction = None

                    # RSI REVERSAL Signals (crossing thresholds)
                    if previous_rsi < RSI_OVERBOUGHT and current_rsi >= RSI_OVERBOUGHT:
                        signal = 'PUT'
                    elif previous_rsi > RSI_OVERSOLD and current_rsi <= RSI_OVERSOLD:
                        signal = 'CALL'

                    # If signal detected, validate with Supertrend and EMA
                    if signal:
                        logger.info("")
                        logger.info("="*80)
                        logger.info(f" RSI REVERSAL SIGNAL DETECTED: {signal}")
                        logger.info("="*80)
                        logger.info("")

                    # Validate PUT conditions
                    if signal == 'PUT':
                        price_above_supertrend = current_price < current_supertrend
                        price_above_ema = current_price > current_ema13

                        logger.info(" PUT SIGNAL VALIDATION:")
                        logger.info(f"   RSI crossed above {RSI_OVERBOUGHT}: TRUE (Current: {current_rsi:.2f}, Previous: {previous_rsi:.2f})")
                        logger.info(f"   {'OK' if price_above_supertrend else 'No'} Price < Supertrend: {price_above_supertrend} ({current_price:.2f} vs {current_supertrend:.2f})")
                        logger.info(f"   {'OK' if price_above_ema else 'No'} Price > EMA13: {price_above_ema} ({current_price:.2f} vs {current_ema13:.2f})")

                        if price_above_supertrend and price_above_ema:
                            trade_valid = True
                            trade_direction = 'PUT'
                            logger.info("")
                            logger.info(" ALL PUT CONDITIONS MET - TRADE APPROVED")
                        else:
                            logger.info("")
                            logger.info(" PUT conditions NOT fully met - Signal rejected")

                    # Validate PUT conditions
                    elif signal == 'CALL':
                        price_below_supertrend = current_price > current_supertrend
                        price_below_ema = current_price < current_ema13

                        logger.info(" CALL SIGNAL VALIDATION:")
                        logger.info(f"    RSI crossed below {RSI_OVERSOLD}: TRUE (Current: {current_rsi:.2f}, Previous: {previous_rsi:.2f})")
                        logger.info(f"   {'OK' if price_below_supertrend else 'NO'} Price > Supertrend: {price_below_supertrend} ({current_price:.2f} vs {current_supertrend:.2f})")
                        logger.info(f"   {'OK' if price_below_ema else 'NO'} Price < EMA13: {price_below_ema} ({current_price:.2f} vs {current_ema13:.2f})")

                        if price_below_supertrend and price_below_ema:
                            trade_valid = True
                            trade_direction = 'CALL'
                            logger.info("")
                            logger.info(" ALL CALL CONDITIONS MET - TRADE APPROVED")
                        else:
                            logger.info("")
                            logger.info(" CALL conditions NOT fully met - Signal rejected")

                    logger.info("="*80)
                    logger.info("")

                    # Execute trade if all conditions met
                    if trade_valid:
                        logger.info(f" INITIATING {trade_direction} TRADE...")

                        # Log to trade journey
                        trade_journey_logger.info("")
                        trade_journey_logger.info("="*60)
                        trade_journey_logger.info(f"SUPERTREND + EMA + RSI SIGNAL")
                        trade_journey_logger.info(f"Trade Type: {trade_direction}")
                        trade_journey_logger.info(f"Time: {latest_candle_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        trade_journey_logger.info(f"Nifty Price: {current_price:.2f}")
                        trade_journey_logger.info(f"Supertrend: {current_supertrend:.2f} ({st_trend_str})")
                        trade_journey_logger.info(f"EMA13: {current_ema13:.2f}")
                        trade_journey_logger.info(f"RSI: {previous_rsi:.2f} -> {current_rsi:.2f}")

                        # Get target profit
                        target_profit = TARGET_PROFIT_PERCENT

                        # Place order with async price confirmation
                        instrument, entry_price, qty, order_id = place_order(
                            trade_direction, EXPIRY_DATE, "Supertrend_RSIREVERSAL", funds_percent=TRADE_FUNDS_PERCENT
                        )

                        if instrument and entry_price:
                            # Start background price confirmation (ASYNC MAINTAINED)
                            if order_id:
                                asyncio.create_task(
                                    confirm_and_update_entry_price(order_id, entry_price, instrument)
                                )
                                logger.info("Background price confirmation task started")

                            entry_spot_price = get_nifty_spot()

                            # Create trade record
                            current_trade = {
                                "entry_price": entry_price,
                                "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "entry_spot_price": entry_spot_price,
                                "entry_type": "Supertrend_RSIREVERSAL",
                                "entry_supertrend": current_supertrend,
                                "entry_ema13": current_ema13,
                                "entry_rsi": current_rsi,
                                "supertrend_direction": st_trend_str,
                                "max_high": entry_price,
                                "max_low": entry_price,
                                "max_high_pct": 0.0,
                                "max_low_pct": 0.0,
                                "current_pct": 0.0,
                                "trailing_stop": None,
                                "target_profit": target_profit,
                                "stop_moved_to_breakeven": False,
                                "partial_exit_done": False,
                                "remaining_quantity": qty
                            }
                            current_position = trade_direction
                            current_instrument = instrument
                            current_quantity = qty

                            # Log successful entry
                            trade_journey_logger.info(f"TRADE #{trade_count + 1} - {current_position} ENTRY")
                            trade_journey_logger.info(f"Entry Price: {entry_price:.2f} | Nifty Spot: {entry_spot_price:.2f}")
                            trade_journey_logger.info(f"Symbol: {option_symbol}")
                            trade_journey_logger.info(f"Quantity: {qty}")
                            trade_journey_logger.info(f"Target: {target_profit}%")
                            trade_journey_logger.info("Price Journey:")

                            log_status("ERSSRRv2", "trading",
                                       f"Entered {trade_direction} at {entry_price:.2f}",
                                       {"position": trade_direction, "price": entry_price, "pnl": 0, "pnl_pct": 0})

                            # Start continuous monitoring task
                            asyncio.create_task(monitor_active_trade())

                            logger.info(f" Trade entry complete: {trade_direction} at {entry_price:.2f}")
                            logger.info("")

                            # Update last processed candle timestamp
                            last_candle_timestamp = latest_candle_time
                        else:
                            logger.error(" Order placement failed")
                            trade_journey_logger.info(" Order placement failed")

            previous_rsi = current_rsi
            # Update last processed candle timestamp
            last_candle_timestamp = latest_candle_time

            # Wait before next iteration
            await asyncio.sleep(2)

        logger.info("Trading session ended.")
        log_status("ERSSRRv2", "stopped", "Trading session completed")

    except Exception as e:
        logger.error(f"Error in monitor_and_trade: {e}")
        logger.exception("Exception details:")
        log_status("ERSSRRv2", "error", f"Error: {str(e)}")


# -------------------------
# Main Asynchronous Runner and Entry Point
# -------------------------
async def main():
    """Main function that runs the Renko strategy"""
    await monitor_and_trade()

def start():
    """Initialize Fyers connection and start the strategy"""
    global ACCESS_TOKEN, available_balance, index_instrument, fyers, config

    # Read configuration file
    config = configparser.ConfigParser()
    config.read("config_fyers.ini")

    init_database()

    # Initialize Fyers API connection
    ACCESS_TOKEN = config.get("FYERS", "access_token")
    client_id = config.get("FYERS", "client_id")

    # Set up index instrument details
    index_instrument = {
        "exchange": "BSE_INDICES",
        "symbol": SYMBOL,
        "instrument_key": SYMBOL
    }


    # Initialize Fyers API client
    fyers = fyersModel.FyersModel(token=ACCESS_TOKEN, is_async=False, client_id=client_id, log_path="")

    # Get available balance
    try:
        funds_data = safe_api_call(fyers.funds)
        for item in funds_data.get("fund_limit", []):
            if item.get("title", "").lower() == "available balance":
                available_balance = float(item.get("equityAmount", 0))
                break
    except Exception as e:
        logger.error(f"Error fetching funds: {e}")
        available_balance = 0

    if available_balance is None or available_balance <= 0:
        logger.warning("No available balance found or balance is zero. Using simulation mode.")
        global is_simulation
        is_simulation = True
        available_balance = DUMMY_CAPITAL

    # Log initial information
    nifty = get_nifty_spot()
    logger.info(f"Funds: Rs.{available_balance:.2f}, Nifty Spot: {nifty if nifty else 'Unknown'}")
    logger.info(f"Index Instrument details: {index_instrument}")
    logger.info(f"Running in {'simulation' if is_simulation else 'live trading'} mode")

    # Run the strategy
    asyncio.run(main())

if __name__ == "__main__":
    try:
        start()
    except KeyboardInterrupt:
        logger.info("Script stopped by user.")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        logger.exception("Exception details:")
