# Claude AI Trading Agent

Clean, focused NSE options trading powered by Claude Sonnet 4.

## Architecture

### Core Components

1. **Main Orchestrator** (`orchestrator.py`) - Decision hub with memory management
2. **Market Sentiment Agent** (`agents/sentiment_agent.py`) - NSE mood analysis
3. **Indicator Analyser** (`agents/indicator_agent.py`) - Technical signal analysis
4. **Price Analyser** (`agents/price_agent.py`) - Price action pattern detection
5. **Trade Manager** (`trade_manager.py`) - Position and order management

### Trading Workflow

```
Every Minute:
  1. Check → Monitor active position for exit conditions
  2. Analyze → 3 AI agents analyze market data in parallel
  3. Decide → Orchestrator makes weighted decision (65%+ confidence)
  4. Execute → Trade Manager places order with streak-based sizing
```

## Features

- **AI-Powered Analysis**: Claude Sonnet 4 analyzes sentiment, indicators, and price action
- **Streak-Based Position Sizing**: Increase size on wins, reduce on losses
- **Daily Win Target**: Stop after 10 consecutive wins
- **Risk Management**: Stop loss, take profit, daily limits
- **Memory & Learning**: Tracks trade history and adjusts strategy
- **Simulation Mode**: Test with virtual capital before going live

## Quick Start

### 1. Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

#### A. Anthropic API Key

Edit `config_trading_agent.ini`:

```ini
[ANTHROPIC]
api_key = YOUR_ANTHROPIC_API_KEY
```

Get your API key from: https://console.anthropic.com/

#### B. Fyers API Credentials

Create `config_fyers.ini`:

```ini
[FYERS]
access_token = YOUR_ACCESS_TOKEN
client_id = YOUR_CLIENT_ID
```

Get Fyers credentials from: https://myapi.fyers.in/dashboard

#### C. Trading Parameters

Review and adjust `config_trading_agent.ini`:

```ini
[TRADING]
index = NIFTY
lot_size = 75
expiry_date = 2025-11-04
start_time = 09:40
end_time = 14:50
check_interval_seconds = 60

[RISK_MANAGEMENT]
daily_win_target = 10
initial_stop_loss_percent = 3.0
target_profit_percent = 3.0
```

### 3. Run the Agent

```bash
python claude_trading_agent.py
```

## Trading Strategy

### Entry Conditions

The agent will only enter trades when:

1. **Minimum Confidence**: Combined analysis confidence > 65%
2. **No Active Position**: One position at a time
3. **Within Trading Hours**: 09:40 - 14:50 IST
4. **Within Limits**:
   - Daily trades < max limit
   - Win streak < target (10)
   - Loss streak < 3
   - Daily P&L within limits

### Exit Conditions

Positions are automatically closed when:

- **Stop Loss**: -3% loss
- **Target Profit**: +3% profit
- **Trailing Stop**: Protects profits
- **Market Close**: End of trading session

### Position Sizing

- **Base**: 90% of available capital
- **Win Streak Bonus**: +10% per win (up to 3 wins)
- **Loss Reduction**: 50% after a loss

## Agent Details

### 1. Market Sentiment Agent

**Analyzes:**
- Volatility state (ATR-based)
- Price momentum and trend
- Market breadth indicators
- Intraday behavior

**Output:**
- Sentiment: BULLISH / BEARISH / NEUTRAL
- Confidence: 0.0 - 1.0
- Trading bias: CALLS / PUTS / NEUTRAL
- Risk level: LOW / MEDIUM / HIGH

### 2. Indicator Analyser Agent

**Analyzes:**
- RSI (6-period) - Oversold/Overbought
- EMA (13-period) - Trend confirmation
- Supertrend (10, 3) - Trend direction
- ATR - Volatility measurement

**Output:**
- Signal: STRONG_BUY_CALL/PUT, WEAK_BUY_CALL/PUT, NEUTRAL
- Confidence: 0.0 - 1.0
- Entry recommendation: IMMEDIATE / WAIT / AVOID
- Risk-reward ratio

### 3. Price Analyser Agent

**Analyzes:**
- Candlestick patterns
- Support & resistance levels
- Market structure (higher highs/lows)
- Price momentum & rejections

**Output:**
- Pattern detected: BULLISH_ENGULFING, HAMMER, etc.
- Pattern strength: STRONG / MODERATE / WEAK
- Confidence: 0.0 - 1.0
- Entry zone with stop loss & target

## Configuration Reference

### Agent Weights

```ini
[AGENTS]
sentiment_weight = 0.30        # 30% weight
indicator_weight = 0.35        # 35% weight
price_action_weight = 0.35     # 35% weight
min_confidence_threshold = 0.65
```

### Risk Parameters

```ini
[RISK_MANAGEMENT]
daily_win_target = 10
max_consecutive_losses = 3
initial_stop_loss_percent = 3.0
trailing_stop_distance = 2.5
target_profit_percent = 3.0
daily_loss_limit = -5.0
daily_profit_limit = 12.0
```

### Position Sizing Multipliers

```ini
base_position_multiplier = 1.0
win_streak_multiplier = 1.2
loss_reduction_multiplier = 0.5
```

## Monitoring

### Real-time Logs

All activity is logged to `logs/claude_agent.log`:

```
2025-10-30 10:15:00 - Orchestrator - INFO - Decision: BUY_CALL (Confidence: 0.78)
2025-10-30 10:15:05 - TradeManager - INFO - Order placed: 12345
2025-10-30 10:30:00 - TradeManager - INFO - Position closed: P&L = ₹2,250.00 (+3.2%)
```

### Status Output

Every 10 cycles, the agent prints:

```
================================================================================
CURRENT STATUS
--------------------------------------------------------------------------------
Daily Trades: 5
Wins: 4 | Losses: 1 | Win Rate: 80.0%
Win Streak: 3 | Loss Streak: 0
Daily P&L: ₹8,500.00
Current Capital: ₹158,500.00
Active Position: NSE:NIFTY25N0423500CE
Current P&L: ₹1,200.00 (+1.8%)
================================================================================
```

### State Persistence

Agent state is saved to `data/agent_state.json` and includes:

- Win/loss streaks
- Trade history (last 50 trades)
- Daily P&L
- Current statistics

## File Structure

```
Trade-ERS/
├── claude_trading_agent.py        # Main execution script
├── orchestrator.py                # Decision-making orchestrator
├── trade_manager.py               # Order & position management
├── market_data.py                 # Data fetching & indicators
├── agents/
│   ├── __init__.py
│   ├── base_agent.py             # Base agent with Claude integration
│   ├── sentiment_agent.py        # Market sentiment analysis
│   ├── indicator_agent.py        # Technical indicator analysis
│   └── price_agent.py            # Price action analysis
├── config_trading_agent.ini      # Main configuration
├── config_fyers.ini              # Fyers API credentials
├── requirements.txt              # Python dependencies
├── logs/                         # Log files
└── data/                         # State persistence
```

## Safety Features

1. **Simulation Mode**: Automatically enabled if no live balance
2. **Daily Limits**: P&L and trade count limits
3. **Streak Protection**: Stops after target wins or max losses
4. **Position Limits**: One position at a time
5. **Trading Hours**: Only trades during market hours
6. **Error Handling**: Graceful failure with neutral defaults

## API Costs

**Claude Sonnet 4**:
- ~3 API calls per trade decision (3 agents)
- ~8,000 tokens per decision cycle
- Estimated: $0.02 - $0.05 per trading decision

**Recommendation**: Monitor Anthropic API usage at https://console.anthropic.com/

## Troubleshooting

### Issue: "Failed to fetch spot price"

**Solution**: Check Fyers API credentials and internet connection

### Issue: "Insufficient capital for trade"

**Solution**: Ensure minimum capital of ₹10,000 for NIFTY (75 lot size)

### Issue: "One or more agents returned errors"

**Solution**: Check Anthropic API key and rate limits

### Issue: Agent makes no trades

**Solution**: Lower `min_confidence_threshold` in config (default: 0.65)

## Performance Tracking

The agent tracks:

- **Win Rate**: % of profitable trades
- **Win Streak**: Consecutive winning trades
- **Average P&L**: Per trade profitability
- **Sharpe Ratio**: Risk-adjusted returns (in development)

Review `logs/claude_agent.log` for detailed performance metrics.

## Disclaimer

This is an **experimental trading system**. Use at your own risk.

- Always start in simulation mode
- Never risk more than you can afford to lose
- Monitor the system closely during live trading
- Past performance does not guarantee future results

## Support

For issues and questions:
- GitHub Issues: https://github.com/anthropics/claude-code/issues
- Fyers API: https://myapi.fyers.in/docsv3

## License

MIT License - See LICENSE file for details

---

**Built with Claude Sonnet 4 - The AI-Powered Trading Edge**
