"""
Reset Daily State Script
Use this at the start of each trading day to reset statistics
"""

import json
import os
from datetime import datetime


def reset_state():
    """Reset the agent state for a new trading day"""

    state_file = "data/agent_state.json"

    # Create backup of previous day
    if os.path.exists(state_file):
        backup_file = f"data/agent_state_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            with open(state_file, 'r') as f:
                old_state = json.load(f)

            with open(backup_file, 'w') as f:
                json.dump(old_state, f, indent=2)

            print(f"✓ Previous state backed up to: {backup_file}")

        except Exception as e:
            print(f"✗ Error backing up state: {str(e)}")

    # Create fresh state
    fresh_state = {
        "win_streak": 0,
        "loss_streak": 0,
        "total_wins": 0,
        "total_losses": 0,
        "daily_pnl": 0.0,
        "daily_trades": 0,
        "last_trade_result": None,
        "trade_history": [],
        "timestamp": datetime.now().isoformat(),
        "reset_date": datetime.now().strftime('%Y-%m-%d')
    }

    # Save fresh state
    os.makedirs("data", exist_ok=True)

    with open(state_file, 'w') as f:
        json.dump(fresh_state, f, indent=2)

    print(f"✓ Daily state reset successfully!")
    print(f"  Date: {fresh_state['reset_date']}")
    print(f"  File: {state_file}")


if __name__ == "__main__":
    print("=" * 60)
    print("Claude AI Trading Agent - Daily State Reset")
    print("=" * 60)
    print()

    confirm = input("Reset daily state? This will clear all statistics. (yes/no): ")

    if confirm.lower() in ['yes', 'y']:
        reset_state()
        print("\nReady to start a new trading day!")
    else:
        print("Reset cancelled.")

    print()
