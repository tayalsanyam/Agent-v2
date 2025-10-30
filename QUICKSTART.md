# Claude AI Trading Agent - Quick Start Guide

## 🚀 Getting Started in 5 Minutes

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Configure API Keys

#### Anthropic Claude API
Edit `config_trading_agent.ini`:
```ini
[ANTHROPIC]
api_key = sk-ant-xxxxxxxxxxxxxxxxxxxxx  # Your API key
```

Get your key: https://console.anthropic.com/

#### Fyers API
Create `config_fyers.ini`:
```ini
[FYERS]
access_token = YOUR_ACCESS_TOKEN
client_id = YOUR_CLIENT_ID
```

Get credentials: https://myapi.fyers.in/dashboard

### Step 3: Verify Setup

```bash
bash setup_guide.sh
```

### Step 4: Start Trading

```bash
python3 claude_trading_agent.py
```

Press `Ctrl+C` to stop.

---

## 📋 Daily Workflow

### Morning (Before Market Opens)

1. **Reset daily state** (optional, for fresh start):
   ```bash
   python3 reset_daily_state.py
   ```

2. **Update expiry date** in `config_trading_agent.ini` if needed:
   ```ini
   [TRADING]
   expiry_date = 2025-11-04  # Current weekly expiry
   ```

3. **Check configuration** (optional):
   ```bash
   bash setup_guide.sh
   ```

### During Market Hours

1. **Start the agent**:
   ```bash
   python3 claude_trading_agent.py
   ```

2. **Monitor logs** (in another terminal):
   ```bash
   tail -f logs/claude_agent.log
   ```

### After Market Close

1. **Review logs**:
   ```bash
   cat logs/claude_agent.log | grep "CURRENT STATUS" -A 10
   ```

2. **Check state**:
   ```bash
   cat data/agent_state.json
   ```

---

## ⚙️ Configuration Quick Reference

### Trading Parameters

```ini
[TRADING]
index = NIFTY              # NIFTY or SENSEX
lot_size = 75              # 75 for NIFTY, 20 for SENSEX
expiry_date = 2025-11-04   # Weekly expiry
start_time = 09:40         # Trading start (IST)
end_time = 14:50           # Trading end (IST)
check_interval_seconds = 60 # Check every minute
```

### Risk Management

```ini
[RISK_MANAGEMENT]
daily_win_target = 10              # Stop after 10 wins
max_consecutive_losses = 3         # Stop after 3 losses
initial_stop_loss_percent = 3.0    # -3% stop loss
target_profit_percent = 3.0        # +3% target
daily_loss_limit = -5.0            # -5% daily loss limit
daily_profit_limit = 12.0          # +12% daily profit limit
```

### Agent Tuning

```ini
[AGENTS]
sentiment_weight = 0.30             # 30% weight to sentiment
indicator_weight = 0.35             # 35% weight to indicators
price_action_weight = 0.35          # 35% weight to price action
min_confidence_threshold = 0.65     # 65% confidence to trade
```

**Lower threshold = More trades** (higher risk)
**Higher threshold = Fewer trades** (lower risk)

---

## 📊 Understanding the Output

### Status Display

```
================================================================================
CURRENT STATUS
--------------------------------------------------------------------------------
Daily Trades: 5                    # Trades executed today
Wins: 4 | Losses: 1 | Win Rate: 80.0%
Win Streak: 3 | Loss Streak: 0    # Current streak
Daily P&L: ₹8,500.00              # Total profit/loss
Current Capital: ₹158,500.00       # Available capital
Active Position: NSE:NIFTY25N0423500CE
Current P&L: ₹1,200.00 (+1.8%)   # Open position P&L
================================================================================
```

### Decision Log

```
Decision: BUY_CALL (Confidence: 0.78)
Agent Summary:
  - sentiment: BULLISH (0.75)
  - indicators: STRONG_BUY_CALL (0.82)
  - price_action: BULLISH (0.73)
Reasoning: Bullish sentiment | Technical: RSI at 28 - Oversold | Price action: HAMMER
```

---

## 🎯 Trading Logic

### Entry Conditions (ALL must be true)

- ✓ Confidence > 65% (configurable)
- ✓ No active position
- ✓ Within trading hours (09:40 - 14:50)
- ✓ Daily trades < limit
- ✓ Win streak < target (10)
- ✓ Loss streak < 3
- ✓ Daily P&L within limits

### Exit Conditions (ANY triggers exit)

- Stop Loss: -3%
- Target: +3%
- Trailing Stop: 2.5% from peak
- Market close

### Position Sizing

- **Base**: 90% of capital
- **After Win**: +10% per win (up to 3)
- **After Loss**: 50% reduction

**Example:**
- Capital: ₹100,000
- After 2 wins: Use ₹108,000 (20% bonus)
- After 1 loss: Use ₹45,000 (50% reduction)

---

## 🔍 Monitoring & Debugging

### Check if Agent is Running

```bash
ps aux | grep claude_trading_agent
```

### View Live Logs

```bash
tail -f logs/claude_agent.log
```

### Filter for Specific Events

```bash
# Show only trades
grep "Trade executed" logs/claude_agent.log

# Show only decisions
grep "Decision:" logs/claude_agent.log

# Show only P&L
grep "P&L" logs/claude_agent.log
```

### Check Agent State

```bash
cat data/agent_state.json | python3 -m json.tool
```

---

## ⚠️ Troubleshooting

### Problem: No trades happening

**Check:**
1. Is confidence threshold too high? Lower it to 0.60
2. Are we within trading hours?
3. Check logs for "WAIT" decisions and reasons

**Solution:**
```ini
[AGENTS]
min_confidence_threshold = 0.60  # Lower from 0.65
```

### Problem: Too many losing trades

**Check:**
1. Is market volatile?
2. Review agent analysis in logs

**Solution:**
- Increase confidence threshold to 0.70
- Reduce position size multipliers
- Tighten stop loss to 2%

### Problem: API errors

**Check:**
1. Anthropic API key valid?
2. Fyers credentials correct?
3. Internet connection stable?

**Solution:**
```bash
# Test Fyers connection
python3 -c "from fyers_apiv3 import fyersModel; print('Fyers module OK')"

# Test Anthropic
python3 -c "import anthropic; print('Anthropic module OK')"
```

---

## 💡 Tips for Success

### Start Conservative

1. **Begin with simulation**: Let the agent run without real money
2. **Lower position size**: Set `base_position_multiplier = 0.5`
3. **Tighter stops**: Use 2% stop loss initially
4. **Higher confidence**: Start with 0.70 threshold

### Optimize Gradually

1. **Monitor for 5-10 trades** before making changes
2. **Adjust one parameter at a time**
3. **Keep notes** on what works
4. **Review daily logs** for patterns

### Risk Management

1. **Never risk more than 2% per trade**
2. **Set strict daily loss limits**
3. **Take profits at target**
4. **Don't override the agent** (trust the system)

---

## 📈 Performance Tracking

### Daily Review Checklist

- [ ] Total trades executed
- [ ] Win rate (target: >60%)
- [ ] Average P&L per trade
- [ ] Max drawdown
- [ ] Streaks (wins/losses)
- [ ] Agent confidence patterns

### Weekly Review

- [ ] Cumulative P&L
- [ ] Best performing times
- [ ] Agent accuracy by condition
- [ ] Parameter adjustments needed

---

## 🎓 Understanding Agent Decisions

### High Confidence Trade Example

```
sentiment: BULLISH (0.82)
  → Market showing strong upward momentum
  → Low volatility, stable trend

indicators: STRONG_BUY_CALL (0.88)
  → RSI at 28 (oversold)
  → Price above EMA13
  → Supertrend bullish

price_action: BULLISH (0.79)
  → Bullish engulfing pattern
  → Strong support holding
  → Higher lows forming

Combined Score: 0.83 → BUY CALL ✓
```

### Low Confidence (WAIT) Example

```
sentiment: NEUTRAL (0.52)
  → Mixed signals, choppy market

indicators: WEAK_BUY_CALL (0.58)
  → RSI neutral at 52
  → Conflicting EMA signals

price_action: NEUTRAL (0.55)
  → No clear pattern
  → Ranging between S/R

Combined Score: 0.55 → WAIT ✗
```

---

## 🔧 Advanced Configuration

### Aggressive Trading (More Trades)

```ini
[AGENTS]
min_confidence_threshold = 0.55

[RISK_MANAGEMENT]
initial_stop_loss_percent = 4.0
target_profit_percent = 2.5
```

### Conservative Trading (Fewer, Higher Quality)

```ini
[AGENTS]
min_confidence_threshold = 0.75

[RISK_MANAGEMENT]
initial_stop_loss_percent = 2.0
target_profit_percent = 4.0
```

---

## 📞 Support Resources

- **Anthropic API Docs**: https://docs.anthropic.com/
- **Fyers API Docs**: https://myapi.fyers.in/docsv3
- **GitHub Issues**: Report bugs and request features

---

## ✅ Pre-Flight Checklist

Before going live:

- [ ] API keys configured and tested
- [ ] Risk parameters reviewed
- [ ] Capital allocation decided
- [ ] Expiry date updated
- [ ] Stop loss and targets set
- [ ] Daily limits configured
- [ ] Backup of previous state
- [ ] Monitoring setup ready

**Ready to trade? Run: `python3 claude_trading_agent.py`**

---

*Remember: This is an experimental system. Start small, monitor closely, and never risk more than you can afford to lose.*
