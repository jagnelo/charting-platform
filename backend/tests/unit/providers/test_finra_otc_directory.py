from unittest.mock import Mock, patch

import httpx
import pytest

import app.providers.finra_otc_directory as directory
from app.config import settings
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from app.providers.finra_otc_directory import FINRAOTCDirectoryProvider


def test_finra_otc_directory_requires_explicit_source(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "")
    with pytest.raises(ProviderNotConfiguredError):
        FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)


def test_finra_otc_directory_parses_status_and_preserves_source(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "https://example.test/otc.txt")
    response = Mock()
    response.text = (
        "Issue_Sym_id|Issue_Type_Cd|Issue_Short_Nm|Status|Mkt_Cat|OATS_Rptbl_Fl|Unit_of_Trade\n"
        "AAA|Common Stock|Alpha Corp|Active|u|Y|100\n"
        "BBB|Common Stock|Beta Corp|Ineligible|u|N|100\n"
    )
    response.raise_for_status.return_value = None
    with (
        patch.object(directory, "_cache", None),
        patch("app.providers.finra_otc_directory.httpx.get", return_value=response) as get,
    ):
        page = FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)
    assert page["total"] == 2
    assert page["quotes"][0]["symbol"] == "AAA"
    assert page["quotes"][0]["status"] == "active"
    assert page["quotes"][1]["status"] == "inactive"
    assert page["quotes"][0]["source_record"]["issue_sym_id"] == "AAA"
    assert page["source_files"] == ["https://example.test/otc.txt"]
    get.assert_called_once()


def test_finra_otc_directory_supports_current_dapi_partition_pagination(monkeypatch):
    dapi_url = "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", dapi_url)

    partitions = Mock()
    partitions.json.return_value = {
        "availablePartitions": [{"partitions": ["2026-09-04", "2026-09-03"]}]
    }
    partitions.raise_for_status.return_value = None

    first_page = Mock()
    first_page.headers = {"record-total": "2"}
    first_page.json.return_value = [
        {
            "issueSymbolIdentifier": "AAA",
            "securityDescription": "Alpha Corp Common Stock",
            "issueType": "Common Stock",
            "asOfDate": "2026-09-04",
            "finraIssuerIdentifier": "1",
        },
        {
            "issueSymbolIdentifier": "BBB",
            "securityDescription": "Beta Corp Common Stock",
            "issueType": "Common Stock",
            "asOfDate": "2026-09-04",
            "finraIssuerIdentifier": "2",
        },
    ]
    first_page.raise_for_status.return_value = None

    with (
        patch.object(directory, "_cache", None),
        patch("app.providers.finra_otc_directory.httpx.get", return_value=partitions) as get,
        patch("app.providers.finra_otc_directory.httpx.post", return_value=first_page) as post,
    ):
        page = FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)

    assert page["total"] == 2
    assert [row["symbol"] for row in page["quotes"]] == ["AAA", "BBB"]
    assert page["quotes"][0]["status"] == "active"
    assert page["quotes"][0]["as_of_date"] == "2026-09-04"
    assert page["quotes"][0]["source_record"]["finraIssuerIdentifier"] == "1"
    get.assert_called_once_with(
        "https://api.finra.org/partitions/group/otcMarket/name/otcSecurityMaster",
        headers={"User-Agent": settings.NASDAQ_USER_AGENT, "Accept": "application/json"},
        timeout=30,
    )
    post.assert_called_once()
    assert post.call_args.kwargs["json"]["compareFilters"][0]["fieldValue"] == "2026-09-04"


def test_finra_otc_directory_continues_after_payload_capped_short_page(monkeypatch):
    dapi_url = "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", dapi_url)

    partitions = Mock()
    partitions.json.return_value = {"availablePartitions": [{"partitions": ["2026-09-04"]}]}
    partitions.raise_for_status.return_value = None

    def page_response(symbol: str) -> Mock:
        response = Mock()
        response.headers = {"record-total": "2", "record-limit": "1"}
        response.json.return_value = [
            {
                "issueSymbolIdentifier": symbol,
                "securityDescription": f"{symbol} Corp Common Stock",
                "asOfDate": "2026-09-04",
            }
        ]
        response.raise_for_status.return_value = None
        return response

    with (
        patch.object(directory, "_cache", None),
        patch("app.providers.finra_otc_directory.httpx.get", return_value=partitions),
        patch(
            "app.providers.finra_otc_directory.httpx.post",
            side_effect=[page_response("AAA"), page_response("BBB")],
        ) as post,
    ):
        rows = directory._fetch_dapi_rows(dapi_url)

    assert [row["symbol"] for row in rows] == ["AAA", "BBB"]
    assert [call.kwargs["json"]["offset"] for call in post.call_args_list] == [0, 1]


def test_finra_otc_directory_transport_failure_is_typed(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "https://example.test/otc.txt")
    failure = httpx.ConnectError(
        "connection failed",
        request=httpx.Request("GET", "https://example.test/otc.txt"),
    )
    with patch.object(directory, "_cache", None), patch(
        "app.providers.finra_otc_directory.httpx.get", side_effect=failure
    ):
        with pytest.raises(ProviderResponseError) as exc_info:
            FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)
    assert exc_info.value.provider_name == "finra_otc_directory"


def test_finra_otc_dapi_malformed_payload_is_typed(monkeypatch):
    dapi_url = "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", dapi_url)
    partitions = Mock()
    partitions.raise_for_status.return_value = None
    partitions.json.side_effect = ValueError("not json")
    with patch.object(directory, "_cache", None), patch(
        "app.providers.finra_otc_directory.httpx.get", return_value=partitions
    ):
        with pytest.raises(ProviderResponseError) as exc_info:
            FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)
    assert exc_info.value.provider_name == "finra_otc_directory"


@pytest.mark.parametrize(
    "text,match",
    [
        ("", "omitted CSV headers"),
        ("symbol|name\nAAA|Alpha\n", "omitted required CSV columns"),
        (
            "Issue_Sym_id|Issue_Short_Nm|Status|Mkt_Cat\n|Alpha|Active|u\n",
            "without issue_sym_id",
        ),
        (
            "Issue_Sym_id|Issue_Short_Nm|Status|Mkt_Cat\nAAA|Alpha|Active\n",
            "malformed CSV row",
        ),
        (
            'Issue_Sym_id|Issue_Short_Nm|Status|Mkt_Cat\nAAA|"Alpha|Active|u\n',
            "malformed CSV",
        ),
    ],
)
def test_finra_otc_legacy_directory_rejects_malformed_rows(monkeypatch, text, match):
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "https://example.test/otc.txt")
    response = Mock()
    response.text = text
    response.raise_for_status.return_value = None
    with (
        patch.object(directory, "_cache", None),
        patch("app.providers.finra_otc_directory.httpx.get", return_value=response),
    ):
        with pytest.raises(ProviderResponseError, match=match):
            FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)


def test_finra_otc_legacy_http_failure_is_typed(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "https://example.test/otc.txt")
    response = httpx.Response(
        500,
        request=httpx.Request("GET", "https://example.test/otc.txt"),
    )
    with patch.object(directory, "_cache", None), patch(
        "app.providers.finra_otc_directory.httpx.get", return_value=response
    ):
        with pytest.raises(ProviderResponseError) as exc_info:
            FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)
    assert exc_info.value.provider_name == "finra_otc_directory"
    assert exc_info.value.status_code == 500


def test_finra_otc_dapi_rate_limit_preserves_headers(monkeypatch):
    dapi_url = "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", dapi_url)
    partitions = Mock()
    partitions.raise_for_status.return_value = None
    partitions.json.return_value = {"availablePartitions": [{"partitions": ["2026-09-04"]}]}
    response = httpx.Response(
        429,
        headers={"Retry-After": "60", "X-RateLimit-Remaining": "0"},
        request=httpx.Request("POST", dapi_url),
        json={"error": "rate limit"},
    )
    with (
        patch.object(directory, "_cache", None),
        patch("app.providers.finra_otc_directory.httpx.get", return_value=partitions),
        patch("app.providers.finra_otc_directory.httpx.post", return_value=response),
    ):
        with pytest.raises(ProviderRateLimitError) as exc_info:
            FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)
    assert exc_info.value.status_code == 429
    assert exc_info.value.scope == "ip"
    assert exc_info.value.headers == {"retry-after": "60", "x-ratelimit-remaining": "0"}
    assert exc_info.value.retry_at is not None
