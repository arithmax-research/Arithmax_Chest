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
    <a href="https://achest.misango.me/health"><img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fachest.misango.me%2Fhealth&label=API&color=22C55E" alt="API Status"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  </p>
</p>

---

**Arithmax Chest** gives you a single, normalized interface to fetch OHLCV market data across multiple asset classes — without worrying about which provider powers each symbol. Just ask for the data and the backend handles the routing.

```python
from achest import MarketDataClient

with MarketDataClient() as client:
    data = client.get(["AAPL", "BTCUSDT", "ES.FUT"],
                      "2025-01-01", "2025-01-31")

print(data.head())
```

## Features

- **Multi-asset** — Equities, crypto, futures, ETFs, indices, forex, economic indicators
- **Multi-resolution** — Tick, second, minute, hour, daily, weekly, monthly
- **Auto-routing** — The backend selects the best provider for each symbol automatically
- **Provider-agnostic client** — Your code never touches provider-specific SDKs or API keys
- **Time-saving** — No more juggling Binance, Yahoo, Polygon, Alpaca, FRED, etc.

## Installation

```bash
pip install arithmaxchest
```

For optional provider support:

```bash
pip install arithmaxchest[all]        # includes yfinance, databento, uvicorn
pip install arithmaxchest[yahoo]      # yfinance support only
pip install arithmaxchest[futures]     # databento support only
pip install arithmaxchest[server]      # uvicorn for self-hosting
```

## Quick Start

### Using the hosted API (no server setup required)

```python
from achest import MarketDataClient

with MarketDataClient() as client:
    # Equities via Yahoo
    aapl = client.get(["AAPL"], "2025-01-01", "2025-01-31")
    print(aapl.head())

    # Crypto via Binance
    btc = client.get(["BTCUSDT"], "2025-01-01", "2025-01-31")
    print(btc.head())

    # Futures via Databento or Polygon
    es = client.get(["ES.FUT"], "2025-01-01", "2025-01-31")
    print(es.head())
```

### With authentication (self-managed token)

```python
from achest import MarketDataClient

with MarketDataClient(token="your-api-token") as client:
    data = client.get(["AAPL"], "2025-01-01", "2025-01-31")
```

### Download to file

```python
client.download(["SPY", "QQQ"], "2025-01-01", "2025-01-31",
                output="market-data.parquet")
```

## Data Shape

All responses return normalized OHLCV data:

| timestamp | symbol | provider | open | high | low | close | volume |
|-----------|--------|----------|------|------|-----|-------|--------|
| 2025-01-02 | AAPL | yahoo | 243.5 | 245.8 | 242.3 | 244.9 | 48234500 |

You only provide:
- **Symbol(s)** — e.g., `AAPL`, `BTCUSDT`, `ES.FUT`, `^GSPC`, `GDP`
- **Date range** — start and end dates
- **Resolution** — `daily`, `hour`, `minute`, `tick`, etc.

## Supported Providers

| Provider | Assets | Resolutions |
|----------|--------|-------------|
| **Yahoo Finance** | Equity, ETF, Index, Crypto, Forex, Futures | minute, hour, daily, weekly, monthly |
| **Binance** | Crypto | tick, second, minute, hour, daily, weekly, monthly |
| **Polygon** | Equity, ETF, Index, Crypto, Forex, Options | tick, second, minute, hour, daily, weekly, monthly |
| **Databento** | Equity, ETF, Futures, Options, Forex | tick, second, minute, hour, daily |
| **Alpaca** | Equity, ETF, Crypto | tick, minute, hour, daily |
| **Tiingo** | Equity, ETF, Index, Crypto, Forex | tick, second, minute, hour, daily |
| **Alpha Vantage** | Equity, ETF, Index, Crypto, Forex, Economic | minute, hour, daily, weekly, monthly |
| **FRED** | Economic indicators | daily, weekly, monthly, quarterly, annual |
| **Quandl** | Equity, ETF, Index, Crypto, Economic, Futures | daily, weekly, monthly, quarterly, annual |

## Self-Hosting

Arithmax Chest is also a FastAPI server you can deploy yourself:

```bash
pip install arithmaxchest[server]
uvicorn achest.server:app --host 0.0.0.0 --port 8000
```

Docker support included — see the [documentation](documentation.md) for EC2 deployment details.

## Why Arithmax Chest?

- **Normalized schema** — Every symbol returns the same columns regardless of provider
- **Provider abstraction** — The backend picks the best source; your code never changes
- **Research-ready** — Clean DataFrames with no provider-specific wrangling
- **Portable** — Works in notebooks, scripts, pipelines, and production systems

## License

MIT

---

*Built by [Arithmax](https://achest.misango.me). Market data for the next generation of analysts and algorithms.*