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
