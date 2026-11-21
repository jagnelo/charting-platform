"""Quota-ledger admission must not scan the append-only ledger.

Production (2026-11-21): every provider call reserves and settles inside one
exclusive ledger write transaction. With 128k baselines and 278k reservations
the admission queries full-scanned both tables, holding the lock ~240 ms per
call and capping the whole platform near one provider request per second.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event

from app.config import settings
from app.services.provider_quota_coordinator import (
    _HOT_PATH_INDEXES,
    _engine_for,
    _engine_url,
    metadata,
    reconcile_provider_quota_baseline,
    reserve_provider_quota,
    settle_provider_quota,
)

NOW = datetime(2026, 11, 21, 0, 30, tzinfo=UTC)
LEDGER_TABLES = ("provider_quota_ledger_baseline", "provider_quota_ledger_reservation")
EXPECTED_INDEXES = {
    "ix_provider_quota_ledger_baseline_dimension_observed": (
        "provider_quota_ledger_baseline",
        ["account_scope", "quota_group", "dimension", "window_seconds", "observed_at"],
    ),
    "ix_provider_quota_ledger_reservation_dimension_created": (
        "provider_quota_ledger_reservation",
        ["account_scope", "quota_group", "dimension", "created_at"],
    ),
    "ix_provider_quota_ledger_reservation_dimension_window": (
        "provider_quota_ledger_reservation",
        ["account_scope", "quota_group", "dimension", "window_started_at"],
    ),
    "ix_provider_quota_ledger_reservation_scope_state_lease": (
        "provider_quota_ledger_reservation",
        ["account_scope", "state", "lease_expires_at"],
    ),
}


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "quota.sqlite3"
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(path))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_EXCLUSIVE_ACCOUNT_SCOPES", {})
    return path


def _ledger_indexes(path) -> dict[str, tuple[str, list[str]]]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT name, tbl_name FROM sqlite_master "
            "WHERE type = 'index' AND name LIKE 'ix_provider_quota_ledger_%'"
        ).fetchall()
        return {
            name: (table, [row[2] for row in connection.execute(f'PRAGMA index_info("{name}")')])
            for name, table in rows
        }


def _row_counts(path) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        return {
            table: connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in (*LEDGER_TABLES, "provider_quota_ledger_window")
        }


def _dimension(name, *, limit=100, unit="requests", window_seconds=60):
    return {
        "name": name,
        "limit": limit,
        "window_seconds": window_seconds,
        "unit": unit,
        "scope": "api_key",
        "source": "https://provider.example/rate-limits",
    }


def _policy(*dimensions, reset="fixed_minute"):
    return SimpleNamespace(
        quota_scope="api_key",
        quota_source="test provider contract",
        quota_contract={"reset": reset, "dimensions": list(dimensions)},
    )


def _admit(policy, units, *, now, identity=None, provider="fixture", release_identities=False):
    for dimension in policy.quota_contract["dimensions"]:
        if dimension["unit"] == "concurrent_requests":
            continue
        reconcile_provider_quota_baseline(
            provider_name=provider,
            capability="price_history",
            policy=policy,
            dimension_name=dimension["name"],
            used_units=0,
            observed_at=now,
            evidence_reference="test-fixture:fixture:isolated-pytest",
            now=now,
        )
    reservation = reserve_provider_quota(
        provider_name=provider,
        capability="price_history",
        operation="fetch_ohlcv",
        policy=policy,
        dimension_units=units,
        usage_identity=identity,
        now=now,
    )
    assert reservation is not None
    settle_provider_quota(
        reservation,
        observed_dimension_units={
            name: amount for name, amount in units.items() if not name.startswith("concurrent")
        },
        release_identities=release_identities,
        now=now + timedelta(seconds=1),
    )
    return reservation


def test_fresh_ledger_has_the_admission_indexes(ledger):
    _engine_for(_engine_url())

    assert _ledger_indexes(ledger) == EXPECTED_INDEXES
    assert {index.name for index in _HOT_PATH_INDEXES} == set(EXPECTED_INDEXES)


def test_existing_ledger_gains_the_indexes_in_place_and_keeps_every_row(ledger):
    # A ledger written before these indexes existed: same tables, no indexes.
    legacy = create_engine(f"sqlite:///{ledger}")
    metadata.create_all(legacy)
    legacy.dispose()
    with sqlite3.connect(ledger) as connection:
        for name in EXPECTED_INDEXES:
            connection.execute(f'DROP INDEX "{name}"')
    assert _ledger_indexes(ledger) == {}

    # Seed rows through a coordinator engine, then strip the indexes again so
    # the next process opens a populated legacy ledger.
    _engine_for.cache_clear()
    _admit(_policy(_dimension("requests_per_minute")), {"requests_per_minute": 1}, now=NOW)
    with sqlite3.connect(ledger) as connection:
        for name in EXPECTED_INDEXES:
            connection.execute(f'DROP INDEX "{name}"')
    before = _row_counts(ledger)
    assert before["provider_quota_ledger_reservation"] >= 1
    assert before["provider_quota_ledger_baseline"] >= 1

    _engine_for.cache_clear()
    _engine_for(_engine_url())

    assert _ledger_indexes(ledger) == EXPECTED_INDEXES
    assert _row_counts(ledger) == before
    # The upgraded ledger still admits and settles.
    _admit(
        _policy(_dimension("requests_per_minute")),
        {"requests_per_minute": 1},
        now=NOW + timedelta(minutes=2),
    )
    assert (
        _row_counts(ledger)["provider_quota_ledger_reservation"]
        == before["provider_quota_ledger_reservation"] + 1
    )


def test_admission_queries_search_an_index_instead_of_scanning(ledger):
    engine = _engine_for(_engine_url())
    captured: list[tuple[str, tuple]] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and any(
            table in statement for table in LEDGER_TABLES
        ):
            captured.append((statement, tuple(parameters or ())))

    try:
        # Fixed window, rolling window, identity-keyed usage and a concurrency
        # lease (whose expired-lease sweep runs at every reservation).
        _admit(_policy(_dimension("requests_per_minute")), {"requests_per_minute": 1}, now=NOW)
        _admit(
            _policy(_dimension("rolling_requests"), reset="rolling"),
            {"rolling_requests": 1},
            now=NOW,
            provider="rolling_fixture",
        )
        symbols = _policy(
            _dimension("symbols_per_day", unit="unique_symbols", window_seconds=86_400)
        )
        for offset in (0, 5):
            _admit(
                symbols,
                {"symbols_per_day": 1},
                now=NOW + timedelta(seconds=offset),
                identity="instrument:ACME",
                provider="identity_fixture",
            )
        # An identity-keyed request that was never sent releases its claim,
        # which looks up the other reservations sharing that identity.
        _admit(
            symbols,
            {"symbols_per_day": 1},
            now=NOW + timedelta(minutes=3),
            identity="instrument:BETA",
            provider="identity_fixture",
            release_identities=True,
        )
        _admit(
            _policy(
                _dimension("credits_per_day", unit="credits", window_seconds=86_400),
                _dimension("concurrent_requests", limit=5, unit="concurrent_requests"),
            ),
            {"credits_per_day": 1, "concurrent_requests": 1},
            now=NOW,
            provider="lease_fixture",
        )
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    # The capture is not vacuous: every hot admission shape ran.
    joined = "\n".join(statement for statement, _ in captured)
    for fragment in (
        "provider_quota_ledger_baseline.observed_at DESC",
        "provider_quota_ledger_reservation.created_at >=",
        "provider_quota_ledger_reservation.window_started_at =",
        "provider_quota_ledger_reservation.identity_digest =",
        "provider_quota_ledger_reservation.lease_expires_at <=",
    ):
        assert fragment in joined, fragment

    scans = []
    with sqlite3.connect(ledger) as connection:
        for statement, parameters in captured:
            plan = [
                row[-1] for row in connection.execute(f"EXPLAIN QUERY PLAN {statement}", parameters)
            ]
            if any(re.match(rf"SCAN {table}\b", step) for step in plan for table in LEDGER_TABLES):
                scans.append((statement, plan))
    assert scans == []
