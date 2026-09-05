from unittest.mock import Mock, patch

import pytest

import app.providers.finra_otc_directory as directory
from app.config import settings
from app.providers.errors import ProviderNotConfiguredError
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
        patch(
            "app.providers.finra_otc_directory.httpx.get", return_value=partitions
        ) as get,
        patch(
            "app.providers.finra_otc_directory.httpx.post", return_value=first_page
        ) as post,
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
