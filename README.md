<div align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Uvicorn-4B32C3?style=for-the-badge&logo=uvicorn&logoColor=white" alt="Uvicorn" />
  <img src="https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white" alt="Pandas" />
  <img src="https://img.shields.io/badge/PyArrow-FFD43B?style=for-the-badge&logo=apache-arrow&logoColor=black" alt="PyArrow" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/AWS-232F3E?style=for-the-badge&logo=amazonaws&logoColor=white" alt="AWS" />
  <img src="https://img.shields.io/badge/Caddy-22C55E?style=for-the-badge&logo=caddy&logoColor=white" alt="Caddy" />
  <img src="https://img.shields.io/badge/Binance-FCD535?style=for-the-badge&logo=binance&logoColor=black" alt="Binance" />
  <img src="https://img.shields.io/badge/Alpaca-1C1C1C?style=for-the-badge&logo=alpaca&logoColor=white" alt="Alpaca" />
  <img src="https://img.shields.io/badge/Tiingo-1A73E8?style=for-the-badge&logo=tiingo&logoColor=white" alt="Tiingo" />
  <img src="https://img.shields.io/badge/Databento-0F172A?style=for-the-badge&logo=data&logoColor=white" alt="Databento" />
</div>

# Arithmax Chest (achest)

<div align="center">
  <img src="Treasure Chest DataGraph Logo.png" alt="Arithmax Chest logo" width="140" />
</div>

Arithmax Chest is a market-data platform for normalized OHLCV data across equities, crypto, futures, and macro market sources. It gives developers and analysts a clean way to request data without needing to understand the underlying provider contracts or routing logic.

## Why Arithmax Chest

- Clean, normalized market data for research and analysis
- Simple request flow: symbol, date range, and resolution
- Supports multiple asset classes with a single interface
- Built for both API users and Python-based workflows

## Quick start

Use the hosted service URL unless you are running a local instance for development.

```python
from achest import MarketDataClient

with MarketDataClient() as client:
    data = client.get(
        ["AAPL"],
        "2024-01-01",
        "2024-01-31",
        resolution="daily",
    )

print(data.head())
```

### Data shape

The API returns normalized OHLCV data with standard columns:

- timestamp
- open
- high
- low
- close
- volume

You only need to provide:

- a symbol such as `AAPL`, `BTCUSDT`, or `ES.FUT`
- a start date
- an end date
- a resolution such as `daily`, `hour`, or `minute`

## Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[all]'
```

## Supported use cases

- Equity price history
- Crypto market data
- Futures and macro datasets
- Research pipelines and analytics workflows
- Lean-style or normalized data ingestion for downstream systems

## Docs

- Public user docs: this README
- Maintainer and deployment notes: [documentation.md](documentation.md)

## Notes

- The public API hides provider complexity by design.
- Provider credentials stay on the server side, not in client code.
- Internal operational tooling and deployment details live in [documentation.md](documentation.md) rather than the end-user README.
