# Developer documentation

This file is for maintainers and deployment work. Public user-facing guidance belongs in the README.

## Deployment and infrastructure

### Hosted service

The public service is expected to live behind a domain such as:

- https://achest.misango.me

The app can also be served from an EC2 instance or container behind a reverse proxy, and the public hostname should be used by end users instead of loopback addresses.

### Local development

The following addresses are for local work only:

```bash
curl http://127.0.0.1:8000/health
```

```bash
uvicorn achest.server:app --host 0.0.0.0 --port 8000
```

`127.0.0.1` is the machine loopback address. It is not the public production endpoint.

## Internal provider routing

The service intentionally abstracts provider choice away from users.

For maintainer reference, the backend chooses providers based on symbol type and resolution:

- crypto -> Binance or Yahoo
- futures -> Databento or Polygon
- equities / ETFs / indexes -> Yahoo

This logic lives in `achest/service.py` and is not intended to be exposed in the public docs.

## Secrets and environment

Provider credentials should be kept on the server, never in client code.

```bash
export DATA_API_TOKEN='replace-with-a-private-client-token'
export BINANCE_BASE_URL='https://api.binance.us'
export BINANCE_API_KEY='optional-if-you-use-binance-keys'
export BINANCE_SECRET_KEY='optional-if-you-use-binance-keys'
export POLYGON_API_KEY='if-you-use-polygon'
export DATABENTO_API_KEY='if-you-use-databento'
export ALPACA_API_KEY='if-you-use-alpaca'
export ALPACA_SECRET_KEY='if-you-use-alpaca'
export ALPHA_VANTAGE_API_KEY='if-you-use-alpha-vantage'
export TIINGO_API_KEY='if-you-use-tiingo'
export FRED_API_KEY='if-you-use-fred'
export QUANDL_API_KEY='if-you-use-quandl'
```

## Local API checks

```bash
curl -H "Authorization: Bearer $DATA_API_TOKEN" \
  "http://127.0.0.1:8000/v1/route?symbol=BTCUSDT&resolution=daily&provider=auto"
```

```bash
curl -X POST http://127.0.0.1:8000/v1/data \
  -H "Authorization: Bearer $DATA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "start": "2024-01-01",
    "end": "2024-01-31",
    "resolution": "daily",
    "provider": "auto",
    "format": "json"
  }'
```

## Docker / EC2 notes

This repo includes a containerized API setup and an EC2-oriented compose file:

- `Dockerfile`
- `docker-compose.ec2.yml`
- `Caddyfile`

A typical deployment pattern is:

1. build the API container
2. expose it on a private or public TCP port
3. terminate TLS with Caddy or an external load balancer
4. inject provider credentials as environment variables in the host/container config
5. keep the project itself free of secrets and static provider keys

Example:

```bash
docker build -t arithmax-chest .
docker run --rm -p 8000:8000 \
  -e DATA_API_TOKEN='token-here' \
  -e POLYGON_API_KEY='key-here' \
  -e DATABENTO_API_KEY='key-here' \
  arithmax-chest
```

## Data pipeline internals

The downloader suite under `Data_Pipeline/` is intended for bulk ingestion and historical collection.

Example:

```bash
cd Data_Pipeline
python main.py --source binance --crypto-symbols BTCUSDT ETHUSDT --start-date 2024-01-01 --end-date 2024-01-31 --resolution daily
```

This is operational and maintenance tooling, not user documentation.

## Contributing

- Keep the README focused on public usage.
- Put deployment, infra, routing, and troubleshooting details in this file or in a maintainer-specific docs area.
- Keep SDK examples and user quick-starts short and provider-agnostic.
- Only expose internal provider names where needed for maintainers or debugging.
