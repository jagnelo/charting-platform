from datetime import UTC, date, datetime

from app.schemas.options import (
    OptionChainResponse,
    OptionChainRowOut,
    OptionChainSnapshotSummaryOut,
    OptionQuotePointOut,
)


def test_option_chain_response_serializes_all_timestamps_as_canonical_utc_z():
    response = OptionChainResponse(
        symbol="SPY",
        expiration=date(2026, 12, 18),
        available_expirations=[date(2026, 12, 18)],
        snapshot=OptionChainSnapshotSummaryOut(
            id=7,
            observed_at=datetime(2026, 9, 12, 16, 30),
            fetched_at=datetime(2026, 9, 12, 17, 30, tzinfo=UTC),
            contract_count=2,
        ),
        rows=[
            OptionChainRowOut(
                instrument_id=42,
                symbol="SPY 2026-12-18 C 600",
                name="SPY 2026-12-18 C 600",
                right="call",
                style="american",
                strike=600,
                expiry_date=date(2026, 12, 18),
                observed_at=datetime(2026, 9, 12, 16, 30),
            )
        ],
    )

    payload = response.model_dump(mode="json")

    assert payload["expiration"] == "2026-12-18"
    assert payload["snapshot"]["observed_at"] == "2026-09-12T16:30:00Z"
    assert payload["snapshot"]["fetched_at"] == "2026-09-12T17:30:00Z"
    assert payload["rows"][0]["observed_at"] == "2026-09-12T16:30:00Z"


def test_option_quote_history_serializes_observation_timestamp_as_canonical_utc_z():
    point = OptionQuotePointOut(
        observed_at=datetime(2026, 9, 12, 18, 30, tzinfo=UTC),
        bid=1.25,
    )

    assert point.model_dump(mode="json")["observed_at"] == "2026-09-12T18:30:00Z"
