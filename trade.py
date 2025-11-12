import config
from exchange import get_client
import re
from market import get_market_summary

# GLOBAL portfolio değişkeni - main.py tarafından set edilecek
portfolio = None

def set_portfolio(portfolio_instance):
    """
    Main script'ten portfolio instance'ını alır.
    Bu sayede tüm modüller aynı portfolio'yu kullanır.
    """
    global portfolio
    portfolio = portfolio_instance
    print(f"[TRADE] Portfolio instance set. Balance: ${portfolio.balance:.2f}")

def get_current_position(symbol: str):
    """Checks the current position for a given symbol."""
    if config.SIMULATION_MODE:
        if portfolio is None:
            print(f"[TRADE] ERROR: Portfolio not initialized!")
            return "flat", 0
        return portfolio.get_position_details(symbol)

    try:
        client = get_client()
        all_positions = client.fetch_positions()
        for position in all_positions:
            if position['info']['symbol'] == symbol.replace('/', ''):
                amount = float(position['contracts'])
                side = position['side']
                if amount > 0:
                    return side, amount
        return "flat", 0
            
    except Exception as e:
        if "Authentication credentials were not provided" in str(e):
            return "flat", 0
        print(f"Could not get position info for {symbol}: {e}")
    return "error", 0

def parse_and_execute(decision: dict, symbol: str, market_data: dict, position_status: tuple):
    """
    Parses the decision dictionary from the engine and executes the trade.
    Accepts market_data and position_status to avoid redundant API calls.
    """
    command = decision.get("command", "hold")
    reasoning = decision.get("reasoning", "No reasoning provided.")
    trade_amount_usd = decision.get("trade_amount_usd", 0)
    print(f"[{symbol}] Command received: '{command}' with amount ${trade_amount_usd:.2f}")

    # Parse leverage from command string
    leverage = 20 # Default
    match = re.search(r'(\d+)x', command)
    if match:
        leverage = int(match.group(1))
        leverage = max(5, min(25, leverage))

    action = command.split()[0]
    
    # Use the position status passed from the worker
    position_type, position_amount = position_status
    print(f"[{symbol}] Current position (from cache): {position_type} ({position_amount})")

    # Determine the executor (simulation or real client)
    if config.SIMULATION_MODE:
        if portfolio is None:
            print(f"[{symbol}] ERROR: Portfolio not initialized! Cannot execute trade.")
            return
        executor = portfolio
    else:
        executor = get_client()

    try:
        # Use the market data passed from the worker
        if not market_data:
            print(f"[{symbol}] Market data is missing. Aborting.")
            return
        current_price = market_data.get('current_price')

        # Prepare params for the executor
        exec_params = {
            'trade_amount_usd': trade_amount_usd,
            'leverage': leverage,
            'reason': reasoning,
            'market_data': market_data
        }

        if action in ["long", "short"]:
            # Close opposite position first if it exists
            if (action == "long" and position_type in ["short", "sell"]) or \
               (action == "short" and position_type in ["long", "buy"]):
                print(f"[{symbol}] Action: Closing existing {position_type.upper()} position...")
                close_params = exec_params.copy()
                close_params['reduceOnly'] = True
                executor.create_order(symbol, 'market', 'buy' if position_type in ["short", "sell"] else 'sell', position_amount, close_params)
                position_type = "flat" # Update status after closing

            # Only open a new position if flat
            if position_type == "flat":
                # Calculate quantity based on the margin AI wants to spend and leverage
                quantity = (trade_amount_usd * leverage) / current_price
                
                print(f"[{symbol}] Action: Setting leverage to {leverage}x...")
                executor.set_leverage(leverage, symbol)
                
                print(f"[{symbol}] Action: Opening {action.upper()} position of {quantity:.6f}...")
                executor.create_order(symbol, 'market', 'buy' if action == "long" else 'sell', quantity, exec_params)
            else:
                print(f"[{symbol}] Already in a {position_type} position, skipping new '{action}' command.")

        elif action == "close":
            if position_type in ["long", "buy"]:
                print(f"[{symbol}] Action: Closing LONG position of {position_amount}...")
                exec_params['reduceOnly'] = True
                executor.create_order(symbol, 'market', 'sell', position_amount, exec_params)
            elif position_type in ["short", "sell"]:
                print(f"[{symbol}] Action: Closing SHORT position of {position_amount}...")
                exec_params['reduceOnly'] = True
                executor.create_order(symbol, 'market', 'buy', position_amount, exec_params)
            else:
                print(f"[{symbol}] No position to close.")
        
        elif action == "hold":
            print(f"[{symbol}] Action: Holding position.")

    except Exception as e:
        print(f"[{symbol}] Error during trade execution: {e}")
        import traceback
        traceback.print_exc()

# Test için
if __name__ == "__main__":
    print("\n--- Trade Modülü Testleri ---")
    if config.SIMULATION_MODE:
        from simulation import SimulatedPortfolio
        test_portfolio = SimulatedPortfolio()
        set_portfolio(test_portfolio)
    
    test_decision = {
        "command": "long 30x",
        "trade_amount_usd": 100,
        "reasoning": "Test reasoning."
    }
    test_symbol = "BTC/USDT"
    parse_and_execute(test_decision, test_symbol)
    print("---")