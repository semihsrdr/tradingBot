import config

def _determine_primary_trend(df, current_price):
    """
    Determines the primary market trend from a higher timeframe DataFrame.
    """
    if df is None or df.empty:
        return 'neutral', "Primary timeframe data is missing."

    last_candle = df.iloc[-1]
    ema_200 = last_candle.get('EMA_200')

    if ema_200 is None:
        return 'neutral', "EMA_200 not calculated on primary timeframe."

    if current_price > ema_200:
        return 'bullish', f"Primary trend is bullish (Price > {config.PRIMARY_TIMEFRAME} EMA200)."
    elif current_price < ema_200:
        return 'bearish', f"Primary trend is bearish (Price < {config.PRIMARY_TIMEFRAME} EMA200)."
    else:
        return 'neutral', f"Price is at the {config.PRIMARY_TIMEFRAME} EMA200, trend is neutral."

def _find_entry_signal(df, strategy, current_price):
    """
    Finds a potential entry signal (long or short) on the entry timeframe DataFrame.
    """
    if df is None or df.empty:
        return 'hold', "Entry timeframe data is missing."

    last_candle = df.iloc[-1]
    rsi = last_candle.get('RSI_14', 50)
    volume = last_candle.get('volume', 0)
    volume_sma = last_candle.get('volume_sma_20', 0)

    filters = strategy.get('filters', {})
    long_cond = strategy.get('long_conditions', {})
    short_cond = strategy.get('short_conditions', {})

    # RSI Pullback Check
    is_long_pullback = long_cond.get('rsi_entry_min', 30) < rsi < long_cond.get('rsi_entry_max', 50)
    is_short_pullback = short_cond.get('rsi_entry_min', 50) < rsi < short_cond.get('rsi_entry_max', 70)

    # Volume Confirmation Check
    volume_confirmed = volume > volume_sma if filters.get('use_volume_confirmation') else True

    if is_long_pullback and volume_confirmed:
        return 'long', f"Entry signal: LONG (RSI pullback at {rsi:.1f} and volume confirmed)."
    
    if is_short_pullback and volume_confirmed:
        return 'short', f"Entry signal: SHORT (RSI pullback at {rsi:.1f} and volume confirmed)."

    return 'hold', f"No entry signal on {config.ENTRY_TIMEFRAME} (RSI: {rsi:.1f})."


def decide_action(strategy: dict, multi_timeframe_data: dict, position_status: tuple, portfolio_summary: dict, cooldown_status: dict = None) -> dict:
    """
    Decides a trading action based on a multi-timeframe analysis.
    
    Args:
        strategy: The strategy rules from strategy.json.
        multi_timeframe_data: A dictionary of DataFrames for different timeframes.
        position_status: A tuple of ('side', quantity).
        portfolio_summary: A dictionary with portfolio details.
        cooldown_status: A dict indicating if a symbol is on cooldown.

    Returns:
        A decision dictionary.
    """
    position_side, _ = position_status
    
    primary_df = multi_timeframe_data.get(config.PRIMARY_TIMEFRAME)
    entry_df = multi_timeframe_data.get(config.ENTRY_TIMEFRAME)

    if entry_df is None or entry_df.empty:
        return {"command": "hold", "reasoning": "Critical error: Entry timeframe data is missing.", "trade_amount_usd": 0}
    
    # Use the most recent price from the entry timeframe for all calculations
    current_price = entry_df.iloc[-1]['close']

    # --- 1. Determine Primary Trend ---
    primary_trend, trend_reason = _determine_primary_trend(primary_df, current_price)

    # --- 2. Handle Existing Positions ---
    if position_side != 'flat':
        # Close position if primary trend reverses
        if (position_side in ['long', 'buy'] and primary_trend == 'bearish') or \
           (position_side in ['short', 'sell'] and primary_trend == 'bullish'):
            return {"command": "close", "reasoning": f"Closing {position_side} position: Primary trend reversed to {primary_trend}.", "trade_amount_usd": 0}
        
        # Add other closing conditions here if needed (e.g., RSI extremes on entry timeframe)
        
        return {"command": "hold", "reasoning": f"Holding {position_side} position. {trend_reason}", "trade_amount_usd": 0}

    # --- 3. Look for New Entry (if flat) ---

    # Cooldown Filter
    if cooldown_status and cooldown_status.get('direction') == ('long' if primary_trend == 'bullish' else 'short'):
         return {"command": "hold", "reasoning": f"Cooldown active for {cooldown_status.get('direction').upper()} trades.", "trade_amount_usd": 0}

    # No-Trade Zone Filter (based on primary trend EMA)
    if primary_df is not None and not primary_df.empty:
        ema_200_primary = primary_df.iloc[-1].get('EMA_200')
        if ema_200_primary and strategy['filters'].get('no_trade_zone_pct', 0) > 0:
            if abs(current_price - ema_200_primary) / ema_200_primary < strategy['filters']['no_trade_zone_pct']:
                return {"command": "hold", "reasoning": f"Price is within the no-trade zone of the {config.PRIMARY_TIMEFRAME} EMA200.", "trade_amount_usd": 0}

    # --- 4. Find Entry Signal on Entry Timeframe ---
    entry_signal, entry_reason = _find_entry_signal(entry_df, strategy, current_price)

    # --- 5. Final Decision: Align Trend and Signal ---
    trade_params = strategy.get('trade_parameters', {})
    leverage = trade_params.get('default_leverage', 20)
    trade_pct = trade_params.get('trade_amount_pct_of_balance', 10)
    balance = portfolio_summary.get('available_balance_usd', 0)
    trade_amount = balance * (trade_pct / 100)

    if primary_trend == 'bullish' and entry_signal == 'long':
        reason = f"Trend: Bullish ({config.PRIMARY_TIMEFRAME}). Signal: Long ({config.ENTRY_TIMEFRAME}). Reason: {entry_reason}"
        return {"command": f"long {leverage}x", "reasoning": reason, "trade_amount_usd": trade_amount}
    
    if primary_trend == 'bearish' and entry_signal == 'short':
        reason = f"Trend: Bearish ({config.PRIMARY_TIMEFRAME}). Signal: Short ({config.ENTRY_TIMEFRAME}). Reason: {entry_reason}"
        return {"command": f"short {leverage}x", "reasoning": reason, "trade_amount_usd": trade_amount}

    return {"command": "hold", "reasoning": f"Holding. {trend_reason}. {entry_reason}", "trade_amount_usd": 0}

