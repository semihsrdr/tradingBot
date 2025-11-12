import schedule
import time
import json
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import config
from market import get_broad_market_analysis # Gerçek analiz fonksiyonunu import et

STRATEGY_FILE = "strategy.json"
TRADE_LOG_FILE = "trading_log.txt"

# --- SAFETY GUARDRAILS (Loosened for Simulation) ---
# Define safe operational limits for the parameters that the LLM can set.
# These have been widened to allow for more experimentation in simulation mode.
VALIDATION_LIMITS = {
    "default_leverage": (1, 75),
    "trade_amount_pct_of_balance": (1, 50),
    "rsi_long_entry_min": (5, 45),
    "rsi_long_entry_max": (50, 70),
    "rsi_exit_extreme_long": (65, 95),
    "rsi_short_entry_min": (30, 50), # Loosened to allow values like 45
    "rsi_short_entry_max": (55, 95),
    "rsi_exit_extreme_short": (5, 35),
}

SYSTEM_PROMPT = """
You are a world-class quantitative trading strategist and systems analyst. Your task is to optimize the trading rules for a scalping bot by analyzing its recent performance and the current market state. You will be given the bot's recent trade log, its current strategy configuration, and a summary of the broader market conditions for multiple assets.

**YOUR GOAL:**
Subtly adjust the parameters in `strategy.json` to improve profitability and reduce unnecessary risk. Make small, incremental changes. Do not drastically alter the strategy unless performance is very poor. Focus on the general strategy parameters, not per-symbol settings.

**ANALYSIS PROCESS:**
1.  **Review Trade Log:** Are the trades winning or losing?
    -   Losing trades: Why did they lose? Was the entry signal weak? Did the stop-loss hit too early? Was it a good signal in a bad (e.g., choppy) market?
    -   Winning trades: Could they have been more profitable? Was the take-profit too soon?
    -   Missed opportunities: Look at the market data. Were there strong moves the bot missed because its rules were too strict?
2.  **Assess Market Conditions:** Look at the analysis for all symbols. Is the market generally trending (ADX > 25) or is it choppy/ranging (ADX < 25)? High volatility (ATR) might require wider stop losses, which we are not controlling yet, but it's good context.
3.  **Formulate a Hypothesis:** Based on your analysis, form a single hypothesis for the overall strategy.
    -   *Example 1:* "The bot is taking small losses in a choppy market (ADX is low across most assets). The RSI entry zone seems too wide. I should tighten it to look for more significant pullbacks."
    -   *Example 2:* "The market is trending strongly (ADX is high), but the bot is missing entries. The RSI entry zone might be too restrictive. I should widen it slightly."
    -   *Example 3:* "The bot is performing well. No changes are needed at this time."
4.  **Propose Changes:** Modify the JSON parameters based on your hypothesis.

**CRITICAL OUTPUT RULES:**
-   Your response MUST be a raw, valid JSON object and NOTHING ELSE.
-   DO NOT include ```json``` markers, explanations, or any text before or after the JSON object.
-   Your entire response must start with `{` and end with `}`.
-   The JSON must be the *complete, updated* content for the `strategy.json` file.
-   If you decide no changes are necessary, you MUST return the original `current_strategy` JSON that you were given.
-   Add a `comment` field at the top of the JSON to explain your reasoning for the change in one sentence.
"""

def read_trade_log(num_bytes=4096):
    """Reads the last `num_bytes` of the trade log file."""
    try:
        with open(TRADE_LOG_FILE, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            seek_pos = max(0, file_size - num_bytes)
            f.seek(seek_pos, os.SEEK_SET)
            return f.read().decode('utf-8', errors='ignore')
    except FileNotFoundError:
        return "Trade log not found. Assuming no trades have been made yet."
    except Exception as e:
        return f"Error reading trade log: {e}"

def read_current_strategy():
    """Reads the current strategy from the JSON file."""
    try:
        with open(STRATEGY_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[STRATEGIST] ERROR: {STRATEGY_FILE} not found!")
        return None
    except json.JSONDecodeError:
        print(f"[STRATEGIST] ERROR: Could not decode JSON from {STRATEGY_FILE}.")
        return None

def validate_strategy(strategy_json: dict) -> bool:
    """
    Validates the LLM-proposed strategy against the safety limits.
    """
    try:
        params = {
            "default_leverage": strategy_json.get("trade_parameters", {}).get("default_leverage"),
            "trade_amount_pct_of_balance": strategy_json.get("trade_parameters", {}).get("trade_amount_pct_of_balance"),
            "rsi_long_entry_min": strategy_json.get("long_conditions", {}).get("rsi_entry_min"),
            "rsi_long_entry_max": strategy_json.get("long_conditions", {}).get("rsi_entry_max"),
            "rsi_exit_extreme_long": strategy_json.get("long_conditions", {}).get("rsi_exit_extreme"),
            "rsi_short_entry_min": strategy_json.get("short_conditions", {}).get("rsi_entry_min"),
            "rsi_short_entry_max": strategy_json.get("short_conditions", {}).get("rsi_entry_max"),
            "rsi_exit_extreme_short": strategy_json.get("short_conditions", {}).get("rsi_exit_extreme"),
        }

        for key, value in params.items():
            if value is None:
                print(f"[STRATEGIST] VALIDATION FAILED: Parameter '{key}' is missing from the proposed strategy.")
                return False
            
            min_val, max_val = VALIDATION_LIMITS[key]
            if not (min_val <= value <= max_val):
                print(f"[STRATEGIST] VALIDATION FAILED: {key} ({value}) is outside the safe range ({min_val}-{max_val}).")
                return False
        
        print("[STRATEGIST] New strategy passed all validation checks.")
        return True
    except KeyError as e:
        print(f"[STRATEGIST] VALIDATION FAILED: Missing key {e} in strategy proposal.")
        return False
    except Exception as e:
        print(f"[STRATEGIST] An error occurred during validation: {e}")
        return False

def update_strategy_file(strategy_json: dict):
    """Writes the new strategy to the strategy.json file."""
    try:
        with open(STRATEGY_FILE, 'w') as f:
            json.dump(strategy_json, f, indent=2)
        print(f"[STRATEGIST] Strategy file updated. New comment: {strategy_json.get('comment')}")
    except Exception as e:
        print(f"[STRATEGIST] ERROR: Could not write to {STRATEGY_FILE}: {e}")


def run_strategist_cycle():
    """
    Executes one cycle of the strategist:
    Read -> Analyze -> Decide -> Validate -> Update
    """
    print(f"\n--- Strategist Cycle Starting: {time.ctime()} ---")

    # 1. Read current state
    current_strategy = read_current_strategy()
    if not current_strategy:
        return # Stop if we can't read the strategy

    trade_log = read_trade_log()
    
    # Get broad market analysis for all symbols
    market_analyses = []
    for symbol in config.TRADING_SYMBOLS:
        analysis = get_broad_market_analysis(symbol=symbol)
        if analysis:
            market_analyses.append(analysis)
        time.sleep(1) # Avoid hitting rate limits

    if not market_analyses:
        print("[STRATEGIST] Could not get broad market analysis for any symbol. Skipping cycle.")
        return

    # 2. Ask LLM for analysis and new strategy
    try:
        llm = ChatOpenAI(
            model_name=config.LLM_MODEL_NAME,
            openai_api_key=config.OPENROUTER_API_KEY,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.5, # Lower temperature for more deterministic and safer suggestions
        )

        human_input_data = {
            "current_strategy": current_strategy,
            "recent_trade_log": trade_log,
            "broader_market_analysis": market_analyses
        }
        human_input = json.dumps(human_input_data, indent=2)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_input)
        ]

        print("[STRATEGIST] Asking LLM to analyze performance and suggest strategy changes...")
        response = llm.invoke(messages)
        response_text = response.content.strip()

        # Strip markdown if present
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()

        new_strategy_json = json.loads(response_text)

        # 3. Validate and Update
        # Compare by converting to string to ignore formatting differences
        if json.dumps(new_strategy_json, sort_keys=True) == json.dumps(current_strategy, sort_keys=True):
            print("[STRATEGIST] LLM decided no changes are needed. Keeping current strategy.")
        elif validate_strategy(new_strategy_json):
            update_strategy_file(new_strategy_json)
        else:
            print("[STRATEGIST] New strategy from LLM failed validation. Discarding changes.")

    except json.JSONDecodeError:
        print(f"[STRATEGIST] ERROR: Could not decode JSON from LLM response: '{response_text}'")
    except Exception as e:
        print(f"[STRATEGIST] An unexpected error occurred: {e}")

    print("--- Strategist Cycle Finished ---")


if __name__ == "__main__":
    print("--- LLM Strategist Initialized ---")
    print(f"Watching {STRATEGY_FILE} and {TRADE_LOG_FILE}")
    print("The strategist will run once every 30 minutes.")
    print("------------------------------------")

    # Schedule the job
    schedule.every(30).minutes.do(run_strategist_cycle)

    # Run once immediately to start
    run_strategist_cycle()

    while True:
        schedule.run_pending()
        time.sleep(1)
