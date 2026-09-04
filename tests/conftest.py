"""Pytest configuration: set dummy provider API keys so routing tests pass."""

import os

# Dummy keys for provider-requiring tests — actual API calls are not made
os.environ.setdefault("BINANCE_API_KEY", "test-dummy-key")
os.environ.setdefault("ALPACA_API_KEY", "test-dummy-key")
os.environ.setdefault("TIINGO_API_KEY", "test-dummy-key")
os.environ.setdefault("ALPHA_VANTAGE_API_KEY", "test-dummy-key")
os.environ.setdefault("FRED_API_KEY", "test-dummy-key")
os.environ.setdefault("DATA_BENTO_API_KEY", "test-dummy-key")
os.environ.setdefault("MASSIVE_API_KEY", "test-dummy-key")
os.environ.setdefault("QUANDL_API_KEY", "test-dummy-key")