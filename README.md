<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="Treasure Chest DataGraph Logo.png">
    <img src="Treasure Chest DataGraph Logo.png" alt="Arithmax Chest" width="120" height="120">
  </picture>
  <h1 align="center">Arithmax Chest</h1>
  <p align="center">
    <em>Normalized market data. One API. Every provider.</em>
    <br>
    Equities &middot; Crypto &middot; Futures &middot; Macro
  </p>
  <p align="center">
    <a href="https://pypi.org/project/arithmaxchest/"><img src="https://img.shields.io/pypi/v/arithmaxchest?color=4B8BBE&label=PyPI" alt="PyPI"></a>
    <a href="https://pypi.org/project/arithmaxchest/"><img src="https://img.shields.io/pypi/pyversions/arithmaxchest?color=4B8BBE" alt="Python Versions"></a>
    <a href="https://achestv2.misango.me/health"><img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fachestv2.misango.me%2Fhealth&label=API&color=22C55E" alt="API Status"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  </p>
</p>

---

**Arithmax Chest** gives you a single, normalized interface to fetch OHLCV market data across multiple asset classes — without worrying about which provider powers each symbol. Just ask for the data and the backend handles the routing.

## Quick Install

```bash
pip install arithmaxchest
```

For optional providers:
```bash
pip install arithmaxchest[all]        # everything (yfinance + databento + uvicorn)
pip install arithmaxchest[yahoo]      # equities via yfinance
pip install arithmaxchest[futures]    # futures via databento
pip install arithmaxchest[server]     # self-host the API
```

## Complete User Guide

### 1. Create a client

```python
from achest import MarketDataClient

# Hosted API (defaults to https://achestv2.misango.me)
client = MarketDataClient()

# Or with your own server + token
client = MarketDataClient(host="https://your-server.com", token="your-api-token")
```

Always use as a context manager:
```python
with MarketDataClient() as client:
    data = client.get(...)
```

### 2. The `get()` method — every parameter explained

```python
client.get(
    symbols,          # list of ticker strings
    start,            # start date — see date formats below
    end,              # end date — see date formats below
    resolution,       # bar size — see resolutions below
    provider          # force a specific provider or "auto"
)
```

#### `symbols` — what tickers look like

| Asset Class | Example Symbols | Notes |
|-------------|----------------|-------|
| **Equities** | `"AAPL"`, `"MSFT"`, `"TSLA"`, `"SPY"` | Standard tickers, 1–5 letters |
| **Crypto** | `"BTCUSDT"`, `"ETHUSDT"`, `"SOLUSDT"`, `"BTC-USD"` | Ends in USDT, USDC, or -USD |
| **Futures** | `"ES.FUT"`, `"NQ.FUT"`, `"CL.FUT"` | Ends in `.FUT` (continuous contracts) |
| **Indices** | `"^GSPC"`, `"^VIX"`, `"^DJI"` | Starts with `^` |
| **Economic** | `"GDP"`, `"UNRATE"`, `"CPIAUCSL"`, `"FEDFUNDS"` | Predefined macro symbols |

You can mix asset classes in one call:
```python
client.get(["AAPL", "BTCUSDT", "ES.FUT", "^GSPC"], "2025-01-01", "2025-01-31")
```

#### `start` / `end` — date formats accepted

All of these work:
```python
# ISO strings
client.get(["AAPL"], "2025-01-01", "2025-01-31")

# datetime.date objects
from datetime import date
client.get(["AAPL"], date(2025, 1, 1), date(2025, 1, 31))

# datetime.datetime objects
from datetime import datetime
client.get(["AAPL"], datetime(2025, 1, 1), datetime(2025, 1, 31))
```

#### `resolution` — bar sizes

| Resolution | Description | Example |
|------------|-------------|---------|
| `"tick"` | Trade-by-trade (raw ticks) | `client.get(["BTCUSDT"], ..., resolution="tick")` |
| `"second"` | 1-second bars | `client.get(["AAPL"], ..., resolution="second")` |
| `"minute"` | 1-minute bars | `client.get(["AAPL"], ..., resolution="minute")` |
| `"hour"` | 1-hour bars | `client.get(["AAPL"], ..., resolution="hour")` |
| `"daily"` | 1-day bars **(default)** | `client.get(["AAPL"], ..., resolution="daily")` |

```python
# Minute-level data for day trading
client.get(["AAPL"], "2025-01-02", "2025-01-03", resolution="minute")

# Hourly data for swing trading
client.get(["BTCUSDT"], "2025-01-01", "2025-01-07", resolution="hour")
```

#### `provider` — auto vs. manual override

| Value | Behavior |
|-------|----------|
| `"auto"` **(default)** | Backend selects the best available provider based on symbol + resolution + configured API keys |
| `"yahoo"` | Force Yahoo Finance |
| `"binance"` | Force Binance (crypto only) |
| `"databento"` | Force Databento (futures, equities) |
| `"alpaca"` | Force Alpaca |
| `"tiingo"` | Force Tiingo |
| `"alpha_vantage"` | Force Alpha Vantage |
| `"fred"` | Force FRED (economic data only) |
| `"quandl"` | Force Quandl |
| `"massive"` | Force Massive |

```python
# Auto-select (recommended)
client.get(["ES.FUT"], "2025-01-01", "2025-01-31", provider="auto")

# Force a specific provider
client.get(["AAPL"], "2025-01-01", "2025-01-31", provider="yahoo")
```

### 3. Full examples

#### Equities — daily data
```python
from achest import MarketDataClient

with MarketDataClient() as client:
    aapl = client.get(["AAPL", "MSFT", "GOOGL"], "2025-01-01", "2025-01-31")
    print(aapl.head())
```

#### Crypto — minute data
```python
with MarketDataClient() as client:
    btc = client.get(["BTCUSDT"], "2025-01-15", "2025-01-16", resolution="minute")
    print(btc.head())
```

#### Futures — daily via Databento
```python
with MarketDataClient() as client:
    es = client.get(["ES.FUT", "NQ.FUT"], "2025-01-01", "2025-01-31")
    print(es.head())
```

#### Mixed assets in one call
```python
with MarketDataClient() as client:
    data = client.get(["AAPL", "BTCUSDT", "ES.FUT"], "2025-01-02", "2025-01-10")
    print(data.groupby("symbol").tail(3))
```

### 4. Download to file

```python
# CSV
client.get(["AAPL"], "2025-01-01", "2025-01-31", format="csv", output="aapl.csv")

# Parquet (fast, compressed)
client.get(["AAPL"], "2025-01-01", "2025-01-31", format="parquet", output="aapl.parquet")

# JSON
client.get(["AAPL"], "2025-01-01", "2025-01-31", format="json", output="aapl.json")
```

### 5. The `download()` method

```python
client.download(["SPY", "QQQ"], "2025-01-01", "2025-01-31",
                output="market-data.parquet")
```

## Data Shape

All responses return normalized OHLCV data:

| timestamp | symbol | provider | open | high | low | close | volume |
|-----------|--------|----------|------|------|-----|-------|--------|
| 2025-01-02 | AAPL | yahoo | 243.5 | 245.8 | 242.3 | 244.9 | 48234500 |
| 2025-01-02 | BTCUSDT | binance | 94250 | 95800 | 93800 | 95430 | 12500 |
| 2025-01-02 | ES.FUT | databento | 5939.25 | 5995.25 | 5874.75 | 5914.75 | 1714061 |

Every row has:
- **`timestamp`** — UTC-normalized datetime
- **`symbol`** — the original ticker you requested
- **`provider`** — which provider served the data
- **`open`**, **`high`**, **`low`**, **`close`**, **`volume`** — OHLCV values

## Symbol Reference

| Input | Classified As | Routed To |
|-------|---------------|-----------|
| `AAPL` | equity | yahoo (default) |
| `MSFT` | equity | yahoo (default) |
| `BTCUSDT` | crypto | binance (if key exists) or yahoo |
| `ETHUSDT` | crypto | binance (if key exists) or yahoo |
| `ES.FUT` | futures | databento (if key exists) or massive |
| `NQ.FUT` | futures | databento (if key exists) or massive |
| `CL.FUT` | futures | databento (if key exists) or massive |
| `^GSPC` | index | yahoo |
| `^VIX` | index | yahoo |
| `GDP` | economic | fred (if key exists) or quandl |
| `UNRATE` | economic | fred (if key exists) or quandl |

## Self-Hosting

Arithmax Chest is also a FastAPI server you can deploy yourself:

```bash
pip install arithmaxchest[all]
uvicorn achest.server:app --host 0.0.0.0 --port 8000
```

With Docker and EC2 support — see the [documentation](documentation.md) for deployment details.

## Why Arithmax Chest?

- **Normalized schema** — Every symbol returns the same columns regardless of provider
- **Provider abstraction** — The backend picks the best source; your code never changes
- **Multi-asset** — Equities, crypto, futures, indices, economic indicators — one API
- **Research-ready** — Clean DataFrames with no provider-specific wrangling
- **Portable** — Works in notebooks, scripts, pipelines, and production systems

## License

MIT

---

*Built by [Arithmax Research](https://achestv2.misango.me). Market data for the next generation of analysts and algorithms.*