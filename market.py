import config
import pandas as pd
import pandas_ta as ta
from exchange import get_client
import json

def get_market_summary(symbol=config.TRADING_SYMBOLS[0], interval='3m', limit=250):
    """
    Fetches recent candles, calculates key indicators including EMA, RSI, ATR, Volume SMA,
    ADX, and Bollinger Bands, and returns a summary for the trading engine.
    """
    try:
        client = get_client()
        # 1. Fetch recent candles
        ohlcv = client.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
        
        # 2. Convert to Pandas DataFrame
        columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = pd.DataFrame(ohlcv, columns=columns)
        
        # Convert necessary columns to numeric types
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        # 3. Calculate All Indicators
        # Standard indicators
        df.ta.ema(length=200, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.atr(length=14, append=True)
        df.ta.sma(close=df['volume'], length=20, append=True)
        
        # ADX for trend strength
        adx_indicator = df.ta.adx(length=14)
        if adx_indicator is not None and not adx_indicator.empty:
            df['ADX_14'] = adx_indicator.iloc[:, 0] # ADX is the first column
        else:
            df['ADX_14'] = 25 # Default neutral value

        # Bollinger Bands for squeeze detection
        df.ta.bbands(length=20, std=2, append=True)
        if 'BBL_20_2.0' in df.columns and 'BBU_20_2.0' in df.columns:
            # Calculate Bandwidth
            df['BBW_20_2.0'] = (df['BBU_20_2.0'] - df['BBL_20_2.0']) / df['close']
        else:
            df['BBW_20_2.0'] = 0

        # Squeeze Detection Logic
        squeeze_lookback = 50
        # Ensure we have enough data for the lookback
        if len(df) > squeeze_lookback:
            # Find the minimum bandwidth in the last `squeeze_lookback` periods
            min_bandwidth = df['BBW_20_2.0'].iloc[-squeeze_lookback:].min()
            # Check if the current bandwidth is at or very near this minimum (within 10%)
            is_in_squeeze = df['BBW_20_2.0'].iloc[-1] <= min_bandwidth * 1.1
        else:
            is_in_squeeze = False # Not enough data to determine a squeeze

        # 4. Select the last candle (most recent data)
        last_candle = df.iloc[-1]

        # Fetch the most recent price using fetch_ticker for accuracy
        ticker = client.fetch_ticker(symbol)
        current_price = ticker['last'] if ticker and 'last' in ticker else last_candle['close']

        # 5. Create summary JSON for the engine
        ema_200_value = round(last_candle['EMA_200'], 2)
        trend = "bullish" if current_price > ema_200_value else "bearish"

        summary = {
            "symbol": symbol,
            "current_price": current_price,
            "ema_200": ema_200_value,
            "rsi_14": round(last_candle['RSI_14'], 2),
            "atr_14": round(last_candle.get('ATRr_14', 0.0), 4) if pd.notna(last_candle.get('ATRr_14')) else 0.0,
            "volume": round(last_candle['volume'], 2),
            "volume_sma_20": round(last_candle.get('SMA_20_volume', last_candle.get('SMA_20')), 2), # pandas-ta column name can vary
            "market_trend": trend,
            "adx_14": round(last_candle.get('ADX_14', 25), 2),
            "bollinger_bandwidth": round(last_candle.get('BBW_20_2.0', 0), 5),
            "is_in_bollinger_squeeze": bool(is_in_squeeze)
        }
        
        return summary
        
    except Exception as e:
        print(f"Error getting market data for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None

# You can test this file directly
if __name__ == "__main__":
    # Test with the first symbol from the config
    test_symbol = config.TRADING_SYMBOLS[0]
    
    print("\n--- Testing get_market_summary (for Engine) ---")
    summary = get_market_summary(symbol=test_symbol)
    if summary:
        print(json.dumps(summary, indent=2))
