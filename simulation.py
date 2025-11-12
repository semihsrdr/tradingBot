import config
import json
import os
from datetime import datetime
from market import get_market_summary # To get prices
from trade_logger import log_trade # Import the logger

STATE_FILE = "simulation_state.json"

class SimulatedPortfolio:
    """
    Manages a virtual portfolio, tracking leveraged positions, balance,
    and PnL across multiple symbols, with state persistence.
    """
    def __init__(self):
        self.balance = config.SIMULATION_STARTING_BALANCE
        self.positions = {}
        self.equity_history = []
        self._load_state()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    self.balance = state.get('balance', config.SIMULATION_STARTING_BALANCE)
                    self.positions = state.get('positions', {})
                    self.equity_history = state.get('equity_history', [])
                print(f"[SIM] Loaded saved state from: {STATE_FILE}")
            except Exception as e:
                print(f"[SIM] Could not read state file, starting fresh: {e}")
        else:
            print("[SIM] No state file, starting fresh.")
            # Add the initial equity point when starting fresh
            self.equity_history.append({
                "timestamp": datetime.now().isoformat(),
                "equity": self.balance
            })

    def _save_state(self):
        try:
            # Add a new data point to the history before saving
            current_summary = self.get_portfolio_summary()
            self.equity_history.append({
                "timestamp": datetime.now().isoformat(),
                "equity": current_summary['total_equity_usd']
            })
            
            # Keep the history from getting too large
            max_history_points = 1440 # Keep last 24 hours of 1-min data
            if len(self.equity_history) > max_history_points:
                self.equity_history = self.equity_history[-max_history_points:]

            with open(STATE_FILE, 'w') as f:
                state = {
                    'balance': self.balance, 
                    'positions': self.positions,
                    'equity_history': self.equity_history
                }
                json.dump(state, f, indent=4)
        except Exception as e:
            print(f"[SIM] Error writing to state file: {e}")

    def get_position_details(self, symbol):
        position = self.positions.get(symbol)
        if not position:
            return "flat", 0
        return position['side'], position['quantity']

    def get_all_open_positions(self):
        return self.positions

    def get_equity_history(self):
        return self.equity_history

    def get_portfolio_summary(self):
        """
        Calculates and returns a summary of the entire portfolio.
        Equity = balance + total_margin + total_unrealized_pnl
        """
        total_margin = sum(p.get('margin', 0) for p in self.positions.values())
        total_unrealized_pnl = sum(p.get('unrealized_pnl', 0) for p in self.positions.values())
        equity = self.balance + total_margin + total_unrealized_pnl
        
        return {
            "available_balance_usd": self.balance,
            "total_equity_usd": equity,
            "unrealized_pnl_usd": total_unrealized_pnl,
            "open_positions_count": len(self.positions)
        }

    def set_leverage(self, leverage, symbol):
        """Stores leverage to be used for the next trade on a symbol."""
        # In this model, leverage is set right before opening.
        # We just need to pass it to the _open_position method.
        print(f"[SIM] Leverage for {symbol} will be set to {leverage}x on next trade.")
        # We don't store it globally anymore, it's per-position.
        return True

    def create_order(self, symbol, order_type, side, quantity, params=None):
        params = params or {}
        # The price from market_data passed in params is more accurate for logging
        market_data = params.get('market_data', get_market_summary(symbol=symbol))
        current_price = market_data.get('current_price')
        reason = params.get('reason', 'N/A')

        if params.get('reduceOnly'):
            self._close_position(symbol, current_price, reason, market_data)
        else:
            trade_amount_usd = params.get('trade_amount_usd')
            leverage = params.get('leverage', 20)
            self._open_position(symbol, side, quantity, current_price, leverage, trade_amount_usd, reason, market_data)

    def _open_position(self, symbol, side, quantity, price, leverage, trade_amount_usd, reason, market_data):
        if symbol in self.positions:
            print(f"[SIM] Position already open for {symbol}.")
            return

        margin_used = trade_amount_usd
        if self.balance < margin_used:
            print(f"[SIM] Insufficient balance to open position for {symbol}. Need {margin_used:.2f}, have {self.balance:.2f}")
            return

        self.balance -= margin_used

        self.positions[symbol] = {
            'side': side,
            'entry_price': price,
            'current_price': price,
            'quantity': quantity,
            'leverage': leverage,
            'margin': margin_used,
            'unrealized_pnl': 0,
            'atr_at_entry': market_data.get('atr_14', 0) # Store ATR on entry
        }
        print(f"[SIM] POSITION OPENED: {symbol} {side.upper()} {quantity:.6f} @ {price}. Margin: {margin_used:.2f} USDT. New Balance: {self.balance:.2f} USDT")
        self._save_state()

        # Log the opening trade
        log_data = {
            'action': 'OPEN',
            'symbol': symbol,
            'reason': reason,
            'side': side,
            'quantity': quantity,
            'leverage': leverage,
            'margin': margin_used,
            'entry_price': price,
            'market_data': market_data
        }
        log_trade(log_data)


    def _close_position(self, symbol, price, reason, market_data):
        position = self.positions.get(symbol)
        if not position:
            print(f"[SIM] No position to close for {symbol}.")
            return

        pnl = self._calculate_pnl(symbol, price)
        margin_returned = position['margin']
        self.balance += margin_returned + pnl
        
        print(f"[SIM] POSITION CLOSED: {symbol}, Exit: {price}, PnL: {pnl:.4f}, Margin Ret: {margin_returned:.2f}, New Balance: {self.balance:.2f}")
        
        # Log the closing trade
        pnl_pct = (pnl / position['margin']) * 100 if position['margin'] > 0 else 0
        log_data = {
            'action': 'CLOSE',
            'symbol': symbol,
            'reason': reason,
            'side': position['side'],
            'quantity': position['quantity'],
            'leverage': position['leverage'],
            'margin': position['margin'],
            'entry_price': position['entry_price'],
            'exit_price': price,
            'pnl_usd': pnl,
            'pnl_pct': pnl_pct,
            'market_data': market_data
        }
        log_trade(log_data)

        del self.positions[symbol]
        self._save_state()

    def _calculate_pnl(self, symbol, current_price):
        position = self.positions.get(symbol)
        if not position:
            return 0
        
        price_diff = current_price - position['entry_price']
        if position['side'] == 'sell':
            price_diff = -price_diff
            
        return price_diff * position['quantity']

    def update_open_positions(self, market_data_cache: dict):
        """ 
        Iterates through open positions, updates current price and unrealized PnL
        using a pre-fetched cache of market data.
        """
        if not self.positions:
            # Still save state to record equity history even if no positions are open
            self._save_state()
            return
        
        print("[SIM] Updating PnL for open positions using cached data...")
        symbols_to_update = list(self.positions.keys())
        updated_count = 0
        
        for symbol in symbols_to_update:
            position = self.positions[symbol]
            market_data = market_data_cache.get(symbol)

            if market_data and market_data.get('current_price'):
                current_price = market_data.get('current_price')
                old_price = position.get('current_price', 'N/A')
                position['current_price'] = current_price
                position['unrealized_pnl'] = self._calculate_pnl(symbol, current_price)
                updated_count += 1
                # This log can be very noisy, let's comment it out for now.
                # print(f"[SIM] Updated {symbol}: Old Price: {old_price}, New Price: {current_price}, Unrealized PnL: {position['unrealized_pnl']:.4f}")
            else:
                print(f"[SIM] Warning: No market data for {symbol} in cache during PnL update.")
        
        # Save state regardless of whether positions were updated, to capture equity history
        self._save_state()
        if updated_count > 0:
            print(f"[SIM] PnL update complete. Updated {updated_count}/{len(symbols_to_update)} positions.")
        else:
            print("[SIM] No positions were updated, but state saved for equity tracking.")

