from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import yfinance as yf

from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import (
    IdentifierRecord,
    InstrumentEventRecord,
    InstrumentProfile,
    ListingRecord,
    OptionContractRecord,
    ProviderSearchResult,
)

logger = logging.getLogger(__name__)

TF_TO_YF: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H2: "2h",
    Timeframe.H4: "4h",
    Timeframe.H12: "1h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1wk",
    Timeframe.MN: "1mo",
}
TF_MAX_LOOKBACK_DAYS: dict[Timeframe, int | None] = {
    Timeframe.M1: 7,
    Timeframe.M5: 60,
    Timeframe.M15: 60,
    Timeframe.M30: 60,
    Timeframe.H1: 730,
    Timeframe.H2: 730,
    Timeframe.H4: 730,
    Timeframe.H12: 730,
    Timeframe.D1: None,
    Timeframe.W1: None,
    Timeframe.MN: None,
}


def _safe_decimal(val: Any) -> Decimal | None:
    try:
        f = float(val)
        if f != f:
            return None
        return Decimal(str(f))
    except (TypeError, ValueError):
        return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "to_dict"):
        try:
            return _jsonable(value.to_dict())
        except Exception:
            return str(value)
    try:
        if value != value:
            return None
    except Exception:
        pass
    if isinstance(value, Decimal):
        return float(value)
    return value


def _normalized_key(value: Any) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _find_by_key(value: Any, key: str, *, depth: int = 0) -> Any:
    if value is None or depth > 4:
        return None
    target = _normalized_key(key)

    if isinstance(value, dict):
        for k, v in value.items():
            if _normalized_key(k) == target:
                return v
        for v in value.values():
            found = _find_by_key(v, key, depth=depth + 1)
            if found is not None:
                return found
        return None

    if hasattr(value, "to_dict"):
        try:
            return _find_by_key(value.to_dict(), key, depth=depth + 1)
        except Exception:
            return None

    return None


def _calendar_value(calendar: Any, key: str) -> Any:
    return _find_by_key(calendar, key)


def _row_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        found = _find_by_key(row, key)
        if found is not None:
            return found
    return None


def _iter_dates(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str) or isinstance(value, datetime) or hasattr(value, "to_pydatetime"):
        return [value]
    if isinstance(value, dict):
        out: list[Any] = []
        for v in value.values():
            out.extend(_iter_dates(v))
        return out
    if hasattr(value, "dropna"):
        try:
            return _iter_dates(list(value.dropna()))
        except Exception:
            pass
    if isinstance(value, list | tuple | set):
        out = []
        for item in value:
            out.extend(_iter_dates(item))
        return out
    return [value]


def _event_time(value: Any) -> tuple[datetime, EventTimeHint] | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif hasattr(value, "to_pydatetime"):
        dt = value.to_pydatetime()
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)

    local_t = dt.time()
    if local_t == time(0, 0):
        hint = EventTimeHint.UNKNOWN
    elif local_t < time(14, 30):
        hint = EventTimeHint.PRE_MARKET
    elif local_t >= time(20, 0):
        hint = EventTimeHint.POST_MARKET
    else:
        hint = EventTimeHint.DURING_MARKET
    return dt, hint


def _payload(row: dict[str, Any]) -> str:
    return json.dumps({k: _jsonable(v) for k, v in row.items()}, sort_keys=True)


def _append_earnings_events(
    symbol: str,
    earnings: Any,
    fetched_at: datetime,
    events: list[InstrumentEventRecord],
) -> tuple[int, int]:
    if earnings is None:
        return 0, 0
    if hasattr(earnings, "empty") and earnings.empty:
        return 0, 0
    if not hasattr(earnings, "iterrows"):
        return 0, 0

    added = 0
    seen = 0
    for idx, row in earnings.iterrows():
        seen += 1
        parsed = _event_time(idx)
        if not parsed:
            parsed = _event_time(_row_value(row.to_dict(), "Earnings Date", "EarningsDate"))
        if not parsed:
            continue

        dt, hint = parsed
        row_dict = row.to_dict()
        eps_est = _safe_decimal(
            _row_value(row_dict, "EPS Estimate", "EPSEstimate", "Earnings Average")
        )
        eps_actual = _safe_decimal(
            _row_value(row_dict, "Reported EPS", "ReportedEPS", "EPS Actual")
        )
        surprise = _safe_decimal(_row_value(row_dict, "Surprise", "EPS Surprise"))
        surprise_pct = _safe_decimal(
            _row_value(row_dict, "Surprise(%)", "Surprise %", "EPSSurprisePct")
        )
        if surprise is None and eps_est is not None and eps_actual is not None:
            surprise = eps_actual - eps_est
        if surprise_pct is None and surprise is not None and eps_est not in (None, 0):
            surprise_pct = surprise / abs(eps_est)
        if surprise_pct is not None and abs(surprise_pct) > 2:
            surprise_pct = surprise_pct / Decimal("100")

        is_estimate = eps_actual is None
        source_event_key = f"earnings:{dt.isoformat()}"
        if any(event.source_event_key == source_event_key for event in events):
            continue
        events.append(
            InstrumentEventRecord(
                event_type=(
                    InstrumentEventType.EARNINGS_ESTIMATE
                    if is_estimate
                    else InstrumentEventType.EARNINGS
                ),
                event_time=dt,
                time_hint=hint,
                title=f"{symbol} Earnings",
                value=eps_est,
                actual=eps_actual,
                eps_estimate=eps_est,
                eps_actual=eps_actual,
                eps_surprise=surprise,
                eps_surprise_pct=surprise_pct,
                source_event_key=source_event_key,
                raw_payload=_payload(row_dict),
                fetched_at=fetched_at,
            )
        )
        added += 1
    return added, seen


class YFinanceProvider:
    name = "yfinance"
    base_url = "https://finance.yahoo.com"
    description = "Yahoo Finance via yfinance"

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        try:
            results = yf.Search(query, max_results=limit)
            quotes = results.quotes if hasattr(results, "quotes") else []
            return [
                ProviderSearchResult(
                    symbol=q.get("symbol", ""),
                    name=q.get("longname") or q.get("shortname", ""),
                    exchange=q.get("exchange", ""),
                    instrument_type=q.get("quoteType", ""),
                )
                for q in quotes
                if q.get("symbol")
            ]
        except Exception as exc:
            logger.error("Ticker search failed for '%s': %s", query, exc)
            return []

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        try:
            info = yf.Ticker(symbol).info or {}
        except Exception as exc:
            logger.error("Failed to get info for %s: %s", symbol, exc)
            return None
        if not info:
            return None

        identifiers = self.fetch_stable_identifiers(symbol)
        return InstrumentProfile(
            provider=self.name,
            symbol=symbol,
            canonical_symbol=symbol,
            name=info.get("longName") or info.get("shortName") or symbol,
            description=info.get("longBusinessSummary"),
            currency=info.get("currency"),
            quote_type=(info.get("quoteType") or "").upper() or None,
            exchange=info.get("exchange"),
            identifiers=identifiers,
            listings=[
                ListingRecord(
                    provider_symbol=symbol,
                    exchange_code=info.get("exchange"),
                    currency=info.get("currency"),
                    provider_instrument_type=(info.get("quoteType") or "").upper() or None,
                    is_primary=True,
                )
            ],
            raw_payload=info,
            extra={
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "country": info.get("country"),
                "website": info.get("website"),
                "market_cap": info.get("marketCap"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "average_volume": info.get("averageVolume") or info.get("averageDailyVolume10Day"),
                "trailing_pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "beta": info.get("beta"),
                "dividend_yield": info.get("dividendYield"),
                "employees": info.get("fullTimeEmployees"),
                "regular_market_price": info.get("regularMarketPrice"),
                "current_price": info.get("currentPrice"),
                "previous_close": info.get("previousClose"),
            },
        )

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
        yf_interval = TF_TO_YF.get(timeframe, "1d")
        try:
            ticker = yf.Ticker(symbol)
            yf_end = (end + timedelta(days=1)).strftime("%Y-%m-%d")
            df = ticker.history(
                start=start.strftime("%Y-%m-%d"),
                end=yf_end,
                interval=yf_interval,
                auto_adjust=adjusted,
                actions=False,
            )
        except Exception as exc:
            logger.error("yfinance fetch failed for %s: %s", symbol, exc)
            return []

        if df is None or df.empty:
            return []

        bars: list[OHLCVBar] = []
        for ts, row in df.iterrows():
            if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            bars.append(
                OHLCVBar(
                    instrument_id=instrument_id or 0,
                    data_source_id=data_source_id or 0,
                    timeframe=timeframe,
                    ts=ts,
                    open=Decimal(str(row["Open"])),
                    high=Decimal(str(row["High"])),
                    low=Decimal(str(row["Low"])),
                    close=Decimal(str(row["Close"])),
                    volume=(
                        Decimal(str(row["Volume"]))
                        if "Volume" in row and pd.notna(row["Volume"])
                        else None
                    ),
                    is_adjusted=adjusted,
                )
            )
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
        return bars[-limit:] if len(bars) > limit else bars

    def get_current_price(self, symbol: str) -> float | None:
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d", interval="1m")
            if data is not None and not data.empty:
                return float(data["Close"].iloc[-1])
            fast_info = ticker.fast_info
            return float(fast_info.last_price) if hasattr(fast_info, "last_price") else None
        except Exception as exc:
            logger.error("Failed to get price for %s: %s", symbol, exc)
            return None

    def fetch_instrument_events(self, symbol: str) -> list[InstrumentEventRecord]:
        ticker = yf.Ticker(symbol)
        fetched_at = datetime.now(UTC)
        events: list[InstrumentEventRecord] = []

        try:
            cal = ticker.calendar
            earnings_date = _calendar_value(cal, "Earnings Date")
            for d in _iter_dates(earnings_date):
                parsed = _event_time(d)
                if not parsed:
                    continue
                dt, hint = parsed
                eps_est = _safe_decimal(_calendar_value(cal, "Earnings Average"))
                events.append(
                    InstrumentEventRecord(
                        event_type=InstrumentEventType.EARNINGS_ESTIMATE,
                        event_time=dt,
                        time_hint=hint,
                        title=f"{symbol} Earnings (estimated)",
                        value=eps_est,
                        eps_estimate=eps_est,
                        source_event_key=f"earnings:{dt.isoformat()}",
                        raw_payload=_payload(cal if isinstance(cal, dict) else {"calendar": cal}),
                        fetched_at=fetched_at,
                    )
                )

            ex_div = _calendar_value(cal, "Ex-Dividend Date")
            for d in _iter_dates(ex_div):
                parsed = _event_time(d)
                if parsed:
                    dt, hint = parsed
                    amount = _safe_decimal(_calendar_value(cal, "Dividend Amount"))
                    events.append(
                        InstrumentEventRecord(
                            event_type=InstrumentEventType.EX_DIVIDEND,
                            event_time=dt,
                            time_hint=hint,
                            title=f"{symbol} Ex-Dividend",
                            value=amount,
                            dividend_amount=amount,
                            source_event_key=f"ex_dividend:{dt.date().isoformat()}",
                            raw_payload=_payload(
                                cal if isinstance(cal, dict) else {"calendar": cal}
                            ),
                            fetched_at=fetched_at,
                        )
                    )

            div_date = _calendar_value(cal, "Dividend Date")
            for d in _iter_dates(div_date):
                parsed = _event_time(d)
                if parsed:
                    dt, hint = parsed
                    amount = _safe_decimal(_calendar_value(cal, "Dividend Amount"))
                    events.append(
                        InstrumentEventRecord(
                            event_type=InstrumentEventType.DIVIDEND,
                            event_time=dt,
                            time_hint=hint,
                            title=f"{symbol} Dividend",
                            value=amount,
                            actual=amount,
                            dividend_amount=amount,
                            source_event_key=f"dividend:{dt.date().isoformat()}",
                            raw_payload=_payload(
                                cal if isinstance(cal, dict) else {"calendar": cal}
                            ),
                            fetched_at=fetched_at,
                        )
                    )
        except Exception as exc:
            logger.debug("yfinance calendar fetch failed for %s: %s", symbol, exc)

        try:
            get_earnings_dates = getattr(ticker, "get_earnings_dates", None)
            if callable(get_earnings_dates):
                limit = 100
                for offset in range(0, 400, limit):
                    try:
                        earnings_page = get_earnings_dates(limit=limit, offset=offset)
                    except TypeError:
                        earnings_page = get_earnings_dates()
                    added, seen = _append_earnings_events(symbol, earnings_page, fetched_at, events)
                    if seen < limit or added == 0:
                        break
        except Exception as exc:
            logger.debug("yfinance get_earnings_dates fetch failed for %s: %s", symbol, exc)

        try:
            earnings = ticker.earnings_dates
            _append_earnings_events(symbol, earnings, fetched_at, events)
        except Exception as exc:
            logger.debug("yfinance earnings_dates fetch failed for %s: %s", symbol, exc)

        try:
            divs = ticker.dividends
            if divs is not None and not divs.empty:
                for idx, amount_raw in divs.items():
                    parsed = _event_time(idx)
                    if parsed:
                        dt, hint = parsed
                        amount = _safe_decimal(amount_raw)
                        events.append(
                            InstrumentEventRecord(
                                event_type=InstrumentEventType.DIVIDEND,
                                event_time=dt,
                                time_hint=hint,
                                title=f"{symbol} Dividend",
                                value=amount,
                                actual=amount,
                                dividend_amount=amount,
                                source_event_key=f"dividend:{dt.date().isoformat()}",
                                raw_payload=_payload({"amount": amount}),
                                fetched_at=fetched_at,
                            )
                        )
        except Exception as exc:
            logger.debug("yfinance dividends fetch failed for %s: %s", symbol, exc)

        try:
            splits = ticker.splits
            if splits is not None and not splits.empty:
                for idx, ratio_raw in splits.items():
                    parsed = _event_time(idx)
                    if not parsed:
                        continue
                    dt, hint = parsed
                    ratio = _safe_decimal(ratio_raw)
                    events.append(
                        InstrumentEventRecord(
                            event_type=InstrumentEventType.SPLIT,
                            event_time=dt,
                            time_hint=hint,
                            title=f"{symbol} Stock Split",
                            value=ratio,
                            actual=ratio,
                            split_ratio=ratio,
                            source_event_key=f"split:{dt.date().isoformat()}",
                            raw_payload=_payload({"ratio": ratio}),
                            fetched_at=fetched_at,
                        )
                    )
        except Exception as exc:
            logger.debug("yfinance splits fetch failed for %s: %s", symbol, exc)

        deduped: dict[str, InstrumentEventRecord] = {}
        for event in events:
            deduped[event.source_event_key] = event
        return list(deduped.values())

    def fetch_stable_identifiers(self, symbol: str) -> list[IdentifierRecord]:
        identifiers: list[IdentifierRecord] = []
        try:
            value = yf.Ticker(symbol).isin
        except Exception as exc:
            logger.debug("yfinance ISIN fetch failed for %s: %s", symbol, exc)
            value = None
        if value and value not in ("-", "None", ""):
            identifiers.append(
                IdentifierRecord(
                    identifier_type="ISIN",
                    identifier_value=str(value),
                    is_primary=True,
                    source=self.name,
                )
            )
        return identifiers

    def list_option_expirations(self, symbol: str) -> list[date]:
        try:
            expirations = yf.Ticker(symbol).options or []
        except Exception as exc:
            logger.debug("yfinance option expirations fetch failed for %s: %s", symbol, exc)
            return []

        parsed: list[date] = []
        for expiration in expirations:
            try:
                parsed.append(date.fromisoformat(str(expiration)))
            except ValueError:
                continue
        return parsed

    def fetch_option_chain(
        self,
        symbol: str,
        *,
        expiration: date | None = None,
    ) -> list[OptionContractRecord]:
        expirations = self.list_option_expirations(symbol)
        if expiration is None:
            if not expirations:
                return []
            expiration = expirations[0]

        try:
            chain = yf.Ticker(symbol).option_chain(expiration.isoformat())
        except Exception as exc:
            logger.debug(
                "yfinance option chain fetch failed for %s %s: %s",
                symbol,
                expiration.isoformat(),
                exc,
            )
            return []

        contracts: list[OptionContractRecord] = []
        for side_name, right in (("calls", "call"), ("puts", "put")):
            frame = getattr(chain, side_name, None)
            if frame is None or frame.empty:
                continue
            for _, row in frame.iterrows():
                row_dict = row.to_dict()
                provider_symbol = str(row_dict.get("contractSymbol") or "")
                if not provider_symbol:
                    continue
                contracts.append(
                    OptionContractRecord(
                        provider_symbol=provider_symbol,
                        underlying_symbol=symbol,
                        expiry_date=expiration,
                        strike=_safe_decimal(row_dict.get("strike")) or Decimal("0"),
                        right=right,
                        currency=row_dict.get("currency"),
                        contract_size=_safe_decimal(row_dict.get("contractSize")),
                        bid=_safe_decimal(row_dict.get("bid")),
                        ask=_safe_decimal(row_dict.get("ask")),
                        mark=(
                            (
                                (_safe_decimal(row_dict.get("bid")) or Decimal("0"))
                                + (_safe_decimal(row_dict.get("ask")) or Decimal("0"))
                            )
                            / Decimal("2")
                            if _safe_decimal(row_dict.get("bid")) is not None
                            and _safe_decimal(row_dict.get("ask")) is not None
                            else None
                        ),
                        last_price=_safe_decimal(row_dict.get("lastPrice")),
                        volume=_safe_decimal(row_dict.get("volume")),
                        open_interest=_safe_decimal(row_dict.get("openInterest")),
                        implied_vol=_safe_decimal(row_dict.get("impliedVolatility")),
                        observed_at=datetime.now(UTC),
                        raw_payload={k: _jsonable(v) for k, v in row_dict.items()},
                    )
                )
        return contracts

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        body = {
            "offset": offset,
            "size": 250,
            "sortField": "ticker",
            "sortType": "ASC",
            "quoteType": quote_type,
            "query": {
                "operator": "AND",
                "operands": [
                    {"operator": "gt", "operands": ["percentchange", -100]},
                ],
            },
        }

        try:
            from yfinance import Screener  # type: ignore[attr-defined]

            screener = Screener()
            screener.set_body(body)
            return screener.response or {}
        except Exception:
            pass

        try:
            from yfinance.data import YfData
            from yfinance.screener.screener import _SCREENER_URL_

            params = {
                "corsDomain": "finance.yahoo.com",
                "formatted": "false",
                "lang": "en-US",
                "region": "US",
            }
            response = YfData().post(
                _SCREENER_URL_,
                data=json.dumps(body, separators=(",", ":"), ensure_ascii=False),
                params=params,
            )
            response.raise_for_status()
            return response.json()["finance"]["result"][0]
        except Exception as exc:
            logger.debug(
                "yfinance screener page failed (type=%s offset=%d): %s",
                quote_type,
                offset,
                exc,
            )
            return {}

    def supported_discovery_types(self) -> list[str]:
        return [
            "EQUITY",
            "ETF",
            "MUTUALFUND",
            "INDEX",
            "CURRENCY",
            "CRYPTOCURRENCY",
            "FUTURE",
        ]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        tf_seconds = {
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
            Timeframe.MN: 2628000,
        }.get(timeframe, 86400)
        days_needed = max(7, int(tf_seconds * limit * 2 / 86400))
        max_lookback = TF_MAX_LOOKBACK_DAYS.get(timeframe)
        if max_lookback is not None:
            days_needed = min(days_needed, max_lookback)
        return datetime.now(UTC) - timedelta(days=days_needed)
