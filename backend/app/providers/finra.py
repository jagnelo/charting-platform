"""FINRA short-interest adapter.

FINRA publishes consolidated short-interest data through a public API, but
endpoints and access policies can evolve.  The URL is configurable and parsing
is intentionally schema-tolerant; unknown rows are preserved in raw_payload.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import stat
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.config import settings
from app.providers.base import MarketEventRecord, ShortInterestRecord
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    provider_response_headers,
    provider_retry_at_from_headers,
    raise_for_provider_error_envelope,
    redact_provider_payload,
)
from app.providers.telemetry import observe_binary_response_payload, observe_response

logger = logging.getLogger(__name__)

_token_cache: tuple[str, datetime, str, str] | None = None
_orf_token_cache: tuple[str, datetime, str, str] | None = None
_SYNC_RECORD_LIMIT = 5_000
_SYNC_OFFSET_LIMIT = 500_000
_SHORT_INTEREST_PAGE_SIZE = 1_000
_SHORT_INTEREST_CURSOR_VERSION = 1
_EVENT_CURSOR_VERSION = 1


@dataclass(slots=True)
class FINRAAsyncJob:
    """State returned by FINRA's three-leg asynchronous Query API flow."""

    status_url: str
    request_id: str | None = None
    status: str = "pending"
    result_link: str | None = field(default=None, repr=False)
    expires: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


class FINRAProvider:
    name = "finra"
    base_url = "https://api.finra.org"
    description = "FINRA consolidated short-interest and market datasets"

    def submit_async_dataset(
        self, dataset_url: str, payload: dict[str, Any] | None = None
    ) -> FINRAAsyncJob:
        """Submit a FINRA Query API dataset request for asynchronous execution.

        FINRA returns no result body for the first leg. The ``Location`` header
        is the authoritative status URL and must be polled by the caller no
        more than once per minute until the job completes.
        """

        token = self._authenticated_token()
        body = dict(payload or {})
        body["async"] = True
        try:
            response = httpx.post(
                dataset_url,
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, f"transport failure: {exc}") from exc
        observe_response(response)
        _raise_for_http_status(response)
        status_url = str(response.headers.get("location") or "").strip()
        if not status_url:
            raise ProviderResponseError(
                "finra", "async response did not contain a Location status URL"
            )
        request_id = status_url.rstrip("/").rsplit("/", 1)[-1] or None
        return FINRAAsyncJob(status_url=status_url, request_id=request_id)

    def poll_async_dataset(self, status_url: str) -> FINRAAsyncJob:
        """Poll one FINRA async status URL; callers own the polling schedule."""

        token = self._authenticated_token()
        try:
            response = httpx.get(
                status_url,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, f"transport failure: {exc}") from exc
        observe_response(response)
        _raise_for_http_status(response)
        try:
            payload = response.json() if response.content else {}
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(
                self.name, "FINRA async status returned invalid JSON"
            ) from exc
        raise_for_provider_error_envelope(
            self.name, payload, response.status_code, headers=provider_response_headers(response)
        )
        if not isinstance(payload, dict):
            raise ProviderResponseError(self.name, "FINRA async status returned an invalid object")
        body = payload
        return FINRAAsyncJob(
            status_url=status_url,
            request_id=str(body.get("requestId") or "").strip() or None,
            status=str(
                body.get("status") or ("complete" if response.status_code == 200 else "pending")
            ),
            result_link=str(body.get("resultLink") or "").strip() or None,
            expires=str(body.get("expires") or "").strip() or None,
            # Keep the live signed link separately for the immediate download
            # leg, but never expose it through diagnostic payloads.
            raw_payload=redact_provider_payload(body),
        )

    def download_async_result(self, result_link: str, *, max_bytes: int | None = None) -> bytes:
        """Download a bounded completed presigned result without OAuth credentials.

        FINRA documents asynchronous result payloads as unbounded. The adapter
        therefore refuses to download a result unless the caller (or
        ``FINRA_ASYNC_MAX_RESULT_BYTES``) supplies a positive bound. This is
        an adapter safety limit, not a provider quota and must not be used to
        make the asynchronous capability routable without durable monthly
        bandwidth accounting.
        """

        link = str(result_link or "").strip()
        if not link:
            raise ValueError("FINRA async resultLink is required")
        configured_limit = getattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", None)
        limit = max_bytes if max_bytes is not None else configured_limit
        try:
            limit = int(limit or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("FINRA async result byte bound must be a positive integer") from exc
        if limit <= 0:
            raise ValueError(
                "FINRA async result download requires FINRA_ASYNC_MAX_RESULT_BYTES "
                "or an explicit max_bytes bound"
            )
        try:
            with httpx.stream(
                "GET", link, headers={"Accept": "application/octet-stream"}, timeout=120
            ) as response:
                # Capture headers and request count without touching response.content;
                # streaming responses are not materialized before the bound check.
                observe_response(response, response_bytes=0)
                _raise_for_http_status(response)
                declared = response.headers.get("content-length")
                declared_bytes: int | None = None
                if declared is not None:
                    try:
                        declared_bytes = int(str(declared).strip())
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            "FINRA async result returned an invalid Content-Length"
                        ) from exc
                    if declared_bytes < 0:
                        raise ValueError("FINRA async result returned a negative Content-Length")
                    if declared_bytes > limit:
                        raise ValueError(
                            "FINRA async result exceeds configured byte bound "
                            f"({declared_bytes} > {limit})"
                        )
                chunks: list[bytes] = []
                total_bytes = 0
                complete = False
                body = b""
                try:
                    for chunk in response.iter_bytes():
                        body_chunk = bytes(chunk)
                        # Keep the bytes before enforcing the adapter bound. If
                        # a provider sends more than the reviewed bound, those
                        # bytes have still been received and must remain in the
                        # durable response evidence along with the failure.
                        chunks.append(body_chunk)
                        total_bytes += len(body_chunk)
                        if total_bytes > limit:
                            raise ValueError(
                                "FINRA async result exceeds configured byte bound "
                                f"({total_bytes} > {limit})"
                            )
                    if declared_bytes is not None and declared_bytes != total_bytes:
                        raise ValueError(
                            "FINRA async result Content-Length did not match the downloaded body"
                        )
                    complete = True
                finally:
                    # A failed/oversized stream still consumed bandwidth. The
                    # runtime settles byte quotas on exceptions too, so report
                    # every byte yielded before the failure instead of leaving
                    # a false zero-byte receipt.
                    observe_response(response, response_bytes=total_bytes, count_request=False)
                    if chunks:
                        body = b"".join(chunks)
                        observe_binary_response_payload(
                            "finra_async_result", body, complete=complete
                        )
                return body
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, f"transport failure: {exc}") from exc

    def fetch_short_interest(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[ShortInterestRecord]:
        """Fetch a single complete FINRA short-interest result.

        Durable callers should use :meth:`fetch_short_interest_page` through
        the persistence service. This compatibility method refuses to return
        a partial result rather than silently treating the first page as the
        full history.
        """

        page = self.fetch_short_interest_page(symbol, start=start, end=end)
        if page["complete"] is not True:
            raise ProviderResponseError(
                self.name,
                "FINRA short-interest result has more rows; use durable cursor pagination",
            )
        return page["records"]

    def fetch_short_interest_page(
        self,
        symbol: str,
        *,
        start: date | None = None,
        end: date | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Fetch and describe one FINRA short-interest page.

        ``Record-Total`` and the page headers determine completion; an empty
        or short page is not considered complete without those headers. The
        cursor is bound to the symbol and date window, and preserves date
        partitions when FINRA's documented offset ceiling would otherwise
        leave records inaccessible.
        """

        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            raise ValueError("FINRA short-interest symbol is required")
        if start and end and start > end:
            return {"records": [], "next_cursor": None, "complete": True}
        cursor_state = _decode_finra_short_interest_cursor(
            symbol=normalized_symbol,
            start=start,
            end=end,
            cursor=cursor,
        )
        token = self._authenticated_token()
        endpoint = str(getattr(settings, "FINRA_SHORT_INTEREST_URL", "") or "").strip()
        if not endpoint:
            endpoint = (
                str(getattr(settings, "FINRA_API_BASE_URL", self.base_url) or self.base_url).rstrip(
                    "/"
                )
                + "/data/group/otcMarket/name/consolidatedShortInterest"
            )
        active = cursor_state["segments"][0]
        segment_start = date.fromisoformat(active["start"]) if active["start"] else None
        segment_end = date.fromisoformat(active["end"]) if active["end"] else None
        offset = active["offset"]
        filters: list[dict[str, Any]] = [
            {
                "fieldName": "symbolCode",
                "compareType": "EQUAL",
                "fieldValue": normalized_symbol,
            }
        ]
        if segment_start:
            filters.append(
                {
                    "fieldName": "settlementDate",
                    "compareType": "GTE",
                    "fieldValue": segment_start.isoformat(),
                }
            )
        if segment_end:
            filters.append(
                {
                    "fieldName": "settlementDate",
                    "compareType": "LTE",
                    "fieldValue": segment_end.isoformat(),
                }
            )
        payload = {
            "compareFilters": filters,
            "limit": _SHORT_INTEREST_PAGE_SIZE,
            "offset": offset,
        }
        try:
            response = httpx.post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, f"transport failure: {exc}") from exc
        observe_response(response)
        _raise_for_http_status(response)
        try:
            raw = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(
                self.name, "FINRA short-interest response returned invalid JSON"
            ) from exc
        raise_for_provider_error_envelope(
            self.name, raw, response.status_code, headers=provider_response_headers(response)
        )
        rows = raw.get("data", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            raise ProviderResponseError(
                self.name, "FINRA short-interest response returned an invalid rows array"
            )
        if any(not isinstance(row, dict) for row in rows):
            raise ProviderResponseError(
                self.name, "FINRA short-interest response returned a malformed row"
            )
        headers = response.headers
        record_total = _finra_page_header(headers, "Record-Total", required=True)
        record_offset = _finra_page_header(headers, "Record-Offset")
        record_limit = _finra_page_header(headers, "Record-Limit")
        record_max_limit = _finra_page_header(headers, "Record-Max-Limit")
        page_count = _finra_page_header(headers, "Total-Records-On-Page")
        if record_offset is not None and record_offset != offset:
            raise ProviderResponseError(
                self.name, "FINRA short-interest returned an unexpected page offset"
            )
        if len(rows) > _SHORT_INTEREST_PAGE_SIZE:
            raise ProviderResponseError(
                self.name, "FINRA short-interest exceeded the requested page size"
            )
        if record_limit is not None and (record_limit <= 0 or len(rows) > record_limit):
            raise ProviderResponseError(
                self.name, "FINRA short-interest returned an invalid effective page limit"
            )
        if record_max_limit is not None and (
            record_max_limit <= 0 or record_max_limit > _SYNC_RECORD_LIMIT
        ):
            raise ProviderResponseError(
                self.name, "FINRA short-interest returned an invalid record maximum"
            )
        if page_count is not None and page_count != len(rows):
            raise ProviderResponseError(
                self.name, "FINRA short-interest page count did not match its rows"
            )
        if record_total is None or record_total < 0 or offset + len(rows) > record_total:
            raise ProviderResponseError(
                self.name, "FINRA short-interest returned an invalid total record count"
            )

        records = _finra_short_interest_records(rows)
        expected_total = active["total"]
        if expected_total is not None and record_total != expected_total:
            active["offset"] = 0
            active["total"] = record_total
            cursor_state["segments"][0] = active
            return {
                "records": records,
                "next_cursor": _encode_finra_short_interest_cursor(cursor_state),
                "complete": False,
            }

        maximum_accessible = _SYNC_OFFSET_LIMIT + _SHORT_INTEREST_PAGE_SIZE
        if record_total > maximum_accessible:
            split = _split_finra_short_interest_segment(segment_start, segment_end)
            if split is None:
                active["offset"] = min(offset + len(rows), _SYNC_OFFSET_LIMIT)
                active["total"] = record_total
                cursor_state["segments"][0] = active
                return {
                    "records": records,
                    "next_cursor": _encode_finra_short_interest_cursor(cursor_state),
                    "complete": False,
                    "blocked_error": (
                        "FINRA short-interest result exceeds the documented offset range; "
                        "use explicit smaller date windows"
                    ),
                }
            left, right = split
            cursor_state["segments"] = [left, right, *cursor_state["segments"][1:]]
            return {
                "records": records,
                "next_cursor": _encode_finra_short_interest_cursor(cursor_state),
                "complete": False,
            }

        if expected_total is None:
            active["total"] = record_total
        if not rows and offset < record_total:
            raise ProviderResponseError(
                self.name,
                "FINRA short-interest returned an empty page before its reported total",
            )
        next_offset = offset + len(rows)
        if next_offset < record_total:
            if next_offset > _SYNC_OFFSET_LIMIT:
                split = _split_finra_short_interest_segment(segment_start, segment_end)
                if split is None:
                    active["offset"] = min(next_offset, _SYNC_OFFSET_LIMIT)
                    active["total"] = record_total
                    cursor_state["segments"][0] = active
                    return {
                        "records": records,
                        "next_cursor": _encode_finra_short_interest_cursor(cursor_state),
                        "complete": False,
                        "blocked_error": (
                            "FINRA short-interest reached the documented offset ceiling; "
                            "use explicit smaller date windows"
                        ),
                    }
                left, right = split
                cursor_state["segments"] = [left, right, *cursor_state["segments"][1:]]
            else:
                active["offset"] = next_offset
                active["total"] = record_total
                cursor_state["segments"][0] = active
        else:
            cursor_state["segments"].pop(0)

        complete = not cursor_state["segments"]
        return {
            "records": records,
            "next_cursor": None if complete else _encode_finra_short_interest_cursor(cursor_state),
            "complete": complete,
        }

    def fetch_market_events(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[MarketEventRecord]:
        """Fetch one complete page of FINRA OTC Daily List evidence.

        The Daily List is a delta feed, not a complete current OTC security
        master. Callers performing durable ingestion should use
        :meth:`fetch_market_events_page` through the paginated event service;
        this compatibility method refuses to return a truncated first page.
        """

        page = self.fetch_market_events_page(start=start, end=end)
        if not page["complete"]:
            raise ProviderResponseError(
                self.name,
                "FINRA OTC Daily List has more rows; use durable cursor pagination",
            )
        return page["events"]

    def fetch_market_events_page(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Fetch one FINRA OTC Daily List page and expose durable continuation.

        FINRA's synchronous Query API caps a request at 5,000 records and the
        offset at 500,000. Response headers carry the authoritative total and
        effective page metadata; malformed or absent totals are not treated as
        proof that a partial result is complete. Large bounded windows are
        split by calendar day when the offset ceiling would otherwise prevent
        complete enumeration. The first probe page may be seen again in those
        subwindows; persistence is keyed by FINRA's stable daily-list ID.
        """

        if start and end and start > end:
            return {"events": [], "next_url": None, "next_cursor": None, "complete": True}
        cursor_state = _decode_finra_event_cursor(start=start, end=end, cursor=cursor)
        endpoint = str(getattr(settings, "FINRA_OTC_DAILY_LIST_URL", "") or "").strip()
        if not endpoint:
            endpoint = (
                str(getattr(settings, "FINRA_API_BASE_URL", self.base_url) or self.base_url).rstrip(
                    "/"
                )
                + "/data/group/otcMarket/name/OTCDAILYLIST"
            )
        token = self._authenticated_token()
        # FINRA exposes the exact date partitions available for this dataset.
        # Use that index whenever either request edge is unbounded, instead of
        # issuing a global query that can hit the 500,000-offset ceiling and
        # strand the remaining history. The partition list is carried in the
        # opaque cursor as one date-sized segment per available calendar day.
        # This is deliberately a separate page from data retrieval so the
        # normal per-call reservation remains the existing OAuth + one API
        # request upper bound.
        if (start is None or end is None) and cursor_state.get("partition_scan") != "complete":
            partition_values = self._fetch_market_event_partitions(endpoint, token)
            requested_start = start
            requested_end = end
            selected_dates = [
                value
                for value in partition_values
                if (requested_start is None or value >= requested_start)
                and (requested_end is None or value <= requested_end)
            ]
            cursor_state["segments"] = [
                _new_finra_event_segment(value, value) for value in selected_dates
            ]
            cursor_state["partition_scan"] = "complete"
            if not selected_dates:
                return {"events": [], "next_url": None, "next_cursor": None, "complete": True}
            return {
                "events": [],
                "next_url": endpoint,
                "next_cursor": _encode_finra_event_cursor(cursor_state),
                "complete": False,
            }

        active = cursor_state["segments"][0]
        segment_start = date.fromisoformat(active["start"]) if active["start"] else None
        segment_end = date.fromisoformat(active["end"]) if active["end"] else None
        offset = active["offset"]
        filters: list[dict[str, Any]] = []
        if segment_start and segment_end and segment_start == segment_end:
            filters.append(
                {
                    "fieldName": "calendarDay",
                    "compareType": "EQUAL",
                    "fieldValue": segment_start.isoformat(),
                }
            )
        else:
            if segment_start:
                filters.append(
                    {
                        "fieldName": "calendarDay",
                        "compareType": "GTE",
                        "fieldValue": segment_start.isoformat(),
                    }
                )
            if segment_end:
                filters.append(
                    {
                        "fieldName": "calendarDay",
                        "compareType": "LTE",
                        "fieldValue": segment_end.isoformat(),
                    }
                )
        payload: dict[str, Any] = {"limit": _SYNC_RECORD_LIMIT, "offset": offset}
        if filters:
            payload["compareFilters"] = filters
        try:
            response = httpx.post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, f"transport failure: {exc}") from exc
        observe_response(response)
        _raise_for_http_status(response)
        try:
            raw = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(
                self.name, "FINRA OTC daily-list response returned invalid JSON"
            ) from exc
        raise_for_provider_error_envelope(
            self.name, raw, response.status_code, headers=provider_response_headers(response)
        )
        rows = raw.get("data", raw) if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            raise ProviderResponseError(
                self.name, "FINRA OTC daily-list response returned an invalid rows array"
            )
        if any(not isinstance(row, dict) for row in rows):
            raise ProviderResponseError(
                self.name, "FINRA OTC daily-list response returned a malformed row"
            )
        headers = response.headers
        record_total = _finra_page_header(headers, "Record-Total", required=True)
        record_offset = _finra_page_header(headers, "Record-Offset")
        record_limit = _finra_page_header(headers, "Record-Limit")
        record_max_limit = _finra_page_header(headers, "Record-Max-Limit")
        page_count = _finra_page_header(headers, "Total-Records-On-Page")
        if record_offset is not None and record_offset != offset:
            raise ProviderResponseError(
                self.name, "FINRA OTC Daily List returned an unexpected page offset"
            )
        if record_limit is not None and (record_limit <= 0 or len(rows) > record_limit):
            raise ProviderResponseError(
                self.name, "FINRA OTC Daily List returned an invalid effective page limit"
            )
        if record_max_limit is not None and (
            record_max_limit <= 0 or record_max_limit > _SYNC_RECORD_LIMIT
        ):
            raise ProviderResponseError(
                self.name, "FINRA OTC Daily List returned an invalid record maximum"
            )
        if page_count is not None and page_count != len(rows):
            raise ProviderResponseError(
                self.name, "FINRA OTC Daily List page count did not match its rows"
            )
        if record_total is None or record_total < 0 or offset + len(rows) > record_total:
            raise ProviderResponseError(
                self.name, "FINRA OTC Daily List returned an invalid total record count"
            )

        expected_total = active["total"]
        if expected_total is not None and record_total != expected_total:
            # The data changed while a multi-page read was in progress. Restart
            # this segment from offset zero; already persisted records remain
            # idempotent and this response will be read again on the new pass.
            active["offset"] = 0
            active["total"] = record_total
            cursor_state["segments"][0] = active
            return {
                "events": _finra_daily_list_events(rows),
                "next_url": endpoint,
                "next_cursor": _encode_finra_event_cursor(cursor_state),
                "complete": False,
            }

        maximum_page = record_max_limit or _SYNC_RECORD_LIMIT
        maximum_accessible = _SYNC_OFFSET_LIMIT + maximum_page
        if record_total > maximum_accessible:
            if not segment_start or not segment_end or segment_start >= segment_end:
                active["offset"] = min(offset + len(rows), _SYNC_OFFSET_LIMIT)
                active["total"] = record_total
                cursor_state["segments"][0] = active
                return {
                    "events": _finra_daily_list_events(
                        rows,
                        fallback_scope=_finra_event_page_scope(segment_start, segment_end, offset),
                    ),
                    "next_url": None,
                    "next_cursor": _encode_finra_event_cursor(cursor_state),
                    "complete": False,
                    "blocked_error": (
                        "FINRA OTC Daily List exceeds the documented offset range; "
                        "this fetched page must be persisted, then the history must be "
                        "requeried in explicit smaller date windows"
                    ),
                }
            midpoint = segment_start + (segment_end - segment_start) // 2
            if midpoint >= segment_end:
                raise ProviderResponseError(
                    self.name,
                    "FINRA OTC Daily List exceeds the documented offset range for a one-day window",
                )
            left = _new_finra_event_segment(segment_start, midpoint)
            right = _new_finra_event_segment(midpoint + timedelta(days=1), segment_end)
            cursor_state["segments"] = [left, right, *cursor_state["segments"][1:]]
            events = _finra_daily_list_events(
                rows, fallback_scope=_finra_event_page_scope(segment_start, segment_end, offset)
            )
            return {
                "events": events,
                "next_url": endpoint,
                "next_cursor": _encode_finra_event_cursor(cursor_state),
                "complete": False,
            }

        if expected_total is None:
            active["total"] = record_total
        if not rows and offset < record_total:
            raise ProviderResponseError(
                self.name,
                "FINRA OTC Daily List returned an empty page before its reported total",
            )
        next_offset = offset + len(rows)
        if next_offset < record_total:
            if next_offset > _SYNC_OFFSET_LIMIT:
                if not segment_start or not segment_end or segment_start >= segment_end:
                    active["offset"] = min(next_offset, _SYNC_OFFSET_LIMIT)
                    active["total"] = record_total
                    cursor_state["segments"][0] = active
                    return {
                        "events": _finra_daily_list_events(
                            rows,
                            fallback_scope=_finra_event_page_scope(
                                segment_start, segment_end, offset
                            ),
                        ),
                        "next_url": None,
                        "next_cursor": _encode_finra_event_cursor(cursor_state),
                        "complete": False,
                        "blocked_error": (
                            "FINRA OTC Daily List reached its documented offset ceiling; "
                            "this fetched page must be persisted, then the history must be "
                            "requeried in explicit smaller date windows"
                        ),
                    }
                midpoint = segment_start + (segment_end - segment_start) // 2
                if midpoint >= segment_end:
                    active["offset"] = min(next_offset, _SYNC_OFFSET_LIMIT)
                    active["total"] = record_total
                    cursor_state["segments"][0] = active
                    return {
                        "events": _finra_daily_list_events(
                            rows,
                            fallback_scope=_finra_event_page_scope(
                                segment_start, segment_end, offset
                            ),
                        ),
                        "next_url": None,
                        "next_cursor": _encode_finra_event_cursor(cursor_state),
                        "complete": False,
                        "blocked_error": (
                            "FINRA OTC Daily List reached its documented offset ceiling "
                            "for a one-day window; this fetched page must be persisted "
                            "and the source's asynchronous or alternate partition method "
                            "is required for remaining rows"
                        ),
                    }
                left = _new_finra_event_segment(segment_start, midpoint)
                right = _new_finra_event_segment(midpoint + timedelta(days=1), segment_end)
                cursor_state["segments"] = [left, right, *cursor_state["segments"][1:]]
                events = _finra_daily_list_events(
                    rows, fallback_scope=_finra_event_page_scope(segment_start, segment_end, offset)
                )
                return {
                    "events": events,
                    "next_url": endpoint,
                    "next_cursor": _encode_finra_event_cursor(cursor_state),
                    "complete": False,
                }
            active["offset"] = next_offset
            active["total"] = record_total
            cursor_state["segments"][0] = active
        else:
            cursor_state["segments"].pop(0)

        complete = not cursor_state["segments"]
        return {
            "events": _finra_daily_list_events(
                rows, fallback_scope=_finra_event_page_scope(segment_start, segment_end, offset)
            ),
            "next_url": None if complete else endpoint,
            "next_cursor": None if complete else _encode_finra_event_cursor(cursor_state),
            "complete": complete,
        }

    def _fetch_market_event_partitions(self, endpoint: str, token: str) -> list[date]:
        """Read FINRA's authoritative available ``calendarDay`` partitions."""

        parsed = urlsplit(endpoint)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise ProviderNotConfiguredError("FINRA OTC Daily List endpoint must use HTTPS")
        partitions_url = (
            f"{parsed.scheme}://{parsed.netloc}/partitions/group/otcMarket/name/OTCDAILYLIST"
        )
        try:
            response = httpx.get(
                partitions_url,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, f"transport failure: {exc}") from exc
        observe_response(response)
        _raise_for_http_status(response)
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(
                self.name, "FINRA OTC Daily List partitions returned invalid JSON"
            ) from exc
        raise_for_provider_error_envelope(
            self.name, payload, response.status_code, headers=provider_response_headers(response)
        )
        if not isinstance(payload, dict):
            raise ProviderResponseError(
                self.name, "FINRA OTC Daily List partitions returned an invalid object"
            )
        fields = payload.get("partitionFields")
        if (
            not isinstance(fields, list)
            or len(fields) != 1
            or str(fields[0]).strip().lower() != "calendarday"
        ):
            raise ProviderResponseError(
                self.name,
                "FINRA OTC Daily List partitions did not identify calendarDay as its sole partition",
            )
        available = payload.get("availablePartitions")
        if not isinstance(available, list):
            raise ProviderResponseError(
                self.name, "FINRA OTC Daily List omitted its available partition list"
            )
        values: list[date] = []
        for item in available:
            if not isinstance(item, dict):
                raise ProviderResponseError(
                    self.name, "FINRA OTC Daily List returned a malformed partition"
                )
            partition = item.get("partitions")
            if not isinstance(partition, list) or len(partition) != 1:
                raise ProviderResponseError(
                    self.name, "FINRA OTC Daily List returned an invalid calendarDay partition"
                )
            raw_value = partition[0]
            if not isinstance(raw_value, str):
                raise ProviderResponseError(
                    self.name, "FINRA OTC Daily List returned a non-text calendarDay partition"
                )
            try:
                parsed_date = date.fromisoformat(raw_value)
            except ValueError as exc:
                raise ProviderResponseError(
                    self.name, "FINRA OTC Daily List returned an invalid calendarDay partition"
                ) from exc
            if parsed_date.isoformat() != raw_value:
                raise ProviderResponseError(
                    self.name, "FINRA OTC Daily List returned a non-canonical calendarDay"
                )
            values.append(parsed_date)
        if len(values) != len(set(values)):
            raise ProviderResponseError(
                self.name, "FINRA OTC Daily List returned duplicate calendarDay partitions"
            )
        if not values:
            raise ProviderResponseError(
                self.name, "FINRA OTC Daily List returned no available calendarDay partitions"
            )
        return sorted(values)

    def _authenticated_token(self) -> str:
        client_id = str(getattr(settings, "FINRA_CLIENT_ID", "") or "").strip()
        client_secret = str(getattr(settings, "FINRA_CLIENT_SECRET", "") or "").strip()
        if not client_id or not client_secret:
            raise ProviderNotConfiguredError(
                "finra requires FINRA_CLIENT_ID and FINRA_CLIENT_SECRET; "
                "FINRA's current API is OAuth-authenticated"
            )
        return _access_token(client_id, client_secret)


def _finra_page_header(headers: Any, name: str, *, required: bool = False) -> int | None:
    raw_value = headers.get(name) if headers is not None else None
    if raw_value is None:
        if required:
            raise ProviderResponseError("finra", f"FINRA response omitted required {name} header")
        return None
    value = str(raw_value).strip()
    if not value.isascii() or not value.isdecimal():
        raise ProviderResponseError("finra", f"FINRA response returned invalid {name} header")
    return int(value)


def _new_finra_short_interest_segment(start: date | None, end: date | None) -> dict[str, Any]:
    return {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "offset": 0,
        "total": None,
    }


def _decode_finra_short_interest_cursor(
    *, symbol: str, start: date | None, end: date | None, cursor: str | None
) -> dict[str, Any]:
    request_start = start.isoformat() if start else None
    request_end = end.isoformat() if end else None
    if not cursor:
        return {
            "version": _SHORT_INTEREST_CURSOR_VERSION,
            "symbol": symbol,
            "request_start": request_start,
            "request_end": request_end,
            "segments": [_new_finra_short_interest_segment(start, end)],
        }
    try:
        state = json.loads(cursor)
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("finra", "FINRA short-interest cursor is invalid JSON") from exc
    if (
        not isinstance(state, dict)
        or state.get("version") != _SHORT_INTEREST_CURSOR_VERSION
        or state.get("symbol") != symbol
        or state.get("request_start") != request_start
        or state.get("request_end") != request_end
        or not isinstance(state.get("segments"), list)
        or not state["segments"]
    ):
        raise ProviderResponseError(
            "finra", "FINRA short-interest cursor does not match its symbol or date window"
        )
    normalized_segments: list[dict[str, Any]] = []
    for segment in state["segments"]:
        if not isinstance(segment, dict):
            raise ProviderResponseError(
                "finra", "FINRA short-interest cursor has a malformed segment"
            )
        segment_start = segment.get("start")
        segment_end = segment.get("end")
        for label, value in (("start", segment_start), ("end", segment_end)):
            if value is not None:
                try:
                    parsed = date.fromisoformat(str(value))
                except ValueError as exc:
                    raise ProviderResponseError(
                        "finra", f"FINRA short-interest cursor has an invalid {label} date"
                    ) from exc
                if label == "start":
                    segment_start = parsed.isoformat()
                else:
                    segment_end = parsed.isoformat()
        if (
            segment_start is not None
            and segment_end is not None
            and date.fromisoformat(segment_start) > date.fromisoformat(segment_end)
        ):
            raise ProviderResponseError(
                "finra", "FINRA short-interest cursor has an inverted date range"
            )
        offset = segment.get("offset")
        total = segment.get("total")
        if (
            not isinstance(offset, int)
            or isinstance(offset, bool)
            or not 0 <= offset <= _SYNC_OFFSET_LIMIT
        ):
            raise ProviderResponseError(
                "finra", "FINRA short-interest cursor has an invalid offset"
            )
        if total is not None and (
            not isinstance(total, int) or isinstance(total, bool) or total < 0
        ):
            raise ProviderResponseError("finra", "FINRA short-interest cursor has an invalid total")
        normalized_segments.append(
            {
                "start": segment_start,
                "end": segment_end,
                "offset": offset,
                "total": total,
            }
        )
    state["segments"] = normalized_segments
    return state


def _encode_finra_short_interest_cursor(state: dict[str, Any]) -> str:
    return json.dumps(state, sort_keys=True, separators=(",", ":"))


def _split_finra_short_interest_segment(
    start: date | None, end: date | None
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if start is None or end is None or start >= end:
        return None
    midpoint = start + (end - start) // 2
    if midpoint >= end:
        return None
    return (
        _new_finra_short_interest_segment(start, midpoint),
        _new_finra_short_interest_segment(midpoint + timedelta(days=1), end),
    )


def _finra_short_interest_records(rows: list[dict[str, Any]]) -> list[ShortInterestRecord]:
    records: list[ShortInterestRecord] = []
    for row in rows:
        settlement = _parse_date(row.get("settlementDate") or row.get("settlement_date"))
        if settlement is None:
            raise ProviderResponseError(
                "finra", "FINRA short-interest response returned an invalid settlement date"
            )
        try:
            short_position = _strict_decimal(
                _first_present(
                    row,
                    "currentShortPositionQuantity",
                    "shortPosition",
                    "short_position",
                )
            )
            short_percent_float = _strict_decimal(
                _first_present(row, "shortPercentFloat", "short_percent_float")
            )
            days_to_cover = _strict_decimal(
                _first_present(row, "daysToCoverQuantity", "daysToCover", "days_to_cover")
            )
        except ValueError as exc:
            raise ProviderResponseError(
                "finra", "FINRA short-interest response returned an invalid numeric field"
            ) from exc
        records.append(
            ShortInterestRecord(
                settlement_date=settlement,
                publication_date=_parse_date(
                    row.get("publicationDate") or row.get("publication_date")
                ),
                short_position=short_position,
                short_percent_float=short_percent_float,
                days_to_cover=days_to_cover,
                source_identifier=str(
                    _first_present(
                        row,
                        "issueIdentifier",
                        "issueSymbolIdentifier",
                        "symbolCode",
                        "sourceIdentifier",
                    )
                    or ""
                )
                or None,
                raw_payload=row,
            )
        )
    return records


def _first_present(payload: dict[str, Any], *fields: str) -> Any:
    for field_name in fields:
        if field_name in payload and payload[field_name] is not None:
            return payload[field_name]
    return None


def _new_finra_event_segment(start: date, end: date) -> dict[str, Any]:
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "offset": 0,
        "total": None,
    }


def _decode_finra_event_cursor(
    *, start: date | None, end: date | None, cursor: str | None
) -> dict[str, Any]:
    requested_start = start.isoformat() if start else None
    requested_end = end.isoformat() if end else None
    if not cursor:
        return {
            "version": _EVENT_CURSOR_VERSION,
            "request_start": requested_start,
            "request_end": requested_end,
            "segments": [
                {
                    "start": requested_start,
                    "end": requested_end,
                    "offset": 0,
                    "total": None,
                }
            ],
        }
    try:
        state = json.loads(cursor)
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("finra", "FINRA Daily List cursor is invalid JSON") from exc
    if (
        not isinstance(state, dict)
        or state.get("version") != _EVENT_CURSOR_VERSION
        or state.get("request_start") != requested_start
        or state.get("request_end") != requested_end
        or not isinstance(state.get("segments"), list)
        or not state["segments"]
    ):
        raise ProviderResponseError(
            "finra", "FINRA Daily List cursor does not match its request window"
        )
    normalized_segments: list[dict[str, Any]] = []
    for segment in state["segments"]:
        if not isinstance(segment, dict):
            raise ProviderResponseError("finra", "FINRA Daily List cursor has a malformed segment")
        segment_start = segment.get("start")
        segment_end = segment.get("end")
        if segment_start is not None:
            try:
                parsed_start = date.fromisoformat(str(segment_start))
            except ValueError as exc:
                raise ProviderResponseError(
                    "finra", "FINRA Daily List cursor has an invalid start date"
                ) from exc
            segment_start = parsed_start.isoformat()
        if segment_end is not None:
            try:
                parsed_end = date.fromisoformat(str(segment_end))
            except ValueError as exc:
                raise ProviderResponseError(
                    "finra", "FINRA Daily List cursor has an invalid end date"
                ) from exc
            segment_end = parsed_end.isoformat()
        if (
            segment_start is not None
            and segment_end is not None
            and date.fromisoformat(segment_start) > date.fromisoformat(segment_end)
        ):
            raise ProviderResponseError(
                "finra", "FINRA Daily List cursor has an inverted date range"
            )
        offset = segment.get("offset")
        total = segment.get("total")
        if (
            not isinstance(offset, int)
            or isinstance(offset, bool)
            or not 0 <= offset <= _SYNC_OFFSET_LIMIT
        ):
            raise ProviderResponseError("finra", "FINRA Daily List cursor has an invalid offset")
        if total is not None and (
            not isinstance(total, int) or isinstance(total, bool) or total < 0
        ):
            raise ProviderResponseError("finra", "FINRA Daily List cursor has an invalid total")
        normalized_segments.append(
            {
                "start": segment_start,
                "end": segment_end,
                "offset": offset,
                "total": total,
            }
        )
    state["segments"] = normalized_segments
    return state


def _encode_finra_event_cursor(state: dict[str, Any]) -> str:
    return json.dumps(state, sort_keys=True, separators=(",", ":"))


def _finra_event_page_scope(start: date | None, end: date | None, offset: int) -> str:
    return f"{start.isoformat() if start else ''}:{end.isoformat() if end else ''}:{offset}"


def _finra_daily_list_events(
    rows: list[dict[str, Any]], *, fallback_scope: str = ""
) -> list[MarketEventRecord]:
    events: list[MarketEventRecord] = []
    fallback_occurrences: dict[str, int] = {}
    page_scope_digest = sha256(fallback_scope.encode()).hexdigest()
    for row in rows:
        event_date = _parse_date(row.get("calendarDay")) or _parse_date(row.get("exDate"))
        event_time = _parse_datetime(row.get("dailyListDatetime"))
        event_type = _daily_list_event_type(row)
        daily_list_id = row.get("OTCDailyListID") or row.get("otcDailyListId")
        if daily_list_id:
            event_key = str(daily_list_id)
        else:
            row_digest = sha256(
                json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode()
            ).hexdigest()
            occurrence = fallback_occurrences.get(row_digest, 0)
            fallback_occurrences[row_digest] = occurrence + 1
            event_key = f"row-sha256:{row_digest}:page:{page_scope_digest}:occ:{occurrence}"
        events.append(
            MarketEventRecord(
                event_type=event_type,
                event_key=f"finra:otc_daily_list:{event_key}",
                event_time=event_time,
                effective_date=event_date,
                title=str(
                    row.get("dailyListReasonDescription")
                    or row.get("newSecurityDescription")
                    or row.get("oldSecurityDescription")
                    or event_type
                ),
                source_version="OTCDAILYLIST",
                is_provisional=True,
                raw_payload=row,
            )
        )
    return events


def _access_token(client_id: str, client_secret: str) -> str:
    global _token_cache
    now = datetime.now(UTC)
    client_secret_digest = sha256(client_secret.encode("utf-8")).hexdigest()
    if (
        _token_cache
        and _token_cache[1] > now
        and _token_cache[2] == client_id
        and _token_cache[3] == client_secret_digest
    ):
        return _token_cache[0]
    try:
        response = httpx.post(
            str(getattr(settings, "FINRA_TOKEN_URL", "") or ""),
            params={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except httpx.RequestError as exc:
        raise ProviderResponseError("finra", f"transport failure: {exc}") from exc
    observe_response(response)
    _raise_for_http_status(response)
    try:
        body = response.json()
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("finra", "FINRA OAuth response returned invalid JSON") from exc
    raise_for_provider_error_envelope(
        "finra", body, response.status_code, headers=provider_response_headers(response)
    )
    if not isinstance(body, dict):
        raise ProviderResponseError("finra", "FINRA OAuth response returned an invalid object")
    token = str(body.get("access_token") or "").strip()
    if not token:
        raise ProviderResponseError("finra", "FINRA OAuth response did not contain access_token")
    try:
        expires_in = int(body.get("expires_in") or 3600) if isinstance(body, dict) else 3600
    except (TypeError, ValueError):
        expires_in = 3600
    # FINRA documents caching the token for at most 30 minutes. Refresh one
    # minute before a shorter provider expiry and never reuse a stale grant.
    cache_seconds = min(1800, max(60, expires_in - 60))
    _token_cache = (
        token,
        now + timedelta(seconds=cache_seconds),
        client_id,
        client_secret_digest,
    )
    return token


def _orf_access_token(refresh_token: str, username: str) -> str:
    """Exchange a TRAQS ORF refresh token for a one-hour file token.

    The ORF file-download API is a separate FINRA product from the Gateway
    Query API. Its documented refresh endpoint accepts the assigned TRAQS
    username and refresh token, so Gateway client credentials must never be
    substituted here.
    """

    global _orf_token_cache
    state_path = _orf_refresh_token_state_path()
    seed_digest = sha256(refresh_token.encode("utf-8")).hexdigest()
    with _orf_refresh_token_state_lock(state_path):
        current_refresh_token = _read_orf_refresh_token_state(
            state_path,
            bootstrap_token=refresh_token,
            username=username,
            bootstrap_digest=seed_digest,
        )
        now = datetime.now(UTC)
        refresh_token_digest = sha256(current_refresh_token.encode("utf-8")).hexdigest()
        if (
            _orf_token_cache
            and _orf_token_cache[1] > now
            and _orf_token_cache[2] == username
            and _orf_token_cache[3] == refresh_token_digest
        ):
            return _orf_token_cache[0]
        return _exchange_orf_access_token(
            state_path=state_path,
            username=username,
            bootstrap_digest=seed_digest,
            refresh_token=current_refresh_token,
        )


def _exchange_orf_access_token(
    *, state_path: Path, username: str, bootstrap_digest: str, refresh_token: str
) -> str:
    global _orf_token_cache
    now = datetime.now(UTC)
    token_url = str(getattr(settings, "FINRA_ORF_TOKEN_URL", "") or "").strip()
    if not token_url:
        raise ProviderNotConfiguredError("finra ORF requires FINRA_ORF_TOKEN_URL")
    try:
        response = httpx.post(
            token_url,
            data={"refreshtoken": refresh_token, "username": username},
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except httpx.RequestError as exc:
        raise ProviderResponseError("finra_otc_directory", f"transport failure: {exc}") from exc
    observe_response(response)
    _raise_for_http_status(response)
    try:
        body = response.json()
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError(
            "finra_otc_directory", "FINRA ORF token response returned invalid JSON"
        ) from exc
    raise_for_provider_error_envelope(
        "finra_otc_directory",
        body,
        response.status_code,
        headers=provider_response_headers(response),
    )
    if not isinstance(body, dict):
        raise ProviderResponseError(
            "finra_otc_directory", "FINRA ORF token response returned an invalid object"
        )
    token = str(body.get("access_token") or "").strip()
    if not token:
        raise ProviderResponseError(
            "finra_otc_directory", "FINRA ORF token response did not contain access_token"
        )
    next_refresh_token = str(body.get("refresh_token") or "").strip()
    if not next_refresh_token:
        raise ProviderResponseError(
            "finra_otc_directory", "FINRA ORF token response did not contain refresh_token"
        )
    try:
        expires_in = int(body.get("expires_in") or 3600)
    except (TypeError, ValueError):
        expires_in = 3600
    cache_seconds = min(3300, max(60, expires_in - 60))
    _write_orf_refresh_token_state(
        state_path,
        username=username,
        bootstrap_digest=bootstrap_digest,
        refresh_token=next_refresh_token,
    )
    next_refresh_digest = sha256(next_refresh_token.encode("utf-8")).hexdigest()
    _orf_token_cache = (
        token,
        now + timedelta(seconds=cache_seconds),
        username,
        next_refresh_digest,
    )
    return token


def _orf_refresh_token_state_path() -> Path:
    """Resolve the private, durable shared state file for ORF token rotation."""

    configured = str(getattr(settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", "") or "").strip()
    if not configured:
        raise ProviderNotConfiguredError(
            "finra ORF requires FINRA_ORF_REFRESH_TOKEN_STATE_FILE, a private durable path "
            "shared by API and worker processes"
        )
    candidate = Path(configured).expanduser()
    if not candidate.name or candidate.name in {".", ".."}:
        raise ProviderNotConfiguredError("finra ORF refresh-token state path is invalid")
    try:
        parent = candidate.parent.resolve(strict=True)
        metadata = parent.stat()
    except OSError as exc:
        raise ProviderNotConfiguredError(
            "finra ORF refresh-token state directory must already exist"
        ) from exc
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o022:
        raise ProviderNotConfiguredError(
            "finra ORF refresh-token state directory must not be group/world writable"
        )
    return parent / candidate.name


def _orf_refresh_token_state_lock(state_path: Path):
    """Lock cross-process token rotation without exposing credential contents."""

    class _Lock:
        def __enter__(self):
            lock_path = state_path.with_name(f".{state_path.name}.lock")
            flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                self.fd = os.open(lock_path, flags, 0o600)
                metadata = os.fstat(self.fd)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                    os.close(self.fd)
                    raise ProviderNotConfiguredError(
                        "finra ORF refresh-token lock must be a private regular file"
                    )
                fcntl.flock(self.fd, fcntl.LOCK_EX)
                probe_fd, probe_path = tempfile.mkstemp(
                    prefix=f".{state_path.name}.probe.", dir=state_path.parent
                )
                os.close(probe_fd)
                Path(probe_path).unlink()
            except OSError as exc:
                if getattr(self, "fd", -1) >= 0:
                    os.close(self.fd)
                    self.fd = -1
                raise ProviderNotConfiguredError(
                    "finra ORF refresh-token state directory must support private locking"
                ) from exc
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)

    return _Lock()


def _read_orf_refresh_token_state(
    state_path: Path,
    *,
    bootstrap_token: str,
    username: str,
    bootstrap_digest: str,
) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(state_path, flags)
    except FileNotFoundError:
        return bootstrap_token
    except OSError as exc:
        raise ProviderNotConfiguredError(
            "finra ORF refresh-token state file is not safely readable"
        ) from exc
    with os.fdopen(fd, "rb") as state_file:
        metadata = os.fstat(state_file.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_mode & 0o077
            or (os.geteuid() != 0 and metadata.st_uid != os.geteuid())
            or metadata.st_size > 8192
        ):
            raise ProviderNotConfiguredError(
                "finra ORF refresh-token state file must be owner-only, regular, and bounded"
            )
        try:
            state = json.loads(state_file.read(8193))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderNotConfiguredError(
                "finra ORF refresh-token state file is malformed"
            ) from exc
    if not isinstance(state, dict):
        raise ProviderNotConfiguredError("finra ORF refresh-token state file is malformed")
    if state.get("username") != username or state.get("bootstrap_sha256") != bootstrap_digest:
        return bootstrap_token
    current = str(state.get("refresh_token") or "").strip()
    if not current:
        raise ProviderNotConfiguredError("finra ORF refresh-token state file has no current token")
    return current


def _write_orf_refresh_token_state(
    state_path: Path,
    *,
    username: str,
    bootstrap_digest: str,
    refresh_token: str,
) -> None:
    """Atomically persist FINRA's newest refresh token with owner-only mode."""

    try:
        existing = state_path.lstat()
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise ProviderNotConfiguredError(
            "finra ORF refresh-token state file cannot be inspected safely"
        ) from exc
    if existing is not None and (not stat.S_ISREG(existing.st_mode) or existing.st_mode & 0o077):
        raise ProviderNotConfiguredError(
            "finra ORF refresh-token state file must be a private regular file"
        )
    state = json.dumps(
        {
            "bootstrap_sha256": bootstrap_digest,
            "refresh_token": refresh_token,
            "username": username,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    fd = -1
    temporary_path = None
    try:
        fd, temporary_name = tempfile.mkstemp(prefix=f".{state_path.name}.", dir=state_path.parent)
        temporary_path = Path(temporary_name)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as state_file:
            fd = -1
            state_file.write(state)
            state_file.flush()
            os.fsync(state_file.fileno())
        os.replace(temporary_path, state_path)
        directory_fd = os.open(state_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise ProviderNotConfiguredError(
            "finra ORF could not persist the rotated refresh token in its private state file"
        ) from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _raise_for_http_status(response: Any) -> None:
    """Convert FINRA HTTP failures into typed, redacted provider errors."""

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        headers = provider_response_headers(response)
        status_code = getattr(response, "status_code", None)
        if status_code in {418, 429}:
            raise ProviderRateLimitError(
                "finra",
                f"FINRA request rejected for capacity (HTTP {status_code})",
                status_code=status_code,
                retry_at=provider_retry_at_from_headers(headers),
                scope="ip",
                headers=headers,
            ) from exc
        raise ProviderResponseError(
            "finra",
            f"FINRA request failed with HTTP {status_code}",
            status_code=status_code,
        ) from exc


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for pattern in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _daily_list_event_type(row: dict[str, Any]) -> str:
    if str(row.get("securityAddFlag") or "").upper() == "Y":
        return "otc_security_added"
    if str(row.get("securityDeleteFlag") or "").upper() == "Y":
        return "otc_security_deleted"
    if str(row.get("changeSymbolFlag") or "").upper() == "Y":
        return "otc_symbol_change"
    if str(row.get("changeSecurityDescriptionFlag") or "").upper() == "Y":
        return "otc_name_change"
    if str(row.get("bankruptcyFlag") or "").upper() == "Y":
        return "otc_bankruptcy"
    if row.get("forwardSplitRate") not in (None, "") or row.get("reverseSplitRate") not in (
        None,
        "",
    ):
        return "otc_split"
    if row.get("cashAmountText") not in (None, "") or row.get("dividendTypeCode") not in (None, ""):
        return "otc_dividend"
    return "otc_daily_list"


def _strict_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric FINRA value")
    try:
        number = Decimal(str(value).strip())
    except Exception as exc:
        raise ValueError("invalid FINRA numeric value") from exc
    if not number.is_finite():
        raise ValueError("non-finite FINRA numeric value")
    return number
