"""Provider routing and normalized market-data retrieval."""

from dataclasses import dataclass
from datetime import date, datetime, time
import os
from typing import Iterable

import pandas as pd
import requests


@dataclass(frozen=True)
class DataRequest:
    symbols: list[str]
    start: date
    end: date
    resolution: str = "daily"
    provider: str = "auto"


PROVIDER_CAPABILITIES = {
    "yahoo": {
        "assets": {"equity", "etf", "index", "crypto", "forex", "futures"},
        "resolutions": {"minute", "hour", "daily", "weekly", "monthly"},
    },
    "binance": {
        "assets": {"crypto"},
        "resolutions": {"tick", "second", "minute", "hour", "daily", "weekly", "monthly"},
    },
    "massive": {
        "assets": {"equity", "etf", "index", "crypto", "forex", "futures", "options"},
        "resolutions": {"tick", "second", "minute", "hour", "daily", "weekly", "monthly"},
    },
    "databento": {
        "assets": {"equity", "etf", "futures", "options", "forex"},
        "resolutions": {"tick", "second", "minute", "hour", "daily"},
    },
    "alpaca": {
        "assets": {"equity", "etf", "crypto"},
        "resolutions": {"tick", "minute", "hour", "daily"},
    },
    "tiingo": {
        "assets": {"equity", "etf", "index", "crypto", "forex"},
        "resolutions": {"tick", "second", "minute", "hour", "daily"},
    },
    "alpha_vantage": {
        "assets": {"equity", "etf", "index", "crypto", "forex", "economic"},
        "resolutions": {"minute", "hour", "daily", "weekly", "monthly"},
    },
    "fred": {
        "assets": {"economic"},
        "resolutions": {"daily", "weekly", "monthly", "quarterly", "annual"},
    },
    "quandl": {
        "assets": {"equity", "etf", "index", "crypto", "economic", "futures"},
        "resolutions": {"daily", "weekly", "monthly", "quarterly", "annual"},
    },
}
FUTURES_ROOTS = {"ES", "NQ", "YM", "RTY", "CL", "GC", "SI", "ZB", "ZN", "NG", "ZS", "ZC", "ZW"}
ECONOMIC_SYMBOLS = {"GDP", "UNRATE", "CPIAUCSL", "FEDFUNDS", "DGS10"}


class UnsupportedRequest(ValueError):
    pass


def classify_symbol(symbol: str) -> str:
    clean = symbol.upper().strip()
    if clean.endswith(("USDT", "USDC", "-USD")):
        return "crypto"
    if clean.endswith(".FUT") or ".c." in clean or clean in FUTURES_ROOTS:
        return "futures"
    if clean.startswith("^"):
        return "index"
    if clean in ECONOMIC_SYMBOLS:
        return "economic"
    if clean.isalpha() and len(clean) <= 5:
        return "equity"
    return "equity"


# Map provider -> env var name for required API key (empty = no key needed)
_PROVIDER_KEY_MAP = {
    "databento": "DATA_BENTO_API_KEY",
    "massive": "MASSIVE_API_KEY",
    "alpaca": "ALPACA_API_KEY",
    "tiingo": "TIINGO_API_KEY",
    "alpha_vantage": "ALPHA_VANTAGE_API_KEY",
    "fred": "FRED_API_KEY",
    "quandl": "QUANDL_API_KEY",
    "binance": "",       # public API, no key required
    "yahoo": "",         # public API, no key required
}


def _provider_key_configured(provider: str) -> bool:
    """Return True if the provider can be used (key configured or not needed)."""
    env_var = _PROVIDER_KEY_MAP.get(provider, "")
    return not env_var or bool(os.getenv(env_var))


def select_provider(symbol: str, requested: str, resolution: str) -> str:
    asset = classify_symbol(symbol)
    if requested != "auto":
        capabilities = PROVIDER_CAPABILITIES.get(requested)
        if not capabilities or asset not in capabilities["assets"] or resolution not in capabilities["resolutions"]:
            raise UnsupportedRequest(f"Provider {requested!r} does not support {asset} at {resolution} resolution")
        if not _provider_key_configured(requested):
            raise UnsupportedRequest(f"Provider {requested!r} is not configured on this server (missing API key)")
        return requested
    preferences = {
        "futures": ["databento", "massive"],
        "crypto": ["binance", "yahoo", "tiingo", "alpha_vantage"],
        "equity": ["yahoo", "alpaca", "tiingo", "alpha_vantage"],
        "etf": ["yahoo", "alpaca", "tiingo"],
        "index": ["yahoo", "alpaca", "tiingo"],
        "economic": ["fred", "quandl"],
    }.get(asset, ["yahoo"])
    for provider in preferences:
        if resolution in PROVIDER_CAPABILITIES[provider]["resolutions"] and _provider_key_configured(provider):
            return provider
    raise UnsupportedRequest(f"No provider supports {asset} at {resolution} resolution")


def _as_datetime(value: date, end_of_day: bool = False) -> datetime:
    return datetime.combine(value, time.max if end_of_day else time.min)


def _frame_from_bars(bars: Iterable[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(list(bars))
    if frame.empty:
        return frame
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.set_index("timestamp").sort_index()[["open", "high", "low", "close", "volume"]]


def _yahoo(symbol: str, request: DataRequest) -> pd.DataFrame:
    import yfinance as yf

    interval = {"minute": "1m", "hour": "1h", "daily": "1d"}[request.resolution]
    history = yf.Ticker(symbol).history(
        start=request.start.isoformat(), end=request.end.isoformat(), interval=interval, auto_adjust=False
    )
    if history.empty:
        return pd.DataFrame()
    history.index.name = "timestamp"
    return history.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})[
        ["open", "high", "low", "close", "volume"]
    ]


def _binance(symbol: str, request: DataRequest) -> pd.DataFrame:
    interval = {"minute": "1m", "hour": "1h", "daily": "1d"}[request.resolution]
    base_url = os.getenv("BINANCE_BASE_URL", "https://api.binance.com").rstrip("/")
    response = requests.get(f"{base_url}/api/v3/klines", params={
        "symbol": symbol.upper(), "interval": interval,
        "startTime": int(_as_datetime(request.start).timestamp() * 1000),
        "endTime": int(_as_datetime(request.end, True).timestamp() * 1000), "limit": 1000,
    }, timeout=60)
    response.raise_for_status()
    return _frame_from_bars({
        "timestamp": datetime.fromtimestamp(row[0] / 1000), "open": row[1], "high": row[2],
        "low": row[3], "close": row[4], "volume": row[5],
    } for row in response.json())


def _massive(symbol: str, request: DataRequest) -> pd.DataFrame:
    """Fetch OHLCV data from Massive (replaces deprecated Polygon)."""
    key = os.getenv("MASSIVE_API_KEY")
    if not key:
        raise RuntimeError("MASSIVE_API_KEY is not configured on the server")
    access_key = os.getenv("MASSIVE_ACCESS_KEY_ID", "")
    secret_key = os.getenv("MASSIVE_SECRET_ACCESS_KEY", "")
    endpoint = os.getenv("MASSIVE_S3_ENDPOINT", "https://files.massive.com")
    bucket = os.getenv("MASSIVE_S3_BUCKET", "flatfiles")
    timespan = {"minute": "minute", "hour": "hour", "daily": "day"}[request.resolution]
    response = requests.get(
        f"{endpoint}/v1/{bucket}/aggs/ticker/{symbol}/range/1/{timespan}/{request.start}/{request.end}",
        params={"apiKey": key, "accessKey": access_key, "secretKey": secret_key, "limit": 50000},
        timeout=120,
    )
    response.raise_for_status()
    return _frame_from_bars({
        "timestamp": datetime.fromtimestamp(row["t"] / 1000), "open": row["o"], "high": row["h"],
        "low": row["l"], "close": row["c"], "volume": row.get("v", 0),
    } for row in response.json().get("results", []))


def _databento(symbol: str, request: DataRequest) -> pd.DataFrame:
    import databento as db
    from databento import Schema, SType

    key = os.getenv("DATA_BENTO_API_KEY")
    if not key:
        raise RuntimeError("DATA_BENTO_API_KEY is not configured on the server")
    continuous = symbol.replace(".FUT", ".c.0")
    schema = {"tick": Schema.MBP_1, "second": Schema.OHLCV_1S, "minute": Schema.OHLCV_1M, "hour": Schema.OHLCV_1H, "daily": Schema.OHLCV_1D}[request.resolution]
    data = db.Historical(key=key).timeseries.get_range(
        dataset="GLBX.MDP3", symbols=continuous, schema=schema,
        start=request.start.isoformat(), end=request.end.isoformat(),
        stype_in=SType.CONTINUOUS if ".c." in continuous else SType.RAW_SYMBOL,
    ).to_df()
    if data.empty:
        return data
    # Databento OHLCV schemas return timestamp as the index named "ts_event"
    if "ts_event" in data.columns:
        data = data.rename(columns={"ts_event": "timestamp"}).set_index("timestamp")
    elif data.index.name == "ts_event":
        data.index.name = "timestamp"
    return data[["open", "high", "low", "close", "volume"]]


def _fred(symbol: str, request: DataRequest) -> pd.DataFrame:
    """Fetch economic indicators from FRED."""
    key = os.getenv("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY is not configured on the server")
    response = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": symbol, "api_key": key, "file_type": "json",
                "observation_start": request.start.isoformat(), "observation_end": request.end.isoformat()},
        timeout=60,
    )
    response.raise_for_status()
    rows = response.json().get("observations", [])
    bars = []
    for row in rows:
        value = row.get("value", ".")
        if value == ".":
            continue
        bars.append({
            "timestamp": row["date"],
            "open": float(value),
            "high": float(value),
            "low": float(value),
            "close": float(value),
            "volume": 0,
        })
    return _frame_from_bars(bars)


def _alpaca(symbol: str, request: DataRequest) -> pd.DataFrame:
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("ALPACA_API_KEY or ALPACA_SECRET_KEY is not configured")
    timespan = {"tick": "tick", "minute": "1Min", "hour": "1Hour", "daily": "1Day"}[request.resolution]
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
    response = requests.get(url, params={
        "timeframe": timespan, "start": request.start.isoformat(), "end": request.end.isoformat(), "limit": 10000,
    }, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}, timeout=60)
    response.raise_for_status()
    return _frame_from_bars({
        "timestamp": bar["t"], "open": bar["o"], "high": bar["h"],
        "low": bar["l"], "close": bar["c"], "volume": bar["v"],
    } for bar in response.json().get("bars", []))


def _tiingo(symbol: str, request: DataRequest) -> pd.DataFrame:
    key = os.getenv("TIINGO_API_KEY")
    if not key:
        raise RuntimeError("TIINGO_API_KEY is not configured")
    freq = {"tick": "tick", "second": "1sec", "minute": "1min", "hour": "1hour", "daily": "daily"}[request.resolution]
    url = f"https://api.tiingo.com/tiingo/{'crypto' if 'USDT' in symbol or 'USD' in symbol else 'daily'}/{symbol}/prices"
    response = requests.get(url, params={
        "startDate": request.start.isoformat(), "endDate": request.end.isoformat(), "resampleFreq": freq,
    }, headers={"Authorization": f"Token {key}"}, timeout=60)
    response.raise_for_status()
    return _frame_from_bars({
        "timestamp": row["date"], "open": row["open"], "high": row["high"],
        "low": row["low"], "close": row["close"], "volume": row.get("volume", 0),
    } for row in response.json())


def _alpha_vantage(symbol: str, request: DataRequest) -> pd.DataFrame:
    key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not key:
        raise RuntimeError("ALPHA_VANTAGE_API_KEY is not configured")
    func = {"minute": "TIME_SERIES_INTRADAY", "hour": "TIME_SERIES_INTRADAY", "daily": "TIME_SERIES_DAILY"}[request.resolution]
    params = {"function": func, "symbol": symbol, "apikey": key, "outputsize": "full"}
    if func == "TIME_SERIES_INTRADAY":
        params["interval"] = {"minute": "1min", "hour": "60min"}[request.resolution]
    response = requests.get("https://www.alphavantage.co/query", params=params, timeout=60)
    response.raise_for_status()
    data = response.json()
    key_map = {"1. open": "open", "2. high": "high", "3. low": "low", "4. close": "close", "5. volume": "volume"}
    time_key = next((k for k in data if "Time Series" in k), None)
    if not time_key:
        return pd.DataFrame()
    return _frame_from_bars(
        {"timestamp": ts, **{key_map[k]: float(v) if k != "5. volume" else int(float(v)) for k, v in row.items() if k in key_map}}
        for ts, row in data[time_key].items()
    )


def _quandl(symbol: str, request: DataRequest) -> pd.DataFrame:
    key = os.getenv("QUANDL_API_KEY")
    if not key:
        raise RuntimeError("QUANDL_API_KEY is not configured")
    response = requests.get(f"https://www.quandl.com/api/v3/datasets/{symbol}/data.json", params={
        "api_key": key, "start_date": request.start.isoformat(), "end_date": request.end.isoformat(),
    }, timeout=60)
    response.raise_for_status()
    data = response.json().get("dataset_data", {})
    cols = {c.lower(): i for i, c in enumerate(data.get("column_names", []))}
    return _frame_from_bars({
        "timestamp": row[0], "open": row[cols.get("open", 1)], "high": row[cols.get("high", 2)],
        "low": row[cols.get("low", 3)], "close": row[cols.get("close", 4)], "volume": row[cols.get("volume", 5)] if "volume" in cols else 0,
    } for row in data.get("data", []))


def fetch_symbol(request: DataRequest, symbol: str) -> tuple[str, pd.DataFrame]:
    provider = select_provider(symbol, request.provider, request.resolution)
    fetchers = {"yahoo": _yahoo, "binance": _binance, "massive": _massive, "databento": _databento, "fred": _fred,
                "alpaca": _alpaca, "tiingo": _tiingo, "alpha_vantage": _alpha_vantage, "quandl": _quandl}
    frame = fetchers[provider](symbol, request)
    if not frame.empty:
        frame.index = pd.to_datetime(frame.index, utc=True)
        frame.insert(0, "symbol", symbol)
        frame.insert(1, "provider", provider)
    return provider, frame


def fetch(request: DataRequest) -> pd.DataFrame:
    if request.start > request.end:
        raise UnsupportedRequest("start must be before or equal to end")
    if not request.symbols:
        raise UnsupportedRequest("at least one symbol is required")
    frames = [frame for symbol in request.symbols if not (frame := fetch_symbol(request, symbol)[1]).empty]
    if not frames:
        return pd.DataFrame(columns=["symbol", "provider", "open", "high", "low", "close", "volume"])
    return pd.concat(frames).sort_index()


# ── Lean format helpers ──────────────────────────────────────────────
_LEAN_PRICE_MULTIPLIER = 10000  # deci-cents for equity/futures


def _milliseconds_since_midnight(dt: datetime) -> int:
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return int((dt - midnight).total_seconds() * 1000)


def _lean_symbol(symbol: str, asset_type: str) -> str:
    """Append asset-type suffix for QuantConnect Lean compatibility."""
    clean = symbol.strip().upper()
    suffixes = {
        "equity": "_EQUITY",
        "forex": "_FOREX",
        "crypto": "_CRYPTO",
        "index": "_INDEX",
        "cfd": "_CFD",
    }
    suffix = suffixes.get(asset_type, "")
    if suffix and not clean.endswith(suffix):
        clean += suffix
    return clean


def to_lean_zip(frame: pd.DataFrame, resolution: str) -> bytes:
    """Convert a DataFrame to a zip of Lean-formatted CSV files.

    Internal path structure mirrors the Lean data-folder layout::

        {asset_type}/{market}/{resolution}/{symbol}_{resolution}_{type}.csv

    Each symbol produces one merged CSV (all dates combined) — matching the
    format that LEAN expects at the resolution level (e.g. ``btcusdt_hour_trade.zip``
    containing ``btcusdt_hour_trade.csv``).
    """
    from io import BytesIO
    import zipfile

    if frame.empty:
        return b""

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for symbol, group in frame.groupby("symbol"):
            asset_type = classify_symbol(symbol)
            lean_sym = _lean_symbol(symbol, asset_type)

            # Determine market sub-directory (matching config.py from Data_Pipeline)
            market_map = {
                "crypto": "binance",
                "equity": "usa",
                "futures": "usa",
                "index": "usa",
                "economic": "interest-rate",
                "forex": "oanda",
                "cfd": "oanda",
            }
            market = market_map.get(asset_type, "usa")
            asset_dir = {"economic": "alternative"}.get(asset_type, asset_type)

            # Place CSV directly at the resolution level (not in a symbol subdir).
            base = f"{asset_dir}/{market}/{resolution}"

            # Price multiplier: 10 000 for equity / index / futures
            multiplier = _LEAN_PRICE_MULTIPLIER if asset_type in ("equity", "index", "futures") else 1

            group_sorted = group.sort_index()
            lines = ["Time,Open,High,Low,Close,Volume"]

            for ts, row in group_sorted.iterrows():
                ts_dt = ts.to_pydatetime()

                # Time column format
                if asset_type == "crypto" or resolution == "daily":
                    time_str = ts_dt.strftime("%Y%m%d %H:%M")
                else:
                    time_str = str(_milliseconds_since_midnight(ts_dt))

                o, h, l, c = (
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                )
                v = int(float(row["volume"]))

                if multiplier == 1:
                    lines.append(f"{time_str},{o},{h},{l},{c},{v}")
                else:
                    lines.append(
                        f"{time_str},"
                        f"{int(round(o * multiplier))},"
                        f"{int(round(h * multiplier))},"
                        f"{int(round(l * multiplier))},"
                        f"{int(round(c * multiplier))},"
                        f"{v}"
                    )

            # Single merged CSV per symbol (all dates), e.g. "trxusdt_hour_trade.csv"
            csv_name = f"{lean_sym.lower()}_{resolution}_trade.csv"
            csv_path = f"{base}/{csv_name}"
            zf.writestr(csv_path, "\n".join(lines))

    return buffer.getvalue()


def _q_literal(value):
    if pd.isna(value):
        return "0n"
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.strftime("%Y.%m.%dD%H:%M:%S.%f")
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


def to_q_table(frame: pd.DataFrame, include_metadata: bool = False) -> str:
    """Render a pandas DataFrame as a KDB/q+ table literal for internal tooling."""
    if frame is None or frame.empty:
        return "([])"

    table = frame.copy()
    if "timestamp" in table.columns:
        table = table.rename(columns={"timestamp": "time"})
    elif table.index.name and table.index.name not in {None, "index"}:
        table = table.reset_index(names=table.index.name)
        table = table.rename(columns={table.index.name: "time"})
    elif table.index.nlevels == 1 and isinstance(table.index, pd.DatetimeIndex):
        table = table.reset_index()
        table = table.rename(columns={"index": "time"})

    if not include_metadata:
        for column in ["symbol", "provider"]:
            if column in table.columns:
                table = table.drop(columns=[column])

    keep = ["time", "open", "high", "low", "close", "volume"]
    if include_metadata:
        keep.extend(["symbol", "provider"])
    for column in list(table.columns):
        if column not in keep and column not in {"time", "open", "high", "low", "close", "volume"}:
            table = table.drop(columns=[column])
    if "time" not in table.columns:
        table["time"] = pd.to_datetime(table.index, utc=True)

    columns = [column for column in ["time", "open", "high", "low", "close", "volume"] + (["symbol", "provider"] if include_metadata else []) if column in table.columns]
    if not columns:
        return "([])"

    lists = []
    for column in columns:
        values = [
            _q_literal(value)
            for value in table[column].tolist()
        ]
        lists.append(f"{column}:({'; '.join(values)})")
    return "([] " + "; ".join(lists) + ")"
