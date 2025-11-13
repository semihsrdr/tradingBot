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

# --- YENİ GÜNCELLENMİŞ FONKSİYON ---
def check_tp_sl(market_data_cache: dict, cycle_errors: list):
    """
    Checks open positions and closes them if TP, Trailing SL, or
    static SL levels are hit.
    
    Priority:
    1. Take Profit
    2. Trailing Stop Loss (if active)
    3. Static Stop Loss (if TSL is not active)
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
            market_summary = market_data_cache.get(symbol)
            if not market_summary:
                print(f"[{symbol}] No market data in cache for TP/SL check. Skipping.")
                continue

            position_status = portfolio.get_position_details(symbol)
            margin = position.get('margin', 0)
            unrealized_pnl = position.get('unrealized_pnl', 0)
            entry_price = position.get('entry_price', 0)
            current_price = position.get('current_price', 0)
            atr_at_entry = position.get('atr_at_entry', 0)
            side = position.get('side')
            
            # YENİ: Pozisyonun gördüğü en yüksek kârı al
            highest_pnl_pct = position.get('highest_pnl_pct', 0.0)

            if margin == 0 or entry_price == 0:
                continue

            # PnL Yüzdesini hesapla
            pnl_pct = (unrealized_pnl / margin) * 100

            # --- POZİSYON KAPATMA MANTIĞI ---

            # 1. ÖNCE: TAKE PROFIT KONTROLÜ (Sabit Kâr Al)
            if pnl_pct >= config.TAKE_PROFIT_PCT:
                reason = f"TAKE PROFIT triggered at {pnl_pct:.2f}%"
                print(f"✅ [{symbol}] {reason}")
                trade.parse_and_execute(
                    {"command": "close", "reasoning": reason},
                    symbol, market_summary, position_status
                )
                continue  # Pozisyon kapandı, sonraki sembole geç

            # 2. YENİ: TRAILING STOP LOSS KONTROLÜ
            trailing_sl_active = False
            if config.ENABLE_TRAILING_STOP and highest_pnl_pct >= config.TRAILING_STOP_TRIGGER_PCT:
                trailing_sl_active = True
                
                # Yeni TSL kâr seviyesini belirle
                trailing_stop_level_pct = highest_pnl_pct - config.TRAILING_STOP_DISTANCE_PCT

                print(f"[{symbol}] PnL: {pnl_pct:.2f}% | Highest: {highest_pnl_pct:.2f}% | Trailing SL: < {trailing_stop_level_pct:.2f}%")

                if pnl_pct <= trailing_stop_level_pct:
                    reason = f"TRAILING STOP LOSS triggered at {pnl_pct:.2f}%. (Highest: {highest_pnl_pct:.2f}%)"
                    print(f"❌ [{symbol}] {reason}")
                    trade.parse_and_execute(
                        {"command": "close", "reasoning": reason},
                        symbol, market_summary, position_status
                    )
                    continue # Pozisyon kapandı, sonraki sembole geç
            
            # 3. SONRA: STATİK STOP LOSS KONTROLÜ (Eğer TSL aktif değilse)
            # TSL devreye girdiyse (örn: kâr %10'da), artık pozisyonun %-5'e düşmesi
            # gibi bir normal SL ile kapanmasını istemeyiz.
            if not trailing_sl_active:
                if atr_at_entry > 0:
                    stop_loss_price = 0
                    if side in ['long', 'buy']:
                        stop_loss_price = entry_price - (atr_at_entry * config.ATR_MULTIPLIER)
                        print(f"[{symbol}] PnL: {pnl_pct:.2f}% | Current: {current_price} | Static SL: < {stop_loss_price:.4f}")
                        if current_price <= stop_loss_price:
                            reason = f"DYNAMIC (ATR) STOP LOSS triggered at {current_price:.4f}"
                            print(f"❌ [{symbol}] {reason}")
                            trade.parse_and_execute(
                                {"command": "close", "reasoning": reason},
                                symbol, market_summary, position_status
                            )
                            continue
                    
                    elif side in ['short', 'sell']:
                        stop_loss_price = entry_price + (atr_at_entry * config.ATR_MULTIPLIER)
                        print(f"[{symbol}] PnL: {pnl_pct:.2f}% | Current: {current_price} | Static SL: > {stop_loss_price:.4f}")
                        if current_price >= stop_loss_price:
                            reason = f"DYNAMIC (ATR) STOP LOSS triggered at {current_price:.4f}"
                            print(f"❌ [{symbol}] {reason}")
                            trade.parse_and_execute(
                                {"command": "close", "reasoning": reason},
                                symbol, market_summary, position_status
                            )
                            continue
                else:
                    # ATR yoksa Fallback (Yedek) Yüzdesel SL
                    print(f"[{symbol}] PnL: {pnl_pct:.2f}% | (Fallback SL: < {-config.STOP_LOSS_PCT}%)")
                    if pnl_pct <= -config.STOP_LOSS_PCT:
                        reason = f"FALLBACK STOP LOSS triggered at {pnl_pct:.2f}%"
                        print(f"❌ [{symbol}] {reason}")
                        trade.parse_and_execute(
                            {"command": "close", "reasoning": reason},
                            symbol, market_summary, position_status
                        )
                        continue

        except Exception as e:
            error_msg = f"[{symbol}] Error during TP/SL check: {e}"
            print(error_msg)
            cycle_errors.append(error_msg)
            import traceback
            traceback.print_exc()
# --- GÜNCELLENEN FONKSİYONUN SONU ---


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

    print(f"\n{'='*60}")
    print(f"--- Cycle Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Cycle #{cycle_count}) ---")
    print(f"--- Strategy: {strategy_rules.get('strategy_name', 'N/A')} ---")
    print(f"{'='*66}")

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
        check_tp_sl(market_data_cache, cycle_errors) # This function internally uses the updated portfolio state

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
            
            # is_cycle_successful = True # Bu değişken artık kullanılmıyor, kaldırılabilir
            
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
print(f"Engine: Running based on rules from 'strategy.json'")
# YENİ: Başlangıç log mesajına TSL bilgisini ekleyelim
print(f"Strategy: TP: {config.TAKE_PROFIT_PCT}% / Static SL (ATR): {config.ATR_MULTIPLIER}x")
print(f"Trailing SL: {'Active' if config.ENABLE_TRAILING_STOP else 'Inactive'}")
if config.ENABLE_TRAILING_STOP:
    print(f"  -> Trigger: {config.TRAILING_STOP_TRIGGER_PCT}%, Distance: {config.TRAILING_STOP_DISTANCE_PCT}%")
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