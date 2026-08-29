# Arithmax Chest

<div align="center">
  <img src="Treasure Chest DataGraph Logo.png" alt="Arithmax Chest logo" width="260" />
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

with MarketDataClient("https://achest.misango.me") as client:
    data = client.get(
        ["AAPL"],
        "2024-01-01",
        "2024-01-31",
        resolution="daily",
    )

print(data.head())
```

Equivalent HTTP request:

```bash
curl -X POST https://achest.misango.me/v1/data \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["AAPL"],
    "start": "2024-01-01",
    "end": "2024-01-31",
    "resolution": "daily",
    "provider": "auto",
    "format": "json"
  }'
```

If a bearer token is required:

```bash
curl -X POST https://achest.misango.me/v1/data \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DATA_API_TOKEN" \
  -d '{
    "symbols": ["AAPL"],
    "start": "2024-01-01",
    "end": "2024-01-31",
    "resolution": "daily",
    "provider": "auto",
    "format": "json"
  }'
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

## Tech stack

### Application and data stack

- Python 3.10+
- FastAPI for the HTTP API layer
- Uvicorn for ASGI serving
- Pandas for time-series normalization and analysis
- PyArrow for efficient data interchange and columnar workflows
- HTTPX and Requests for upstream API access
- dotenv-based environment configuration

### Market data and ingestion stack

- Binance for crypto market data
- Alpaca for equities and market bars
- Tiingo and Alpha Vantage for additional market coverage
- FRED, Quandl, and macro data providers for economic and alternative series
- Databento and Massive/Polygon-based futures and market data integration
- Lean-style data organization for downstream research and quant pipelines

### DevOps and systems

- Docker for containerized deployment
- EC2-based hosting and service deployment patterns
- Caddy / reverse-proxy TLS termination
- Environment-variable driven secrets and runtime config
- Local `.env` configuration for development
- Data pipeline tooling under `Data_Pipeline/` for historical ingestion and maintenance workflows

## Docs

- Public user docs: this README
- Maintainer and deployment notes: [documentation.md](documentation.md)

## Notes

- The public API hides provider complexity by design.
- Provider credentials stay on the server side, not in client code.
- Internal operational tooling and deployment details live in [documentation.md](documentation.md) rather than the end-user README.
