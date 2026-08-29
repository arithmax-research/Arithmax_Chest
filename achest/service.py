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


def fetch_symbol(request: DataRequest, symbol: str) -> tuple[str, pd.DataFrame]:
    provider = select_provider(symbol, request.provider, request.resolution)
    fetchers = {"yahoo": _yahoo, "binance": _binance, "massive": _massive, "databento": _databento}
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
