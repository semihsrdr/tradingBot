import json

def decide_action(strategy: dict, market_data: dict, position_status: tuple, portfolio_summary: dict) -> dict:
    """
    Decides a trading action based on a set of rules from the strategy file.
    This function is PURE Python and does not call any LLM.

    Args:
        strategy: A dictionary containing the strategy rules from strategy.json.
        market_data: A dictionary with the latest market data (price, indicators).
        position_status: A tuple of ('side', quantity).
        portfolio_summary: A dictionary with portfolio details (balance, etc.).

    Returns:
        A decision dictionary (e.g., {"command": "long 20x", "reasoning": "...", "trade_amount_usd": 100}).
    """
    # Unpack data for easier access
    current_price = market_data.get('current_price', 0)
    ema_200 = market_data.get('ema_200', 0)
    rsi = market_data.get('rsi_14', 50)
    volume = market_data.get('volume', 0)
    volume_sma = market_data.get('volume_sma_20', 0)
    position_side, position_qty = position_status

    # Unpack strategy rules
    filters = strategy.get('filters', {})
    long_cond = strategy.get('long_conditions', {})
    short_cond = strategy.get('short_conditions', {})
    trade_params = strategy.get('trade_parameters', {})

    # --- RULE 0: If we are in a position, only decide between 'hold' or 'close' ---
    if position_side != 'flat':
        reason = f"Holding existing {position_side} position."
        # Trend Reversal Check
        if filters.get('use_ema_trend_filter'):
            if position_side in ['long', 'buy'] and current_price < ema_200:
                return {"command": "close", "reasoning": "Closing long position: Trend reversed (price crossed below EMA200).", "trade_amount_usd": 0}
            if position_side in ['short', 'sell'] and current_price > ema_200:
                return {"command": "close", "reasoning": "Closing short position: Trend reversed (price crossed above EMA200).", "trade_amount_usd": 0}
        
        # RSI Extreme Check
        if filters.get('use_rsi_pullback'):
            if position_side in ['long', 'buy'] and rsi > long_cond.get('rsi_exit_extreme', 75):
                return {"command": "close", "reasoning": f"Closing long position: RSI is overbought ({rsi:.1f} > {long_cond.get('rsi_exit_extreme', 75)}).", "trade_amount_usd": 0}
            if position_side in ['short', 'sell'] and rsi < short_cond.get('rsi_exit_extreme', 25):
                return {"command": "close", "reasoning": f"Closing short position: RSI is oversold ({rsi:.1f} < {short_cond.get('rsi_exit_extreme', 25)}).", "trade_amount_usd": 0}

        return {"command": "hold", "reasoning": reason, "trade_amount_usd": 0}

    # --- From here, we are 'flat' and looking for an entry ---

    # --- RULE 1: Trend Filter ---
    if filters.get('use_ema_trend_filter'):
        is_bullish = current_price > ema_200
        is_bearish = current_price < ema_200
        if not is_bullish and not is_bearish:
             return {"command": "hold", "reasoning": "Price is exactly at EMA200, market direction unclear.", "trade_amount_usd": 0}
    else: # If filter is off, allow both directions
        is_bullish = True
        is_bearish = True

    # --- RULE 2: No-Trade Zone Filter ---
    if filters.get('use_ema_trend_filter') and filters.get('no_trade_zone_pct', 0) > 0:
        if abs(current_price - ema_200) / ema_200 < filters['no_trade_zone_pct']:
            return {"command": "hold", "reasoning": f"Price is within the {filters['no_trade_zone_pct']*100}% no-trade zone around EMA200.", "trade_amount_usd": 0}

    # --- RULE 3: Entry Signal (RSI Pullback) ---
    if filters.get('use_rsi_pullback'):
        # Bullish case
        if is_bullish:
            if not (long_cond.get('rsi_entry_min', 30) < rsi < long_cond.get('rsi_entry_max', 50)):
                return {"command": "hold", "reasoning": f"Bullish trend, but RSI ({rsi:.1f}) is not in the pullback zone ({long_cond.get('rsi_entry_min', 30)}-{long_cond.get('rsi_entry_max', 50)}).", "trade_amount_usd": 0}
        # Bearish case
        if is_bearish:
            if not (short_cond.get('rsi_entry_min', 50) < rsi < short_cond.get('rsi_entry_max', 70)):
                 return {"command": "hold", "reasoning": f"Bearish trend, but RSI ({rsi:.1f}) is not in the pullback zone ({short_cond.get('rsi_entry_min', 50)}-{short_cond.get('rsi_entry_max', 70)}).", "trade_amount_usd": 0}
    
    # --- RULE 4: Volume Filter ---
    if filters.get('use_volume_confirmation'):
        if volume < volume_sma:
            return {"command": "hold", "reasoning": f"Entry signal found, but volume ({volume:.2f}) is below SMA ({volume_sma:.2f}). Waiting for confirmation.", "trade_amount_usd": 0}

    # --- EXECUTION: If all filters passed, open a position ---
    leverage = trade_params.get('default_leverage', 20)
    trade_pct = trade_params.get('trade_amount_pct_of_balance', 10)
    balance = portfolio_summary.get('available_balance_usd', 0)
    trade_amount = balance * (trade_pct / 100)

    if is_bullish:
        reason = f"All conditions met for LONG: Bullish trend, RSI pullback ({rsi:.1f}), and Volume confirmation."
        return {"command": f"long {leverage}x", "reasoning": reason, "trade_amount_usd": trade_amount}
    
    if is_bearish:
        reason = f"All conditions met for SHORT: Bearish trend, RSI pullback ({rsi:.1f}), and Volume confirmation."
        return {"command": f"short {leverage}x", "reasoning": reason, "trade_amount_usd": trade_amount}

    # Default case if something goes wrong
    return {"command": "hold", "reasoning": "Default hold, no conditions were met.", "trade_amount_usd": 0}
