import schedule
import time
import market
import engine # trader'ı engine ile değiştiriyoruz
import config
import json
from datetime import datetime
import trade_logger
import mailer # Import the new mailer module

# ÖNCE trade modülünü import et
import trade

# Initialize portfolio ONCE at startup
portfolio = None
if config.SIMULATION_MODE:
    from simulation import SimulatedPortfolio
    portfolio = SimulatedPortfolio()
    # Şimdi portfolio'yu trade modülüne set et
    trade.set_portfolio(portfolio)
    print(f"[INIT] Portfolio initialized and shared with trade module.")

def check_tp_sl():
    """
    Checks open positions and closes them if TP (percentage-based) or
    dynamic SL (ATR-based) levels are hit.
    """
    if not config.SIMULATION_MODE:
        print("TP/SL check is currently only supported in simulation mode.")
        return

    open_positions = portfolio.get_all_open_positions()
    if not open_positions:
        return

    print("\n[MGM] Checking open positions for TP/SL...")
    for symbol, position in list(open_positions.items()):
        try:
            margin = position.get('margin', 0)
            unrealized_pnl = position.get('unrealized_pnl', 0)
            entry_price = position.get('entry_price', 0)
            current_price = position.get('current_price', 0)
            atr_at_entry = position.get('atr_at_entry', 0)
            side = position.get('side')

            if margin == 0 or entry_price == 0:
                continue

            # 1. Check for Take Profit (percentage-based)
            pnl_pct = (unrealized_pnl / margin) * 100
            if pnl_pct >= config.TAKE_PROFIT_PCT:
                reason = f"TAKE PROFIT triggered at {pnl_pct:.2f}%"
                print(f"✅ [{symbol}] {reason}")
                trade.parse_and_execute({"command": "close", "reasoning": reason}, symbol)
                continue # Move to next position

            # 2. Check for Dynamic Stop Loss (ATR-based)
            if atr_at_entry > 0:
                stop_loss_price = 0
                if side in ['long', 'buy']:
                    stop_loss_price = entry_price - (atr_at_entry * config.ATR_MULTIPLIER)
                    print(f"[{symbol}] PnL: {pnl_pct:.2f}% | Current: {current_price} | Dynamic SL Price: < {stop_loss_price:.4f}")
                    if current_price <= stop_loss_price:
                        reason = f"DYNAMIC STOP LOSS triggered at price {current_price:.4f} (ATR: {atr_at_entry}, Multiplier: {config.ATR_MULTIPLIER})"
                        print(f"❌ [{symbol}] {reason}")
                        trade.parse_and_execute({"command": "close", "reasoning": reason}, symbol)
                elif side in ['short', 'sell']:
                    stop_loss_price = entry_price + (atr_at_entry * config.ATR_MULTIPLIER)
                    print(f"[{symbol}] PnL: {pnl_pct:.2f}% | Current: {current_price} | Dynamic SL Price: > {stop_loss_price:.4f}")
                    if current_price >= stop_loss_price:
                        reason = f"DYNAMIC STOP LOSS triggered at price {current_price:.4f} (ATR: {atr_at_entry}, Multiplier: {config.ATR_MULTIPLIER})"
                        print(f"❌ [{symbol}] {reason}")
                        trade.parse_and_execute({"command": "close", "reasoning": reason}, symbol)
            else:
                # Fallback to old percentage-based SL if ATR is not available
                print(f"[{symbol}] PnL: {pnl_pct:.2f}% | Current: {current_price} | (Fallback SL: < {-config.STOP_LOSS_PCT}%)")
                if pnl_pct <= -config.STOP_LOSS_PCT:
                    reason = f"FALLBACK STOP LOSS triggered at {pnl_pct:.2f}%"
                    print(f"❌ [{symbol}] {reason}")
                    trade.parse_and_execute({"command": "close", "reasoning": reason}, symbol)

        except Exception as e:
            print(f"[{symbol}] Error during TP/SL check: {e}")


# --- State Management ---
cycle_count = 0
consecutive_error_cycles = 0
last_cycle_errors = []
strategy_rules = {}
# --- End State Management ---

def load_strategy():
    """Loads strategy rules from strategy.json."""
    global strategy_rules
    try:
        with open('strategy.json', 'r') as f:
            strategy_rules = json.load(f)
        print("[INIT] Strategy rules loaded from strategy.json")
    except Exception as e:
        print(f"[CRITICAL] Could not load strategy.json: {e}. Bot will not run.")
        strategy_rules = {} # Reset to prevent running with old/bad config

def main_job():
    """
    Main job flow: Fetch all data once -> Update PnL -> Check TP/SL -> For each symbol: Decide -> Execute.
    This new structure uses a "Cycle Cache" to prevent redundant API calls.
    """
    global cycle_count, consecutive_error_cycles, last_cycle_errors
    cycle_count += 1
    
    # Reload strategy every cycle to catch updates made by the strategist
    load_strategy()
    if not strategy_rules:
        print("[WORKER] Halting cycle because strategy rules are not loaded.")
        return

    cycle_errors = []
    is_cycle_successful = False

    print(f"\n{'='*60}")
    print(f"--- Cycle Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Cycle #{cycle_count}) ---")
    print(f"--- Strategy: {strategy_rules.get('strategy_name', 'N/A')} ---")
    print(f"{'='*60}")

    # --- "CYCLE CACHE" DATA FETCH ---
    # 1. Fetch market data for all symbols ONCE at the beginning of the cycle.
    print("\n[STEP 1] Fetching market data for all symbols...")
    market_data_cache = {}
    for symbol in config.TRADING_SYMBOLS:
        summary = market.get_market_summary(symbol=symbol, interval='3m')
        if summary:
            market_data_cache[symbol] = summary
        else:
            error_msg = f"[{symbol}] Could not get market summary, it will be skipped this cycle."
            print(error_msg)
            cycle_errors.append(error_msg)
    
    if not market_data_cache:
        print("[WORKER] Could not fetch market data for ANY symbol. Skipping cycle.")
        consecutive_error_cycles += 1
        last_cycle_errors = cycle_errors
        return # Exit early if no data is available at all
    
    # 2. Update PnL for all open positions using the cached data
    if config.SIMULATION_MODE and portfolio:
        print("\n[STEP 2] Updating open positions from cached market data...")
        portfolio.update_open_positions(market_data_cache)
        
    # 3. Check for TP/SL on existing positions
    if config.SIMULATION_MODE and portfolio:
        print("\n[STEP 3] Checking TP/SL triggers...")
        check_tp_sl() # This function internally uses the updated portfolio state

    # 4. Get a fresh portfolio summary
    portfolio_summary = {}
    if config.SIMULATION_MODE and portfolio:
        print("\n[STEP 4] Getting portfolio summary...")
        portfolio_summary = portfolio.get_portfolio_summary()
        print("[PF] Portfolio Summary:", json.dumps(portfolio_summary, indent=2))

    # 5. For each symbol, run the main trading logic using cached data
    print("\n[STEP 5] Processing trading symbols with RULE-BASED ENGINE...")
    for symbol in config.TRADING_SYMBOLS:
        try:
            market_summary = market_data_cache.get(symbol)
            if not market_summary:
                # Already logged the error during fetch, just skip
                continue

            print(f"\n-> Processing {symbol}...")
            
            # a. Get current position status
            position_status = trade.get_current_position(symbol=symbol)
            
            # b. Get trade decision from the RULE-BASED ENGINE
            print(f"[{symbol}] Data (from cache): {json.dumps(market_summary)}")
            print(f"[{symbol}] Current Position: {position_status[0]}")
            decision = engine.decide_action(
                strategy=strategy_rules,
                market_data=market_summary, 
                position_status=position_status, 
                portfolio_summary=portfolio_summary
            )
            print(f"[{symbol}] Engine Decision: '{decision.get('command')}' | Reason: {decision.get('reasoning')}")

            # c. Execute the decision, passing the cached data
            trade.parse_and_execute(decision, symbol, market_summary, position_status)
            
            is_cycle_successful = True
            
        except Exception as e:
            error_msg = f"[{symbol}] An unexpected error occurred in the main loop: {e}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            cycle_errors.append(error_msg)
    
    # 6. Save state to file for web UI
    if config.SIMULATION_MODE and portfolio:
        print("\n[STEP 6] Saving state to portfolio_state.json for web UI...")
        try:
            state_data = {
                "portfolio_summary": portfolio.get_portfolio_summary(),
                "open_positions": portfolio.get_all_open_positions(),
                "equity_history": portfolio.get_equity_history()
            }
            with open('portfolio_state.json', 'w') as f:
                json.dump(state_data, f, indent=2)
        except Exception as e:
            print(f"Error saving state to file: {e}")

    # 7. Handle Error and Summary Email Logic
    if not is_cycle_successful and len(config.TRADING_SYMBOLS) > 0:
        consecutive_error_cycles += 1
        print(f"\n[WORKER] Cycle failed for all symbols. Consecutive error count: {consecutive_error_cycles}")
        last_cycle_errors = cycle_errors
    else:
        if consecutive_error_cycles > 0:
            print(f"\n[WORKER] Cycle succeeded. Resetting consecutive error count from {consecutive_error_cycles} to 0.")
        consecutive_error_cycles = 0

    if consecutive_error_cycles >= 5:
        print(f"\n[WORKER] Reached {consecutive_error_cycles} consecutive errors. Sending alert email...")
        mailer.send_error_email(last_cycle_errors)
        consecutive_error_cycles = 0 # Reset after sending to avoid spam

    # Send summary email every 30 cycles
    if cycle_count > 0 and cycle_count % 30 == 0:
        print(f"\n[WORKER] Reached cycle {cycle_count}. Sending periodic summary email...")
        open_positions = portfolio.get_all_open_positions() if portfolio else {}
        mailer.send_summary_email(portfolio_summary, open_positions)

    print(f"\n{'='*60}")
    print(f"--- Cycle End: Next run in 1 minute ---")
    print(f"{'='*60}\n")


print("--- RULE-BASED Scalping Bot Initialized ---")
print(f"Trading Assets: {', '.join(config.TRADING_SYMBOLS)}")
print(f"Engine: Running based on rules from 'strategy.json'")
print(f"Strategy: TP: {config.TAKE_PROFIT_PCT}% / SL: {config.STOP_LOSS_PCT}%")
print(f"Simulation Mode: {'Active' if config.SIMULATION_MODE else 'Inactive'}")
print(f"Run Interval: Every 1 minute (analyzing 3m candles)")
print("------------------------------------")

# Load strategy rules at startup
load_strategy()

print("\n[WORKER] Starting trading bot worker...")

# Schedule the main job to run every 1 minute
schedule.every(1).minutes.do(main_job)

# Run the job once immediately to start
if strategy_rules:
    main_job()
else:
    print("[WORKER] Bot not started due to missing strategy rules.")


# Main loop for the scheduler
print("\n[SCHEDULER] Worker is now running. Press Ctrl+C to stop.\n")
while True:
    schedule.run_pending()
    time.sleep(1)