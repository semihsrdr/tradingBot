import config
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import json

SYSTEM_PROMPT = """
You are a disciplined and expert scalping trader. Your primary goal is to preserve capital and only trade high-probability setups. You will follow the rules below with NO exceptions.

**RULE 1: THE HIERARCHY OF DECISION MAKING**
You MUST evaluate the market in this exact order. Do not skip any steps.
1.  **Trend Filter (The Most Important Rule):** Look at `market_data.ema_200` and `market_data.current_price`. This is your master trend direction.
    *   If `current_price` > `ema_200`, the trend is **BULLISH**. You are ONLY PERMITTED to look for `long` or `close` opportunities.
    *   If `current_price` < `ema_200`, the trend is **BEARISH**. You are ONLY PERMITTED to look for `short` or `close` opportunities.
    *   **IT IS STRICTLY FORBIDDEN TO OPEN A TRADE AGAINST THE EMA_200 TREND.** Do not try to predict reversals. Your job is to follow the main trend.

2.  **No-Trade Zone Filter:** Calculate the percentage difference between `current_price` and `ema_200`.
    *   If the price is within 0.5% of the `ema_200` (e.g., `abs(current_price - ema_200) / ema_200 < 0.005`), the market is choppy and directionless.
    *   In this zone, your ONLY command is `hold`. DO NOT open new positions.

3.  **Entry Signal Filter (RSI Pullback):** If you are flat (`position_status.side` is 'flat') and not in the No-Trade Zone, use RSI to find a pullback entry IN THE DIRECTION OF THE TREND.
    *   **In a BULLISH trend:** Only consider opening a `long` position if `rsi_14` is in the **30-50 zone**. This signals a healthy pullback. Do not buy if RSI is above 65.
    *   **In a BEARISH trend:** Only consider opening a `short` position if `rsi_14` is in the **50-70 zone**. This signals a relief rally to a good short entry. Do not short if RSI is below 35.

4.  **Volume Filter (Confirmation):** If the RSI filter passes, you must check for volume confirmation.
    *   A new position can ONLY be opened if `volume` > `volume_sma_20`. This confirms there is conviction behind the move.
    *   If the volume is not confirmed, `hold` and wait for the next candle.

5.  **Execution:** If all filters above are passed, you can decide to open a position.

**RULE 2: POSITION MANAGEMENT**
*   **If Position is Open:** Your only commands are `hold` or `close`. You cannot add to a position. You should close if the trend reverses (e.g., price crosses the `ema_200` against you) or if RSI becomes extreme (e.g., >75 on a long, <25 on a short), suggesting the move is exhausted.
*   **Leverage:** For new positions, use a leverage between **5x and 25x**.
*   **Trade Size:** For new positions, use the `trade_amount_usd` field to risk between 5% (low confidence) and 20% (high confidence) of your `available_balance_usd`.

**RULE 3: OUTPUT FORMAT**
Your response MUST be a valid JSON object. Do not add any text before or after it.
The JSON object must have three keys: "reasoning", "command", and "trade_amount_usd".
*   `reasoning`: A brief analysis explaining your decision by referencing the hierarchy (Trend -> No-Trade Zone -> RSI -> Volume).
*   `command`: The trading command string (e.g., "long 20x", "short 15x", "close", "hold").
*   `trade_amount_usd`: Required for 'long' or 'short'. Must be 0 for 'hold' or 'close'.

---
**EXAMPLE 1: Bullish Trend, Good Entry**
*Input:* `current_price` is 10% above `ema_200`, `rsi_14` is 45, `volume` is 1.5M, `volume_sma_20` is 1.1M, position is 'flat'.
*JSON Output:*
{
  "reasoning": "Trend is bullish (price > EMA200). Not in no-trade zone. RSI is 45 (pullback). Volume is strong (1.5M > 1.1M). All conditions met for a long entry.",
  "command": "long 15x",
  "trade_amount_usd": 100
}

**EXAMPLE 2: Bullish Trend, But Weak Volume**
*Input:* `current_price` is 10% above `ema_200`, `rsi_14` is 45, `volume` is 0.8M, `volume_sma_20` is 1.1M, position is 'flat'.
*JSON Output:*
{
  "reasoning": "Trend is bullish and RSI is in a good pullback zone. However, volume is below average (0.8M < 1.1M), showing no conviction. Waiting for confirmation. Holding.",
  "command": "hold",
  "trade_amount_usd": 0
}

**EXAMPLE 3: Bearish Trend, No-Trade Zone**
*Input:* `current_price` is 0.2% below `ema_200`, `rsi_14` is 60, position is 'flat'.
*JSON Output:*
{
  "reasoning": "Trend is bearish, but the price is inside the 0.5% no-trade zone around the EMA200. The market is too choppy to trade. Holding.",
  "command": "hold",
  "trade_amount_usd": 0
}
"""

def get_trade_decision(market_summary: dict, position_status: tuple, portfolio_summary: dict) -> dict:
    """
    Takes market summary, position, and portfolio status,
    asks the LLM, and returns the trade decision dictionary.
    """
    default_decision = {"command": "hold", "trade_amount_usd": 0, "reasoning": "Default action due to error or missing key."}
    
    if not config.OPENROUTER_API_KEY:
        print("OpenRouter API key not provided. Defaulting to 'hold'.")
        return default_decision

    try:
        # Point to OpenRouter's OpenAI-compatible API endpoint
        llm = ChatOpenAI(
            model_name=config.LLM_MODEL_NAME,
            openai_api_key=config.OPENROUTER_API_KEY,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.7,
        )
    except Exception as e:
        print(f"Error initializing LLM: {e}")
        return default_decision

    # Normalize position side for the LLM to be consistent with the prompt ('long'/'short')
    side, quantity = position_status
    if side == 'buy':
        side = 'long'
    elif side == 'sell':
        side = 'short'

    # Create a combined input for the LLM
    combined_input = {
        "portfolio_summary": portfolio_summary,
        "market_data": market_summary,
        "position_status": {
            "side": side,
            "quantity": quantity
        }
    }
    human_input = json.dumps(combined_input, indent=2)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_input)
    ]

    try:
        response = llm.invoke(messages)
        response_text = response.content.strip()

        # LLM sometimes wraps the JSON in markdown, so we strip it.
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()

        # Parse the JSON output
        try:
            decision_json = json.loads(response_text)
            command = decision_json.get("command", "hold").lower()
            reasoning = decision_json.get("reasoning", "No reasoning provided.")
            trade_amount = decision_json.get("trade_amount_usd", 0)

            print(f"[AI Reasoning] {reasoning}")

            # Validate command and amount
            parts = command.split()
            action = parts[0]
            if action not in ['long', 'short', 'hold', 'close']:
                print(f"Invalid command action from LLM: '{action}'. Defaulting to 'hold'.")
                return default_decision

            if action in ['long', 'short']:
                if not isinstance(trade_amount, (int, float)) or trade_amount <= 0:
                    print(f"Invalid or missing 'trade_amount_usd' for new position. Got: {trade_amount}. Defaulting to 5% of balance.")
                    trade_amount = portfolio_summary.get('total_balance_usd', 1000) * 0.05
                
                # Cap the trade amount at 50% of balance for safety
                max_trade_size = portfolio_summary.get('total_balance_usd', 1000) * 0.5
                if trade_amount > max_trade_size:
                    print(f"Trade amount {trade_amount} exceeds safety cap. Adjusting to {max_trade_size}.")
                    trade_amount = max_trade_size

            return {
                "command": command,
                "trade_amount_usd": trade_amount,
                "reasoning": reasoning
            }

        except json.JSONDecodeError:
            print(f"Could not decode JSON from LLM response: '{response_text}'. Defaulting to 'hold'.")
            return default_decision

    except Exception as e:
        print(f"Error during LLM decision: {e}")
        return default_decision

# Bu dosyayı doğrudan çalıştırarak test edebilirsiniz
if __name__ == "__main__":
    test_market_data = {
        "symbol": "BTC/USDT",
        "current_price": 68500.50,
        "ema_20": 68450.0,
        "ema_50": 68300.0,
        "rsi_14": 62.0,
        "market_trend": "bullish"
    }
    test_position = ('flat', 0)
    test_portfolio = {
        "total_balance_usd": 1000.00,
        "unrealized_pnl_usd": 0
    }

    print("--- LLM Agent Testi (Yeni Pozisyon Açma) ---")
    print(f"Girdi: {json.dumps({'market_data': test_market_data, 'position': test_position, 'portfolio': test_portfolio}, indent=2)}")
    decision = get_trade_decision(test_market_data, test_position, test_portfolio)
    print(f"Çıktı (Karar): {decision}")

    print("\n--- LLM Agent Testi (Mevcut Pozisyonu Tutma) ---")
    test_position_hold = ('long', 0.01)
    test_portfolio_hold = {
        "total_balance_usd": 1050.75,
        "unrealized_pnl_usd": 50.25
    }
    print(f"Girdi: {json.dumps({'market_data': test_market_data, 'position': test_position_hold, 'portfolio': test_portfolio_hold}, indent=2)}")
    decision_hold = get_trade_decision(test_market_data, test_position_hold, test_portfolio_hold)
    print(f"Çıktı (Karar): {decision_hold}")