#!/bin/bash

# Claude AI Trading Agent - Setup Guide
# Run this script to check your setup

echo "================================================================"
echo "Claude AI Trading Agent - Setup Verification"
echo "================================================================"
echo ""

# Function to check if file exists
check_file() {
    if [ -f "$1" ]; then
        echo "✓ $1 exists"
        return 0
    else
        echo "✗ $1 NOT FOUND"
        return 1
    fi
}

# Function to check if directory exists
check_dir() {
    if [ -d "$1" ]; then
        echo "✓ $1/ directory exists"
        return 0
    else
        echo "✗ $1/ directory NOT FOUND"
        mkdir -p "$1"
        echo "  → Created $1/ directory"
        return 1
    fi
}

# Check Python
echo "Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✓ $PYTHON_VERSION"
else
    echo "✗ Python 3 not found"
    echo "  Please install Python 3.8 or higher"
fi
echo ""

# Check required files
echo "Checking required files..."
check_file "claude_trading_agent.py"
check_file "orchestrator.py"
check_file "trade_manager.py"
check_file "market_data.py"
check_file "agents/__init__.py"
check_file "agents/base_agent.py"
check_file "agents/sentiment_agent.py"
check_file "agents/indicator_agent.py"
check_file "agents/price_agent.py"
check_file "requirements.txt"
echo ""

# Check configuration files
echo "Checking configuration files..."
if check_file "config_trading_agent.ini"; then
    if grep -q "YOUR_ANTHROPIC_API_KEY" config_trading_agent.ini; then
        echo "  ⚠  WARNING: Anthropic API key not configured"
        echo "     Edit config_trading_agent.ini and add your API key"
    fi
fi

if check_file "config_fyers.ini"; then
    if grep -q "YOUR_ACCESS_TOKEN" config_fyers.ini 2>/dev/null || [ ! -s config_fyers.ini ]; then
        echo "  ⚠  WARNING: Fyers credentials not configured"
        echo "     Edit config_fyers.ini and add your credentials"
    fi
else
    echo "  → Creating template config_fyers.ini"
    cat > config_fyers.ini << 'EOF'
[FYERS]
access_token = YOUR_ACCESS_TOKEN
client_id = YOUR_CLIENT_ID
EOF
fi
echo ""

# Check directories
echo "Checking required directories..."
check_dir "logs"
check_dir "data"
check_dir "agents"
echo ""

# Check Python packages
echo "Checking Python packages..."
echo "Attempting to install requirements..."
if command -v pip3 &> /dev/null; then
    pip3 install -r requirements.txt --quiet
    if [ $? -eq 0 ]; then
        echo "✓ All required packages installed"
    else
        echo "✗ Error installing packages"
        echo "  Run: pip3 install -r requirements.txt"
    fi
else
    echo "✗ pip3 not found"
    echo "  Please install pip3"
fi
echo ""

# Final summary
echo "================================================================"
echo "Setup Status Summary"
echo "================================================================"
echo ""

ALL_GOOD=true

# Check critical items
if [ ! -f "config_trading_agent.ini" ]; then
    echo "✗ Missing: config_trading_agent.ini"
    ALL_GOOD=false
fi

if grep -q "YOUR_ANTHROPIC_API_KEY" config_trading_agent.ini 2>/dev/null; then
    echo "⚠  TODO: Configure Anthropic API key in config_trading_agent.ini"
    ALL_GOOD=false
fi

if [ ! -f "config_fyers.ini" ]; then
    echo "✗ Missing: config_fyers.ini"
    ALL_GOOD=false
elif grep -q "YOUR_ACCESS_TOKEN" config_fyers.ini 2>/dev/null; then
    echo "⚠  TODO: Configure Fyers credentials in config_fyers.ini"
    ALL_GOOD=false
fi

echo ""

if [ "$ALL_GOOD" = true ]; then
    echo "✓ Setup complete! Ready to run."
    echo ""
    echo "To start trading:"
    echo "  python3 claude_trading_agent.py"
    echo ""
    echo "To reset daily state:"
    echo "  python3 reset_daily_state.py"
else
    echo "⚠  Setup incomplete. Please complete the TODO items above."
    echo ""
    echo "Configuration steps:"
    echo "  1. Get Anthropic API key from: https://console.anthropic.com/"
    echo "  2. Get Fyers credentials from: https://myapi.fyers.in/dashboard"
    echo "  3. Edit config files with your credentials"
    echo "  4. Run this script again to verify"
fi

echo ""
echo "================================================================"
