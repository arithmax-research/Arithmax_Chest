"""Python client for the centralized market-data API."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
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

# Chunk thresholds per resolution (days).  0 = no auto-chunking (single request).
# High-res data over long ranges is split into smaller parallel requests.
_CHUNK_DAYS: dict[str, int] = {
    "tick": 1,
    "second": 1,
    "minute": 7,
    "hour": 30,
}


def _chunk_date_range(
    start: date,
    end: date,
    resolution: str,
    chunk_days: int | None = None,
) -> list[tuple[date, date]]:
    """Split (start, end) into non-overlapping sub-ranges for parallel fetching.

    The API treats *end* as exclusive (the day *after* the last trading day),
    so consecutive chunks tile perfectly: chunk₂.start == chunk₁.end.

    Returns ``[(start, end)]`` (no split) for low-res data or when the range
    is already smaller than one chunk.
    """
    size = _CHUNK_DAYS.get(resolution, 0) if chunk_days is None else chunk_days
    if size <= 0:
        return [(start, end)]

    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor < end:
        chunk_end = cursor + timedelta(days=size)
        if chunk_end > end:
            chunk_end = end
        chunks.append((cursor, chunk_end))
        cursor = chunk_end  # end is exclusive, so this tiles cleanly
    return chunks


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

    Returns a DataFrame with the same lowercase column schema as the
    JSON / CSV formats: ``timestamp, symbol, open, high, low, close, volume``.
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
                    # Normalise column names to lowercase (Open → open, Volume → volume)
                    df.columns = [col.lower() for col in df.columns]
                    frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame(columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"])


class MarketDataClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 300.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        max_workers: int = 4,
        chunk_days: int | None = None,
    ):
        final_base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.Client(base_url=final_base_url, headers=headers, timeout=timeout)
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._max_workers = max_workers
        # None = use per-resolution defaults from _CHUNK_DAYS
        self._chunk_days = chunk_days

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
        symbols = list(symbols)

        start_date = start if isinstance(start, date) else date.fromisoformat(str(start))
        end_date = end if isinstance(end, date) else date.fromisoformat(str(end))

        chunks = _chunk_date_range(start_date, end_date, resolution, self._chunk_days)

        if len(chunks) <= 1:
            return self._fetch_chunk(symbols, start, end, resolution, provider, format)

        # Parallel fetch across chunks
        frames: list[pd.DataFrame] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {
                pool.submit(
                    self._fetch_chunk, symbols, cs, ce, resolution, provider, format
                ): (cs, ce)
                for cs, ce in chunks
            }
            for future in as_completed(futures):
                frames.append(future.result())

        result = pd.concat(frames, ignore_index=True)
        if "timestamp" in result.columns:
            result = result.sort_values("timestamp").reset_index(drop=True)
        return result

    def _fetch_chunk(
        self,
        symbols: list[str],
        start: date | str,
        end: date | str,
        resolution: str,
        provider: str,
        format: str,
    ) -> pd.DataFrame:
        """Execute a single date-range request and return a DataFrame."""
        body = {
            "symbols": symbols,
            "start": str(start),
            "end": str(end),
            "resolution": resolution,
            "provider": provider,
            "format": format,
        }
        response = self._request("post", "/v1/data", json=body)
        response.raise_for_status()

        if format == "lean":
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
        symbols = list(symbols)
        if output is None:
            if format == "lean":
                output = _default_output_path(symbols, resolution)
            else:
                ext = {"parquet": ".parquet", "csv": ".csv", "json": ".json"}.get(format, "")
                output = Path("Custom_Downloads") / f"{symbols[0].lower()}_{resolution}{ext}"
        destination = Path(output)

        start_date = start if isinstance(start, date) else date.fromisoformat(str(start))
        end_date = end if isinstance(end, date) else date.fromisoformat(str(end))

        chunks = _chunk_date_range(start_date, end_date, resolution, self._chunk_days)

        if len(chunks) <= 1:
            return self._download_single(
                symbols, start, end, resolution, provider, format, destination,
            )

        # Parallel chunks
        if format == "lean":
            destination.mkdir(parents=True, exist_ok=True)
            with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
                futures = {
                    pool.submit(
                        self._download_single,
                        symbols, cs, ce, resolution, provider, format, destination,
                    ): (cs, ce)
                    for cs, ce in chunks
                }
                for future in as_completed(futures):
                    future.result()  # re-raises if the chunk failed
            return destination

        # Non-lean: fetch chunks as DataFrames in parallel, concat, write final file
        frames: list[pd.DataFrame] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {
                pool.submit(
                    self._fetch_chunk, symbols, cs, ce, resolution, provider, format,
                ): (cs, ce)
                for cs, ce in chunks
            }
            for future in as_completed(futures):
                frames.append(future.result())

        result = pd.concat(frames, ignore_index=True)
        if "timestamp" in result.columns:
            result = result.sort_values("timestamp").reset_index(drop=True)

        destination.parent.mkdir(parents=True, exist_ok=True)
        if format == "csv":
            result.to_csv(destination, index=False)
        elif format == "json":
            destination.write_text(result.to_json(orient="records", date_format="iso"))
        else:  # parquet
            result.to_parquet(destination, index=False)
        return destination

    def _download_single(
        self,
        symbols: list[str],
        start: date | str,
        end: date | str,
        resolution: str,
        provider: str,
        format: str,
        destination: Path,
    ) -> Path:
        """Execute a single date-range download and write to *destination*."""
        body = {
            "symbols": symbols,
            "start": str(start),
            "end": str(end),
            "resolution": resolution,
            "provider": provider,
            "format": format,
        }
        response = self._request("post", "/v1/data", json=body)
        response.raise_for_status()

        if format == "lean":
            destination.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(BytesIO(response.content)) as outer_zf:
                for zip_name in outer_zf.namelist():
                    if not zip_name.endswith(".zip"):
                        continue
                    (destination / zip_name).write_bytes(outer_zf.read(zip_name))
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return destination

# ── Eulerpool Extended Data Methods ─────────────────────────────────────

    def fundamentals(self, identifier: str, data_type: str = "overview") -> dict | list:
        """Fetch Eulerpool fundamental data for a security.

        Parameters
        ----------
        identifier : str
            ISIN, ticker, CUSIP, SEDOL, or WKN.
        data_type : str
            One of ``profile``, ``overview``, ``income``, ``balance``,
            ``cashflow``, ``metrics``, ``key-figures``, ``growth``,
            ``margins``, ``esg``, ``aaqs``, ``fair-value``.

        Returns
        -------
        dict or list
        """
        resp = self._request("get", f"/v1/eulerpool/fundamentals/{data_type}/{identifier}")
        resp.raise_for_status()
        return resp.json()

    def analyst(self, identifier: str, data_type: str = "estimates") -> dict | list:
        """Fetch Eulerpool analyst data.

        Parameters
        ----------
        identifier : str
        data_type : str
            One of ``estimates``, ``price-target``, ``upgrades``, ``recommendations``.
        """
        resp = self._request("get", f"/v1/eulerpool/analyst/{data_type}/{identifier}")
        resp.raise_for_status()
        return resp.json()

    def ownership(self, identifier: str, data_type: str = "institutional") -> list:
        """Fetch Eulerpool ownership data.

        Parameters
        ----------
        identifier : str
        data_type : str
            One of ``institutional``, ``fund``, ``insider``, ``etf-exposure``.
        """
        resp = self._request("get", f"/v1/eulerpool/ownership/{data_type}/{identifier}")
        resp.raise_for_status()
        return resp.json()

    def macro(self, endpoint: str, **params) -> dict | list:
        """Fetch Eulerpool macro-economic data.

        Examples
        --------
        client.macro("country-risk")
        client.macro("fred/GDP", limit=100)
        client.macro("fred-latest")
        client.macro("credit-spreads", days=365)
        """
        resp = self._request("get", f"/v1/eulerpool/macro/{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()

    def crypto_data(self, endpoint: str, **params) -> dict | list:
        """Fetch Eulerpool crypto extended data.

        Examples
        --------
        client.crypto_data("top")
        client.crypto_data("market-overview")
        client.crypto_data("analysis/BTC")
        client.crypto_data("fear-greed", days=90)
        client.crypto_data("funding-rates/BTC", days=30)
        client.crypto_data("onchain/BTC")
        """
        resp = self._request("get", f"/v1/eulerpool/crypto/{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()

    def options_data(self, endpoint: str, **params) -> dict | list:
        """Fetch Eulerpool options & derivatives data.

        Examples
        --------
        client.options_data("chain/AAPL")
        client.options_data("greeks/AAPL")
        client.options_data("iv-surface/AAPL")
        client.options_data("unusual-activity", min_volume=1000)
        client.options_data("vix-term-structure")
        """
        resp = self._request("get", f"/v1/eulerpool/options/{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()

    def alternative_data(self, endpoint: str, **params) -> dict | list:
        """Fetch Eulerpool alternative data.

        Examples
        --------
        client.alternative_data("fear-greed")
        client.alternative_data("superinvestors")
        client.alternative_data("congress-trading", symbol="AAPL")
        client.alternative_data("patents/AAPL")
        client.alternative_data("google-trends/AAPL")
        """
        resp = self._request("get", f"/v1/eulerpool/alternative/{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()

    def news_research(self, endpoint: str, **params) -> list:
        """Fetch Eulerpool news & research data.

        Examples
        --------
        client.news_research("AAPL")
        client.news_research("market", limit=50)
        client.news_research("transcripts/list/AAPL")
        client.news_research("transcripts/search", q="AI", ticker="MSFT")
        """
        resp = self._request("get", f"/v1/eulerpool/news/{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()

    def etf_data(self, identifier: str, data_type: str = "profile") -> dict | list:
        """Fetch Eulerpool ETF-specific data.

        Parameters
        ----------
        identifier : str
        data_type : str
            One of ``profile``, ``holdings``, ``flows``.
        """
        resp = self._request("get", f"/v1/eulerpool/etf/{data_type}/{identifier}")
        resp.raise_for_status()
        return resp.json()

    def market_data_ext(self, endpoint: str, **params) -> dict | list:
        """Fetch Eulerpool market-wide data.

        Examples
        --------
        client.market_data_ext("latest-quotes", stocks="AAPL,MSFT")
        client.market_data_ext("top-movers")
        client.market_data_ext("status")
        client.market_data_ext("breadth", days=30)
        """
        resp = self._request("get", f"/v1/eulerpool/market/{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()

    def index_constituents(self, index_id: str = "sp500", start: int = 0, end: int = 500) -> list:
        """Fetch index constituents from Eulerpool."""
        resp = self._request("get", f"/v1/eulerpool/index/{index_id}", params={"start": start, "end": end})
        resp.raise_for_status()
        return resp.json()

    def yield_curve(self, country: str = "US", days: int = 90) -> list:
        """Fetch government bond yield curve from Eulerpool."""
        resp = self._request("get", "/v1/eulerpool/bonds/yield-curve", params={"country": country, "days": days})
        resp.raise_for_status()
        return resp.json()

    def forex_rates(self, base: str = "USD") -> list:
        """Fetch current exchange rates from Eulerpool."""
        resp = self._request("get", f"/v1/eulerpool/forex/rates/{base}")
        resp.raise_for_status()
        return resp.json()

    def logo(self, symbol: str, size: int = 128) -> bytes:
        """Fetch company logo image by ticker symbol (returns raw PNG bytes)."""
        resp = self._request("get", f"/v1/eulerpool/logo/{symbol}", params={"size": size})
        resp.raise_for_status()
        return resp.content
        return resp.json()

    def dividends_data(self, identifier: str, data_type: str = "history") -> dict | list:
        """Fetch Eulerpool dividend data.

        Parameters
        ----------
        identifier : str
        data_type : str
            One of ``history``, ``quality``.
        """
        resp = self._request("get", f"/v1/eulerpool/dividends/{data_type}/{identifier}")
        resp.raise_for_status()
        return resp.json()

    def short_data(self, identifier: str, data_type: str = "volume") -> list:
        """Fetch Eulerpool short-selling data.

        Parameters
        ----------
        identifier : str
        data_type : str
            One of ``volume``, ``interest``.
        """
        resp = self._request("get", f"/v1/eulerpool/short/{data_type}/{identifier}")
        resp.raise_for_status()
        return resp.json()

    def sentiment_data(self, identifier: str, data_type: str = "news") -> dict | list:
        """Fetch Eulerpool sentiment data.

        Parameters
        ----------
        identifier : str
        data_type : str
            One of ``news``, ``social``, ``insider``, ``swot``.
        """
        resp = self._request("get", f"/v1/eulerpool/sentiment/{data_type}/{identifier}")
        resp.raise_for_status()
        return resp.json()
    def q_table(self, symbols: Iterable[str], start: date | str, end: date | str, resolution: str = "daily", provider: str = "auto", include_metadata: bool = False) -> str:
        frame = self.get(symbols, start, end, resolution=resolution, provider=provider)
        return to_q_table(frame, include_metadata=include_metadata)

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
