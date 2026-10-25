"""Explicit test-only ETF history fixtures for consumer integration tests."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument


def seed_etf_profile(
    db: Session,
    client: TestClient,
    admin_headers: dict[str, str],
    symbol: str,
) -> ETFProfile:
    """Create only the ETF identity/profile; do not simulate an import or provider success."""

    response = client.patch(
        f"/api/v1/etf-holdings/{symbol}/profile",
        headers=admin_headers,
        json={
            "legal_metadata": {
                "source_tier": "none",
                "test_fixture_only": True,
            }
        },
    )
    assert response.status_code == 200, response.text
    profile = db.get(ETFProfile, response.json()["id"])
    assert profile is not None
    assert (profile.legal_metadata or {}).get("source_tier") == "none"
    return profile


def seed_historical_snapshot(
    db: Session,
    *,
    profile: ETFProfile,
    composition_date: date,
    known_at: datetime,
    rows: list[dict[str, Any]],
    instrument_type_id: int | None = None,
) -> ETFHoldingsSnapshot:
    """Seed synthetic, non-current history without passing old known_at through ingest."""

    fixture_rows: list[dict[str, Any]] = []
    for row in rows:
        fixture_row = dict(row)
        symbol = str(fixture_row.get("symbol") or "").strip().upper()
        if fixture_row.get("instrument_id") is None and symbol:
            instrument = db.query(Instrument).filter_by(symbol=symbol).one_or_none()
            if instrument is None:
                if instrument_type_id is None:
                    raise AssertionError(
                        f"No test instrument for {symbol}; supply instrument_type_id explicitly"
                    )
                instrument = Instrument(
                    symbol=symbol,
                    name=str(fixture_row.get("name") or symbol),
                    currency=str(fixture_row.get("currency") or "USD"),
                    instrument_type_id=instrument_type_id,
                    is_active=True,
                )
                db.add(instrument)
                db.flush()
            fixture_row["instrument_id"] = instrument.id
        fixture_rows.append(fixture_row)

    fixture_identity = {
        "profile_id": profile.id,
        "composition_date": composition_date.isoformat(),
        "known_at": known_at.isoformat(),
        "rows": fixture_rows,
    }
    snapshot_hash = hashlib.sha256(
        json.dumps(fixture_identity, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    total_weight = sum(
        (Decimal(str(row["weight"])) for row in fixture_rows if row.get("weight") is not None),
        Decimal("0"),
    )
    resolved_count = sum(
        1
        for row in fixture_rows
        if row.get("instrument_id") is not None and row.get("is_resolved", True)
    )
    snapshot = ETFHoldingsSnapshot(
        etf_profile_id=profile.id,
        composition_date=composition_date,
        as_of_date=composition_date,
        known_at=known_at,
        published_at=None,
        provenance="test_historical_fixture",
        source_provider="integration_test_fixture",
        source_quality="unknown",
        completeness_status="unknown",
        row_count=len(fixture_rows),
        resolved_count=resolved_count,
        unresolved_count=len(fixture_rows) - resolved_count,
        total_weight=total_weight,
        parser_version="test-fixture-v1",
        snapshot_hash=snapshot_hash,
        notes="Synthetic test-only historical data; not evidence of publisher support.",
        extra_data={
            "test_fixture_only": True,
            "legal_metadata": {"source_tier": "none", "test_fixture_only": True},
        },
    )
    db.add(snapshot)
    db.flush()

    for position, row in enumerate(fixture_rows, start=1):
        row_payload = {key: value for key, value in row.items() if key != "instrument_id"}
        row_hash = hashlib.sha256(
            json.dumps(
                {"snapshot_hash": snapshot_hash, "position": position, "row": row_payload},
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        instrument_id = row.get("instrument_id")
        is_resolved = instrument_id is not None and row.get("is_resolved", True)
        db.add(
            ETFHolding(
                snapshot_id=snapshot.id,
                constituent_instrument_id=instrument_id if is_resolved else None,
                position=position,
                reported_symbol=row.get("symbol"),
                reported_name=row.get("name"),
                weight=Decimal(str(row["weight"])) if row.get("weight") is not None else None,
                shares=Decimal(str(row["shares"])) if row.get("shares") is not None else None,
                market_value=(
                    Decimal(str(row["market_value"]))
                    if row.get("market_value") is not None
                    else None
                ),
                currency=row.get("currency"),
                holding_type=str(row.get("holding_type") or "equity"),
                row_type=str(row.get("row_type") or "security"),
                source_row_id=row.get("source_row_id"),
                source_row_hash=row_hash,
                is_resolved=is_resolved,
                resolution_note=(
                    "Synthetic test-only canonical mapping; not publisher identity evidence."
                    if is_resolved
                    else "Synthetic test-only unresolved row."
                ),
            )
        )
    db.flush()
    return snapshot
