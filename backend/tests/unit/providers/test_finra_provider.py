import base64
import hashlib
import json
import stat
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from app.config import settings
from app.providers import finra
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from app.providers.finra import FINRAProvider
from app.providers.telemetry import activate, deactivate


def _short_interest_response(rows, *, total, offset, limit=1000):
    response = Mock(status_code=200)
    response.json.return_value = {"data": rows}
    response.headers = {
        "Record-Total": str(total),
        "Record-Offset": str(offset),
        "Record-Limit": str(limit),
        "Record-Max-Limit": "5000",
        "Total-Records-On-Page": str(len(rows)),
    }
    response.raise_for_status.return_value = None
    return response


def test_finra_orf_access_token_uses_traqs_refresh_flow(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "FINRA_ORF_TOKEN_URL", "https://example.test/refresh")
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", str(tmp_path / "orf-token"))
    response = Mock(status_code=200)
    response.headers = {}
    response.json.return_value = {
        "access_token": "orf-token",
        "refresh_token": "refresh-token",
        "expires_in": 3600,
    }
    response.raise_for_status.return_value = None
    with (
        patch.object(finra, "_orf_token_cache", None),
        patch("app.providers.finra.httpx.post", return_value=response) as post,
    ):
        assert finra._orf_access_token("refresh-token", "traqs-user") == "orf-token"
    post.assert_called_once_with(
        "https://example.test/refresh",
        data={"refreshtoken": "refresh-token", "username": "traqs-user"},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    state_file = tmp_path / "orf-token"
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o600
    assert json.loads(state_file.read_text())["refresh_token"] == "refresh-token"


def test_finra_orf_refresh_token_rotation_is_shared_across_refreshes(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "FINRA_ORF_TOKEN_URL", "https://example.test/refresh")
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", str(tmp_path / "orf-token"))
    first = Mock(status_code=200, headers={})
    first.json.return_value = {
        "access_token": "first-access",
        "refresh_token": "rotated-refresh",
        "expires_in": 3600,
    }
    first.raise_for_status.return_value = None
    second = Mock(status_code=200, headers={})
    second.json.return_value = {
        "access_token": "second-access",
        "refresh_token": "rotated-again",
        "expires_in": 3600,
    }
    second.raise_for_status.return_value = None
    with (
        patch.object(finra, "_orf_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[first, second]) as post,
    ):
        assert finra._orf_access_token("bootstrap-refresh", "traqs-user") == "first-access"
        finra._orf_token_cache = (
            "expired-access",
            datetime.now(UTC) - timedelta(seconds=1),
            "traqs-user",
            hashlib.sha256(b"rotated-refresh").hexdigest(),
        )
        assert finra._orf_access_token("bootstrap-refresh", "traqs-user") == "second-access"
    assert post.call_args_list[0].kwargs["data"]["refreshtoken"] == "bootstrap-refresh"
    assert post.call_args_list[1].kwargs["data"]["refreshtoken"] == "rotated-refresh"
    state = json.loads((tmp_path / "orf-token").read_text())
    assert state["refresh_token"] == "rotated-again"
    assert stat.S_IMODE((tmp_path / "orf-token").stat().st_mode) == 0o600


def test_finra_orf_access_token_requires_durable_private_state_path(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", "")
    with patch("app.providers.finra.httpx.post") as post:
        with pytest.raises(ProviderNotConfiguredError, match="FINRA_ORF_REFRESH_TOKEN_STATE_FILE"):
            finra._orf_access_token("bootstrap-refresh", "traqs-user")
    post.assert_not_called()


def test_finra_orf_access_token_refuses_unsafe_state_file_before_provider_call(
    monkeypatch, tmp_path
):
    state_path = tmp_path / "orf-token"
    state_path.write_text(
        json.dumps(
            {
                "bootstrap_sha256": hashlib.sha256(b"bootstrap-refresh").hexdigest(),
                "refresh_token": "rotated-refresh",
                "username": "traqs-user",
            }
        )
    )
    state_path.chmod(0o644)
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", str(state_path))
    with patch("app.providers.finra.httpx.post") as post:
        with pytest.raises(ProviderNotConfiguredError, match="owner-only"):
            finra._orf_access_token("bootstrap-refresh", "traqs-user")
    post.assert_not_called()


def test_finra_orf_access_token_rejects_response_without_rotated_token(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "FINRA_ORF_TOKEN_URL", "https://example.test/refresh")
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", str(tmp_path / "orf-token"))
    response = Mock(status_code=200, headers={})
    response.json.return_value = {"access_token": "orf-token", "expires_in": 3600}
    response.raise_for_status.return_value = None
    with (
        patch.object(finra, "_orf_token_cache", None),
        patch("app.providers.finra.httpx.post", return_value=response),
    ):
        with pytest.raises(ProviderResponseError, match="refresh_token"):
            finra._orf_access_token("bootstrap-refresh", "traqs-user")


def test_finra_orf_access_token_cache_is_scoped_to_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "FINRA_ORF_TOKEN_URL", "https://example.test/refresh")
    monkeypatch.setattr(
        settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", str(tmp_path / "orf-token-cache")
    )
    first = Mock(status_code=200)
    first.headers = {}
    first.json.return_value = {
        "access_token": "first-token",
        "refresh_token": "refresh-one",
        "expires_in": 3600,
    }
    first.raise_for_status.return_value = None
    second = Mock(status_code=200)
    second.headers = {}
    second.json.return_value = {
        "access_token": "second-token",
        "refresh_token": "refresh-two",
        "expires_in": 3600,
    }
    second.raise_for_status.return_value = None
    with (
        patch.object(finra, "_orf_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[first, second]) as post,
    ):
        assert finra._orf_access_token("refresh-one", "traqs-user") == "first-token"
        assert finra._orf_access_token("refresh-two", "traqs-user") == "second-token"
    assert post.call_count == 2


def test_finra_gateway_access_token_cache_is_scoped_to_credentials(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_TOKEN_URL", "https://example.test/oauth")
    first = Mock(status_code=200)
    first.headers = {}
    first.json.return_value = {"access_token": "first-token", "expires_in": 3600}
    first.raise_for_status.return_value = None
    second = Mock(status_code=200)
    second.headers = {}
    second.json.return_value = {"access_token": "second-token", "expires_in": 3600}
    second.raise_for_status.return_value = None
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[first, second]) as post,
    ):
        assert finra._access_token("client-one", "secret-one") == "first-token"
        assert finra._access_token("client-two", "secret-two") == "second-token"
    assert post.call_count == 2


def test_finra_parser_keeps_publication_and_raw_provenance(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_SHORT_INTEREST_URL", "https://example.test/short")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    response = Mock()
    response.json.return_value = {
        "data": [
            {
                "settlementDate": "2026-08-29",
                "publicationDate": "2026-09-01",
                "symbolCode": "AAPL",
                "currentShortPositionQuantity": "1200",
                "shortPercentFloat": "0.12",
                "daysToCoverQuantity": "2.5",
                "issueIdentifier": "CUSIP123",
            }
        ]
    }
    response.headers = {
        "Record-Total": "1",
        "Record-Offset": "0",
        "Record-Limit": "1000",
        "Record-Max-Limit": "5000",
        "Total-Records-On-Page": "1",
    }
    response.raise_for_status.return_value = None
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]) as post,
    ):
        rows = FINRAProvider().fetch_short_interest("AAPL", start=date(2026, 8, 1))
    assert rows[0].settlement_date == date(2026, 8, 29)
    assert rows[0].short_position == 1200
    assert rows[0].raw_payload["issueIdentifier"] == "CUSIP123"
    token_call, dataset_call = post.call_args_list
    assert token_call.kwargs["params"] == {"grant_type": "client_credentials"}
    assert dataset_call.kwargs["json"]["compareFilters"] == [
        {"fieldName": "symbolCode", "compareType": "EQUAL", "fieldValue": "AAPL"},
        {"fieldName": "settlementDate", "compareType": "GTE", "fieldValue": "2026-08-01"},
    ]


def test_finra_short_interest_follows_authoritative_offset_pages(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_SHORT_INTEREST_URL", "https://example.test/short")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    rows = [
        {
            "settlementDate": f"2026-08-{day:02d}",
            "symbolCode": "AAPL",
            "currentShortPositionQuantity": str(day),
        }
        for day in (1, 2)
    ]
    first = _short_interest_response(rows[:1], total=2, offset=0)
    second = _short_interest_response(rows[1:], total=2, offset=1)
    with (
        patch.object(finra, "_token_cache", None),
        patch(
            "app.providers.finra.httpx.post",
            side_effect=[token_response, first, second],
        ) as post,
    ):
        provider = FINRAProvider()
        first_page = provider.fetch_short_interest_page("aapl")
        second_page = provider.fetch_short_interest_page("AAPL", cursor=first_page["next_cursor"])

    assert first_page["complete"] is False
    assert first_page["records"][0].short_position == 1
    assert second_page["complete"] is True
    assert second_page["records"][0].short_position == 2
    assert [call.kwargs["json"]["offset"] for call in post.call_args_list[1:]] == [0, 1]


def test_finra_short_interest_compatibility_method_refuses_partial_result(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_SHORT_INTEREST_URL", "https://example.test/short")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    response = _short_interest_response(
        [{"settlementDate": "2026-08-01", "symbolCode": "AAPL"}],
        total=2,
        offset=0,
    )
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]),
    ):
        with pytest.raises(ProviderResponseError, match="use durable cursor pagination"):
            FINRAProvider().fetch_short_interest("AAPL")


def test_finra_short_interest_requires_authoritative_total(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_SHORT_INTEREST_URL", "https://example.test/short")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    response = Mock(status_code=200)
    response.json.return_value = {"data": []}
    response.headers = {}
    response.raise_for_status.return_value = None
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]),
    ):
        with pytest.raises(ProviderResponseError, match="omitted required Record-Total"):
            FINRAProvider().fetch_short_interest_page("AAPL")


def test_finra_short_interest_keeps_rows_and_restarts_if_total_changes(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_SHORT_INTEREST_URL", "https://example.test/short")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    response = _short_interest_response(
        [
            {
                "settlementDate": "2026-08-02",
                "symbolCode": "AAPL",
                "currentShortPositionQuantity": "0",
            }
        ],
        total=3,
        offset=1,
    )
    cursor = finra._encode_finra_short_interest_cursor(
        {
            "version": finra._SHORT_INTEREST_CURSOR_VERSION,
            "symbol": "AAPL",
            "request_start": None,
            "request_end": None,
            "segments": [{"start": None, "end": None, "offset": 1, "total": 2}],
        }
    )
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]),
    ):
        page = FINRAProvider().fetch_short_interest_page("AAPL", cursor=cursor)

    assert page["records"][0].short_position == 0
    resumed = json.loads(page["next_cursor"])
    assert resumed["segments"][0]["offset"] == 0
    assert resumed["segments"][0]["total"] == 3


def test_finra_short_interest_offset_overflow_splits_bounded_dates_losslessly(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_SHORT_INTEREST_URL", "https://example.test/short")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    row = {"settlementDate": "2026-08-02", "symbolCode": "AAPL"}
    response = _short_interest_response([row], total=600_000, offset=500_000)
    start, end = date(2026, 8, 1), date(2026, 8, 3)
    cursor = finra._encode_finra_short_interest_cursor(
        {
            "version": finra._SHORT_INTEREST_CURSOR_VERSION,
            "symbol": "AAPL",
            "request_start": start.isoformat(),
            "request_end": end.isoformat(),
            "segments": [
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "offset": 500_000,
                    "total": 600_000,
                }
            ],
        }
    )
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]),
    ):
        page = FINRAProvider().fetch_short_interest_page(
            "AAPL", start=start, end=end, cursor=cursor
        )

    assert len(page["records"]) == 1
    assert page["complete"] is False
    segments = json.loads(page["next_cursor"])["segments"]
    assert [(segment["start"], segment["end"]) for segment in segments] == [
        ("2026-08-01", "2026-08-02"),
        ("2026-08-03", "2026-08-03"),
    ]


def test_finra_short_interest_unbounded_offset_overflow_returns_rows_and_blocker(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_SHORT_INTEREST_URL", "https://example.test/short")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    response = _short_interest_response(
        [{"settlementDate": "2026-08-02", "symbolCode": "AAPL"}],
        total=600_000,
        offset=500_000,
    )
    cursor = finra._encode_finra_short_interest_cursor(
        {
            "version": finra._SHORT_INTEREST_CURSOR_VERSION,
            "symbol": "AAPL",
            "request_start": None,
            "request_end": None,
            "segments": [{"start": None, "end": None, "offset": 500_000, "total": 600_000}],
        }
    )
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]),
    ):
        page = FINRAProvider().fetch_short_interest_page("AAPL", cursor=cursor)

    assert len(page["records"]) == 1
    assert page["complete"] is False
    assert page["next_cursor"] is not None
    assert "explicit smaller date windows" in page["blocked_error"]


@pytest.mark.parametrize(
    "row",
    [
        "not-a-row",
        {"settlementDate": "2026-08-29", "shortPercentFloat": "not-a-number"},
        {"settlementDate": "not-a-date", "shortPosition": "1200"},
    ],
)
def test_finra_short_interest_rejects_malformed_rows(monkeypatch, row):
    monkeypatch.setattr(settings, "FINRA_SHORT_INTEREST_URL", "https://example.test/short")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    response = Mock()
    response.json.return_value = {"data": [row]}
    response.headers = {
        "Record-Total": "1",
        "Record-Offset": "0",
        "Record-Limit": "1000",
        "Record-Max-Limit": "5000",
        "Total-Records-On-Page": "1",
    }
    response.raise_for_status.return_value = None
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]),
    ):
        with pytest.raises(ProviderResponseError, match="FINRA short-interest"):
            FINRAProvider().fetch_short_interest("AAPL")


def test_finra_daily_list_rejects_mixed_rows(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_DAILY_LIST_URL", "https://example.test/daily")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    response = Mock()
    response.json.return_value = [{"calendarDay": "2026-08-29"}, 42]
    response.raise_for_status.return_value = None
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]),
    ):
        with pytest.raises(ProviderResponseError, match="FINRA OTC daily-list"):
            FINRAProvider().fetch_market_events_page(start=date(2026, 8, 1), end=date(2026, 8, 31))


def test_finra_http_success_failed_status_is_typed(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.status_code = 200
    token_response.raise_for_status.return_value = None
    status_response = Mock()
    status_response.status_code = 200
    status_response.content = b'{"status":"failed","message":"query rejected"}'
    status_response.json.return_value = {"status": "failed", "message": "query rejected"}
    status_response.raise_for_status.return_value = None
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", return_value=token_response),
        patch("app.providers.finra.httpx.get", return_value=status_response),
    ):
        with pytest.raises(ProviderResponseError) as exc_info:
            FINRAProvider().poll_async_dataset("https://example.test/status")
    assert exc_info.value.provider_name == "finra"


def test_finra_otc_daily_list_normalizes_lifecycle_events(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_DAILY_LIST_URL", "https://example.test/daily")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    response = Mock()
    response.json.return_value = [
        {
            "OTCDailyListID": 139933,
            "dailyListDatetime": "2018-12-18 16:30:49.0",
            "calendarDay": "2018-12-18",
            "dailyListEventCode": "DA",
            "dailyListReasonDescription": "Cash Dividend Regular",
            "oldSymbolCode": "SOBS",
            "newSymbolCode": "SOBS",
            "cashAmountText": "0.34",
            "dividendTypeCode": "CD",
        }
    ]
    response.headers = {
        "Record-Total": "1",
        "Record-Offset": "0",
        "Record-Limit": "5000",
        "Record-Max-Limit": "5000",
        "Total-Records-On-Page": "1",
    }
    response.raise_for_status.return_value = None
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]) as post,
    ):
        rows = FINRAProvider().fetch_market_events(start=date(2018, 12, 1), end=date(2018, 12, 31))
    assert len(rows) == 1
    assert rows[0].event_type == "otc_dividend"
    assert rows[0].event_key == "finra:otc_daily_list:139933"
    assert rows[0].effective_date == date(2018, 12, 18)
    assert rows[0].event_time is not None
    assert rows[0].raw_payload["oldSymbolCode"] == "SOBS"
    assert post.call_args_list[1].kwargs["json"]["compareFilters"] == [
        {"fieldName": "calendarDay", "compareType": "GTE", "fieldValue": "2018-12-01"},
        {"fieldName": "calendarDay", "compareType": "LTE", "fieldValue": "2018-12-31"},
    ]


def test_finra_daily_list_paginates_using_authoritative_response_headers(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_DAILY_LIST_URL", "https://example.test/daily")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    row_template = {
        "dailyListDatetime": "2026-08-29 16:30:49.0",
        "calendarDay": "2026-08-29",
        "dailyListEventCode": "SC",
        "oldSymbolCode": "OLD",
        "newSymbolCode": "NEW",
    }
    first = Mock(status_code=200)
    first.json.return_value = [{**row_template, "OTCDailyListID": 101}]
    first.headers = {
        "Record-Total": "2",
        "Record-Offset": "0",
        "Record-Limit": "5000",
        "Record-Max-Limit": "5000",
        "Total-Records-On-Page": "1",
    }
    first.raise_for_status.return_value = None
    second = Mock(status_code=200)
    second.json.return_value = [{**row_template, "OTCDailyListID": 102}]
    second.headers = {
        "Record-Total": "2",
        "Record-Offset": "1",
        "Record-Limit": "5000",
        "Record-Max-Limit": "5000",
        "Total-Records-On-Page": "1",
    }
    second.raise_for_status.return_value = None

    with (
        patch.object(finra, "_token_cache", None),
        patch(
            "app.providers.finra.httpx.post",
            side_effect=[token_response, first, second],
        ) as post,
    ):
        provider = FINRAProvider()
        first_page = provider.fetch_market_events_page(
            start=date(2026, 8, 1), end=date(2026, 8, 31)
        )
        second_page = provider.fetch_market_events_page(
            start=date(2026, 8, 1), end=date(2026, 8, 31), cursor=first_page["next_cursor"]
        )

    assert first_page["complete"] is False
    assert first_page["events"][0].event_key == "finra:otc_daily_list:101"
    assert second_page["complete"] is True
    assert second_page["events"][0].event_key == "finra:otc_daily_list:102"
    assert [call.kwargs["json"]["offset"] for call in post.call_args_list[1:]] == [0, 1]


def test_finra_daily_list_requires_authoritative_total_for_completion(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_DAILY_LIST_URL", "https://example.test/daily")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    response = Mock(status_code=200)
    response.json.return_value = []
    response.headers = {}
    response.raise_for_status.return_value = None
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]),
    ):
        with pytest.raises(ProviderResponseError, match="omitted required Record-Total"):
            FINRAProvider().fetch_market_events_page(start=date(2026, 8, 1), end=date(2026, 8, 31))


def test_finra_daily_list_keeps_page_rows_when_total_changes_and_restarts(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_DAILY_LIST_URL", "https://example.test/daily")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    response = Mock(status_code=200)
    response.json.return_value = [{"OTCDailyListID": 103, "calendarDay": "2026-08-01"}]
    response.headers = {
        "Record-Total": "3",
        "Record-Offset": "1",
        "Record-Limit": "5000",
        "Record-Max-Limit": "5000",
        "Total-Records-On-Page": "1",
    }
    response.raise_for_status.return_value = None
    cursor = finra._encode_finra_event_cursor(
        {
            "version": finra._EVENT_CURSOR_VERSION,
            "request_start": "2026-08-01",
            "request_end": "2026-08-01",
            "segments": [{"start": "2026-08-01", "end": "2026-08-01", "offset": 1, "total": 2}],
        }
    )

    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]),
    ):
        page = FINRAProvider().fetch_market_events_page(
            start=date(2026, 8, 1), end=date(2026, 8, 1), cursor=cursor
        )

    assert page["complete"] is False
    assert [event.event_key for event in page["events"]] == ["finra:otc_daily_list:103"]
    restarted = finra._decode_finra_event_cursor(
        start=date(2026, 8, 1), end=date(2026, 8, 1), cursor=page["next_cursor"]
    )
    assert restarted["segments"][0]["offset"] == 0
    assert restarted["segments"][0]["total"] == 3


def test_finra_daily_list_splits_windows_when_platform_offset_would_truncate(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_DAILY_LIST_URL", "https://example.test/daily")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    probe = Mock(status_code=200)
    probe.json.return_value = [
        {
            "OTCDailyListID": 101,
            "calendarDay": "2026-08-01",
            "dailyListEventCode": "SC",
            "oldSymbolCode": "OLD",
            "newSymbolCode": "NEW",
        }
    ]
    probe.headers = {
        "Record-Total": "505001",
        "Record-Offset": "0",
        "Record-Limit": "5000",
        "Record-Max-Limit": "5000",
        "Total-Records-On-Page": "1",
    }
    probe.raise_for_status.return_value = None
    left = Mock(status_code=200)
    left.json.return_value = []
    left.headers = {
        "Record-Total": "0",
        "Record-Offset": "0",
        "Record-Limit": "5000",
        "Record-Max-Limit": "5000",
        "Total-Records-On-Page": "0",
    }
    left.raise_for_status.return_value = None

    with (
        patch.object(finra, "_token_cache", None),
        patch(
            "app.providers.finra.httpx.post",
            side_effect=[token_response, probe, left],
        ) as post,
    ):
        provider = FINRAProvider()
        first_page = provider.fetch_market_events_page(start=date(2026, 8, 1), end=date(2026, 8, 2))
        left_page = provider.fetch_market_events_page(
            start=date(2026, 8, 1),
            end=date(2026, 8, 2),
            cursor=first_page["next_cursor"],
        )

    assert first_page["complete"] is False
    assert first_page["events"][0].event_key == "finra:otc_daily_list:101"
    assert left_page["complete"] is False
    assert post.call_args_list[2].kwargs["json"]["compareFilters"] == [
        {"fieldName": "calendarDay", "compareType": "EQUAL", "fieldValue": "2026-08-01"}
    ]


def test_finra_daily_list_retains_fetched_rows_when_one_day_cannot_be_split(monkeypatch):
    start = end = date(2026, 8, 1)
    monkeypatch.setattr(settings, "FINRA_OTC_DAILY_LIST_URL", "https://example.test/daily")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    page = Mock(status_code=200)
    page.json.return_value = [
        {
            "OTCDailyListID": 991,
            "calendarDay": "2026-08-01",
            "vendor_extension": {"must_be_retained": True},
        }
    ]
    page.headers = {
        "Record-Total": "505001",
        "Record-Offset": "0",
        "Record-Limit": "5000",
        "Record-Max-Limit": "5000",
        "Total-Records-On-Page": "1",
    }
    page.raise_for_status.return_value = None
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, page]),
    ):
        result = FINRAProvider().fetch_market_events_page(start=start, end=end)

    assert result["complete"] is False
    assert result["next_cursor"] is not None
    assert result["next_url"] is None
    assert "persisted" in result["blocked_error"]
    assert result["events"][0].event_key == "finra:otc_daily_list:991"
    assert result["events"][0].raw_payload["vendor_extension"] == {"must_be_retained": True}


def test_finra_daily_list_unbounded_history_uses_available_date_partitions(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_DAILY_LIST_URL", "https://example.test/daily")
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    partitions = Mock(status_code=200)
    partitions.json.return_value = {
        "partitionFields": ["calendarDay"],
        "availablePartitions": [
            {"partitions": ["2026-08-02"]},
            {"partitions": ["2026-08-01"]},
        ],
    }
    partitions.raise_for_status.return_value = None
    data = Mock(status_code=200)
    data.json.return_value = [
        {"OTCDailyListID": 992, "calendarDay": "2026-08-01", "dailyListEventCode": "SA"}
    ]
    data.headers = {
        "Record-Total": "1",
        "Record-Offset": "0",
        "Record-Limit": "5000",
        "Record-Max-Limit": "5000",
        "Total-Records-On-Page": "1",
    }
    data.raise_for_status.return_value = None
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.get", return_value=partitions) as get,
        patch("app.providers.finra.httpx.post", side_effect=[token_response, data]) as post,
    ):
        provider = FINRAProvider()
        index_page = provider.fetch_market_events_page()
        data_page = provider.fetch_market_events_page(cursor=index_page["next_cursor"])

    assert index_page["events"] == []
    assert index_page["complete"] is False
    cursor_state = json.loads(index_page["next_cursor"])
    assert [(item["start"], item["end"]) for item in cursor_state["segments"]] == [
        ("2026-08-01", "2026-08-01"),
        ("2026-08-02", "2026-08-02"),
    ]
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer token"
    assert post.call_args.kwargs["json"]["compareFilters"] == [
        {"fieldName": "calendarDay", "compareType": "EQUAL", "fieldValue": "2026-08-01"}
    ]
    assert data_page["events"][0].event_key == "finra:otc_daily_list:992"


def test_finra_daily_list_fallback_identity_does_not_collapse_distinct_rows():
    common = {
        "calendarDay": "2026-08-01",
        "dailyListEventCode": "SC",
        "oldSymbolCode": "OLD",
        "newSymbolCode": "NEW",
    }
    rows = finra._finra_daily_list_events(
        [{**common, "cashAmountText": "1.00"}, {**common, "cashAmountText": "2.00"}]
    )

    assert len(rows) == 2
    assert rows[0].event_key != rows[1].event_key


def test_finra_daily_list_fallback_identity_keeps_identical_rows_distinct():
    row = {"calendarDay": "2026-08-01", "dailyListEventCode": "SC"}

    same_page = finra._finra_daily_list_events([row, row], fallback_scope="2026-08-01:2026-08-01:0")
    replay = finra._finra_daily_list_events([row, row], fallback_scope="2026-08-01:2026-08-01:0")
    other_page = finra._finra_daily_list_events([row], fallback_scope="2026-08-01:2026-08-01:5000")

    assert len({event.event_key for event in same_page}) == 2
    assert [event.event_key for event in same_page] == [event.event_key for event in replay]
    assert same_page[0].event_key != other_page[0].event_key


def test_finra_daily_list_normalization_retains_every_provider_row():
    rows = finra._finra_daily_list_events(
        [
            {"OTCDailyListID": 1, "calendarDay": "2026-08-01"},
            {"OTCDailyListID": 2, "calendarDay": "2026-08-02"},
            {"OTCDailyListID": 3, "calendarDay": "not-a-date"},
        ]
    )

    assert len(rows) == 3
    assert [row.event_key for row in rows] == [
        "finra:otc_daily_list:1",
        "finra:otc_daily_list:2",
        "finra:otc_daily_list:3",
    ]
    assert [row.raw_payload["OTCDailyListID"] for row in rows] == [1, 2, 3]


def test_finra_async_query_flow_honors_location_and_presigned_download(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 1024)
    token_response = Mock()
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    submit_response = Mock(status_code=202)
    submit_response.headers = {"location": "https://api.example.test/async-requests/job-123"}
    submit_response.content = b""
    submit_response.raise_for_status.return_value = None
    pending_response = Mock(status_code=202)
    pending_response.headers = {}
    pending_response.content = b'{"requestId":"job-123","status":"pending"}'
    pending_response.json.return_value = {"requestId": "job-123", "status": "pending"}
    pending_response.raise_for_status.return_value = None
    result_response = MagicMock(status_code=200)
    result_response.headers = {"content-length": "12"}
    result_response.iter_bytes.return_value = [b"result-", b"bytes"]
    result_response.raise_for_status.return_value = None
    result_response.__enter__.return_value = result_response
    result_response.__exit__.return_value = None

    result_response.json.side_effect = ValueError("streaming body not buffered")
    result_response.text = None
    with (
        patch.object(finra, "_token_cache", None),
        patch(
            "app.providers.finra.httpx.post", side_effect=[token_response, submit_response]
        ) as post,
        patch("app.providers.finra.httpx.get", return_value=pending_response) as get,
        patch("app.providers.finra.httpx.stream", return_value=result_response) as stream,
    ):
        provider = FINRAProvider()
        job = provider.submit_async_dataset(
            "https://api.example.test/data/group/equity/name/dataset",
            {"limit": 100000},
        )
        pending = provider.poll_async_dataset(job.status_url)
        measurement, token = activate(capture_response_payloads=True)
        try:
            result = provider.download_async_result("https://signed.example.test/result")
        finally:
            deactivate(token)

    assert job.request_id == "job-123"
    assert pending.status == "pending"
    assert result == b"result-bytes"
    assert post.call_args_list[1].kwargs["json"] == {"limit": 100000, "async": True}
    assert get.call_args_list[0].kwargs["headers"]["Authorization"] == "Bearer token"
    assert "Authorization" not in stream.call_args.kwargs["headers"]
    result_archive = measurement.response_payloads[-1]
    assert result_archive["kind"] == "finra_async_result"
    assert result_archive["complete"] is True
    assert result_archive["bytes_received"] == len(result)
    assert base64.b64decode(result_archive["body_base64"]) == result


def test_finra_async_poll_keeps_signed_link_transient_and_redacts_diagnostics(monkeypatch):
    signed_link = (
        "https://download.example.test/result.csv?X-Amz-Credential=credential-value"
        "&X-Amz-Signature=signature-value&X-Amz-Security-Token=session-value"
    )
    body = {
        "requestId": "job-456",
        "status": "complete",
        "resultLink": signed_link,
        "expires": "2026-10-04T12:00:00Z",
    }
    response = Mock(status_code=200)
    response.headers = {}
    response.content = b"status response"
    response.json.return_value = body
    monkeypatch.setattr(FINRAProvider, "_authenticated_token", lambda self: "oauth-token")

    measurement, token = activate(capture_response_payloads=True)
    try:
        with patch("app.providers.finra.httpx.get", return_value=response):
            job = FINRAProvider().poll_async_dataset(
                "https://api.example.test/async-requests/job-456"
            )
    finally:
        deactivate(token)

    assert job.result_link == signed_link
    assert job.raw_payload["resultLink"].startswith(
        "https://download.example.test/result.csv?X-Amz-Credential=<redacted>"
    )
    diagnostics = repr(job) + str(measurement.as_dict())
    for secret in ("credential-value", "signature-value", "session-value", "oauth-token"):
        assert secret not in diagnostics
    assert job.raw_payload["requestId"] == "job-456"


def test_finra_async_result_requires_a_positive_bound(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 0)
    with patch("app.providers.finra.httpx.stream") as stream:
        try:
            FINRAProvider().download_async_result("https://signed.example.test/result")
        except ValueError as exc:
            assert "requires FINRA_ASYNC_MAX_RESULT_BYTES" in str(exc)
        else:
            raise AssertionError("unbounded FINRA async downloads must fail closed")
    stream.assert_not_called()


def test_finra_async_result_rejects_declared_payload_above_bound():
    response = MagicMock(status_code=200)
    response.headers = {"content-length": "2048"}
    response.iter_bytes.return_value = [b"small"]
    response.raise_for_status.return_value = None
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    with patch("app.providers.finra.httpx.stream", return_value=response):
        try:
            FINRAProvider().download_async_result(
                "https://signed.example.test/result", max_bytes=1024
            )
        except ValueError as exc:
            assert "exceeds configured byte bound" in str(exc)
        else:
            raise AssertionError("declared FINRA async payload over bound must fail closed")


def test_finra_async_result_measures_bytes_received_before_stream_failure():
    request = httpx.Request("GET", "https://signed.example.test/result")

    def interrupted_body():
        yield b"received-before-reset"
        raise httpx.ReadError("connection reset", request=request)

    response = MagicMock(status_code=200)
    response.headers = {"content-length": "128"}
    response.iter_bytes.return_value = interrupted_body()
    response.json.side_effect = ValueError("streaming body not buffered")
    response.text = None
    response.raise_for_status.return_value = None
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    measurement, token = activate(capture_response_payloads=True)
    try:
        with (
            patch("app.providers.finra.httpx.stream", return_value=response),
            pytest.raises(ProviderResponseError, match="transport failure"),
        ):
            FINRAProvider().download_async_result(
                "https://signed.example.test/result", max_bytes=1024
            )
    finally:
        deactivate(token)

    assert measurement.http_requests == 1
    assert measurement.response_bytes == len(b"received-before-reset")
    archived = measurement.response_payloads[-1]
    assert archived == {
        "kind": "finra_async_result",
        "encoding": "base64",
        "complete": False,
        "bytes_received": len(b"received-before-reset"),
        "sha256": hashlib.sha256(b"received-before-reset").hexdigest(),
        "body_base64": base64.b64encode(b"received-before-reset").decode("ascii"),
    }


def test_finra_async_result_archives_chunk_that_exceeds_bound():
    response = MagicMock(status_code=200)
    response.headers = {"content-length": "9"}
    response.iter_bytes.return_value = [b"received", b"-more"]
    response.raise_for_status.return_value = None
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    measurement, token = activate(capture_response_payloads=True)
    try:
        with (
            patch("app.providers.finra.httpx.stream", return_value=response),
            pytest.raises(ValueError, match="exceeds configured byte bound"),
        ):
            FINRAProvider().download_async_result(
                "https://signed.example.test/result", max_bytes=10
            )
    finally:
        deactivate(token)

    received = b"received-more"
    archived = measurement.response_payloads[-1]
    assert archived["complete"] is False
    assert archived["bytes_received"] == len(received)
    assert base64.b64decode(archived["body_base64"]) == received


def test_finra_async_result_transport_failure_is_typed():
    failure = httpx.ConnectError(
        "connection failed",
        request=httpx.Request("GET", "https://signed.example.test/result"),
    )
    with patch("app.providers.finra.httpx.stream", side_effect=failure):
        with pytest.raises(ProviderResponseError) as exc_info:
            FINRAProvider().download_async_result(
                "https://signed.example.test/result", max_bytes=1024
            )
    assert exc_info.value.provider_name == "finra"


def test_finra_transport_failure_is_typed(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    failure = httpx.ConnectError(
        "connection failed",
        request=httpx.Request("POST", "https://api.finra.org/token"),
    )
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=failure),
    ):
        with pytest.raises(ProviderResponseError) as exc_info:
            FINRAProvider().fetch_short_interest("AAPL")
    assert exc_info.value.provider_name == "finra"


def test_finra_http_rate_limit_preserves_provider_capacity_evidence(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.status_code = 200
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    token_response.raise_for_status.return_value = None
    response = httpx.Response(
        429,
        headers={"Retry-After": "7", "X-RateLimit-Remaining": "0", "Authorization": "secret"},
        request=httpx.Request("POST", "https://example.test/short"),
        json={"message": "too many requests"},
    )
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", side_effect=[token_response, response]),
    ):
        with pytest.raises(ProviderRateLimitError) as exc_info:
            FINRAProvider().fetch_short_interest("AAPL")
    error = exc_info.value
    assert error.provider_name == "finra"
    assert error.status_code == 429
    assert error.scope == "ip"
    assert error.retry_at is not None
    assert error.headers == {"retry-after": "7", "x-ratelimit-remaining": "0"}


def test_finra_malformed_oauth_payload_is_typed(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    token_response = Mock()
    token_response.status_code = 200
    token_response.raise_for_status.return_value = None
    token_response.json.side_effect = ValueError("not json")
    with (
        patch.object(finra, "_token_cache", None),
        patch("app.providers.finra.httpx.post", return_value=token_response),
    ):
        with pytest.raises(ProviderResponseError) as exc_info:
            FINRAProvider().fetch_short_interest("AAPL")
    assert exc_info.value.provider_name == "finra"
