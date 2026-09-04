from datetime import date
from unittest.mock import Mock, patch

from app.config import settings
from app.providers.finra import FINRAProvider


def test_finra_parser_keeps_publication_and_raw_provenance(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_SHORT_INTEREST_URL", "https://example.test/short")
    response = Mock()
    response.json.return_value = {
        "data": [
            {
                "settlementDate": "2026-08-29",
                "publicationDate": "2026-09-01",
                "shortPosition": "1200",
                "shortPercentFloat": "0.12",
                "daysToCover": "2.5",
                "issueIdentifier": "CUSIP123",
            }
        ]
    }
    response.raise_for_status.return_value = None
    with patch("app.providers.finra.httpx.post", return_value=response):
        rows = FINRAProvider().fetch_short_interest("AAPL", start=date(2026, 8, 1))
    assert rows[0].settlement_date == date(2026, 8, 29)
    assert rows[0].short_position == 1200
    assert rows[0].raw_payload["issueIdentifier"] == "CUSIP123"
