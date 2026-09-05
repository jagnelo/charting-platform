from datetime import date
from unittest.mock import Mock, patch

from app.config import settings
from app.providers import finra
from app.providers.finra import FINRAProvider


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
    response.raise_for_status.return_value = None
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
