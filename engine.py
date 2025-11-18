from config import ADX_TREND_THRESHOLD, ADX_RANGE_THRESHOLD

# The DEFAULT_STRATEGY dictionary is no longer the primary driver of the main logic,
# but it can be kept for specific parameters like RSI levels if needed, or removed if fully replaced.
# For this implementation, we will use its values but the core logic is in decide_action.
DEFAULT_STRATEGY = {
    "filters": {
        "use_ema_trend_filter": True,
        "use_rsi_pullback": True,
        "use_volume_confirmation": True
    },
    "long_conditions": {
        "rsi_exit_extreme": 75,
        "rsi_entry_min": 30,
        "rsi_entry_max": 50
    },
    "short_conditions": {
        "rsi_exit_extreme": 25,
        "rsi_entry_min": 50,
        "rsi_entry_max": 70
    },
    "trade_parameters": {
        "default_leverage": 20,
        "trade_amount_pct_of_balance": 10
    }
}


def decide_action(market_data: dict, position_status: tuple, portfolio_summary: dict, cooldown_status: bool = False) -> dict:
    """
    Decides a trading action based on a hybrid strategy:
    1. In Ranging Markets (ADX < threshold): Uses a trend-aligned Mean Reversion strategy.
    2. In Trending Markets (ADX > threshold): Uses a trend-following Pullback strategy.

    Args:
        market_data: A dictionary with the latest market data (price, indicators).
        position_status: A tuple of ('side', quantity).
        portfolio_summary: A dictionary with portfolio details (balance, etc.).
        cooldown_status: A boolean indicating if the symbol is on cooldown.

    Returns:
        A decision dictionary (e.g., {"command": "long 20x", "reasoning": "...", "trade_amount_usd": 100}).
    """
    # --- Unpack data for easier access ---
    current_price = market_data.get('current_price', 0)
    ema_200 = market_data.get('ema_200', 0)
    rsi = market_data.get('rsi_14', 50)
    adx = market_data.get('adx_14', 25)
    lower_band = market_data.get('bollinger_lower', 0)
    upper_band = market_data.get('bollinger_upper', 0)
    volume = market_data.get('volume', 0)
    volume_sma = market_data.get('volume_sma_20', 0)
    position_side, _ = position_status

    # Unpack strategy rules from the dictionary
    strategy = DEFAULT_STRATEGY
    filters = strategy.get('filters', {})
    long_cond = strategy.get('long_conditions', {})
    short_cond = strategy.get('short_conditions', {})
    trade_params = strategy.get('trade_parameters', {})

    # --- RULE 0: If we are in a position, only decide between 'hold' or 'close' ---
    if position_side != 'flat':
        # Trend Reversal Check (Price crossing EMA200)
        if filters.get('use_ema_trend_filter'):
            if position_side in ['long', 'buy'] and current_price < ema_200:
                return {"command": "close", "reasoning": "Closing long: Trend reversed (price < EMA200).", "trade_amount_usd": 0}
            if position_side in ['short', 'sell'] and current_price > ema_200:
                return {"command": "close", "reasoning": "Closing short: Trend reversed (price > EMA200).", "trade_amount_usd": 0}
        
        # RSI Extreme Check (Exit on overbought/oversold)
        if filters.get('use_rsi_pullback'):
            if position_side in ['long', 'buy'] and rsi > long_cond.get('rsi_exit_extreme', 75):
                return {"command": "close", "reasoning": f"Closing long: RSI overbought ({rsi:.1f}).", "trade_amount_usd": 0}
            if position_side in ['short', 'sell'] and rsi < short_cond.get('rsi_exit_extreme', 25):
                return {"command": "close", "reasoning": f"Closing short: RSI oversold ({rsi:.1f}).", "trade_amount_usd": 0}

        return {"command": "hold", "reasoning": f"Holding existing {position_side} position.", "trade_amount_usd": 0}

    # --- From here, we are 'flat' and looking for an entry ---

    # --- MASTER FILTER: COOLDOWN ---
    if cooldown_status:
        return {"command": "hold", "reasoning": "Cooldown active after a recent loss.", "trade_amount_usd": 0}

    # --- HYBRID STRATEGY LOGIC ---
    
    # --- STRATEGY 1: RANGING MARKET - MEAN REVERSION (ADX is low) ---
    if adx < ADX_RANGE_THRESHOLD:
        is_bullish_trend = current_price > ema_200
        is_bearish_trend = current_price < ema_200

        # Long entry: Main trend is bullish, but price has dipped to the lower band
        if is_bullish_trend and current_price <= lower_band:
            leverage = trade_params.get('default_leverage', 20)
            trade_pct = trade_params.get('trade_amount_pct_of_balance', 10)
            balance = portfolio_summary.get('available_balance_usd', 0)
            trade_amount = balance * (trade_pct / 100)
            reason = f"Mean Reversion LONG: Main trend is Bullish, but price hit Lower Bollinger Band ({current_price:.2f}). Expecting bounce."
            return {"command": f"long {leverage}x", "reasoning": reason, "trade_amount_usd": trade_amount}

        # Short entry: Main trend is bearish, but price has spiked to the upper band
        if is_bearish_trend and current_price >= upper_band:
            leverage = trade_params.get('default_leverage', 20)
            trade_pct = trade_params.get('trade_amount_pct_of_balance', 10)
            balance = portfolio_summary.get('available_balance_usd', 0)
            trade_amount = balance * (trade_pct / 100)
            reason = f"Mean Reversion SHORT: Main trend is Bearish, but price hit Upper Bollinger Band ({current_price:.2f}). Expecting drop."
            return {"command": f"short {leverage}x", "reasoning": reason, "trade_amount_usd": trade_amount}
        
        return {"command": "hold", "reasoning": f"Ranging market (ADX < {ADX_RANGE_THRESHOLD}), but no mean reversion signal.", "trade_amount_usd": 0}

    # --- STRATEGY 2: TRENDING MARKET - PULLBACK (ADX is high) ---
    elif adx > ADX_TREND_THRESHOLD:
        is_bullish = current_price > ema_200
        is_bearish = current_price < ema_200

        # Bullish Pullback Entry
        if is_bullish:
            rsi_in_zone = long_cond.get('rsi_entry_min', 30) < rsi < long_cond.get('rsi_entry_max', 50)
            volume_confirmed = volume > volume_sma if filters.get('use_volume_confirmation') else True
            
            if rsi_in_zone and volume_confirmed:
                leverage = trade_params.get('default_leverage', 20)
                trade_pct = trade_params.get('trade_amount_pct_of_balance', 10)
                balance = portfolio_summary.get('available_balance_usd', 0)
                trade_amount = balance * (trade_pct / 100)
                reason = f"Trend Pullback LONG: ADX > {ADX_TREND_THRESHOLD}, RSI in pullback zone ({rsi:.1f}), and Volume confirmed."
                return {"command": f"long {leverage}x", "reasoning": reason, "trade_amount_usd": trade_amount}

        # Bearish Pullback Entry
        if is_bearish:
            rsi_in_zone = short_cond.get('rsi_entry_min', 50) < rsi < short_cond.get('rsi_entry_max', 70)
            volume_confirmed = volume > volume_sma if filters.get('use_volume_confirmation') else True

            if rsi_in_zone and volume_confirmed:
                leverage = trade_params.get('default_leverage', 20)
                trade_pct = trade_params.get('trade_amount_pct_of_balance', 10)
                balance = portfolio_summary.get('available_balance_usd', 0)
                trade_amount = balance * (trade_pct / 100)
                reason = f"Trend Pullback SHORT: ADX > {ADX_TREND_THRESHOLD}, RSI in pullback zone ({rsi:.1f}), and Volume confirmed."
                return {"command": f"short {leverage}x", "reasoning": reason, "trade_amount_usd": trade_amount}

        return {"command": "hold", "reasoning": f"Trending market (ADX > {ADX_TREND_THRESHOLD}), but no pullback signal.", "trade_amount_usd": 0}

    # --- INDECISIVE ZONE (ADX is between range and trend thresholds) ---
    else:
        return {"command": "hold", "reasoning": f"Indecisive market condition (ADX is between {ADX_RANGE_THRESHOLD} and {ADX_TREND_THRESHOLD}).", "trade_amount_usd": 0}

