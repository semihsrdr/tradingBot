import logging
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime

LOG_FILE = "trading_log.txt"

def setup_trade_logger():
    """Sets up a rotating file logger for trade activities."""
    global logger
    logger = logging.getLogger("TradeLogger")
    logger.setLevel(logging.INFO)
    
    # Prevent adding multiple handlers if called more than once
    if logger.hasHandlers():
        logger.handlers.clear()

    # Use a rotating file handler to keep log size in check
    handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=2) # 5 MB per file, 2 backups
    
    # No formatter, we will format the string manually for readability
    # formatter = logging.Formatter('%(asctime)s - %(message)s')
    # handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    return logger

def log_trade(log_data: dict):
    """
    Logs a trade event (open or close) in a readable, structured format.
    
    Args:
        log_data (dict): A dictionary containing all relevant trade information.
                         Keys like 'action', 'symbol', 'reason', 'pnl_usd', etc.
    """
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        action = log_data.get('action', 'N/A').upper()
        symbol = log_data.get('symbol', 'N/A')
        
        log_entry = f"--- {action} EVENT: {symbol} | {timestamp} ---\n"
        
        # Reason for the action
        log_entry += f"Reason: {log_data.get('reason', 'No reason provided.')}\n"
        
        # Position Details
        side = log_data.get('side', 'N/A').upper()
        quantity = log_data.get('quantity', 0)
        leverage = log_data.get('leverage', 0)
        margin = log_data.get('margin', 0)
        entry_price = log_data.get('entry_price', 0)
        
        log_entry += f"Position: {side} | Qty: {quantity:.6f} | Leverage: {leverage}x | Margin: ${margin:.2f}\n"
        
        # Market Signals
        market_data = log_data.get('market_data', {})
        current_price = market_data.get('current_price', 0)
        ema_20 = market_data.get('ema_20', 0)
        ema_50 = market_data.get('ema_50', 0)
        rsi_14 = market_data.get('rsi_14', 0)
        trend = market_data.get('market_trend', 'N/A')
        
        log_entry += f"Signals: Price: ${current_price} | EMA20: {ema_20} | EMA50: {ema_50} | RSI: {rsi_14} | Trend: {trend}\n"
        
        # Entry/Exit and PnL
        if action == 'OPEN':
            log_entry += f"Entry Price: ${entry_price}\n"
        elif action == 'CLOSE':
            exit_price = log_data.get('exit_price', 0)
            pnl_usd = log_data.get('pnl_usd', 0)
            pnl_pct = log_data.get('pnl_pct', 0)
            log_entry += f"Entry: ${entry_price} | Exit: ${exit_price}\n"
            log_entry += f"Result: PnL: ${pnl_usd:.4f} | PnL % on Margin: {pnl_pct:.2f}%\n"

        log_entry += "-" * 50 + "\n\n"
        
        logger.info(log_entry)

    except Exception as e:
        # Fallback for any formatting errors
        error_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.error(f"--- LOGGING ERROR | {error_timestamp} ---\nCould not format log entry. Raw data: {json.dumps(log_data)}\nError: {e}\n" + "-"*50 + "\n\n")

# Initialize the logger when the module is imported
logger = setup_trade_logger()
