"""FastAPI application for the centralized market-data service."""
from __future__ import annotations

from datetime import date
from io import BytesIO
import os
from typing import Any

import zipfile

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
app = FastAPI(title="Central Market Data API", version="0.5.0")


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


# ── helpers ───────────────────────────────────────────────────────────────

def _get_eulerpool() -> Any:
    """Lazy-import and return an EulerpoolProvider instance."""
    from .eulerpool_provider import EulerpoolProvider
    return EulerpoolProvider()


def _json_response(data: Any) -> Response:
    """Return a JSON Response from any JSON-serialisable object."""
    import json
    return Response(json.dumps(data, default=str), media_type="application/json")


# ── Core OHLCV endpoints (existing) ────────────────────────────────────────


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
    try:
        if request.format == "json":
            return Response(table.to_json(orient="records", date_format="iso"), media_type="application/json")
        if request.format == "csv":
            return Response(table.to_csv(index=False), media_type="text/csv")
        if request.format == "lean":
            per_symbol_zips = to_lean_zip(table.set_index("timestamp"), request.resolution)
            # Wrap individual per-symbol zips into one outer zip for HTTP transport.
            outer_buf = BytesIO()
            with zipfile.ZipFile(outer_buf, "w", zipfile.ZIP_DEFLATED) as outer_zf:
                for zip_name, zip_bytes in per_symbol_zips.items():
                    outer_zf.writestr(zip_name, zip_bytes)
            return Response(
                outer_buf.getvalue(),
                media_type="application/zip",
                headers={"Content-Disposition": "attachment; filename=market-data-lean.zip"},
            )
        output = BytesIO()
        table.to_parquet(output, index=False)
        return Response(output.getvalue(), media_type="application/octet-stream", headers={"Content-Disposition": "attachment; filename=market-data.parquet"})
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"output serialization failed: {error}") from error
# ── Health ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
#  EULERPOOL EXTENDED DATA ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/v1/eulerpool/fundamentals/profile/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_profile(identifier: str, language: str = Query(default="en")):
    """Company profile: description, sector, employees, website."""
    return _json_response(_get_eulerpool().company_profile(identifier, language))

@app.get("/v1/eulerpool/fundamentals/overview/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_overview(identifier: str):
    """Compact overview: P/E, P/S, div yield, 52w range, fair value."""
    return _json_response(_get_eulerpool().company_overview(identifier))

@app.get("/v1/eulerpool/fundamentals/income/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_income(identifier: str):
    """Annual income statements."""
    return _json_response(_get_eulerpool().income_statement(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/fundamentals/balance/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_balance(identifier: str):
    """Annual balance sheets."""
    return _json_response(_get_eulerpool().balance_sheet(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/fundamentals/cashflow/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_cashflow(identifier: str):
    """Annual cash-flow statements."""
    return _json_response(_get_eulerpool().cash_flow_statement(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/fundamentals/metrics/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_metrics(identifier: str):
    """40+ financial ratios: P/E, ROE, margins, growth, leverage."""
    return _json_response(_get_eulerpool().financial_metrics(identifier))

@app.get("/v1/eulerpool/fundamentals/esg/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_esg(identifier: str):
    """ESG scores + controversy screening flags."""
    return _json_response(_get_eulerpool().esg_rating(identifier))

@app.get("/v1/eulerpool/fundamentals/aaqs/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_aaqs(identifier: str):
    """AlleAktien Quality Score (0-10) -- unique to Eulerpool."""
    return _json_response(_get_eulerpool().aaqs_score(identifier))

@app.get("/v1/eulerpool/fundamentals/fair-value/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_fair_value(identifier: str):
    """Computed fair value with upside/downside."""
    return _json_response(_get_eulerpool().fair_value(identifier))

# ── Analyst Estimates & Price Targets ──────────────────────────────────────

@app.get("/v1/eulerpool/analyst/estimates/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_estimates(identifier: str):
    """Revenue / EPS / EBIT estimates."""
    return _json_response(_get_eulerpool().analyst_estimates(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/analyst/price-target/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_price_target(identifier: str):
    """Price target consensus (high, low, mean, median)."""
    return _json_response(_get_eulerpool().price_target_consensus(identifier))

@app.get("/v1/eulerpool/analyst/upgrades/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_upgrades(identifier: str):
    """Analyst upgrade/downgrade events."""
    return _json_response(_get_eulerpool().analyst_upgrades(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/ownership/etf-exposure/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_etf_exposure(identifier: str):
    """Every ETF that holds this stock."""
    return _json_response(_get_eulerpool().etf_exposure(identifier).to_dict(orient="records"))

# ── Dividends & Splits ─────────────────────────────────────────────────────

@app.get("/v1/eulerpool/dividends/history/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_dividends(identifier: str):
    """Individual dividend payments."""
    return _json_response(_get_eulerpool().dividends(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/dividends/quality/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_dividend_quality(identifier: str):
    """Dividend quality: years paid, frequency, ex/pay dates."""
    return _json_response(_get_eulerpool().dividend_quality(identifier))

@app.get("/v1/eulerpool/dividends/calendar/{year}", dependencies=[Depends(require_client_token)])
def eulerpool_dividend_calendar(year: str = "initial", country: str = Query(default="US"), limit: int = Query(default=500)):
    """Ex-dividend dates and amounts."""
    return _json_response(_get_eulerpool().dividend_calendar(year, country, limit).to_dict(orient="records"))

# ── Sentiment ──────────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/sentiment/news/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_news_sentiment(identifier: str):
    """Aggregated news sentiment."""
    return _json_response(_get_eulerpool().news_sentiment(identifier))

@app.get("/v1/eulerpool/sentiment/social/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_social_sentiment(identifier: str):
    """Social media sentiment."""
    return _json_response(_get_eulerpool().social_sentiment(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/sentiment/insider/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_insider_sentiment(identifier: str):
    """Monthly MSPR insider sentiment (-100 to +100)."""
    return _json_response(_get_eulerpool().insider_sentiment(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/sentiment/swot/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_swot(identifier: str):
    """AI-powered SWOT analysis."""
    return _json_response(_get_eulerpool().swot_analysis(identifier))

# ── Macro / Economic ───────────────────────────────────────────────────────

@app.get("/v1/eulerpool/macro/country-risk", dependencies=[Depends(require_client_token)])
def eulerpool_country_risk(region: str | None = Query(default=None)):
    """Equity risk premiums for 249 countries."""
    return _json_response(_get_eulerpool().country_risk(region).to_dict(orient="records"))

@app.get("/v1/eulerpool/macro/calendar", dependencies=[Depends(require_client_token)])
def eulerpool_macro_calendar(start: str | None = Query(None), end: str | None = Query(None), countries: str | None = Query(None)):
    """Economic events calendar (FOMC, CPI, NFP)."""
    return _json_response(_get_eulerpool().macro_calendar(start, end, countries).to_dict(orient="records"))

@app.get("/v1/eulerpool/macro/fred/{series_id}", dependencies=[Depends(require_client_token)])
def eulerpool_fred(series_id: str, limit: int = Query(default=500)):
    """FRED observations (GDP, UNRATE, CPIAUCSL, DGS10, ...)."""
    return _json_response(_get_eulerpool().fred_observations(series_id, limit))

@app.get("/v1/eulerpool/macro/fred-latest", dependencies=[Depends(require_client_token)])
def eulerpool_fred_latest():
    """Latest observations for ALL FRED series in one call."""
    return _json_response(_get_eulerpool().fred_latest().to_dict(orient="records"))

# ── Crypto Extended ────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/crypto/top", dependencies=[Depends(require_client_token)])
def eulerpool_top_crypto():
    """Top 100 cryptocurrencies by market cap."""
    return _json_response(_get_eulerpool().top_cryptocurrencies().to_dict(orient="records"))

@app.get("/v1/eulerpool/crypto/market-overview", dependencies=[Depends(require_client_token)])
def eulerpool_crypto_market_overview():
    """Fear & Greed, gainers/losers, DeFi TVL, stablecoins."""
    return _json_response(_get_eulerpool().crypto_market_overview())

@app.get("/v1/eulerpool/crypto/analysis/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_crypto_analysis(symbol: str):
    """Technical + derivatives analysis for a crypto pair."""
    return _json_response(_get_eulerpool().crypto_analysis(symbol))

@app.get("/v1/eulerpool/crypto/fear-greed", dependencies=[Depends(require_client_token)])
def eulerpool_crypto_fear_greed(days: int = Query(default=90)):
    """Crypto Fear & Greed history."""
    return _json_response(_get_eulerpool().crypto_fear_greed(days).to_dict(orient="records"))

@app.get("/v1/eulerpool/crypto/funding-rates/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_funding_rates(symbol: str, days: int = Query(default=30)):
    """Perpetual futures funding rates."""
    return _json_response(_get_eulerpool().crypto_funding_rates(symbol, days).to_dict(orient="records"))

@app.get("/v1/eulerpool/crypto/open-interest/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_open_interest(symbol: str, days: int = Query(default=30)):
    """Perpetual futures open interest."""
    return _json_response(_get_eulerpool().crypto_open_interest(symbol, days).to_dict(orient="records"))

@app.get("/v1/eulerpool/crypto/defi-protocols", dependencies=[Depends(require_client_token)])
def eulerpool_defi_protocols(limit: int = Query(default=50)):
    """Top DeFi protocols by TVL."""
    return _json_response(_get_eulerpool().defi_protocols(limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/crypto/onchain/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_onchain(symbol: str = "BTC"):
    """On-chain metrics (hash rate, active addresses, fees, NVT)."""
    return _json_response(_get_eulerpool().onchain_metrics(symbol))

# ── Options & Derivatives ──────────────────────────────────────────────────

@app.get("/v1/eulerpool/options/chain/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_options_chain(ticker: str, expiration: str | None = Query(None)):
    """Options chain from CBOE."""
    return _json_response(_get_eulerpool().options_chain(ticker, expiration))

@app.get("/v1/eulerpool/options/greeks/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_options_greeks(identifier: str):
    """Greeks (delta, gamma, theta, vega, rho)."""
    return _json_response(_get_eulerpool().options_greeks(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/options/iv-surface/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_iv_surface(identifier: str):
    """Implied volatility surface."""
    return _json_response(_get_eulerpool().iv_surface(identifier))

@app.get("/v1/eulerpool/options/unusual-activity", dependencies=[Depends(require_client_token)])
def eulerpool_unusual_options(min_volume: int = Query(default=1000), limit: int = Query(default=50)):
    """Unusual options activity."""
    return _json_response(_get_eulerpool().unusual_options_activity(min_volume, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/options/vix-term-structure", dependencies=[Depends(require_client_token)])
def eulerpool_vix_term_structure(days: int = Query(default=30)):
    """VIX futures term structure."""
    return _json_response(_get_eulerpool().vix_term_structure(days).to_dict(orient="records"))

# ── Alternative Data ───────────────────────────────────────────────────────

@app.get("/v1/eulerpool/alternative/fear-greed", dependencies=[Depends(require_client_token)])
def eulerpool_fear_greed(days: int = Query(default=30)):
    """Market Fear & Greed Index."""
    return _json_response(_get_eulerpool().fear_greed_index(days))

@app.get("/v1/eulerpool/alternative/superinvestors", dependencies=[Depends(require_client_token)])
def eulerpool_superinvestors():
    """All tracked superinvestors."""
    return _json_response(_get_eulerpool().superinvestors_list().to_dict(orient="records"))

@app.get("/v1/eulerpool/alternative/superinvestor/{slug}", dependencies=[Depends(require_client_token)])
def eulerpool_superinvestor_holdings(slug: str):
    """Portfolio of a specific superinvestor."""
    return _json_response(_get_eulerpool().superinvestor_holdings(slug))

@app.get("/v1/eulerpool/alternative/congress-trading", dependencies=[Depends(require_client_token)])
def eulerpool_congress_trading(symbol: str | None = Query(None), limit: int = Query(default=100)):
    """US Congress stock trades."""
    return _json_response(_get_eulerpool().congress_trading(symbol, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/alternative/patents/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_patents(ticker: str, limit: int = Query(default=100)):
    """Patent filings for a company."""
    return _json_response(_get_eulerpool().patents(ticker, limit).to_dict(orient="records"))

# ── ETF Data ───────────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/etf/profile/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_etf_profile(identifier: str):
    """ETF profile (AUM, NAV, expense ratio, holdings)."""
    return _json_response(_get_eulerpool().etf_profile(identifier))

@app.get("/v1/eulerpool/etf/holdings/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_etf_holdings(identifier: str):
    """Top ETF holdings."""
    return _json_response(_get_eulerpool().etf_holdings(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/etf/flows/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_etf_flows(ticker: str, days: int = Query(default=90)):
    """Daily ETF fund flows (inflows/outflows)."""
    return _json_response(_get_eulerpool().etf_flows(ticker, days).to_dict(orient="records"))

# ── Market Data ────────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/market/latest-quotes", dependencies=[Depends(require_client_token)])
def eulerpool_latest_quotes(stocks: str | None = Query(None)):
    """Latest price for tickers."""
    return _json_response(_get_eulerpool().latest_quotes(stocks).to_dict(orient="records"))

@app.get("/v1/eulerpool/market/top-movers", dependencies=[Depends(require_client_token)])
def eulerpool_top_movers(country: str = Query(default="US"), limit: int = Query(default=20)):
    """Top gainers & losers."""
    return _json_response(_get_eulerpool().top_movers(country, limit))

@app.get("/v1/eulerpool/market/status", dependencies=[Depends(require_client_token)])
def eulerpool_market_status():
    """Exchange open/close status."""
    return _json_response(_get_eulerpool().market_status())

@app.get("/v1/eulerpool/market/breadth", dependencies=[Depends(require_client_token)])
def eulerpool_market_breadth(days: int = Query(default=30)):
    """Advancing/declining stocks and A/D ratio."""
    return _json_response(_get_eulerpool().market_breadth(days).to_dict(orient="records"))

# ── News & Research ────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/news/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_company_news(ticker: str):
    """Latest news articles for a company."""
    return _json_response(_get_eulerpool().company_news(ticker).to_dict(orient="records"))

@app.get("/v1/eulerpool/news/market", dependencies=[Depends(require_client_token)])
def eulerpool_market_news(limit: int = Query(default=50)):
    """Latest general market news."""
    return _json_response(_get_eulerpool().market_news(limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/transcripts/list/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_transcript_list(identifier: str, limit: int = Query(default=20)):
    """Earnings call transcripts list."""
    return _json_response(_get_eulerpool().earnings_call_list(identifier, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/transcripts/search", dependencies=[Depends(require_client_token)])
def eulerpool_transcript_search(q: str = Query(...), ticker: str | None = Query(None), limit: int = Query(default=20)):
    """Full-text search in earnings call transcripts."""
    return _json_response(_get_eulerpool().search_transcripts(q, ticker, limit).to_dict(orient="records"))

# ── Calendar ───────────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/calendar/earnings/{date_str}", dependencies=[Depends(require_client_token)])
def eulerpool_earnings_calendar(date_str: str):
    """Earnings reports for the week containing the given date."""
    return _json_response(_get_eulerpool().earnings_calendar_weekly(date_str).to_dict(orient="records"))

@app.get("/v1/eulerpool/calendar/earnings-by-symbol/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_earnings_by_symbol(symbol: str):
    """Upcoming/past earnings dates for a company."""
    return _json_response(_get_eulerpool().earnings_by_symbol(symbol).to_dict(orient="records"))

@app.get("/v1/eulerpool/calendar/earnings-surprises/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_earnings_surprises(symbol: str):
    """Historical earnings surprises."""
    return _json_response(_get_eulerpool().earnings_surprises(symbol).to_dict(orient="records"))

# ── Index Constituents ─────────────────────────────────────────────────────

@app.get("/v1/eulerpool/index/{index_id}", dependencies=[Depends(require_client_token)])
def eulerpool_index_constituents(index_id: str = "sp500", start: int = Query(default=0), end: int = Query(default=500)):
    """Index constituents (S&P 500, DAX, NASDAQ 100, Dow Jones)."""
    return _json_response(_get_eulerpool().index_constituents(index_id, start, end).to_dict(orient="records"))

# ── Yield Curve & Bonds ────────────────────────────────────────────────────

@app.get("/v1/eulerpool/bonds/yield-curve", dependencies=[Depends(require_client_token)])
def eulerpool_yield_curve(country: str = Query(default="US"), days: int = Query(default=90)):
    """Government bond yield curve by tenor."""
    return _json_response(_get_eulerpool().yield_curve(country, days).to_dict(orient="records"))

# ── Logo (returns raw image bytes) ────────────────────────────────────────

@app.get("/v1/eulerpool/logo/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_logo(symbol: str, size: int = Query(default=128)):
    """Company logo by ticker symbol, returns PNG bytes."""
    img = _get_eulerpool().logo_by_ticker(symbol, size)
    if not img:
        raise HTTPException(status_code=404, detail="logo not found")
    return Response(img, media_type="image/png")

# ── Forex Rates ────────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/forex/rates/{base}", dependencies=[Depends(require_client_token)])
def eulerpool_forex_rates(base: str = "USD"):
    """Exchange rates for a base currency."""
    return _json_response(_get_eulerpool().forex_rates(base).to_dict(orient="records"))

@app.get("/v1/eulerpool/forex/history/{from_curr}/{to_curr}", dependencies=[Depends(require_client_token)])
def eulerpool_fx_series(from_curr: str, to_curr: str, range_: str = Query(default="1y", alias="range")):
    """Historical exchange rates between two currencies."""
    return _json_response(_get_eulerpool().fx_series(from_curr, to_curr, range_).to_dict(orient="records"))

# ── Commodities ────────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/commodity/list", dependencies=[Depends(require_client_token)])
def eulerpool_commodity_list():
    """All available commodities with prices."""
    return _json_response(_get_eulerpool().commodity_list().to_dict(orient="records"))

@app.get("/v1/eulerpool/commodity/futures-curve/{product}", dependencies=[Depends(require_client_token)])
def eulerpool_futures_curve(product: str):
    """Futures term structure (contango/backwardation)."""
    return _json_response(_get_eulerpool().futures_curve(product).to_dict(orient="records"))

@app.get("/v1/eulerpool/calendar/ipo", dependencies=[Depends(require_client_token)])
def eulerpool_ipo_calendar():
    """Upcoming and recent IPOs."""
    return _json_response(_get_eulerpool().ipo_calendar().to_dict(orient="records"))

@app.get("/v1/eulerpool/calendar/economic", dependencies=[Depends(require_client_token)])
def eulerpool_economic_calendar(days: int = Query(default=30)):
    """Upcoming economic events (FOMC, CPI, NFP)."""
    return _json_response(_get_eulerpool().economic_calendar(days).to_dict(orient="records"))

@app.get("/v1/eulerpool/market/indicators", dependencies=[Depends(require_client_token)])
def eulerpool_market_indicators(days: int = Query(default=30)):
    """VIX, put/call ratio, market-wide indicators."""
    return _json_response(_get_eulerpool().market_indicators(days).to_dict(orient="records"))

@app.get("/v1/eulerpool/alternative/gov-contracts/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_gov_contracts(ticker: str, limit: int = Query(default=100)):
    """Government contracts awarded to a company."""
    return _json_response(_get_eulerpool().government_contracts(ticker, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/alternative/google-trends/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_google_trends(ticker: str, limit: int = Query(default=90)):
    """Google search interest over time."""
    return _json_response(_get_eulerpool().google_trends(ticker, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/macro/credit-spreads", dependencies=[Depends(require_client_token)])
def eulerpool_credit_spreads(days: int = Query(default=365)):
    """Credit spread indices (OAS, Baa/Aaa, TED, yield curve)."""
    return _json_response(_get_eulerpool().credit_spreads(days).to_dict(orient="records"))

# ── Short Data ─────────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/short/volume/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_short_volume(identifier: str, limit: int = Query(default=90)):
    """FINRA daily short volume."""
    return _json_response(_get_eulerpool().short_volume(identifier, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/short/interest/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_short_interest(identifier: str, limit: int = Query(default=24)):
    """FINRA bi-monthly short interest."""
    return _json_response(_get_eulerpool().short_interest(identifier, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/analyst/recommendations/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_recommendations(ticker: str):
    """Buy/hold/sell consensus + price targets per period."""
    return _json_response(_get_eulerpool().analyst_recommendations(ticker).to_dict(orient="records"))

# ── Ownership & Insider ────────────────────────────────────────────────────

@app.get("/v1/eulerpool/ownership/institutional/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_inst_ownership(identifier: str):
    """13-F institutional holders."""
    return _json_response(_get_eulerpool().institutional_ownership(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/ownership/fund/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_fund_ownership(identifier: str):
    """Mutual fund holders."""
    return _json_response(_get_eulerpool().fund_ownership(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/ownership/insider/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_insider_trades(identifier: str):
    """Insider trading activity."""
    return _json_response(_get_eulerpool().insider_trades(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/fundamentals/key-figures/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_key_figures(identifier: str):
    """Condensed key-figure panel."""
    return _json_response(_get_eulerpool().key_figures(identifier))
# ── Equity Extended ─────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/equity/stock-splits/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_stock_splits(identifier: str):
    """Historical stock split events."""
    return _json_response(_get_eulerpool().stock_splits(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/equity/shares-outstanding/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_shares_outstanding(identifier: str):
    """Historical shares outstanding."""
    return _json_response(_get_eulerpool().shares_outstanding_history(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/equity/market-cap/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_market_cap(identifier: str, range_: str = Query(default="1y", alias="range")):
    """Historical market capitalization."""
    return _json_response(_get_eulerpool().market_cap_history(identifier, range_))

@app.get("/v1/eulerpool/equity/employee-count/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_employee_count(identifier: str):
    """Historical employee count."""
    return _json_response(_get_eulerpool().employee_count_history(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/equity/shares-float/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_shares_float(identifier: str):
    """Shares float and short ratio."""
    return _json_response(_get_eulerpool().shares_float(identifier))
@app.get("/v1/eulerpool/equity/growth-metrics/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_growth_metrics(identifier: str):
    """Revenue & earnings growth rates."""
    return _json_response(_get_eulerpool().growth_metrics(identifier))

@app.get("/v1/eulerpool/equity/margins/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_margins(identifier: str):
    """Profit, operating, EBITDA margins."""
    return _json_response(_get_eulerpool().margins(identifier))

@app.get("/v1/eulerpool/equity/revenue-by-region/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_revenue_by_region(identifier: str):
    """Revenue breakdown by geographic region."""
    return _json_response(_get_eulerpool().revenue_by_region(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/equity/business-segments/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_business_segments(identifier: str):
    """Revenue breakdown by business segment."""
    return _json_response(_get_eulerpool().business_segments(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/equity/segment-history/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_segment_history(identifier: str):
    """Historical segment revenue data."""
    return _json_response(_get_eulerpool().segment_history(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/equity/valuation-history/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_valuation_history(identifier: str):
    """Trailing and forward valuation multiples over time."""
    return _json_response(_get_eulerpool().valuation_history(identifier))

@app.get("/v1/eulerpool/equity/stock-returns/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_stock_returns(identifier: str, years: int = Query(default=10)):
    """Historical total stock returns (1/3/5/10y)."""
    return _json_response(_get_eulerpool().stock_returns(identifier, years))

# ── Analyst Extended ───────────────────────────────────────────────────────

@app.get("/v1/eulerpool/analyst/forecast/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_analyst_forecast(identifier: str):
    """Detailed analyst forecasts (revenue, EPS, EBITDA)."""
    return _json_response(_get_eulerpool().analyst_forecast(identifier))

@app.get("/v1/eulerpool/analyst/grades/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_analyst_grades(identifier: str, limit: int = Query(default=50)):
    """Latest analyst grades / ratings."""
    return _json_response(_get_eulerpool().analyst_grades(identifier, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/analyst/price-target-history/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_price_target_history(identifier: str):
    """Historical price target changes."""
    return _json_response(_get_eulerpool().price_target_history(identifier).to_dict(orient="records"))

# ── Ownership Extended ─────────────────────────────────────────────────────

@app.get("/v1/eulerpool/ownership/stock/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_stock_ownership(identifier: str):
    """All ownership types aggregated for a stock."""
    return _json_response(_get_eulerpool().stock_ownership(identifier).to_dict(orient="records"))

# ── Fundamentals Extended ────────────────────────────────────────────────────

@app.get("/v1/eulerpool/fundamentals/quarterly-income/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_quarterly_income(identifier: str):
    """Quarterly income statements."""
    return _json_response(_get_eulerpool().quarterly_income_statement(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/fundamentals/quarterly-cashflow/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_quarterly_cashflow(identifier: str):
    """Quarterly cash flow statements."""
    return _json_response(_get_eulerpool().quarterly_cash_flow(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/fundamentals/quarterly-fundamentals/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_quarterly_fundamentals(identifier: str):
    """Quarterly fundamentals (condensed P&L, balance, ratios)."""
    return _json_response(_get_eulerpool().quarterly_fundamentals(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/fundamentals/quality-scores/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_quality_scores(ticker: str):
    """Quality scores (profitability, growth, safety, payout)."""
    return _json_response(_get_eulerpool().quality_scores(ticker))

@app.get("/v1/eulerpool/fundamentals/dividend-safety/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_dividend_safety(ticker: str):
    """Dividend safety score."""
    return _json_response(_get_eulerpool().dividend_safety(ticker))

@app.get("/v1/eulerpool/fundamentals/executives/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_executives(identifier: str):
    """Company executive team."""
    return _json_response(_get_eulerpool().executives(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/fundamentals/peers/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_peers(identifier: str):
    """Peer companies comparison."""
    return _json_response(_get_eulerpool().peers(identifier))

@app.get("/v1/eulerpool/fundamentals/supply-chain/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_supply_chain(identifier: str):
    """Supply chain partners (customers, suppliers)."""
    return _json_response(_get_eulerpool().supply_chain(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/fundamentals/risk-return/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_risk_return(identifier: str, range_: str = Query(default="1y", alias="range")):
    """Risk & return analytics (alpha, beta, sharpe, sortino)."""
    return _json_response(_get_eulerpool().risk_return_analytics(identifier, range_))

@app.get("/v1/eulerpool/fundamentals/correlation/{isin1}/{isin2}", dependencies=[Depends(require_client_token)])
def eulerpool_correlation(isin1: str, isin2: str, range_: str = Query(default="1y", alias="range")):
    """Correlation between two securities."""
    return _json_response(_get_eulerpool().correlation(isin1, isin2, range_))

@app.get("/v1/eulerpool/fundamentals/auto-peers/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_auto_peers(identifier: str):
    """AI-powered peer group identification."""
    return _json_response(_get_eulerpool().auto_peers(identifier))

@app.get("/v1/eulerpool/fundamentals/relative-valuation/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_relative_valuation(identifier: str):
    """Relative valuation vs peers."""
    return _json_response(_get_eulerpool().relative_valuation(identifier))

@app.get("/v1/eulerpool/fundamentals/benchmarking/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_financial_benchmarking(identifier: str):
    """Financial benchmarking vs industry."""
    return _json_response(_get_eulerpool().financial_benchmarking(identifier))
@app.get("/v1/eulerpool/ownership/beneficial/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_beneficial_ownership(identifier: str):
    """Beneficial ownership (>5% holders)."""
    return _json_response(_get_eulerpool().beneficial_ownership(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/ownership/derivative-insider/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_derivative_insider(identifier: str):
    """SEC derivative insider trades."""
    return _json_response(_get_eulerpool().insider_trades_derivatives(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/ownership/eu-insider/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_eu_insider(identifier: str):
    """EU insider trading disclosures."""
    return _json_response(_get_eulerpool().insider_trades_eu(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/ownership/sec-form4/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_sec_form4(identifier: str, limit: int = Query(default=50), days: int = Query(default=365)):
    """SEC Form 4 insider filings."""
    return _json_response(_get_eulerpool().sec_form4(identifier, limit, days).to_dict(orient="records"))

# ── ETF Extended ────────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/etf/sectors/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_etf_sectors(identifier: str):
    """ETF sector allocation."""
    return _json_response(_get_eulerpool().etf_sectors(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/etf/countries/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_etf_countries(identifier: str):
    """ETF country allocation."""
    return _json_response(_get_eulerpool().etf_countries(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/etf/description/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_etf_description(identifier: str, language: str = Query(default="en")):
    """ETF full description."""
    return _json_response(_get_eulerpool().etf_description(identifier, language))

@app.get("/v1/eulerpool/etf/list", dependencies=[Depends(require_client_token)])
def eulerpool_etf_list():
    """List all available ETFs."""
    return _json_response(_get_eulerpool().etf_list())

# ── More Crypto ────────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/crypto/profile/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_crypto_profile(symbol: str):
    """Cryptocurrency profile / metadata."""
    return _json_response(_get_eulerpool().crypto_profile(symbol))

@app.get("/v1/eulerpool/crypto/ohlcv/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_crypto_ohlcv(symbol: str, interval: str = Query(default="1d"), limit: int = Query(default=100)):
    """Crypto OHLCV data."""
    return _json_response(_get_eulerpool().crypto_ohlcv(symbol, interval, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/crypto/derivatives/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_crypto_derivatives(symbol: str):
    """Crypto derivatives data (open interest, funding)."""
    return _json_response(_get_eulerpool().crypto_derivatives(symbol))

@app.get("/v1/eulerpool/crypto/globals", dependencies=[Depends(require_client_token)])
def eulerpool_global_crypto_market(days: int = Query(default=90)):
    """Global crypto market data."""
    return _json_response(_get_eulerpool().global_crypto_market(days))

@app.get("/v1/eulerpool/crypto/stablecoins", dependencies=[Depends(require_client_token)])
def eulerpool_stablecoin_market_caps(days: int = Query(default=30)):
    """Stablecoin market caps."""
    return _json_response(_get_eulerpool().stablecoin_market_caps(days))

@app.get("/v1/eulerpool/crypto/defi-yields", dependencies=[Depends(require_client_token)])
def eulerpool_defi_yields(chain: str | None = Query(None), limit: int = Query(default=50)):
    """DeFi yield rates across protocols."""
    return _json_response(_get_eulerpool().defi_yields(chain, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/crypto/dex-volumes", dependencies=[Depends(require_client_token)])
def eulerpool_dex_volumes():
    """DEX trading volumes by protocol."""
    return _json_response(_get_eulerpool().dex_volumes().to_dict(orient="records"))

@app.get("/v1/eulerpool/crypto/dex-trending-pools", dependencies=[Depends(require_client_token)])
def eulerpool_dex_trending_pools():
    """Trending DEX pools."""
    return _json_response(_get_eulerpool().dex_trending_pools().to_dict(orient="records"))

@app.get("/v1/eulerpool/crypto/dex-new-pools", dependencies=[Depends(require_client_token)])
def eulerpool_dex_new_pools():
    """Newly created DEX pools."""
    return _json_response(_get_eulerpool().dex_new_pools().to_dict(orient="records"))

@app.get("/v1/eulerpool/crypto/dex-network-pools/{network}", dependencies=[Depends(require_client_token)])
def eulerpool_dex_network_pools(network: str = "eth"):
    """DEX pools on a specific network."""
    return _json_response(_get_eulerpool().dex_network_pools(network).to_dict(orient="records"))
# ── More Options ──────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/options/flow", dependencies=[Depends(require_client_token)])
def eulerpool_options_flow(identifier: str | None = Query(None), limit: int = Query(default=100)):
    """Options flow (large/block trades)."""
    return _json_response(_get_eulerpool().options_flow(identifier, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/options/cboe-indices", dependencies=[Depends(require_client_token)])
def eulerpool_cboe_indices(days: int = Query(default=30)):
    """CBOE market volatility indices."""
    return _json_response(_get_eulerpool().cboe_indices(days).to_dict(orient="records"))

# ── More Alternatives ─────────────────────────────────────────────────────

@app.get("/v1/eulerpool/alternative/superinvestor-top-holdings", dependencies=[Depends(require_client_token)])
def eulerpool_superinvestor_top_holdings(limit: int = Query(default=30)):
    """Top holdings across all superinvestors."""
    return _json_response(_get_eulerpool().superinvestor_top_holdings(limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/alternative/superinvestor-recent-activity", dependencies=[Depends(require_client_token)])
def eulerpool_superinvestor_recent_activity(limit: int = Query(default=100)):
    """Recent superinvestor portfolio activity."""
    return _json_response(_get_eulerpool().superinvestor_recent_activity(limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/alternative/stocktwits/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_stocktwits(ticker: str):
    """StockTwits sentiment for a ticker."""
    return _json_response(_get_eulerpool().stocktwits_sentiment(ticker))

@app.get("/v1/eulerpool/alternative/reddit-mentions/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_reddit_mentions(ticker: str, limit: int = Query(default=30)):
    """Reddit mention counts for a ticker."""
    return _json_response(_get_eulerpool().reddit_mentions(ticker, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/alternative/wikipedia-pageviews/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_wikipedia_pageviews(ticker: str, limit: int = Query(default=90)):
    """Wikipedia pageviews for a ticker."""
    return _json_response(_get_eulerpool().wikipedia_pageviews(ticker, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/alternative/press-releases/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_press_releases(ticker: str):
    """Press releases for a company."""
    return _json_response(_get_eulerpool().press_releases(ticker).to_dict(orient="records"))

# ── More Macro ────────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/macro/country-indicators/{country}", dependencies=[Depends(require_client_token)])
def eulerpool_country_indicators(country: str = "US"):
    """All economic indicators for a country."""
    return _json_response(_get_eulerpool().country_indicators(country))

@app.get("/v1/eulerpool/macro/treasury-auctions", dependencies=[Depends(require_client_token)])
def eulerpool_treasury_auctions(days: int = Query(default=90)):
    """US Treasury auction results."""
    return _json_response(_get_eulerpool().treasury_auctions(days).to_dict(orient="records"))

@app.get("/v1/eulerpool/macro/ecb-series-list", dependencies=[Depends(require_client_token)])
def eulerpool_ecb_series_list(category: str | None = Query(None)):
    """ECB statistical series list."""
    return _json_response(_get_eulerpool().ecb_series_list(category).to_dict(orient="records"))

@app.get("/v1/eulerpool/macro/ecb-observations/{series_key}", dependencies=[Depends(require_client_token)])
def eulerpool_ecb_observations(series_key: str, limit: int = Query(default=500)):
    """ECB statistical observations."""
    return _json_response(_get_eulerpool().ecb_observations(series_key, limit))

@app.get("/v1/eulerpool/macro/ecb-exchange-rates", dependencies=[Depends(require_client_token)])
def eulerpool_ecb_exchange_rates(currency: str | None = Query(None)):
    """ECB daily exchange rates."""
    return _json_response(_get_eulerpool().ecb_exchange_rates(currency))

@app.get("/v1/eulerpool/macro/ecb-key-rates", dependencies=[Depends(require_client_token)])
def eulerpool_ecb_key_rates():
    """ECB key interest rates."""
    return _json_response(_get_eulerpool().ecb_key_rates())

# ── More Commodities ──────────────────────────────────────────────────────

@app.get("/v1/eulerpool/commodity/profile/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_commodity_profile(ticker: str):
    """Commodity profile with specifications."""
    return _json_response(_get_eulerpool().commodity_profile(ticker))

@app.get("/v1/eulerpool/commodity/crack-spreads", dependencies=[Depends(require_client_token)])
def eulerpool_crack_spreads(days: int = Query(default=90)):
    """Crack spreads (refining margins)."""
    return _json_response(_get_eulerpool().crack_spreads(days).to_dict(orient="records"))

@app.get("/v1/eulerpool/commodity/ice-swap/{code}", dependencies=[Depends(require_client_token)])
def eulerpool_ice_swap(code: str):
    """ICE Swap Rate data."""
    return _json_response(_get_eulerpool().ice_swap(code).to_dict(orient="records"))

@app.get("/v1/eulerpool/commodity/futures-curve-history/{product}", dependencies=[Depends(require_client_token)])
def eulerpool_futures_curve_history(product: str, days: int = Query(default=90)):
    """Historical futures curve evolution."""
    return _json_response(_get_eulerpool().futures_curve_history(product, days).to_dict(orient="records"))
# ── Search & Screener ─────────────────────────────────────────────────────

@app.get("/v1/eulerpool/search/symbols/{query}", dependencies=[Depends(require_client_token)])
def eulerpool_search_symbols(query: str):
    """Search for symbols / companies."""
    return _json_response(_get_eulerpool().search_symbols(query))

@app.post("/v1/eulerpool/screen/stocks", dependencies=[Depends(require_client_token)])
def eulerpool_screen_stocks(filters: list[dict]):
    """Screen stocks with custom filters."""
    return _json_response(_get_eulerpool().screen_stocks(filters).to_dict(orient="records"))

@app.get("/v1/eulerpool/screen/metadata", dependencies=[Depends(require_client_token)])
def eulerpool_screener_metadata():
    """Available screener filters and options."""
    return _json_response(_get_eulerpool().screener_metadata())

# ── Mutual Funds ──────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/mutual-fund/profile/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_mf_profile(identifier: str):
    """Mutual fund profile / overview."""
    return _json_response(_get_eulerpool().mutual_fund_profile(identifier))

@app.get("/v1/eulerpool/mutual-fund/holdings/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_mf_holdings(symbol: str):
    """Mutual fund top holdings."""
    return _json_response(_get_eulerpool().mutual_fund_holdings(symbol).to_dict(orient="records"))

@app.get("/v1/eulerpool/mutual-fund/sectors/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_mf_sectors(symbol: str):
    """Mutual fund sector allocation."""
    return _json_response(_get_eulerpool().mutual_fund_sectors(symbol).to_dict(orient="records"))
# ── Institutional / 13F ────────────────────────────────────────────────────

@app.get("/v1/eulerpool/institutional/profile/{cik}", dependencies=[Depends(require_client_token)])
def eulerpool_inst_profile(cik: str):
    """Institutional investor (hedge fund) profile."""
    return _json_response(_get_eulerpool().institutional_profile(cik))

@app.get("/v1/eulerpool/institutional/portfolio/{cik}", dependencies=[Depends(require_client_token)])
def eulerpool_inst_portfolio(cik: str):
    """Institutional investor full 13F portfolio holdings."""
    return _json_response(_get_eulerpool().institutional_portfolio(cik).to_dict(orient="records"))

@app.get("/v1/eulerpool/institutional/13f-holders/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_13f_holders(ticker: str):
    """All 13F filers holding a stock."""
    return _json_response(_get_eulerpool().sec_13f_holders(ticker).to_dict(orient="records"))

@app.get("/v1/eulerpool/institutional/top-13f-filers", dependencies=[Depends(require_client_token)])
def eulerpool_top_13f_filers(limit: int = Query(default=50)):
    """Largest 13F filers by AUM."""
    return _json_response(_get_eulerpool().top_13f_filers(limit).to_dict(orient="records"))

# ── SEC / XBRL ─────────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/sec/filings/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_sec_filings(identifier: str):
    """Recent SEC filings (10-K, 10-Q, 8-K)."""
    return _json_response(_get_eulerpool().sec_filings(identifier).to_dict(orient="records"))

@app.get("/v1/eulerpool/sec/company-info/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_sec_company_info(ticker: str):
    """SEC EDGAR metadata (CIK, SIC, fiscal year)."""
    return _json_response(_get_eulerpool().sec_company_info(ticker))

@app.get("/v1/eulerpool/sec/xbrl-facts/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_xbrl_facts(ticker: str):
    """All XBRL facts for a company."""
    return _json_response(_get_eulerpool().xbrl_facts(ticker))

@app.get("/v1/eulerpool/sec/xbrl-fact-series/{ticker}/{tag}", dependencies=[Depends(require_client_token)])
def eulerpool_xbrl_fact_series(ticker: str, tag: str):
    """XBRL fact time series for a specific tag."""
    return _json_response(_get_eulerpool().xbrl_fact_series(ticker, tag).to_dict(orient="records"))
# ── Corporate / Events ─────────────────────────────────────────────────────

@app.get("/v1/eulerpool/corporate/ma-deals", dependencies=[Depends(require_client_token)])
def eulerpool_ma_deals(symbol: str | None = Query(None), days: int = Query(default=365)):
    """M&A deals."""
    return _json_response(_get_eulerpool().ma_deals(symbol, days).to_dict(orient="records"))

@app.get("/v1/eulerpool/corporate/ipo-pipeline", dependencies=[Depends(require_client_token)])
def eulerpool_ipo_pipeline(status: str | None = Query(None), limit: int = Query(default=200)):
    """IPO pipeline (filed, priced, withdrawn)."""
    return _json_response(_get_eulerpool().ipo_pipeline(status, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/corporate/events/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_corporate_events(ticker: str, limit: int = Query(default=50)):
    """Corporate events calendar for a company."""
    return _json_response(_get_eulerpool().corporate_events(ticker, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/corporate/forward-dividend-calendar", dependencies=[Depends(require_client_token)])
def eulerpool_forward_dividend_calendar(days: int = Query(default=60), limit: int = Query(default=100)):
    """Upcoming dividend dates."""
    return _json_response(_get_eulerpool().forward_dividend_calendar(days, limit).to_dict(orient="records"))

@app.get("/v1/eulerpool/corporate/gov-contract-stats/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_gov_contract_stats(ticker: str):
    """Government contract statistics."""
    return _json_response(_get_eulerpool().government_contract_stats(ticker).to_dict(orient="records"))

@app.get("/v1/eulerpool/corporate/fund-disclosure/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_fund_disclosure(symbol: str):
    """Fund manager disclosures."""
    return _json_response(_get_eulerpool().fund_disclosure(symbol).to_dict(orient="records"))

@app.get("/v1/eulerpool/corporate/investment-themes", dependencies=[Depends(require_client_token)])
def eulerpool_investment_themes():
    """Investment themes and cohorts."""
    return _json_response(_get_eulerpool().investment_themes().to_dict(orient="records"))

# ── Logo Extended ──────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/logo/isin/{code}", dependencies=[Depends(require_client_token)])
def eulerpool_logo_isin(code: str, size: int = Query(default=128)):
    """Company logo by ISIN, returns PNG bytes."""
    img = _get_eulerpool().logo_by_isin(code, size)
    if not img:
        raise HTTPException(status_code=404, detail="logo not found")
    return Response(img, media_type="image/png")

# ── Ticker Trends ─────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/trends/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_ticker_trends(symbol: str = "all"):
    """Ticker trends and current values."""
# ── OHLCV Quotes (Eulerpool variant) ────────────────────────────────────────

@app.get("/v1/eulerpool/equity/quotes/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_equity_quotes(identifier: str, start: str = Query(default=None), end: str = Query(default=None)):
    """Eulerpool equity OHLCV quotes."""
    return _json_response(_get_eulerpool().equity_quotes(identifier, start, end).to_dict(orient="records"))

@app.get("/v1/eulerpool/crypto/quotes/{symbol}", dependencies=[Depends(require_client_token)])
def eulerpool_crypto_quotes(symbol: str, start: str = Query(default=None), end: str = Query(default=None)):
    """Eulerpool crypto OHLCV quotes."""
    return _json_response(_get_eulerpool().crypto_quotes(symbol, start, end).to_dict(orient="records"))

@app.get("/v1/eulerpool/etf/quotes/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_etf_quotes(identifier: str, start: str = Query(default=None), end: str = Query(default=None)):
    """Eulerpool ETF OHLCV quotes."""
    return _json_response(_get_eulerpool().etf_quotes(identifier, start, end).to_dict(orient="records"))

@app.get("/v1/eulerpool/commodity/quotes/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_commodity_quotes(ticker: str, start: str = Query(default=None), end: str = Query(default=None)):
    """Eulerpool commodity OHLCV quotes."""
    return _json_response(_get_eulerpool().commodity_quotes(ticker, start, end).to_dict(orient="records"))

@app.get("/v1/eulerpool/market/intraday-quotes/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_intraday_quotes(identifier: str, exchange: str | None = Query(None)):
    """Intraday quotes for a symbol from an exchange."""
    return _json_response(_get_eulerpool().intraday_quotes(identifier, exchange).to_dict(orient="records"))

@app.get("/v1/eulerpool/market/exchanges", dependencies=[Depends(require_client_token)])
def eulerpool_exchanges():
    """All exchanges with their details."""
    return _json_response(_get_eulerpool().exchanges().to_dict(orient="records"))

@app.get("/v1/eulerpool/market/holidays", dependencies=[Depends(require_client_token)])
def eulerpool_market_holidays():
    """Market holiday calendars by exchange."""
    return _json_response(_get_eulerpool().market_holidays().to_dict(orient="records"))

@app.get("/v1/eulerpool/market/sector-performance", dependencies=[Depends(require_client_token)])
def eulerpool_sector_performance(period: str = Query(default="1d"), days: int = Query(default=30)):
    """Sector performance over time."""
    return _json_response(_get_eulerpool().sector_performance(period, days).to_dict(orient="records"))

# ── Dividends by Fiscal Year ───────────────────────────────────────────────

@app.get("/v1/eulerpool/dividends/fiscal-year/{identifier}", dependencies=[Depends(require_client_token)])
def eulerpool_dividends_fiscal_year(identifier: str):
    """Dividends aggregated by fiscal year."""
    return _json_response(_get_eulerpool().dividends_by_fiscal_year(identifier).to_dict(orient="records"))

# ── Transcripts Extended ────────────────────────────────────────────────────

@app.get("/v1/eulerpool/transcripts/call/{identifier}/{call_id}", dependencies=[Depends(require_client_token)])
def eulerpool_transcript_call(identifier: str, call_id: int):
    """Full earnings call transcript."""
    return _json_response(_get_eulerpool().earnings_call_transcript(identifier, call_id))

@app.get("/v1/eulerpool/transcripts/call-nlp/{identifier}/{call_id}", dependencies=[Depends(require_client_token)])
def eulerpool_transcript_call_nlp(identifier: str, call_id: int):
    """Earnings call NLP analysis (sentiment, topics, tone)."""
    return _json_response(_get_eulerpool().earnings_call_nlp(identifier, call_id))

# ── FRED Series List ────────────────────────────────────────────────────────

@app.get("/v1/eulerpool/macro/fred-series", dependencies=[Depends(require_client_token)])
def eulerpool_fred_series(category: str | None = Query(None)):
    """List all available FRED series."""
    return _json_response(_get_eulerpool().fred_series_list(category).to_dict(orient="records"))

# ── SEC Fail-to-Deliver ─────────────────────────────────────────────────────

@app.get("/v1/eulerpool/sec/fail-to-deliver/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_fail_to_deliver(ticker: str, days: int = Query(default=90)):
    """SEC fail-to-deliver data."""
    return _json_response(_get_eulerpool().sec_fail_to_deliver(ticker, days).to_dict(orient="records"))

# ── Patent Statistics ───────────────────────────────────────────────────────

@app.get("/v1/eulerpool/alternative/patent-stats/{ticker}", dependencies=[Depends(require_client_token)])
def eulerpool_patent_stats(ticker: str):
    """Patent statistics for a company."""
    return _json_response(_get_eulerpool().patent_statistics(ticker).to_dict(orient="records"))
    return _json_response(_get_eulerpool().ticker_trends(symbol))