from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.models.instrument import Instrument
from app.models.workstation import MarketGroup, MarketGroupMember
from app.services.top_down_taxonomy import (
    _BENCHMARKS,
    _SECTORS,
    industry_proxy_candidates,
    seed_top_down_taxonomy,
)


class _AsyncSessionFacade:
    """Exercise the real async taxonomy contract against the unit SQLite session."""

    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def flush(self):
        self.session.flush()

    def add(self, value):
        self.session.add(value)


def test_industry_proxy_registry_is_explicit_and_does_not_infer_unknown_labels():
    assert industry_proxy_candidates("Semiconductors") == ("SOXX", "SMH")
    assert industry_proxy_candidates("semiconductors") == ()
    assert industry_proxy_candidates("Unclassified industry") == ()


def test_seed_top_down_taxonomy_attaches_known_proxies_and_is_idempotent(db, instrument_type):
    symbols = [(symbol, name) for symbol, name, *_ in _BENCHMARKS] + list(_SECTORS)
    db.add_all(
        [
            Instrument(
                symbol=symbol,
                name=name,
                currency="USD",
                instrument_type_id=instrument_type.id,
                is_active=True,
            )
            for symbol, name in symbols
        ]
    )
    db.flush()
    facade = _AsyncSessionFacade(db)

    asyncio.run(seed_top_down_taxonomy(facade))
    asyncio.run(seed_top_down_taxonomy(facade))

    groups = db.execute(select(MarketGroup)).scalars().all()
    assert {group.stable_key for group in groups} == {"us-benchmarks", "sp500-sectors"}
    members = db.execute(select(MarketGroupMember)).scalars().all()
    assert len(members) == len(_BENCHMARKS) + len(_SECTORS)
    assert {member.source for member in members} == {"curated_top_down_taxonomy"}
    assert {member.verification_state for member in members} == {"proxy_verified"}
    benchmark = next(group for group in groups if group.stable_key == "us-benchmarks")
    assert benchmark.provenance["benchmark_identities"]["sp500"]["official_index_symbol"] == "SPX"
    assert benchmark.provenance["benchmark_identities"]["sp500"]["default_tradable_proxy"] == "SPY"
