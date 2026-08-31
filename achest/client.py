"""Python client for the centralized market-data API."""

from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Iterable
import time
import zipfile

import httpx
import pandas as pd

from .service import to_q_table

_DEFAULT_BASE_URL = "https://achest.misango.me"

#: Transport-level exceptions that are safe to retry (transient network/SSL failures).
_RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
)


def _read_lean_zip(zip_bytes: bytes) -> pd.DataFrame:
    """Parse a Lean-format zip file back into a pandas DataFrame."""
    frames = []
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if not name.endswith(".csv"):
                continue
            parts = name.split("/")
            fname = parts[-1]
            # Support two path layouts:
            #   OLD: {asset}/{market}/{resolution}/{symbol}/{date}_{symbol}_{resolution}_trade.csv
            #   NEW: {asset}/{market}/{resolution}/{symbol}_{resolution}_trade.csv
            if len(parts) >= 4:
                # New format: symbol is embedded in the CSV filename before the resolution.
                # e.g. "trxusdt_hour_trade.csv" -> symbol = "trxusdt"
                tokens = fname.replace(".csv", "").split("_")
                # tokens: [symbol, resolution, (quote|trade)]  or  [date, symbol, resolution, (quote|trade)]
                if tokens[0].isdigit() and len(tokens) >= 4:
                    symbol_from_path = tokens[1].upper()
                elif not tokens[0].isdigit() and len(tokens) >= 3:
                    symbol_from_path = tokens[0].upper()
                else:
                    symbol_from_path = "UNKNOWN"
            else:
                symbol_from_path = parts[-2] if len(parts) >= 2 else "unknown"

            df = pd.read_csv(zf.open(name))
            df["symbol"] = symbol_from_path
            # Parse the Lean time column
            raw = df["Time"].astype(str)
            # Try ISO-like or YYYYMMDD HH:MM format
            parsed = pd.to_datetime(raw, format="%Y%m%d %H:%M", errors="coerce")
            # If parsing failed, maybe it's milliseconds-since-midnight
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
        symbols: Iterable[str],
        start: date | str,
        end: date | str,
        resolution: str = "daily",
        provider: str = "auto",
        format: str = "json",
    ) -> pd.DataFrame:
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
            zip_bytes = BytesIO(response.content)
            data_root = Path.cwd() / "data"
            with zipfile.ZipFile(zip_bytes) as zf:
                zf.extractall(data_root)
            return _read_lean_zip(response.content)

        return pd.DataFrame(response.json())

    def download(
        self,
        symbols: Iterable[str],
        start: date | str,
        end: date | str,
        output: str | Path,
        resolution: str = "daily",
        provider: str = "auto",
        format: str = "parquet",
    ) -> Path:
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
            with zipfile.ZipFile(BytesIO(response.content)) as zf:
                zf.extractall(data_dir)
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
