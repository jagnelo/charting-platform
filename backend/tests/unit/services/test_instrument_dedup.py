"""Duplicate-instrument identity rules and the reconciliation root-cause fix."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import MarketUniverseReconciliationRun
from app.services.exchange_catalog import upsert_instrument_listing
from app.services.instrument_dedup import (
    InstrumentRow,
    classify_cause,
    identifier_conflict,
    normalize_symbol,
)
from app.services.market_universe import _reconcile_rows
from tests.unit.conftest import AsyncSessionAdapter


def _row(id_, symbol="ABBV", domain_key=None, issuer_id=None, status="resolved", name="AbbVie"):
    return InstrumentRow(id_, 1, symbol, name, status, domain_key, issuer_id)


def test_normalize_symbol_collapses_class_separators_and_case():
    assert normalize_symbol("brk-b") == normalize_symbol("BRK.B") == normalize_symbol(" BRK/B ")
    assert normalize_symbol("AGMI") != normalize_symbol("AGM.I")


def test_canonical_rank_prefers_figi_then_issuer_then_lowest_id():
    figi = _row(9, domain_key="composite-figi:BBG1")
    cusip = _row(1, domain_key="cusip:00287Y109")
    keyless = _row(2, issuer_id=5)
    assert sorted([cusip, keyless, figi], key=lambda r: r.rank) == [figi, cusip, keyless]


def test_different_cusips_or_domain_keys_are_a_conflict():
    a = _row(1, domain_key="cusip:AAA")
    b = _row(2, domain_key="cusip:BBB")
    assert identifier_conflict(a, b, [], []) == "domain_key_conflict"
    c = _row(3, domain_key="composite-figi:X")
    d = _row(4)
    assert identifier_conflict(c, d, [("CUSIP", "111")], [("CUSIP", "222")]) == "cusip_conflict"
    assert identifier_conflict(c, d, [("CUSIP", "111")], [("CUSIP", "111 ")]) is None
    assert identifier_conflict(c, d, [("COMPOSITE_FIGI", "X")], [("CUSIP", "222")]) is None


def test_classify_cause():
    figi = _row(1, domain_key="composite-figi:X")
    assert classify_cause(figi, _row(2, domain_key="cusip:1")) == "legacy_key_vs_figi"
    assert classify_cause(figi, _row(2, status="quarantined")) == "keyless_vs_stable"
    assert classify_cause(_row(1, "BRK.B"), _row(2, "BRK-B")) == "separator_variant"


async def _reconcile(db, name="Apple Inc.", **row):
    source = DataSource(name="massive", base_url="https://example.test")
    db.add(source)
    db.flush()
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type="EQUITY",
        observed_at=datetime(2026, 11, 19, tzinfo=UTC),
    )
    db.add(run)
    db.flush()
    await _reconcile_rows(
        AsyncSessionAdapter(db),
        run=run,
        provider_name="massive",
        rows=[{"symbol": "AAPL", "name": name, "exchange": "NASDAQ", "currency": "USD", **row}],
        quote_type="EQUITY",
        observed_at=run.observed_at,
    )
    return run


async def _legacy_listing(db, instrument, domain_key="cusip:037833100"):
    instrument.symbol = "AAPL"
    instrument.name = "Apple Inc. Common Stock"
    instrument.domain_key = domain_key
    await upsert_instrument_listing(
        AsyncSessionAdapter(db), instrument, "AAPL", exchange_code="NASDAQ", is_primary=True
    )
    db.flush()


@pytest.mark.asyncio
async def test_new_figi_row_adopts_the_unique_legacy_listing_instead_of_duplicating(db, instrument):
    await _legacy_listing(db, instrument)

    run = await _reconcile(db, figi="BBG000B9XRY4")

    assert run.new_count == 0 and run.updated_count == 1
    assert db.query(Instrument).count() == 1
    identifier = db.query(InstrumentIdentifier).filter_by(identifier_value="BBG000B9XRY4").one()
    assert identifier.instrument_id == instrument.id
    assert db.query(InstrumentListing).filter_by(ticker="AAPL").count() == 1


@pytest.mark.asyncio
async def test_legacy_listing_with_conflicting_identifier_is_not_adopted(db, instrument):
    await _legacy_listing(db, instrument)
    db.add(
        InstrumentIdentifier(
            instrument_id=instrument.id,
            identifier_type=InstrumentIdentifierType.FIGI,
            identifier_value="BBG000OTHER0",
            is_primary=False,
            is_active=True,
        )
    )
    db.flush()

    run = await _reconcile(db, figi="BBG000B9XRY4")

    assert run.new_count == 1
    assert db.query(Instrument).count() == 2


@pytest.mark.asyncio
async def test_legacy_listing_with_incompatible_name_is_not_adopted(db, instrument):
    await _legacy_listing(db, instrument)
    instrument.name = "Zebra Holdings"
    db.flush()

    run = await _reconcile(db, figi="BBG000B9XRY4")

    assert run.new_count == 1
    assert db.query(Instrument).count() == 2


@pytest.mark.asyncio
async def test_stronger_existing_figi_owner_is_never_adopted_over(db, instrument):
    await _legacy_listing(db, instrument, domain_key="composite-figi:BBG0000EXIST")

    run = await _reconcile(db, figi="BBG000B9XRY4")

    assert run.new_count == 1
    assert db.query(Instrument).count() == 2


@pytest.mark.asyncio
async def test_only_enabled_evidence_tiers_are_merged(monkeypatch):
    """Merging deletes rows, so tiers outside the enabled list are reported, not merged."""

    from contextlib import asynccontextmanager

    from app.services import instrument_dedup

    report = instrument_dedup.PlanReport(
        plans=[
            instrument_dedup.MergePlan(1, 2, "figi_vs_cusip", {"evidence": "same_listing"}),
            instrument_dedup.MergePlan(3, 4, "keyless_vs_stable", {"evidence": "bar_agreement"}),
            instrument_dedup.MergePlan(5, 6, "other", {"evidence": "separator_spelling"}),
        ]
    )

    async def fake_plan(_db):
        return report

    @asynccontextmanager
    async def session_factory():
        yield object()

    monkeypatch.setattr(instrument_dedup, "plan_duplicate_merges", fake_plan)
    summary = await instrument_dedup.merge_duplicate_instruments(
        session_factory, dry_run=True, evidence=["same_listing", "separator_spelling"]
    )

    assert summary["planned"] == 2
    assert summary["skipped"] == {"evidence_not_enabled:bar_agreement": 1}
    assert [plan.duplicate_id for plan in report.plans] == [2, 6]
