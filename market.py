import config
import pandas as pd
import pandas_ta as ta
from exchange import get_client
import json

def get_market_summary(symbol=config.TRADING_SYMBOLS[0], interval='3m', limit=250):
    """
    Fetches recent candles, calculates key indicators including EMA, RSI, ATR, and Volume SMA,
    and returns a JSON summary for the LLM.
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

        # 3. Calculate Indicators (using pandas-ta)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df.ta.ema(length=200, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.atr(length=14, append=True) # For dynamic stop-loss
        df.ta.sma(close=df['volume'], length=20, append=True) # For volume confirmation
        
        # 4. Select the last candle (most recent data)
        last_candle = df.iloc[-1]

        # Fetch the most recent price using fetch_ticker for accuracy
        ticker = client.fetch_ticker(symbol)
        current_price = ticker['last'] if ticker and 'last' in ticker else last_candle['close']

        # 5. Create summary JSON for the LLM
        ema_200_value = round(last_candle['EMA_200'], 2)
        trend = "bullish" if current_price > ema_200_value else "bearish"

        summary = {
            "symbol": symbol,
            "current_price": current_price,
            "ema_20": round(last_candle['EMA_20'], 2),
            "ema_50": round(last_candle['EMA_50'], 2),
            "ema_200": ema_200_value,
            "rsi_14": round(last_candle['RSI_14'], 2),
            "atr_14": round(last_candle['ATRr_14'], 4), # ATR value
            "volume": round(last_candle['volume'], 2),
            "volume_sma_20": round(last_candle['SMA_20'], 2), # Volume SMA
            "market_trend": trend
        }
        
        return summary
        
    except Exception as e:
        print(f"Error getting market data for {symbol}: {e}")
        return None

def get_broad_market_analysis(symbol=config.TRADING_SYMBOLS[0], interval='3m', limit=480):
    """
    Fetches a larger dataset of candles (e.g., last 24h) to analyze the broader market context.
    Calculates ADX for trend strength and overall volatility.
    This is used by the Strategist LLM.
    """
    try:
        client = get_client()
        ohlcv = client.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
        
        columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = pd.DataFrame(ohlcv, columns=columns)
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        # Calculate ADX for trend strength
        adx_indicator = df.ta.adx(length=14)
        if adx_indicator is not None and not adx_indicator.empty:
            df['ADX_14'] = adx_indicator.iloc[:, 0] # ADX is the first column
        else:
            df['ADX_14'] = 25 # Default neutral value

        # Calculate overall volatility (e.g., ATR as a percentage of price)
        df.ta.atr(length=14, append=True)
        
        last_candle = df.iloc[-1]
        current_price = last_candle['close']
        
        atr_value = last_candle.get('ATRr_14', 0)
        atr_pct = (atr_value / current_price) * 100 if current_price > 0 else 0
        
        adx_value = last_candle.get('ADX_14', 25)
        
        market_condition = "Trending" if adx_value > 25 else "Choppy/Ranging"

        analysis = {
            "symbol": symbol,
            "timeframe": f"{limit * int(interval.replace('m', '')) / 60:.1f} hours",
            "market_condition": market_condition,
            "trend_strength_adx_14": round(adx_value, 2),
            "volatility_atr_pct": round(atr_pct, 4)
        }
        return analysis

    except Exception as e:
        print(f"Error getting broad market analysis for {symbol}: {e}")
        return None


# You can test this file directly
if __name__ == "__main__":
    # Test with the first symbol from the config
    test_symbol = config.TRADING_SYMBOLS[0]
    
    print("\n--- Testing get_market_summary (for Engine) ---")
    summary = get_market_summary(symbol=test_symbol)
    if summary:
        print(json.dumps(summary, indent=2))

    print("\n--- Testing get_broad_market_analysis (for Strategist) ---")
    broad_analysis = get_broad_market_analysis(symbol=test_symbol)
    if broad_analysis:
        print(json.dumps(broad_analysis, indent=2))
