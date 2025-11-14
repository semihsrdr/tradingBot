import unittest
import pandas as pd
import config
from engine import decide_action

# Helper function to create a mock DataFrame for a specific scenario
def create_mock_df(price, ema_200, rsi, volume, volume_sma):
    """Creates a single-row DataFrame to simulate the last candle."""
    return pd.DataFrame([{
        'close': price,
        'EMA_200': ema_200,
        'RSI_14': rsi,
        'volume': volume,
        'volume_sma_20': volume_sma
    }])

class TestMultiTimeframeEngine(unittest.TestCase):

    def setUp(self):
        """Set up common data for all tests."""
        self.strategy = {
            "filters": {"use_volume_confirmation": True, "no_trade_zone_pct": 0.01},
            "long_conditions": {"rsi_entry_min": 40, "rsi_entry_max": 50},
            "short_conditions": {"rsi_entry_min": 50, "rsi_entry_max": 60},
            "trade_parameters": {"default_leverage": 20, "trade_amount_pct_of_balance": 10}
        }
        self.portfolio_summary = {"available_balance_usd": 1000}
        config.PRIMARY_TIMEFRAME = '1h'
        config.ENTRY_TIMEFRAME = '15m'

    def test_long_signal_aligned_with_trend(self):
        """
        Scenario: Primary trend is bullish, and entry timeframe gives a long signal.
        Expected: 'long' command.
        """
        print("\n--- Testing Scenario: Correct LONG signal ---")
        multi_timeframe_data = {
            '1h': create_mock_df(price=105, ema_200=100, rsi=60, volume=100, volume_sma=50), # Bullish trend
            '15m': create_mock_df(price=105, ema_200=102, rsi=45, volume=120, volume_sma=100) # Valid long pullback
        }
        decision = decide_action(self.strategy, multi_timeframe_data, ('flat', 0), self.portfolio_summary)
        self.assertTrue(decision['command'].startswith('long'))
        print(f"Decision: {decision['command']} | Reason: {decision['reasoning']}")

    def test_short_signal_aligned_with_trend(self):
        """
        Scenario: Primary trend is bearish, and entry timeframe gives a short signal.
        Expected: 'short' command.
        """
        print("\n--- Testing Scenario: Correct SHORT signal ---")
        multi_timeframe_data = {
            '1h': create_mock_df(price=95, ema_200=100, rsi=40, volume=100, volume_sma=50), # Bearish trend
            '15m': create_mock_df(price=95, ema_200=98, rsi=55, volume=120, volume_sma=100) # Valid short pullback
        }
        decision = decide_action(self.strategy, multi_timeframe_data, ('flat', 0), self.portfolio_summary)
        self.assertTrue(decision['command'].startswith('short'))
        print(f"Decision: {decision['command']} | Reason: {decision['reasoning']}")

    def test_hold_when_signal_conflicts_with_trend(self):
        """
        Scenario: Primary trend is bullish, but entry timeframe gives a short signal.
        Expected: 'hold' command.
        """
        print("\n--- Testing Scenario: HOLD on conflicting signals ---")
        multi_timeframe_data = {
            '1h': create_mock_df(price=105, ema_200=100, rsi=60, volume=100, volume_sma=50), # Bullish trend
            '15m': create_mock_df(price=105, ema_200=102, rsi=55, volume=120, volume_sma=100) # Short pullback signal
        }
        decision = decide_action(self.strategy, multi_timeframe_data, ('flat', 0), self.portfolio_summary)
        self.assertEqual(decision['command'], 'hold')
        print(f"Decision: {decision['command']} | Reason: {decision['reasoning']}")

    def test_hold_when_rsi_is_not_in_entry_zone(self):
        """
        Scenario: Primary trend is bullish, but entry RSI is not in the pullback zone.
        Expected: 'hold' command.
        """
        print("\n--- Testing Scenario: HOLD on invalid RSI ---")
        multi_timeframe_data = {
            '1h': create_mock_df(price=105, ema_200=100, rsi=60, volume=100, volume_sma=50), # Bullish trend
            '15m': create_mock_df(price=105, ema_200=102, rsi=55, volume=120, volume_sma=100) # RSI out of long zone
        }
        decision = decide_action(self.strategy, multi_timeframe_data, ('flat', 0), self.portfolio_summary)
        self.assertEqual(decision['command'], 'hold')
        print(f"Decision: {decision['command']} | Reason: {decision['reasoning']}")

    def test_close_long_position_on_trend_reversal(self):
        """
        Scenario: Holding a long position, but the primary trend flips to bearish.
        Expected: 'close' command.
        """
        print("\n--- Testing Scenario: CLOSE position on trend reversal ---")
        multi_timeframe_data = {
            '1h': create_mock_df(price=95, ema_200=100, rsi=40, volume=100, volume_sma=50), # Trend flips to bearish
            '15m': create_mock_df(price=95, ema_200=98, rsi=45, volume=120, volume_sma=100)
        }
        decision = decide_action(self.strategy, multi_timeframe_data, ('long', 100), self.portfolio_summary)
        self.assertEqual(decision['command'], 'close')
        print(f"Decision: {decision['command']} | Reason: {decision['reasoning']}")

if __name__ == '__main__':
    print("="*70)
    print("Running tests for the new Multi-Timeframe Trading Engine...")
    print("="*70)
    unittest.main()