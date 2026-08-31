"""FastAPI application for the centralized market-data service."""

from datetime import date
from io import BytesIO
import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from .service import (
    PROVIDER_CAPABILITIES,
    DataRequest,
    UnsupportedRequest,
    fetch,
    select_provider,
    to_lean_zip,
)

load_dotenv()
app = FastAPI(title="Central Market Data API", version="0.2.0")


class DownloadRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    start: date
    end: date
    resolution: str = "daily"
    provider: str = "auto"
    format: str = "csv"

    @field_validator("resolution")
    @classmethod
    def valid_resolution(cls, value: str) -> str:
        if value not in {"tick", "second", "minute", "hour", "daily"}:
            raise ValueError("unsupported resolution")
        return value

    @field_validator("format")
    @classmethod
    def valid_format(cls, value: str) -> str:
        if value not in {"json", "csv", "parquet", "lean"}:
            raise ValueError("format must be json, csv, parquet, or lean")
        return value


def require_client_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("DATA_API_TOKEN")
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid client token")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/providers", dependencies=[Depends(require_client_token)])
def providers() -> dict:
    return {"providers": PROVIDER_CAPABILITIES}


@app.get("/v1/route", dependencies=[Depends(require_client_token)])
def route(symbol: str, resolution: str = Query(default="daily"), provider: str = Query(default="auto")) -> dict[str, str]:
    try:
        selected = select_provider(symbol, provider, resolution)
    except UnsupportedRequest as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"symbol": symbol, "resolution": resolution, "provider": selected}


@app.post("/v1/data", dependencies=[Depends(require_client_token)])
def data(request: DownloadRequest) -> Response:
    try:
        frame = fetch(DataRequest(request.symbols, request.start, request.end, request.resolution, request.provider))
    except (UnsupportedRequest, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"provider request failed: {error}") from error
    table = frame.reset_index(names="timestamp")
    if request.format == "json":
        return Response(table.to_json(orient="records", date_format="iso"), media_type="application/json")
    if request.format == "csv":
        return Response(table.to_csv(index=False), media_type="text/csv")
    if request.format == "lean":
        zip_bytes = to_lean_zip(table.set_index("timestamp"), request.resolution)
        return Response(
            zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=market-data-lean.zip"},
        )
    output = BytesIO()
    table.to_parquet(output, index=False)
    return Response(output.getvalue(), media_type="application/octet-stream", headers={"Content-Disposition": "attachment; filename=market-data.parquet"})
