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
