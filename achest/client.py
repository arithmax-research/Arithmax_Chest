"""Python client for the centralized market-data API."""

from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Iterable
import time
import zipfile

import httpx
import pandas as pd

from .service import classify_symbol, to_q_table

_DEFAULT_BASE_URL = "https://achestv2.misango.me"

#: Transport-level exceptions that are safe to retry (transient network/SSL failures).
_RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
)


def _default_output_path(symbols: list[str], resolution: str) -> Path:
    """Derive a sensible output-directory path from symbol types and resolution.

    Uses the same convention as the repo's ``Data/`` directory layout::

        Data/equity/usa/{resolution}/   for equities
        Data/crypto/{resolution}/       for crypto
        Data/futures/{resolution}/      for futures
        Data/forex/{resolution}/        for forex
        Data/other/{resolution}/        for everything else
    """
    if not symbols:
        return Path.cwd()
    # Classify the first symbol to pick the directory
    asset_type = classify_symbol(symbols[0])
    market = {
        "equity": "equity/usa",
        "etf": "equity/usa",
        "index": "equity/usa",
        "crypto": "crypto",
        "futures": "futures",
        "forex": "forex",
        "economic": "other",
    }.get(asset_type, "other")
    return Path("Data") / market / resolution
def _read_lean_zip(zip_bytes: bytes) -> pd.DataFrame:
    """Parse a Lean-format zip-of-zips back into a pandas DataFrame.

    The server returns an outer zip containing individual per-symbol zips
    (e.g. ``spy.zip``).  Each inner zip holds a single merged CSV
    with columns ``Time,Open,High,Low,Close,Volume``.
    """
    frames = []
    with zipfile.ZipFile(BytesIO(zip_bytes)) as outer_zf:
        for inner_name in outer_zf.namelist():
            if not inner_name.endswith(".zip"):
                continue
            inner_bytes = outer_zf.read(inner_name)
            with zipfile.ZipFile(BytesIO(inner_bytes)) as inner_zf:
                for csv_name in inner_zf.namelist():
                    if not csv_name.endswith(".csv"):
                        continue
                    # Extract symbol from the CSV filename: "spy_daily_trade.csv" → "SPY"
                    tokens = csv_name.replace(".csv", "").split("_")
                    symbol_from_path = tokens[0].upper() if tokens else "UNKNOWN"

                    df = pd.read_csv(inner_zf.open(csv_name))
                    df["symbol"] = symbol_from_path
                    # Parse the Lean time column
                    raw = df["Time"].astype(str)
                    parsed = pd.to_datetime(raw, format="%Y%m%d %H:%M", errors="coerce")
                    if parsed.isna().all():
                        parsed = pd.to_numeric(raw, errors="coerce")
                        parsed = pd.to_datetime(parsed, unit="ms", origin="unix", errors="coerce")
                    df["timestamp"] = parsed
                    df = df.drop(columns=["Time"])
                    frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "symbol", "timestamp"])


class MarketDataClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 300.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        final_base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.Client(base_url=final_base_url, headers=headers, timeout=timeout)
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Send an HTTP request, retrying on transient transport errors.

        Retries with exponential backoff for ``ConnectError``,
        ``TimeoutException``, and ``RemoteProtocolError``.  Non-2xx
        HTTP statuses are **not** retried — they raise immediately.
        """
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                return getattr(self.client, method)(path, **kwargs)
            except _RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay * (2**attempt))
                    continue
                raise
        # Should never reach here, but keeps type-checkers happy
        raise RuntimeError("unreachable") from last_exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, symbol: str, resolution: str = "daily", provider: str = "auto") -> dict:
        response = self._request("get", "/v1/route", params={"symbol": symbol, "resolution": resolution, "provider": provider})
        response.raise_for_status()
        return response.json()

    def get(
        self,
        symbols: str | Iterable[str],
        start: date | str,
        end: date | str,
        resolution: str = "daily",
        provider: str = "auto",
        format: str = "json",
    ) -> pd.DataFrame:
        if isinstance(symbols, str):
            symbols = [symbols]
        body = {
            "symbols": list(symbols),
            "start": str(start),
            "end": str(end),
            "resolution": resolution,
            "provider": provider,
            "format": format,
        }
        response = self._request("post", "/v1/data", json=body)
        response.raise_for_status()

        if format == "lean":
            # Server returns a zip-of-zips. Extract inner zips and read CSVs.
            return _read_lean_zip(response.content)

        return pd.DataFrame(response.json())

    def download(
        self,
        symbols: str | Iterable[str],
        start: date | str,
        end: date | str,
        resolution: str = "daily",
        provider: str = "auto",
        format: str = "lean",
        output: str | Path | None = None,
    ) -> Path:
        if isinstance(symbols, str):
            symbols = [symbols]
        if output is None:
            output = _default_output_path(list(symbols), resolution)
        body = {
            "symbols": list(symbols),
            "start": str(start),
            "end": str(end),
            "resolution": resolution,
            "provider": provider,
            "format": format,
        }
        response = self._request("post", "/v1/data", json=body)
        response.raise_for_status()

        if format == "lean":
            data_dir = Path(output)
            data_dir.mkdir(parents=True, exist_ok=True)
            # Server returns a zip-of-zips: extract each inner zip and save it.
            with zipfile.ZipFile(BytesIO(response.content)) as outer_zf:
                for zip_name in outer_zf.namelist():
                    if not zip_name.endswith(".zip"):
                        continue
                    inner_bytes = outer_zf.read(zip_name)
                    (data_dir / zip_name).write_bytes(inner_bytes)
            return data_dir

        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return destination

    def q_table(self, symbols: Iterable[str], start: date | str, end: date | str, resolution: str = "daily", provider: str = "auto", include_metadata: bool = False) -> str:
        frame = self.get(symbols, start, end, resolution=resolution, provider=provider)
        return to_q_table(frame, include_metadata=include_metadata)

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
