"""Python client for the centralized market-data API."""

from datetime import date
from pathlib import Path
from typing import Iterable

import httpx
import pandas as pd

from .service import to_q_table

_DEFAULT_BASE_URL = "https://achest.misango.me"


class MarketDataClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 300.0):
        final_base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.Client(base_url=final_base_url, headers=headers, timeout=timeout)

    def route(self, symbol: str, resolution: str = "daily", provider: str = "auto") -> dict:
        response = self.client.get("/v1/route", params={"symbol": symbol, "resolution": resolution, "provider": provider})
        response.raise_for_status()
        return response.json()

    def get(self, symbols: Iterable[str], start: date | str, end: date | str, resolution: str = "daily", provider: str = "auto") -> pd.DataFrame:
        response = self.client.post("/v1/data", json={"symbols": list(symbols), "start": str(start), "end": str(end), "resolution": resolution, "provider": provider, "format": "json"})
        response.raise_for_status()
        return pd.DataFrame(response.json())

    def download(self, symbols: Iterable[str], start: date | str, end: date | str, output: str | Path, resolution: str = "daily", provider: str = "auto", format: str = "parquet") -> Path:
        response = self.client.post("/v1/data", json={"symbols": list(symbols), "start": str(start), "end": str(end), "resolution": resolution, "provider": provider, "format": format})
        response.raise_for_status()
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
