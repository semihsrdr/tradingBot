import ccxt
import pandas as pd
import pandas_ta as ta
import os

def fetch_market_state():
    exchange = ccxt.binance({
        "apiKey": os.getenv("BINANCE_TESTNET_KEY"),
        "secret": os.getenv("BINANCE_TESTNET_SECRET"),
    })
    exchange.set_sandbox_mode(True)

    # 3m candles
    ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="3m", limit=50)
    df = pd.DataFrame(ohlcv, columns=['ts','o','h','l','c','v'])
    
    df['ema10'] = ta.ema(df['c'], length=10)
    df['ema20'] = ta.ema(df['c'], length=20)
    df['atr']   = ta.atr(df['h'], df['l'], df['c'], length=14)

    latest = df.iloc[-1]

    return {
        "timestamp": int(latest['ts']),
        "price": float(latest['c']),
        "ema10": float(latest['ema10']),
        "ema20": float(latest['ema20']),
        "atr": float(latest['atr']),
    }

print(fetch_market_state())