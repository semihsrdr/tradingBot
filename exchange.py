import ccxt
import os
from dotenv import load_dotenv
import config

load_dotenv()

def get_client():
    """
    Creates and configures the CCXT exchange client.
    - In simulation mode, it connects without API keys to fetch live public data.
    - In live mode, it connects to the testnet with API keys for trading.
    """
    if config.SIMULATION_MODE:
        # Simulation mode: No API keys needed for public data (like price feeds)
        exchange = ccxt.binance({
            "enableRateLimit": True,
        })
    else:
        # Live/trading mode: Use API keys and connect to the testnet
        api_key = config.BINANCE_API_KEY
        api_secret = config.BINANCE_API_SECRET
        
        exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })
        # For safety, we keep trading on the testnet unless explicitly changed
        exchange.set_sandbox_mode(True)
        # exchange.verbose = True # Uncomment to see requests

    return exchange
