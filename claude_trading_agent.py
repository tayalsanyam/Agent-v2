"""
Claude AI Trading Agent - Main Execution Script
Clean, focused NSE options trading powered by Claude Sonnet 4
"""

import logging
import configparser
import time
from datetime import datetime, time as dt_time
import sys
import os

from fyers_apiv3 import fyersModel

from orchestrator import TradingOrchestrator
from trade_manager import TradeManager
from market_data import MarketDataProvider


def setup_logging(log_dir: str, log_file: str, log_level: str = "INFO"):
    """Setup logging configuration"""
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, log_file)

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info("Claude AI Trading Agent Starting")
    logger.info("=" * 80)

    return logger


def load_config(config_file: str = "config_trading_agent.ini") -> dict:
    """Load configuration from INI file"""
    config = configparser.ConfigParser()
    config.read(config_file)

    # Also load Fyers config
    fyers_config = configparser.ConfigParser()
    fyers_config.read("config_fyers.ini")

    return {
        # Anthropic
        "anthropic_api_key": config.get("ANTHROPIC", "api_key"),
        "anthropic_model": config.get("ANTHROPIC", "model"),

        # Fyers
        "fyers_access_token": fyers_config.get("FYERS", "access_token"),
        "fyers_client_id": fyers_config.get("FYERS", "client_id"),

        # Trading
        "index": config.get("TRADING", "index"),
        "lot_size": config.getint("TRADING", "lot_size"),
        "expiry_date": config.get("TRADING", "expiry_date"),
        "trade_funds_percent": config.getfloat("TRADING", "trade_funds_percent"),
        "max_daily_trades": config.getint("TRADING", "max_daily_trades"),
        "start_time": config.get("TRADING", "start_time"),
        "end_time": config.get("TRADING", "end_time"),
        "check_interval_seconds": config.getint("TRADING", "check_interval_seconds"),

        # Risk Management
        "daily_win_target": config.getint("RISK_MANAGEMENT", "daily_win_target"),
        "max_consecutive_wins": config.getint("RISK_MANAGEMENT", "max_consecutive_wins"),
        "max_consecutive_losses": config.getint("RISK_MANAGEMENT", "max_consecutive_losses"),
        "initial_stop_loss_percent": config.getfloat("RISK_MANAGEMENT", "initial_stop_loss_percent"),
        "trailing_stop_distance": config.getfloat("RISK_MANAGEMENT", "trailing_stop_distance"),
        "target_profit_percent": config.getfloat("RISK_MANAGEMENT", "target_profit_percent"),
        "base_position_multiplier": config.getfloat("RISK_MANAGEMENT", "base_position_multiplier"),
        "win_streak_multiplier": config.getfloat("RISK_MANAGEMENT", "win_streak_multiplier"),
        "loss_reduction_multiplier": config.getfloat("RISK_MANAGEMENT", "loss_reduction_multiplier"),
        "daily_loss_limit": config.getfloat("RISK_MANAGEMENT", "daily_loss_limit"),
        "daily_profit_limit": config.getfloat("RISK_MANAGEMENT", "daily_profit_limit"),

        # Agents
        "sentiment_weight": config.getfloat("AGENTS", "sentiment_weight"),
        "indicator_weight": config.getfloat("AGENTS", "indicator_weight"),
        "price_action_weight": config.getfloat("AGENTS", "price_action_weight"),
        "min_confidence_threshold": config.getfloat("AGENTS", "min_confidence_threshold"),
        "min_hold_confidence": config.getfloat("AGENTS", "min_hold_confidence", fallback=0.45),

        # Memory
        "track_last_n_trades": config.getint("MEMORY", "track_last_n_trades"),
        "save_state_interval": config.getint("MEMORY", "save_state_interval"),
        "state_file": config.get("MEMORY", "state_file"),

        # Logging
        "log_dir": config.get("LOGGING", "log_dir"),
        "agent_log_file": config.get("LOGGING", "agent_log_file"),
        "log_level": config.get("LOGGING", "log_level")
    }


def is_trading_time(start_time: str, end_time: str) -> bool:
    """Check if current time is within trading hours"""
    now = datetime.now().time()

    start = datetime.strptime(start_time, "%H:%M").time()
    end = datetime.strptime(end_time, "%H:%M").time()

    return start <= now <= end


def initialize_fyers(access_token: str, client_id: str) -> fyersModel.FyersModel:
    """Initialize Fyers API client"""
    fyers = fyersModel.FyersModel(
        token=access_token,
        is_async=False,
        client_id=client_id,
        log_path=""
    )

    return fyers


def get_available_balance(fyers: fyersModel.FyersModel, logger) -> float:
    """Get available balance from Fyers account"""
    try:
        response = fyers.funds()

        if response and response.get("s") == "ok":
            fund_limit = response.get("fund_limit", [])
            if fund_limit and len(fund_limit) > 0:
                available_balance = fund_limit[0].get("equityAmount", 0)
                logger.info(f"Available balance: ₹{available_balance:.2f}")
                return float(available_balance)

        logger.warning("Could not fetch balance, using simulation mode")
        return 0.0

    except Exception as e:
        logger.error(f"Error fetching balance: {str(e)}")
        return 0.0


def print_status(orchestrator: TradingOrchestrator, logger):
    """Print current status"""
    stats = orchestrator.get_statistics()

    logger.info("=" * 80)
    logger.info("CURRENT STATUS")
    logger.info("-" * 80)
    logger.info(f"Daily Trades: {stats['daily_trades']}")
    logger.info(f"Wins: {stats['total_wins']} | Losses: {stats['total_losses']} | "
               f"Win Rate: {stats['win_rate']:.1f}%")
    logger.info(f"Win Streak: {stats['win_streak']} | Loss Streak: {stats['loss_streak']}")
    logger.info(f"Daily P&L: ₹{stats['daily_pnl']:.2f}")
    logger.info(f"Current Capital: ₹{stats['current_capital']:.2f}")

    if orchestrator.trade_manager.has_active_position():
        pnl_info = orchestrator.trade_manager.get_current_pnl()
        logger.info(f"Active Position: {pnl_info.get('symbol', 'N/A')}")
        logger.info(f"Current P&L: ₹{pnl_info.get('pnl', 0):.2f} "
                   f"({pnl_info.get('pnl_percent', 0):+.2f}%)")
    else:
        logger.info("Active Position: None")

    logger.info("=" * 80)


def main():
    """Main execution loop"""
    logger = None  # Initialize logger as None
    orchestrator = None  # Initialize orchestrator as None

    try:
        # Load configuration
        config = load_config()

        # Setup logging
        logger = setup_logging(
            config["log_dir"],
            config["agent_log_file"],
            config["log_level"]
        )

        logger.info("Configuration loaded successfully")

        # Initialize Fyers API
        logger.info("Initializing Fyers API...")
        fyers = initialize_fyers(
            config["fyers_access_token"],
            config["fyers_client_id"]
        )

        # Get available balance
        available_balance = get_available_balance(fyers, logger)

        # Determine if simulation mode
        is_simulation = available_balance <= 6000
        initial_capital = 150000 if is_simulation else available_balance

        if is_simulation:
            logger.warning("Running in SIMULATION mode with ₹150,000")
        else:
            logger.info(f"Running in LIVE mode with ₹{initial_capital:.2f}")

        # Initialize components
        logger.info("Initializing trading components...")

        trade_manager = TradeManager(
            fyers_client=fyers,
            index=config["index"],
            lot_size=config["lot_size"],
            expiry_date=config["expiry_date"],
            initial_capital=initial_capital,
            is_simulation=is_simulation
        )

        market_data_provider = MarketDataProvider(
            fyers_client=fyers,
            index=config["index"]
        )

        orchestrator = TradingOrchestrator(
            api_key=config["anthropic_api_key"],
            trade_manager=trade_manager,
            config=config
        )

        logger.info("All components initialized successfully")
        logger.info(f"Target: {config['daily_win_target']} consecutive wins")
        logger.info(f"Trading hours: {config['start_time']} - {config['end_time']}")
        logger.info(f"Check interval: {config['check_interval_seconds']} seconds")

        # Main trading loop
        logger.info("\nStarting main trading loop...")
        logger.info("Press Ctrl+C to stop\n")

        cycle_count = 0

        while True:
            try:
                cycle_count += 1

                # Check if trading time
                if not is_trading_time(config["start_time"], config["end_time"]):
                    if cycle_count == 1 or cycle_count % 60 == 0:
                        logger.info("Outside trading hours. Waiting...")
                    time.sleep(config["check_interval_seconds"])
                    continue

                logger.info(f"\n{'=' * 80}")
                logger.info(f"CYCLE {cycle_count} - {datetime.now().strftime('%H:%M:%S')}")
                logger.info(f"{'=' * 80}")

                # Step 1: Check for exit conditions (if position exists)
                if orchestrator.trade_manager.has_active_position():
                    logger.info("Checking exit conditions...")
                    exit_reason = orchestrator.check_exit_conditions()

                    # Step 1b: If no technical exit, re-evaluate position with agents
                    if not exit_reason:
                        logger.info("No technical exit. Re-evaluating position with agents...")
                        market_data = market_data_provider.get_market_data()

                        if market_data:
                            hold_evaluation = orchestrator.evaluate_ongoing_position(market_data)

                            if hold_evaluation.get("hold_recommendation") == "EXIT":
                                exit_reason = "AGENT_CONFIDENCE_DROP"
                                logger.info(f"Agents recommend exit: {hold_evaluation.get('reasoning')}")
                                logger.info(f"Hold confidence: {hold_evaluation.get('confidence', 0):.2f} "
                                          f"(Threshold: {orchestrator.min_hold_confidence:.2f})")
                            else:
                                logger.info(f"Agents recommend HOLD (Confidence: {hold_evaluation.get('confidence', 0):.2f})")
                        else:
                            logger.warning("Failed to fetch market data for position re-evaluation")

                    if exit_reason:
                        logger.info(f"Exit condition met: {exit_reason}")
                        result = orchestrator.close_position_and_update(exit_reason)

                        if result.get("success"):
                            logger.info(f"Position closed successfully")
                            print_status(orchestrator, logger)
                    else:
                        # Show current P&L
                        pnl_info = orchestrator.trade_manager.get_current_pnl()
                        logger.info(f"Position P&L: ₹{pnl_info.get('pnl', 0):.2f} "
                                   f"({pnl_info.get('pnl_percent', 0):+.2f}%)")

                # Step 2: If no position, analyze market and look for entry
                if not orchestrator.trade_manager.has_active_position():
                    logger.info("No active position. Analyzing market...")

                    # Fetch market data
                    market_data = market_data_provider.get_market_data()

                    if not market_data:
                        logger.error("Failed to fetch market data")
                        time.sleep(config["check_interval_seconds"])
                        continue

                    # Analyze market
                    analysis = orchestrator.analyze_market(market_data)

                    # Make decision
                    decision = orchestrator.make_decision(analysis)

                    logger.info(f"Decision: {decision.get('action')} "
                               f"(Confidence: {decision.get('confidence', 0):.2f})")

                    # Execute decision
                    if decision.get("action") != "WAIT":
                        execution_result = orchestrator.execute_decision(decision)

                        if execution_result.get("executed"):
                            logger.info("Trade executed successfully!")
                            print_status(orchestrator, logger)
                        else:
                            logger.info(f"Trade not executed: "
                                      f"{execution_result.get('reason', 'Unknown')}")
                    else:
                        logger.info(f"Waiting: {decision.get('reasoning', 'Low confidence')}")

                # Print status every 10 cycles
                if cycle_count % 10 == 0:
                    print_status(orchestrator, logger)

                # Sleep until next check (faster monitoring during active trades)
                if orchestrator.trade_manager.has_active_position():
                    logger.info("Active position: Sleeping for 5 seconds...")
                    time.sleep(5)
                else:
                    logger.info(f"Sleeping for {config['check_interval_seconds']} seconds...")
                    time.sleep(config['check_interval_seconds'])

            except KeyboardInterrupt:
                logger.info("\nShutdown signal received")
                raise

            except Exception as e:
                logger.error(f"Error in trading loop: {str(e)}", exc_info=True)
                time.sleep(config['check_interval_seconds'])

    except KeyboardInterrupt:
        if logger:
            logger.info("\n" + "=" * 80)
            logger.info("SHUTTING DOWN")
            logger.info("=" * 80)
        else:
            print("\nSHUTTING DOWN")

        # Close any active positions
        if orchestrator and orchestrator.trade_manager.has_active_position():
            if logger:
                logger.info("Closing active position...")
            result = orchestrator.close_position_and_update("MANUAL_SHUTDOWN")
            if result.get("success") and logger:
                logger.info("Position closed successfully")

        # Print final statistics
        if orchestrator and logger:
            print_status(orchestrator, logger)

        if logger:
            logger.info("\nClaude AI Trading Agent stopped")
            logger.info("=" * 80)
        else:
            print("\nClaude AI Trading Agent stopped")

    except Exception as e:
        if logger:
            logger.error(f"Fatal error: {str(e)}", exc_info=True)
        else:
            print(f"Fatal error: {str(e)}")
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
