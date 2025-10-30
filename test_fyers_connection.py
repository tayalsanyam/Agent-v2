"""
Test Fyers API Connection
Quick script to verify Fyers credentials are working
"""

import configparser
from fyers_apiv3 import fyersModel
from datetime import datetime, timedelta

print("=" * 60)
print("Fyers API Connection Test")
print("=" * 60)

# Load config
config = configparser.ConfigParser()
config.read("config_fyers.ini")

try:
    access_token = config.get("FYERS", "access_token")
    client_id = config.get("FYERS", "client_id")

    print(f"\nClient ID: {client_id}")
    print(f"Access Token: {access_token[:20]}..." if len(access_token) > 20 else f"Access Token: {access_token}")

except Exception as e:
    print(f"\n❌ Error reading config: {e}")
    print("\nMake sure config_fyers.ini exists and has:")
    print("[FYERS]")
    print("access_token = YOUR_TOKEN")
    print("client_id = YOUR_CLIENT_ID")
    exit(1)

# Initialize Fyers
print("\n" + "-" * 60)
print("Initializing Fyers API...")
print("-" * 60)

fyers = fyersModel.FyersModel(
    token=access_token,
    is_async=False,
    client_id=client_id,
    log_path=""
)

print("✓ Fyers client initialized")

# Test 1: Get NIFTY spot price
print("\n" + "-" * 60)
print("Test 1: Fetching NIFTY spot price...")
print("-" * 60)

try:
    response = fyers.quotes({"symbols": "NSE:NIFTY50-INDEX"})
    print(f"Response: {response}")

    if response and response.get("s") == "ok":
        data = response.get("d", [])
        if data and len(data) > 0:
            ltp = data[0].get("v", {}).get("lp", 0)
            print(f"✓ NIFTY Current Price: {ltp}")
        else:
            print("❌ No data in response")
    else:
        print(f"❌ API Error: {response.get('message', 'Unknown error')}")
        print(f"   Status: {response.get('s', 'unknown')}")
        print(f"   Code: {response.get('code', 'N/A')}")

except Exception as e:
    print(f"❌ Exception: {e}")

# Test 2: Get historical data
print("\n" + "-" * 60)
print("Test 2: Fetching historical candles...")
print("-" * 60)

try:
    to_date = datetime.now()
    from_date = to_date - timedelta(days=2)

    data = {
        "symbol": "NSE:NIFTY50-INDEX",
        "resolution": "1",  # 1 minute
        "date_format": "1",
        "range_from": str(int(from_date.timestamp())),
        "range_to": str(int(to_date.timestamp())),
        "cont_flag": "1"
    }

    print(f"Request: {data}")

    response = fyers.history(data=data)
    print(f"Response: {response}")

    if response and response.get("s") == "ok":
        candles = response.get("candles", [])
        print(f"✓ Received {len(candles)} candles")

        if len(candles) > 0:
            print(f"  First candle: {candles[0]}")
            print(f"  Last candle: {candles[-1]}")
        else:
            print("⚠ No candles returned (market might be closed)")

    else:
        print(f"❌ API Error: {response.get('message', 'Unknown error')}")
        print(f"   Status: {response.get('s', 'unknown')}")
        print(f"   Code: {response.get('code', 'N/A')}")

except Exception as e:
    print(f"❌ Exception: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Check funds
print("\n" + "-" * 60)
print("Test 3: Checking account funds...")
print("-" * 60)

try:
    response = fyers.funds()
    print(f"Response: {response}")

    if response and response.get("s") == "ok":
        fund_limit = response.get("fund_limit", [])
        if fund_limit and len(fund_limit) > 0:
            balance = fund_limit[0].get("equityAmount", 0)
            print(f"✓ Available Balance: ₹{balance:,.2f}")
        else:
            print("❌ No fund data in response")
    else:
        print(f"❌ API Error: {response.get('message', 'Unknown error')}")

except Exception as e:
    print(f"❌ Exception: {e}")

print("\n" + "=" * 60)
print("Test Complete")
print("=" * 60)

# Summary
print("\n📋 Summary:")
print("If all tests passed ✓ - Your Fyers API is working!")
print("If tests failed ❌ - Check:")
print("  1. Access token is valid (regenerate if needed)")
print("  2. Client ID is correct")
print("  3. Market hours (9:15 AM - 3:30 PM IST for NSE)")
print("  4. Internet connection")
print("\nGet new credentials at: https://myapi.fyers.in/dashboard")
print()
