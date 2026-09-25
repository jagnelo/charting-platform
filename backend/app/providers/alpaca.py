"""
Alpaca Markets data provider.

Capabilities:
  - PriceHistoryProvider  : US equity + crypto OHLCV (all timeframes)
  - LatestPriceProvider   : current price via latest bar
  - EventProvider         : corporate actions (splits, dividends)
  - DiscoveryProvider     : US equity + crypto universe

Auth: ALPACA_API_KEY + ALPACA_SECRET_KEY (free account sufficient).
Data feed: ALPACA_DATA_FEED = "iex" (free) | "sip" (paid consolidated).

Rate limits (free IEX feed): 200 req/min on data endpoints.
Assets endpoint: single call returns all tradeable symbols (~9 000 equities).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import ceil
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings
from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import (
    IdentifierRecord,
    InstrumentEventPage,
    InstrumentEventRecord,
    InstrumentProfile,
    ListingRecord,
    ProviderAccountUsage,
    ProviderAccountUsageDimension,
)
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderResponseError,
    provider_response_headers,
    redact_provider_message,
)
from app.providers.telemetry import observe_response

logger = logging.getLogger(__name__)

_DATA_BASE = "https://data.alpaca.markets/v2"
_DATA_V1_BASE = "https://data.alpaca.markets/v1"
_DEFAULT_TRADING_BASE = "https://paper-api.alpaca.markets/v2"
_ALLOWED_TRADING_BASES = {
    "https://paper-api.alpaca.markets/v2",
    "https://api.alpaca.markets/v2",
}
_PAGE_SIZE = 250

_TF_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "1Min",
    Timeframe.M5: "5Min",
    Timeframe.M15: "15Min",
    Timeframe.M30: "30Min",
    Timeframe.H1: "1Hour",
    Timeframe.H2: "2Hour",
    Timeframe.H4: "4Hour",
    Timeframe.H12: "12Hour",
    Timeframe.D1: "1Day",
    Timeframe.W1: "1Week",
    Timeframe.MN: "1Month",
}

_TF_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H2: 7200,
    Timeframe.H4: 14400,
    Timeframe.H12: 43200,
    Timeframe.D1: 86400,
    Timeframe.W1: 604800,
    Timeframe.MN: 2592000,
}

_BARS_PAGE_SIZE = 1000

# Module-level asset cache: keyed by asset_class string
_asset_cache: dict[str, list[dict]] = {}
_asset_cache_ts: float = 0.0
_ASSET_CACHE_TTL = 3600 * 4  # 4 hours


class AlpacaProvider:
    name = "alpaca"
    base_url = "https://data.alpaca.markets"
    description = (
        "Alpaca Markets free data API — US equity + crypto OHLCV, "
        "corporate actions (splits/dividends), universe discovery"
    )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": settings.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": settings.ALPACA_SECRET_KEY,
        }

    def _ok(self) -> bool:
        has_creds = bool(settings.ALPACA_API_KEY and settings.ALPACA_SECRET_KEY)
        if not has_creds:
            logger.warning(
                "alpaca: ALPACA_API_KEY / ALPACA_SECRET_KEY are not set — "
                "skipping this call and falling back to next provider. "
                "Set these in .env.dev to enable Alpaca."
            )
        return has_creds

    def _require_configured(self) -> None:
        """Fail explicitly when the account credentials are absent.

        An empty provider result is a valid no-observation outcome, not proof
        that a credentialed adapter was unavailable.  Keeping this distinction
        lets the runtime record configuration failures and select a fallback
        without silently treating an unconfigured Alpaca account as empty
        market data.
        """

        if not self._ok():
            raise ProviderNotConfiguredError(
                "alpaca requires ALPACA_API_KEY and ALPACA_SECRET_KEY"
            )

    def fetch_account_usage(self) -> ProviderAccountUsage | None:
        """Observe Alpaca's native market-data request-window headers.

        Alpaca does not expose a separate account-usage endpoint.  A bounded
        latest-bar request is therefore used solely as a native usage
        observation.  The response must include the provider's exact limit,
        remaining count, and a valid epoch reset header; missing or malformed
        headers fail closed.  The native reset is integer-second evidence and
        may equal or slightly precede the client observation when transport
        crosses that boundary.  The reviewed Alpaca rolling contract admits
        only its bounded skew; the configured policy still decides whether the
        observed pool may be used for ordinary routing.
        """

        self._require_configured()
        url = f"{_DATA_BASE}/stocks/bars/latest"
        params = {"symbols": "AAPL", "feed": settings.ALPACA_DATA_FEED}
        # Capture the observation instant before transport. Alpaca's native
        # reset header is retained as an observation even when it denotes the
        # current/previous window boundary rather than a future timestamp;
        # the quota coordinator applies the reviewed Alpaca skew allowance and
        # keeps ordinary routing fail-closed for anything older.
        observed_at = datetime.now(UTC)
        try:
            response = httpx.get(url, params=params, headers=self._headers(), timeout=30)
            observe_response(response)
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, "Alpaca account-usage transport failure") from exc

        headers = provider_response_headers(response)
        try:
            raw_payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(
                self.name, "Alpaca returned invalid account-usage JSON"
            ) from exc
        if not isinstance(raw_payload, dict):
            raise ProviderResponseError(
                self.name, "Alpaca returned an invalid account-usage payload"
            )
        try:
            limit = int(headers["x-ratelimit-limit"])
            remaining = int(headers["x-ratelimit-remaining"])
            reset_epoch = int(headers["x-ratelimit-reset"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderResponseError(
                self.name,
                "Alpaca omitted its native limit/remaining/reset headers",
            ) from exc

        try:
            reset_at = datetime.fromtimestamp(reset_epoch, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise ProviderResponseError(
                self.name, "Alpaca returned an invalid native reset timestamp"
            ) from exc
        if (
            limit <= 0
            or remaining < 0
            or remaining > limit
            or reset_epoch <= 0
        ):
            raise ProviderResponseError(
                self.name, "Alpaca returned invalid native request-window counters"
            )

        dimension = ProviderAccountUsageDimension(
            name="market_data_requests_per_minute",
            unit="requests",
            limit=limit,
            remaining=remaining,
            consumed=limit - remaining,
            reset_at=reset_at,
        )
        return ProviderAccountUsage(
            provider=self.name,
            observed_at=observed_at,
            unit="requests",
            limit=limit,
            remaining=remaining,
            consumed=limit - remaining,
            reset_at=reset_at,
            account_plan="market_data_headers",
            dimensions=(dimension,),
            raw_payload=raw_payload,
            response_headers=headers,
        )

    # ── Price History ─────────────────────────────────────────────────────────

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        *,
        adjusted: bool = True,
        instrument_id: int | None = None,
        data_source_id: int | None = None,
    ) -> list[OHLCVBar]:
        self._require_configured()
        tf_str = _TF_MAP.get(timeframe)
        if tf_str is None:
            raise ProviderResponseError(
                self.name, f"Alpaca does not support timeframe {timeframe.value}"
            )

        is_crypto = _is_crypto(symbol)
        alpaca_sym = _to_alpaca_crypto(symbol) if is_crypto else symbol
        url = f"{_DATA_BASE}/{'crypto' if is_crypto else 'stocks'}/bars"
        params: dict[str, Any] = {
            "symbols": alpaca_sym,
            "timeframe": tf_str,
            "start": _fmt_dt(start),
            "end": _fmt_dt(end),
            "limit": 1000,
            "adjustment": "all" if adjusted else "raw",
        }
        if not is_crypto:
            params["feed"] = settings.ALPACA_DATA_FEED

        bars: list[OHLCVBar] = []
        page_token: str | None = None
        seen_page_tokens: set[str] = set()

        while True:
            if page_token:
                params["page_token"] = page_token
            try:
                r = httpx.get(url, params=params, headers=self._headers(), timeout=30)
                observe_response(r)
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, dict):
                    raise ProviderResponseError(self.name, "Alpaca returned an invalid JSON object")
            except httpx.HTTPStatusError:
                # Let provider_runtime convert 429/418 into a typed,
                # reset-aware capacity failure instead of returning partial
                # bars as if the provider had no observations.
                raise
            except httpx.RequestError as exc:
                raise ProviderResponseError(self.name, str(exc)) from exc
            except (TypeError, ValueError) as exc:
                raise ProviderResponseError(self.name, "Alpaca returned invalid JSON") from exc

            bars_payload = data.get("bars") or {}
            if not isinstance(bars_payload, dict):
                raise ProviderResponseError(self.name, "Alpaca returned an invalid bars object")
            raw_rows = bars_payload.get(alpaca_sym, [])
            if raw_rows is None:
                raise ProviderResponseError(self.name, "Alpaca returned null bars for the requested symbol")
            if not isinstance(raw_rows, list):
                raise ProviderResponseError(self.name, "Alpaca returned an invalid bars array")
            for b in raw_rows:
                if not isinstance(b, dict):
                    raise ProviderResponseError(self.name, "Alpaca returned a malformed bar row")
                if any(field not in b for field in ("t", "o", "h", "l", "c")):
                    raise ProviderResponseError(self.name, "Alpaca returned an incomplete bar row")
                try:
                    ts = datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
                    _require_finite_number(b["o"])
                    _require_finite_number(b["h"])
                    _require_finite_number(b["l"])
                    _require_finite_number(b["c"])
                    if b.get("v") is not None:
                        _require_finite_number(b["v"])
                    if b.get("vw") is not None:
                        _require_finite_number(b["vw"])
                    bars.append(
                        OHLCVBar(
                            instrument_id=instrument_id,
                            data_source_id=data_source_id,
                            timeframe=timeframe,
                            ts=ts,
                            open=b["o"],
                            high=b["h"],
                            low=b["l"],
                            close=b["c"],
                            volume=b.get("v"),
                            vwap=b.get("vw"),
                            is_adjusted=adjusted,
                            adjustment_basis=(
                                "provider_adjusted" if adjusted else "raw"
                            ),
                            adjustment_version=("alpaca-all" if adjusted else "provider-native"),
                            provenance={
                                "provider": self.name,
                                "endpoint": url,
                                "provider_symbol": alpaca_sym,
                                "feed": params.get("feed"),
                                "adjustment": params["adjustment"],
                                "provider_payload": b,
                            },
                        )
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ProviderResponseError(self.name, "Alpaca returned an invalid bar row") from exc

            page_token = data.get("next_page_token")
            if page_token is not None and not isinstance(page_token, str):
                raise ProviderResponseError(self.name, "Alpaca returned an invalid pagination token")
            if not page_token:
                break
            if page_token in seen_page_tokens:
                raise ProviderResponseError(
                    self.name, "Alpaca returned a repeated pagination token"
                )
            seen_page_tokens.add(page_token)

        return bars

    def fetch_latest_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int,
        *,
        adjusted: bool = True,
        instrument_id: int | None = None,
        data_source_id: int | None = None,
    ) -> list[OHLCVBar]:
        start = self.latest_window_start(timeframe, limit)
        bars = self.fetch_ohlcv(
            symbol,
            timeframe,
            start,
            datetime.now(UTC),
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
        )
        return bars[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        seconds = _TF_SECONDS.get(timeframe)
        if seconds is None:
            raise ProviderResponseError(
                self.name, f"Alpaca does not support timeframe {timeframe.value}"
            )
        lookback = timedelta(seconds=seconds * limit * 1.4 + 86400)
        return datetime.now(UTC) - lookback

    # ── Latest Price ──────────────────────────────────────────────────────────

    def get_current_price(self, symbol: str) -> float | None:
        self._require_configured()
        is_crypto = _is_crypto(symbol)
        alpaca_sym = _to_alpaca_crypto(symbol) if is_crypto else symbol
        url = f"{_DATA_BASE}/{'crypto' if is_crypto else 'stocks'}/bars/latest"
        params: dict[str, Any] = {"symbols": alpaca_sym}
        if not is_crypto:
            params["feed"] = settings.ALPACA_DATA_FEED
        try:
            r = httpx.get(url, params=params, headers=self._headers(), timeout=10)
            observe_response(r)
            r.raise_for_status()
            payload = r.json()
            if not isinstance(payload, dict):
                raise ProviderResponseError(self.name, "Alpaca returned an invalid JSON object")
            bars_payload = payload.get("bars") or {}
            if not isinstance(bars_payload, dict):
                raise ProviderResponseError(self.name, "Alpaca returned an invalid bars object")
            bar = bars_payload.get(alpaca_sym)
            if bar is None:
                return None
            if not isinstance(bar, dict) or "c" not in bar:
                raise ProviderResponseError(self.name, "Alpaca returned an invalid latest bar")
            _require_finite_number(bar["c"])
            return float(bar["c"])
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "Alpaca returned invalid JSON") from exc
        except KeyError as exc:
            logger.debug(
                "alpaca get_current_price %s: %s", symbol, redact_provider_message(exc)[:1000]
            )
            return None

    # ── Instrument Metadata ─────────────────────────────────────────────────

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        """Return Alpaca's authenticated asset metadata for one symbol.

        The trading API's asset object is an instrument/listing observation,
        not a claim that Alpaca's UUID is a cross-provider canonical identity.
        We therefore retain the provider asset id as an explicit identifier and
        preserve the complete provider payload for later FIGI/CIK enrichment.
        A documented 404 is treated as an unknown symbol; malformed successful
        responses remain typed errors rather than being converted to an empty
        result.
        """

        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            return None
        self._require_configured()
        lookup_symbol = (
            _to_alpaca_crypto(normalized_symbol)
            if _is_crypto(normalized_symbol)
            else normalized_symbol
        )
        url = f"{_trading_base_url()}/assets/{quote(lookup_symbol, safe='._-')}"
        try:
            response = httpx.get(url, headers=self._headers(), timeout=20)
            observe_response(response)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "Alpaca returned invalid asset JSON") from exc

        if not isinstance(payload, dict):
            raise ProviderResponseError(self.name, "Alpaca returned an invalid asset object")
        provider_symbol = str(payload.get("symbol") or "").strip().upper()
        if not provider_symbol:
            raise ProviderResponseError(self.name, "Alpaca asset response omitted symbol")
        if provider_symbol != lookup_symbol.upper():
            raise ProviderResponseError(
                self.name,
                "Alpaca asset response returned a different symbol than requested",
            )
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ProviderResponseError(self.name, "Alpaca asset response omitted name")

        asset_class = str(payload.get("class") or payload.get("asset_class") or "").strip()
        quote_type = "CRYPTOCURRENCY" if asset_class == "crypto" else "EQUITY"
        exchange = str(payload.get("exchange") or "").strip() or None
        currency = str(payload.get("currency") or "").strip().upper() or None
        asset_id = str(payload.get("id") or "").strip()
        identifiers = (
            [
                IdentifierRecord(
                    identifier_type="ALPACA_ASSET_ID",
                    identifier_value=asset_id,
                    source=self.name,
                )
            ]
            if asset_id
            else []
        )
        listing = ListingRecord(
            provider_symbol=provider_symbol,
            exchange_code=exchange,
            currency=currency,
            provider_instrument_type=asset_class or None,
            is_primary=True,
            known_at=datetime.now(UTC),
            extra_data={
                key: payload[key]
                for key in (
                    "status",
                    "tradable",
                    "marginable",
                    "shortable",
                    "easy_to_borrow",
                    "fractionable",
                )
                if key in payload
            },
        )
        extra = {
            key: payload[key]
            for key in (
                "id",
                "class",
                "status",
                "tradable",
                "marginable",
                "shortable",
                "easy_to_borrow",
                "fractionable",
                "maintenance_margin_requirement",
                "attributes",
                "min_order_size",
                "min_trade_increment",
                "price_increment",
            )
            if key in payload
        }
        return InstrumentProfile(
            provider=self.name,
            symbol=normalized_symbol,
            canonical_symbol=normalized_symbol,
            name=name,
            currency=currency,
            quote_type=quote_type,
            exchange=exchange,
            identifiers=identifiers,
            listings=[listing],
            raw_payload=dict(payload),
            extra=extra,
        )

    # ── Corporate Actions (Events) ────────────────────────────────────────────

    def fetch_instrument_events(self, symbol: str) -> list[InstrumentEventRecord]:
        """Fetch the complete available corporate-action history.

        This compatibility method intentionally follows every cursor.  The
        durable service uses ``fetch_instrument_events_page`` to pause and
        resume between jobs, but a direct provider call must never silently
        truncate a result set because of a local page budget.
        """

        self._require_configured()
        events: list[InstrumentEventRecord] = []
        page_token: str | None = None
        seen_page_tokens: set[str] = set()
        while True:
            page = self.fetch_instrument_events_page(symbol, page_token)
            events.extend(page.events)
            next_token = page.next_page_token
            if next_token is None or next_token == "":
                break
            if not isinstance(next_token, str) or next_token == page_token:
                raise ProviderResponseError(self.name, "Alpaca returned an invalid corporate-actions pagination token")
            if next_token in seen_page_tokens:
                raise ProviderResponseError(
                    self.name,
                    "Alpaca returned a repeated corporate-actions pagination token",
                )
            seen_page_tokens.add(next_token)
            page_token = next_token

        return events

    def fetch_instrument_events_page(
        self,
        symbol: str,
        page_token: str | None = None,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> InstrumentEventPage:
        """Fetch exactly one complete corporate-action page.

        The returned raw envelope and continuation token are persisted by the
        ingestion service.  A worker may therefore stop after this request and
        continue later without refetching earlier pages.
        """

        self._require_configured()
        fetched = datetime.now(UTC)
        params: dict[str, Any] = {
            "symbols": symbol,
            # Request every corporate-action family documented by Alpaca. The
            # normalized event rows remain additive; the raw page is retained
            # even when a future family needs a new canonical model.
            "types": (
                "forward_split,reverse_split,unit_split,cash_dividend,stock_dividend,"
                "spin_off,cash_merger,stock_merger,stock_and_cash_merger,redemption,"
                "name_change,worthless_removal,rights_distribution,partial_call,"
                "reorganization,capital_gains_distribution"
            ),
            "start": start_date
            or str(getattr(settings, "ALPACA_CORPORATE_ACTIONS_START_DATE", "1900-01-01")),
            "end": end_date or (fetched + timedelta(days=90)).strftime("%Y-%m-%d"),
            "limit": 1000,
        }
        if page_token:
            params["page_token"] = page_token
        try:
            response = httpx.get(
                f"{_DATA_V1_BASE}/corporate-actions",
                params=params,
                headers=self._headers(),
                timeout=30,
            )
            observe_response(response)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "Alpaca returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError(self.name, "Alpaca returned an invalid JSON object")
        ca = payload.get("corporate_actions") or {}
        if not isinstance(ca, dict):
            raise ProviderResponseError(self.name, "Alpaca returned an invalid corporate-actions object")
        next_token = payload.get("next_page_token")
        if next_token is not None and not isinstance(next_token, str):
            raise ProviderResponseError(self.name, "Alpaca returned an invalid corporate-actions pagination token")
        return InstrumentEventPage(
            events=_parse_corporate_action_events(ca, symbol, fetched),
            next_page_token=next_token or None,
            request_page_token=page_token,
            raw_payload=payload,
        )

    # ── Universe Discovery ────────────────────────────────────────────────────

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        self._require_configured()
        asset_class = {"EQUITY": "us_equity", "CRYPTOCURRENCY": "crypto"}.get(quote_type)
        if asset_class is None:
            return {"total": 0, "quotes": []}

        assets = _cached_assets(self._headers(), asset_class)
        page = assets[offset : offset + _PAGE_SIZE]
        return {
            "total": len(assets),
            "quotes": [_asset_to_quote(a, quote_type) for a in page],
        }

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY", "CRYPTOCURRENCY"]


def _trading_base_url() -> str:
    """Return the explicitly selected Alpaca paper/live assets host.

    The credentials supplied for this workstream are paper-account keys.  The
    paper and live trading hosts are separate even though both use the same
    authenticated assets route; silently sending paper keys to the live host
    produces a misleading 401 and leaves universe discovery unverified.
    Restricting the setting to Alpaca's documented hosts also prevents a
    malformed deployment value from redirecting credentials elsewhere.
    """

    configured = getattr(settings, "ALPACA_TRADING_BASE_URL", _DEFAULT_TRADING_BASE)
    if not isinstance(configured, str) or not configured.strip():
        configured = _DEFAULT_TRADING_BASE
    normalized = configured.strip().rstrip("/")
    if normalized not in _ALLOWED_TRADING_BASES:
        raise ProviderNotConfiguredError(
            "alpaca requires ALPACA_TRADING_BASE_URL to be the documented paper or live host"
        )
    return normalized


# ── Module-level helpers ──────────────────────────────────────────────────────


def estimate_ohlcv_request_count(
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> int | None:
    """Reserve every conservative page request for an Alpaca bar range.

    The adapter follows ``next_page_token`` with a 1,000-bar page size.  A
    runtime reservation of one request would therefore undercount long-range
    history and could admit work beyond the account's documented 200/minute
    window.  Calendar-time candle counts intentionally overestimate sessions,
    which is safe before provider execution.
    """
    seconds = _TF_SECONDS.get(timeframe)
    if seconds is None or end <= start:
        return None
    candles = max(1, ceil((end - start).total_seconds() / seconds))
    return max(1, (candles + _BARS_PAGE_SIZE - 1) // _BARS_PAGE_SIZE)


def estimate_latest_ohlcv_request_count(timeframe: Timeframe, limit: int) -> int | None:
    """Estimate pages for the exact lookback used by ``fetch_latest_ohlcv``."""
    seconds = _TF_SECONDS.get(timeframe)
    if limit <= 0 or seconds is None:
        return None
    lookback_seconds = seconds * limit * 1.4 + 86400
    candles = max(1, ceil(lookback_seconds / seconds) + 1)
    return max(1, (candles + _BARS_PAGE_SIZE - 1) // _BARS_PAGE_SIZE)


def _is_crypto(symbol: str) -> bool:
    return "/" in symbol or (
        "-" in symbol and symbol.split("-", 1)[1].upper() in ("USD", "USDT", "BTC", "ETH")
    )


def _to_alpaca_crypto(symbol: str) -> str:
    """BTC-USD → BTC/USD (Alpaca crypto format)."""
    return symbol.replace("-", "/", 1) if "-" in symbol else symbol


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _safe_decimal(v: Any) -> Decimal | None:
    try:
        value = Decimal(str(v)) if v is not None else None
        return value if value is not None and value.is_finite() else None
    except Exception:
        return None


def _safe_ratio(new_rate: Any, old_rate: Any) -> Decimal | None:
    try:
        if new_rate is not None and old_rate is not None:
            value = Decimal(str(new_rate)) / Decimal(str(old_rate))
            return value if value.is_finite() else None
    except Exception:
        pass
    return None


def _corporate_action_rows(payload: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """Validate a provider action collection before normalizing its rows."""

    value = payload.get(field)
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ProviderResponseError(
            "alpaca", f"Alpaca returned an invalid {field} collection"
        )
    return value


def _parse_corporate_action_events(
    payload: dict[str, Any], symbol: str, fetched: datetime
) -> list[InstrumentEventRecord]:
    """Normalize currently modeled events without dropping the raw envelope.

    Alpaca supports additional corporate-action families.  Those rows remain
    durably available in the page snapshot even before a dedicated canonical
    event type is added; this parser only creates normalized rows for the
    existing economic-event schema.
    """

    events: list[InstrumentEventRecord] = []
    for split_field, title, key_prefix in (
        ("forward_splits", "Forward Split", "alpaca_fwd_split"),
        ("reverse_splits", "Reverse Split", "alpaca_rev_split"),
    ):
        for row in _corporate_action_rows(payload, split_field):
            dt = _parse_date(row.get("ex_date") or row.get("effective_date") or "")
            if dt is None:
                raise ProviderResponseError("alpaca", f"Alpaca returned a {title.lower()} without a valid date")
            split_ratio = _safe_ratio(row.get("new_rate"), row.get("old_rate"))
            if row.get("new_rate") is not None or row.get("old_rate") is not None:
                if split_ratio is None or split_ratio <= 0:
                    raise ProviderResponseError("alpaca", f"Alpaca returned an invalid {title.lower()} ratio")
            events.append(
                InstrumentEventRecord(
                    event_type=InstrumentEventType.SPLIT,
                    event_time=dt,
                    time_hint=EventTimeHint.UNKNOWN,
                    title=f"{title} {symbol}",
                    source_event_key=f"{key_prefix}_{row.get('id', dt.date())}",
                    fetched_at=fetched,
                    split_ratio=split_ratio,
                    raw_payload=str(row),
                )
            )

    for row in _corporate_action_rows(payload, "cash_dividends"):
        ex_dt = _parse_date(row.get("ex_date") or "")
        pay_dt = _parse_date(row.get("payable_date") or row.get("pay_date") or "")
        amount = _safe_decimal(row.get("rate"))
        if row.get("rate") is not None and amount is None:
            raise ProviderResponseError("alpaca", "Alpaca returned an invalid cash-dividend rate")
        if ex_dt is None and pay_dt is None:
            raise ProviderResponseError("alpaca", "Alpaca returned a cash dividend without a valid date")
        if ex_dt:
            events.append(
                InstrumentEventRecord(
                    event_type=InstrumentEventType.EX_DIVIDEND,
                    event_time=ex_dt,
                    time_hint=EventTimeHint.UNKNOWN,
                    title=f"Ex-Dividend {symbol}",
                    source_event_key=f"alpaca_exdiv_{row.get('id', ex_dt.date())}",
                    fetched_at=fetched,
                    dividend_amount=amount,
                    raw_payload=str(row),
                )
            )
        if pay_dt:
            events.append(
                InstrumentEventRecord(
                    event_type=InstrumentEventType.DIVIDEND,
                    event_time=pay_dt,
                    time_hint=EventTimeHint.UNKNOWN,
                    title=f"Dividend {symbol}",
                    source_event_key=f"alpaca_div_{row.get('id', pay_dt.date())}",
                    fetched_at=fetched,
                    dividend_amount=amount,
                    raw_payload=str(row),
                )
            )
    return events


def _cached_assets(headers: dict, asset_class: str) -> list[dict]:
    global _asset_cache, _asset_cache_ts
    now = time.monotonic()
    if asset_class in _asset_cache and (now - _asset_cache_ts) < _ASSET_CACHE_TTL:
        return _asset_cache[asset_class]
    try:
        r = httpx.get(
            f"{_trading_base_url()}/assets",
            params={"status": "active", "asset_class": asset_class},
            headers=headers,
            timeout=30,
        )
        observe_response(r)
        r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, list):
            raise ProviderResponseError("alpaca", "Alpaca returned an invalid JSON array")
        if any(not isinstance(asset, dict) for asset in payload):
            raise ProviderResponseError("alpaca", "Alpaca returned a malformed asset row")
        assets = [a for a in payload if a.get("tradable")]
        _asset_cache[asset_class] = assets
        _asset_cache_ts = now
        return assets
    except httpx.HTTPStatusError:
        raise
    except httpx.RequestError as exc:
        raise ProviderResponseError("alpaca", str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("alpaca", "Alpaca returned invalid JSON") from exc


def _asset_to_quote(asset: dict, quote_type: str) -> dict[str, Any]:
    symbol = asset.get("symbol", "")
    if quote_type == "CRYPTOCURRENCY" and "/" in symbol:
        symbol = symbol.replace("/", "-", 1)
    return {
        "symbol": symbol,
        "shortName": asset.get("name", ""),
        "displayName": asset.get("name", ""),
        "quoteType": quote_type,
        "exchange": asset.get("exchange", ""),
        "currency": "USD",
    }


def _require_finite_number(value: Any) -> None:
    """Reject booleans, non-numeric values, and non-finite provider numbers."""

    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric market-data value")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ValueError("invalid numeric market-data value") from exc
    if not number.is_finite():
        raise ValueError("non-finite market-data value")
