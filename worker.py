import schedule
import time
import market
import engine # trader'ı engine ile değiştiriyoruz
import config
import json
from datetime import datetime, timedelta
import trade_logger
import mailer # Import the new mailer module

# --- State Management ---
cycle_count = 0
consecutive_error_cycles = 0
last_cycle_errors = []
cooldown_manager = {} # Manages cooldown periods for symbols

# ÖNCE trade modülünü import et
import trade

# Initialize portfolio ONCE at startup
portfolio = None
if config.SIMULATION_MODE:
    from simulation import SimulatedPortfolio
    # Pass the cooldown manager to the portfolio
    portfolio = SimulatedPortfolio(cooldown_manager)
    # Şimdi portfolio'yu trade modülüne set et
    trade.set_portfolio(portfolio)
    print(f"[INIT] Portfolio initialized and shared with trade module and cooldown manager.")

def main_job():
    """
    Main job flow: Fetch all data once -> Update PnL -> For each symbol: Decide -> Execute.
    This new structure uses a "Cycle Cache" to prevent redundant API calls.
    """
    global cycle_count, consecutive_error_cycles, last_cycle_errors
    cycle_count += 1
    
    cycle_errors = []

    print(f"\n{'='*60}")
    print(f"--- Cycle Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Cycle #{cycle_count}) ---")
    print(f"{'='*66}")

    # --- "CYCLE CACHE" DATA FETCH ---
    # 1. Fetch market data for all symbols ONCE at the beginning of the cycle.
    print("\n[STEP 1] Fetching market data for all symbols...")
    market_data_cache = {}
    for symbol in config.TRADING_SYMBOLS:
        summary = market.get_market_summary(symbol=symbol, interval='15m')
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

    # 3. Get a fresh portfolio summary
    portfolio_summary = {}
    if config.SIMULATION_MODE and portfolio:
        print("\n[STEP 3] Getting portfolio summary...")
        portfolio_summary = portfolio.get_portfolio_summary()
        print("[PF] Portfolio Summary:", json.dumps(portfolio_summary, indent=2))

    # 4. For each symbol, run the main trading logic using cached data
    print("\n[STEP 4] Processing trading symbols with RULE-BASED ENGINE...")
    for symbol in config.TRADING_SYMBOLS:
        try:
            market_summary = market_data_cache.get(symbol)
            if not market_summary:
                # Already logged the error during fetch, just skip
                continue

            print(f"\n-> Processing {symbol}...")
            
            # a. Get current position status
            position_status = trade.get_current_position(symbol=symbol)
            
            # b. Check for and manage cooldown period
            cooldown_status = None
            if symbol in cooldown_manager:
                cooldown_info = cooldown_manager[symbol]
                if datetime.now() < cooldown_info["until"]:
                    cooldown_status = cooldown_info # Pass the active cooldown info
                    print(f"[{symbol}] Symbol is in cooldown for '{cooldown_status['direction']}' trades until {cooldown_info['until'].strftime('%H:%M:%S')}.")
                else:
                    print(f"[{symbol}] Cooldown expired for '{cooldown_info['direction']}' trades.")
                    del cooldown_manager[symbol] # Cleanup expired cooldown
            
            # c. Get trade decision from the RULE-BASED ENGINE
            print(f"[{symbol}] Data (from cache): {json.dumps(market_summary)}")
            print(f"[{symbol}] Current Position: {position_status[0]}")
            decision = engine.decide_action(
                market_data=market_summary, 
                position_status=position_status, 
                portfolio_summary=portfolio_summary,
                cooldown_status=cooldown_status # Pass cooldown status to engine
            )
            print(f"[{symbol}] Engine Decision: '{decision.get('command')}' | Reason: {decision.get('reasoning')}")

            # d. Execute the decision, passing the cached data
            trade.parse_and_execute(decision, symbol, market_summary, position_status)
            
        except Exception as e:
            error_msg = f"[{symbol}] An unexpected error occurred in the main loop: {e}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            cycle_errors.append(error_msg)
    
    # 5. Save state to file for web UI
    if config.SIMULATION_MODE and portfolio:
        print("\n[STEP 5] Saving state to portfolio_state.json for web UI...")
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

    # 6. Handle Error and Summary Email Logic
    if cycle_errors:
        consecutive_error_cycles += 1
        last_cycle_errors.extend(cycle_errors)
        print(f"\n[WORKER] Cycle finished with {len(cycle_errors)} error(s). Total accumulated errors: {len(last_cycle_errors)}. Consecutive error cycles: {consecutive_error_cycles}.")
    else:
        if consecutive_error_cycles > 0:
            print(f"\n[WORKER] Cycle succeeded. Resetting consecutive error count from {consecutive_error_cycles} to 0.")
        consecutive_error_cycles = 0
        last_cycle_errors = []

    if len(last_cycle_errors) >= 15:
        print(f"\n[WORKER] Accumulated {len(last_cycle_errors)} errors over {consecutive_error_cycles} cycles. Sending alert email...")
        mailer.send_error_email(last_cycle_errors)
        consecutive_error_cycles = 0
        last_cycle_errors = []

    # Send summary email every 30 cycles
    if cycle_count > 0 and cycle_count % 120 == 0:
        print(f"\n[WORKER] Reached cycle {cycle_count}. Sending periodic summary email...")
        open_positions = portfolio.get_all_open_positions() if portfolio else {}
        mailer.send_summary_email(portfolio_summary, open_positions)

    print(f"\n{'='*60}")
    print(f"--- Cycle End: Next run in 1 minute ---")
    print(f"{'='*60}\n")


print("--- RULE-BASED Scalping Bot Initialized ---")
print(f"Trading Assets: {', '.join(config.TRADING_SYMBOLS)}")
print(f"Engine: Running with hardcoded strategy rules.")
# YENİ: Başlangıç log mesajına TSL bilgisini ekleyelim
print(f"Strategy: TP: {config.TAKE_PROFIT_PCT}% / Static SL (ATR): {config.ATR_MULTIPLIER}x")
print(f"Trailing SL: {'Active' if config.ENABLE_TRAILING_STOP else 'Inactive'}")
if config.ENABLE_TRAILING_STOP:
    print(f"  -> Trigger: {config.TRAILING_STOP_TRIGGER_PCT}%, Distance: {config.TRAILING_STOP_DISTANCE_PCT}%")
print(f"Simulation Mode: {'Active' if config.SIMULATION_MODE else 'Inactive'}")
print(f"Run Interval: Every 1 minute (analyzing 3m candles)")
print("------------------------------------")

print("\n[WORKER] Starting trading bot worker...")

# Schedule the main job to run every 1 minute
schedule.every(1).minutes.do(main_job)

# Run the job once immediately to start
main_job()


# Main loop for the scheduler
print("\n[SCHEDULER] Worker is now running. Press Ctrl+C to stop.\n")
while True:
    schedule.run_pending()
    time.sleep(1)