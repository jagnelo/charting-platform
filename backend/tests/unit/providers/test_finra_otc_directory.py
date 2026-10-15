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
from app.providers.finra_otc_directory import (
    FINRAOTCDirectoryProvider,
    parse_otc_markets_security_master,
)
from app.providers.telemetry import activate as activate_provider_telemetry
from app.providers.telemetry import deactivate as deactivate_provider_telemetry

_OTC_MARKETS_SECURITY_MASTER = (
    "Date|SecID|CompID|Symbol|CUSIP|Company Name|Security Name|Security Type|"
    "Security Class|Security Status|OTC Tier|Tier ID|Overnight Eligible|Reference Price\n"
    "2026-09-16|100|200|AAA|123456789|Alpha Corp|Alpha Common|common|A|A|OTCQX|2|Y|12.3456\n"
    "2026-09-16|101|201|BBB||Beta Corp|Beta Warrant|warrant|B|H|Grey Market|30|N|0.125\n"
)

_ORF_SECURITY_MASTER = (
    "FINRA_OTC_ID|CUSIP_ID|SYM_CD|SYM_SUF_CD|SCRTY_DS|RND_LOT_QT|CPN_RT|"
    "DTC_ELGBL_FL|SCRTY_TYPE_CD|WIS_DSTRD_CD|STTS_CD|NACTV_DT|TEST_SCRTY_FL|"
    "PRICE_CK_FL|SCRTY_EFCTV_TS|SIP_SYM_ID|OTCBB_QUOTE_FL|CLASS_TX|OFRNG_TYPE_CD\n"
    "100|123456789|AAA||Alpha Corp|100|||||A||N|Y|20260916120000|AAA|Y|A|\n"
    "Footer - Count: 00000001, Facility: ORF, File Created: 20260916120000\n"
)
_ORF_INACTIVE_SECURITY_MASTER = _ORF_SECURITY_MASTER.replace(
    "100|123456789|AAA||Alpha Corp|100|||||A||N|Y|20260916120000|AAA|Y|A|",
    "101||BBB|P|Beta Corp|100|||||I|20250916120000|N|Y|20250916120000|BBB|Y|B|",
)


def test_finra_otc_directory_requires_explicit_source(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "")
    with pytest.raises(ProviderNotConfiguredError):
        FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)


def test_finra_otc_directory_parses_status_and_preserves_source(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "https://example.test/otc.txt")
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "")
    payload = (
        "Issue_Sym_id|Issue_Type_Cd|Issue_Short_Nm|Status|Mkt_Cat|OATS_Rptbl_Fl|Unit_of_Trade\n"
        "AAA|Common Stock|Alpha Corp|Active|u|Y|100\n"
        "BBB|Common Stock|Beta Corp|Ineligible|u|N|100\n"
    )
    rows = directory._parse_directory(payload)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "AAA"
    assert rows[0]["status"] == "active"
    assert rows[1]["status"] == "inactive"
    assert rows[0]["source_record"]["issue_sym_id"] == "AAA"


def test_finra_otc_directory_rejects_undocumented_single_url_without_network(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "")
    monkeypatch.setattr(
        settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "https://api.finra.org/otcSecurityMaster"
    )
    with patch("app.providers.finra_otc_directory.httpx.get") as get:
        with pytest.raises(ProviderNotConfiguredError, match="official FINRA OTC Query API"):
            FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)
    get.assert_not_called()


def test_finra_otc_directory_orf_cache_is_scoped_to_credentials(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
    )
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF",
    )
    monkeypatch.setattr(settings, "FINRA_ORF_USERNAME", "traqs-user")
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN", "first-refresh-token")
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSED", True)
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "CGS agreement ref")
    first_active = Mock(text=_ORF_SECURITY_MASTER, status_code=200, headers={})
    first_inactive = Mock(text=_ORF_INACTIVE_SECURITY_MASTER, status_code=200, headers={})
    second_active = Mock(
        text=_ORF_SECURITY_MASTER.replace("AAA", "CCC"), status_code=200, headers={}
    )
    second_inactive = Mock(
        text=_ORF_INACTIVE_SECURITY_MASTER.replace("BBB", "DDD"),
        status_code=200,
        headers={},
    )
    with (
        patch.object(directory, "_cache", None),
        patch("app.providers.finra_otc_directory._orf_access_token", return_value="token"),
        patch(
            "app.providers.finra_otc_directory.httpx.post",
            side_effect=[first_active, first_inactive, second_active, second_inactive],
        ) as post,
    ):
        first_page = FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)
        monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN", "second-refresh-token")
        second_page = FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)

    assert first_page["quotes"][0]["symbol"] == "AAA"
    assert second_page["quotes"][0]["symbol"] == "CCC"
    assert post.call_count == 4


def test_parse_otc_markets_security_master_fixture_without_enabling_live_source():
    rows = parse_otc_markets_security_master(_OTC_MARKETS_SECURITY_MASTER)
    assert len(rows) == 2
    assert rows[0]["security_id"] == "100"
    assert rows[0]["cusip"] == "123456789"
    assert rows[0]["status"] == "active"
    assert rows[0]["overnight_eligible"] == "Y"
    assert rows[1]["status"] == "inactive"
    assert rows[1]["financial_status"] == "H"


def test_orf_security_master_keeps_rows_when_unlicensed_cusip_field_is_blank(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSED", False)
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "")
    payload = _ORF_SECURITY_MASTER.replace("100|123456789|", "100||")

    rows = directory._parse_orf_security_master(payload, expected_active=True)

    assert len(rows) == 1
    assert rows[0]["finra_otc_id"] == "100"
    assert rows[0]["symbol"] == "AAA"
    assert rows[0]["cusip"] is None


def test_finra_otc_directory_fetches_documented_orf_active_and_inactive_masters(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
    )
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF",
    )
    monkeypatch.setattr(settings, "FINRA_ORF_USERNAME", "traqs-user")
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSED", True)
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "CGS agreement ref")
    active = Mock(text=_ORF_SECURITY_MASTER, status_code=200)
    active.headers = {}
    active.raise_for_status.return_value = None
    inactive = Mock(text=_ORF_INACTIVE_SECURITY_MASTER, status_code=200)
    inactive.headers = {}
    inactive.raise_for_status.return_value = None
    with (
        patch.object(directory, "_cache", None),
        patch("app.providers.finra_otc_directory._orf_access_token", return_value="token"),
        patch(
            "app.providers.finra_otc_directory.httpx.post",
            side_effect=[active, inactive],
        ) as post,
    ):
        page = FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)
        subsequent_page = FINRAOTCDirectoryProvider().discover_universe_page("OTC", 1)
    assert page["total"] == 2
    assert [row["symbol"] for row in page["quotes"]] == ["AAA", "BBB"]
    assert subsequent_page["quotes"] == [page["quotes"][1]]
    assert subsequent_page["source_documents"] == {}
    assert page["quotes"][0]["status"] == "active"
    assert page["quotes"][1]["status"] == "inactive"
    assert page["quotes"][1]["symbol_suffix"] == "P"
    assert page["source_files"] == [
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF",
    ]
    assert page["source_documents"] == {
        page["source_files"][0]: _ORF_SECURITY_MASTER,
        page["source_files"][1]: _ORF_INACTIVE_SECURITY_MASTER,
    }
    assert all(
        call.kwargs["headers"]["Authorization"] == "Bearer token" for call in post.call_args_list
    )
    assert all(call.kwargs["data"] == {"username": "traqs-user"} for call in post.call_args_list)


def test_orf_active_file_response_is_observed_when_inactive_download_fails(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
    )
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF",
    )
    monkeypatch.setattr(settings, "FINRA_ORF_USERNAME", "traqs-user")
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSED", True)
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "fixture-license")
    active = httpx.Response(
        200,
        text=_ORF_SECURITY_MASTER,
        request=httpx.Request("POST", "https://apidownload.finratraqs.org/active"),
    )

    with (
        patch.object(directory, "_cache", None),
        patch("app.providers.finra_otc_directory._orf_access_token", return_value="access-token"),
        patch(
            "app.providers.finra_otc_directory.httpx.post",
            side_effect=[active, httpx.ReadTimeout("inactive file unavailable")],
        ),
    ):
        measurement, token = activate_provider_telemetry(capture_response_payloads=True)
        try:
            with pytest.raises(ProviderResponseError, match="transport failure"):
                FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)
        finally:
            deactivate_provider_telemetry(token)

    assert measurement.http_requests == 1
    assert measurement.response_payloads == [_ORF_SECURITY_MASTER]


def test_finra_otc_directory_orf_rejects_cusip_without_license_evidence(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
    )
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF",
    )
    monkeypatch.setattr(settings, "FINRA_ORF_USERNAME", "traqs-user")
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSED", False)
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "")
    active = Mock(text=_ORF_SECURITY_MASTER, status_code=200)
    active.headers = {}
    inactive = Mock(text=_ORF_INACTIVE_SECURITY_MASTER, status_code=200)
    inactive.headers = {}
    with (
        patch.object(directory, "_cache", None),
        patch("app.providers.finra_otc_directory._orf_access_token", return_value="token"),
        patch(
            "app.providers.finra_otc_directory.httpx.post",
            side_effect=[active, inactive],
        ),
        pytest.raises(ProviderResponseError, match="CGS license evidence"),
    ):
        FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)


def test_finra_otc_directory_orf_requires_traqs_refresh_credentials(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
    )
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF",
    )
    monkeypatch.setattr(settings, "FINRA_ORF_USERNAME", "")
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN", "")
    with pytest.raises(ProviderNotConfiguredError, match="FINRA_ORF_USERNAME"):
        FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)


def test_finra_otc_directory_orf_requires_inactive_master(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
    )
    monkeypatch.setattr(settings, "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL", "")
    with pytest.raises(ProviderNotConfiguredError, match="INACTIVE"):
        FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)


def test_finra_otc_directory_orf_requires_documented_download_handler_path(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://apidownload.finratraqs.org/not-the-download-handler?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
    )
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF",
    )
    with pytest.raises(ProviderNotConfiguredError, match="DownloadHandler"):
        FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (_ORF_SECURITY_MASTER.rsplit("\n", 2)[0] + "\n", "footer"),
        (
            _ORF_SECURITY_MASTER.replace("Count: 00000001", "Count: 00000002"),
            "footer count",
        ),
        (
            _ORF_SECURITY_MASTER.replace("Facility: ORF", "Facility: TRACE"),
            "footer",
        ),
    ],
)
def test_orf_security_master_requires_and_checks_documented_footer(payload, match, monkeypatch):
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSED", True)
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "fixture license")
    with pytest.raises(ValueError, match=match):
        directory._parse_orf_security_master(payload, expected_active=True)


def test_parse_otc_markets_security_master_verifies_validation_record_count():
    validation = (
        "Datafile|Source|Date/Time|Record Count\n"
        "otc-overnight-sec-2026-09-16-1725.txt|OTC Markets Group|"
        "2026-09-16 17:25:00|2\n"
    )
    rows = parse_otc_markets_security_master(
        _OTC_MARKETS_SECURITY_MASTER,
        validation_text=validation,
    )
    assert [row["symbol"] for row in rows] == ["AAA", "BBB"]


@pytest.mark.parametrize(
    "validation,match",
    [
        (
            "Datafile|Source|Date/Time|Record Count\n"
            "file|OTC Markets Group|2026-09-16 17:25:00|1\n",
            "record count does not match",
        ),
        (
            "Datafile|Source|Date/Time|Record Count\n" "file|Other Source|2026-09-16 17:25:00|2\n",
            "unexpected source",
        ),
        (
            "Datafile|Source|Date/Time|Record Count\n"
            "file|OTC Markets Group|2026-09-16 17:25:00|not-a-count\n",
            "invalid record count",
        ),
    ],
)
def test_parse_otc_markets_security_master_rejects_invalid_validation_file(validation, match):
    with pytest.raises(ProviderResponseError, match=match):
        parse_otc_markets_security_master(
            _OTC_MARKETS_SECURITY_MASTER,
            validation_text=validation,
        )


@pytest.mark.parametrize(
    "row,match",
    [
        (
            "2026-09-16|100|200|AAA|123456789|Alpha Corp|Alpha Common|common|A|A|OTCQX|2|Y|12.3456\n"
            "2026-09-16|101|201|AAA||Beta Corp|Beta Warrant|warrant|B|H|Grey Market|30|N|0.125\n",
            "duplicate symbol",
        ),
        (
            "2026-09-16|100|200|AAA|123456789|Alpha Corp|Alpha Common|common|A|X|OTCQX|2|Y|12.3456\n",
            "unknown security status",
        ),
    ],
)
def test_finra_otc_directory_rejects_invalid_otc_markets_rows(row, match):
    response_text = (
        "Date|SecID|CompID|Symbol|CUSIP|Company Name|Security Name|Security Type|"
        "Security Class|Security Status|OTC Tier|Tier ID|Overnight Eligible|Reference Price\n" + row
    )
    with pytest.raises(ProviderResponseError, match=match):
        directory._parse_directory(response_text)


def test_legacy_dapi_parser_follows_every_partition_page_as_fixture_only(monkeypatch):
    dapi_url = "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", dapi_url)
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")

    partitions = Mock()
    partitions.json.return_value = {
        "availablePartitions": [{"partitions": ["2026-09-04", "2026-09-03"]}]
    }
    partitions.raise_for_status.return_value = None

    first_page = Mock()
    first_page.headers = {
        "record-total": "2",
        "record-offset": "0",
        "record-limit": "5000",
        "record-max-limit": "5000",
    }
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
        patch.object(directory, "_dapi_partition_cache", None),
        patch("app.providers.finra_otc_directory._access_token", return_value="token"),
        patch("app.providers.finra_otc_directory.httpx.get", return_value=partitions) as get,
        patch("app.providers.finra_otc_directory.httpx.post", return_value=first_page) as post,
    ):
        rows = directory._fetch_dapi_rows(dapi_url)

    assert len(rows) == 2
    assert [row["symbol"] for row in rows] == ["AAA", "BBB"]
    assert rows[0]["status"] == "active"
    assert rows[0]["as_of_date"] == "2026-09-04"
    assert rows[0]["source_record"]["finraIssuerIdentifier"] == "1"
    get.assert_called_once_with(
        "https://api.finra.org/partitions/group/otcMarket/name/otcSecurityMaster",
        headers={
            "Authorization": "Bearer token",
            "User-Agent": settings.NASDAQ_USER_AGENT,
            "Accept": "application/json",
        },
        timeout=30,
    )
    post.assert_called_once()
    assert post.call_args.kwargs["json"]["compareFilters"][0]["fieldValue"] == "2026-09-04"


def test_query_api_discovery_exposes_lossless_page_and_raw_documents(monkeypatch):
    dapi_url = "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_otc_query_api")
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", dapi_url)
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    partitions = Mock(
        text='{"availablePartitions":[{"partitions":["2026-09-04"]}]}',
        status_code=200,
        headers={},
    )
    partitions.json.return_value = {"availablePartitions": [{"partitions": ["2026-09-04"]}]}
    partitions.raise_for_status.return_value = None
    page_response = Mock(
        text=(
            '[{"issueSymbolIdentifier":"AAA","securityDescription":"Alpha",'
            '"asOfDate":"2026-09-04","finraIssuerIdentifier":"1"}]'
        ),
        status_code=200,
        headers={
            "record-total": "1",
            "record-offset": "0",
            "record-limit": "5000",
            "record-max-limit": "5000",
        },
    )
    page_response.json.return_value = [
        {
            "issueSymbolIdentifier": "AAA",
            "securityDescription": "Alpha",
            "asOfDate": "2026-09-04",
            "finraIssuerIdentifier": "1",
        }
    ]
    page_response.raise_for_status.return_value = None

    with (
        patch.object(directory, "_dapi_partition_cache", None),
        patch("app.providers.finra_otc_directory._access_token", return_value="token"),
        patch("app.providers.finra_otc_directory.httpx.get", return_value=partitions),
        patch("app.providers.finra_otc_directory.httpx.post", return_value=page_response),
    ):
        provider = FINRAOTCDirectoryProvider()
        page = provider.discover_universe_page("EQUITY", 0)

    assert provider.supported_discovery_types() == ["EQUITY"]
    assert page["total"] == 1
    assert page["complete"] is True
    assert page["next_offset"] is None
    assert page["source_snapshot_date"] == "2026-09-04"
    assert page["quotes"][0]["symbol"] == "AAA"
    assert len(page["source_documents"]) == 2
    assert all(isinstance(value, str) for value in page["source_documents"].values())


def test_finra_otc_directory_continues_after_payload_capped_short_page(monkeypatch):
    dapi_url = "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", dapi_url)
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")

    partitions = Mock()
    partitions.json.return_value = {"availablePartitions": [{"partitions": ["2026-09-04"]}]}
    partitions.raise_for_status.return_value = None

    def page_response(symbol: str, offset: int) -> Mock:
        response = Mock()
        response.headers = {
            "record-total": "2",
            "record-offset": str(offset),
            "record-limit": "1",
            "record-max-limit": "5000",
        }
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
        patch.object(directory, "_dapi_partition_cache", None),
        patch("app.providers.finra_otc_directory._access_token", return_value="token"),
        patch("app.providers.finra_otc_directory.httpx.get", return_value=partitions),
        patch(
            "app.providers.finra_otc_directory.httpx.post",
            side_effect=[page_response("AAA", 0), page_response("BBB", 1)],
        ) as post,
    ):
        rows = directory._fetch_dapi_rows(dapi_url)

    assert [row["symbol"] for row in rows] == ["AAA", "BBB"]
    assert [call.kwargs["json"]["offset"] for call in post.call_args_list] == [0, 1]


def test_finra_otc_directory_unreviewed_transport_is_never_attempted(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "")
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "https://example.test/otc.txt")
    with patch("app.providers.finra_otc_directory.httpx.get") as get:
        with pytest.raises(ProviderNotConfiguredError):
            FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)
    get.assert_not_called()


def test_finra_otc_dapi_malformed_payload_is_typed(monkeypatch):
    dapi_url = "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", dapi_url)
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
    partitions = Mock()
    partitions.raise_for_status.return_value = None
    partitions.json.side_effect = ValueError("not json")
    with (
        patch.object(directory, "_dapi_partition_cache", None),
        patch("app.providers.finra_otc_directory._access_token", return_value="token"),
        patch("app.providers.finra_otc_directory.httpx.get", return_value=partitions),
    ):
        with pytest.raises(ProviderResponseError) as exc_info:
            directory._fetch_dapi_rows(dapi_url)
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
    with pytest.raises(ProviderResponseError, match=match):
        directory._parse_directory(text)


def test_finra_otc_legacy_http_failure_is_typed(monkeypatch):
    response = httpx.Response(
        500,
        request=httpx.Request("GET", "https://example.test/otc.txt"),
    )
    with pytest.raises(ProviderResponseError) as exc_info:
        directory._raise_for_provider_status(response)
    assert exc_info.value.provider_name == "finra_otc_directory"
    assert exc_info.value.status_code == 500


def test_finra_otc_dapi_rate_limit_preserves_headers(monkeypatch):
    dapi_url = "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", dapi_url)
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "secret")
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
        patch.object(directory, "_dapi_partition_cache", None),
        patch("app.providers.finra_otc_directory._access_token", return_value="token"),
        patch("app.providers.finra_otc_directory.httpx.get", return_value=partitions),
        patch("app.providers.finra_otc_directory.httpx.post", return_value=response),
    ):
        with pytest.raises(ProviderRateLimitError) as exc_info:
            directory._fetch_dapi_rows(dapi_url)
    assert exc_info.value.status_code == 429
    assert exc_info.value.scope == "ip"
    assert exc_info.value.headers == {"retry-after": "60", "x-ratelimit-remaining": "0"}
    assert exc_info.value.retry_at is not None
