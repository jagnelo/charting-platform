from datetime import UTC, datetime

from app.schemas.workstation import (
    ETFIndustryCompositionOut,
    ETFIndustryConstituentsOut,
    ETFIndustryProxyOut,
    InstrumentNoteOut,
    InstrumentReferenceOut,
    MarketGroupMemberOut,
    MarketGroupOut,
    MarketGroupProxyOut,
    WorkspaceLibraryItemOut,
    WorkspaceOut,
    WorkspaceTabOut,
    WorkspaceWindowOut,
)


def test_workstation_response_schemas_serialize_timestamps_as_canonical_utc_z():
    naive = datetime(2026, 9, 12, 14, 30)
    aware = datetime(2026, 9, 12, 16, 30, tzinfo=UTC)
    instrument = InstrumentReferenceOut(id=7, symbol="SPY", name="SPDR S&P 500 ETF", is_active=True)

    window = WorkspaceWindowOut(
        id=11,
        tab_id=3,
        instance_key="chart-1",
        tool_type="chart",
        created_at=naive,
        updated_at=aware,
    )
    tab = WorkspaceTabOut(
        id=3,
        workspace_id=2,
        stable_key="overview",
        name="Overview",
        windows=[window],
        created_at=naive,
        updated_at=aware,
    )
    workspace = WorkspaceOut(
        id=2,
        user_id=5,
        name="US Top Down",
        is_default=True,
        position=0,
        revision=4,
        schema_version=1,
        settings={},
        tabs=[tab],
        created_at=naive,
        updated_at=aware,
    )
    library_item = WorkspaceLibraryItemOut(
        id=13,
        user_id=5,
        kind="chart_template",
        stable_key="daily-strength",
        name="Daily strength",
        version=2,
        created_at=naive,
        updated_at=aware,
    )
    note = InstrumentNoteOut(
        id=17,
        user_id=5,
        instrument_id=7,
        content="Watch the breakout.",
        created_at=naive,
        updated_at=aware,
    )
    member = MarketGroupMemberOut(
        id=19,
        instrument_id=7,
        relationship_type="constituent",
        weight=0.25,
        position=1,
        source="curated",
        verification_state="verified",
        effective_at=naive,
        known_at=aware,
        provenance={},
        instrument=instrument,
    )
    proxy = MarketGroupProxyOut(
        id=23,
        instrument_id=7,
        relationship_type="representative",
        source="curated",
        verification_state="verified",
        effective_at=naive,
        known_at=aware,
        provenance={},
        instrument=instrument,
    )
    group = MarketGroupOut(
        id=29,
        stable_key="sp500",
        group_type="index",
        name="S&P 500",
        parent_id=None,
        representative_instrument_id=7,
        equal_weight_instrument_id=None,
        source="curated",
        provenance={},
        effective_at=naive,
        known_at=aware,
        members=[member],
        proxies=[proxy],
    )
    etf_proxy = ETFIndustryProxyOut(
        symbol="XLK",
        name="Technology Select Sector SPDR Fund",
        composition_date="2026-09-01",
        known_at=naive,
        provenance="sec",
        source_provider="sec",
        matching_constituent_count=10,
        classified_constituent_count=10,
        classification_coverage=1,
    )
    composition = ETFIndustryCompositionOut(
        etf_symbol="XLK",
        composition_date="2026-09-01",
        known_at=aware,
        provenance="sec",
        source_provider="sec",
        completeness_status="complete",
    )
    constituents = ETFIndustryConstituentsOut(
        etf_symbol="XLK",
        industry="Semiconductors",
        composition_date="2026-09-01",
        known_at=naive,
        provenance="sec",
        source_provider="sec",
    )

    assert workspace.model_dump(mode="json")["created_at"] == "2026-09-12T14:30:00Z"
    assert workspace.model_dump(mode="json")["tabs"][0]["windows"][0]["updated_at"] == (
        "2026-09-12T16:30:00Z"
    )
    assert library_item.model_dump(mode="json")["updated_at"] == "2026-09-12T16:30:00Z"
    assert note.model_dump(mode="json")["created_at"] == "2026-09-12T14:30:00Z"
    assert group.model_dump(mode="json")["effective_at"] == "2026-09-12T14:30:00Z"
    assert group.model_dump(mode="json")["members"][0]["known_at"] == "2026-09-12T16:30:00Z"
    assert group.model_dump(mode="json")["proxies"][0]["effective_at"] == "2026-09-12T14:30:00Z"
    assert etf_proxy.model_dump(mode="json")["known_at"] == "2026-09-12T14:30:00Z"
    assert composition.model_dump(mode="json")["known_at"] == "2026-09-12T16:30:00Z"
    assert constituents.model_dump(mode="json")["known_at"] == "2026-09-12T14:30:00Z"
