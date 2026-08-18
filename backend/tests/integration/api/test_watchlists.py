from datetime import UTC, datetime, timedelta

import pytest

from app.models.screener import ScreenerDefinition
from app.models.watchlist import Watchlist
from app.models.workstation import MarketGroup, MarketGroupMember


class TestWatchlistsAuth:
    def test_list_requires_auth(self, client):
        res = client.get("/api/v1/watchlists")
        assert res.status_code == 401


class TestWatchlistsCrud:
    def test_market_map_accepts_personal_source_and_rolls_up_constituents(
        self, client, auth_headers, admin_headers, db, watchlist, instrument, instrument_b
    ):
        from app.models.instrument import EquityDetail
        from app.models.instrument_stats import InstrumentStats
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.watchlist import WatchlistItem

        db.add_all(
            [
                WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id, position=0),
                WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument_b.id, position=1),
                EquityDetail(instrument_id=instrument.id, sector="Technology", industry="Hardware"),
                EquityDetail(instrument_id=instrument_b.id, sector="Technology", industry="Software"),
                InstrumentStats(instrument_id=instrument.id, market_cap=100),
                InstrumentStats(instrument_id=instrument_b.id, market_cap=50),
            ]
        )
        base = datetime(2024, 1, 1, tzinfo=UTC)
        for offset, price in enumerate((100, 101, 102, 103, 104, 105, 106)):
            for member, multiplier in ((instrument, 1), (instrument_b, 2)):
                db.add(
                    OHLCVBar(
                        instrument_id=member.id,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=offset),
                        open=price * multiplier,
                        high=price * multiplier + 1,
                        low=price * multiplier - 1,
                        close=price * multiplier,
                        volume=1_000_000,
                        is_adjusted=True,
                    )
                )
        db.flush()

        response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "sector_industry",
                "period": "1W",
                "area_metric": "market_cap",
                "color_metric": "return",
                "end": "2024-01-07T00:00:00Z",
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["source"]["source_id"] == f"watchlist:{watchlist.id}"
        assert body["requested_count"] == 2
        assert body["evaluated_count"] == 2
        assert body["coverage"] == 1
        assert {cell["symbol"] for cell in body["cells"]} == {"AAPL", "MSFT"}
        assert all(cell["area_provenance"]["kind"] == "current_metadata" for cell in body["cells"])
        assert all(cell["area_provenance"]["point_in_time"] is False for cell in body["cells"])
        assert {node["label"] for node in body["nodes"]} >= {"Technology", "Hardware", "Software"}
        assert body["nodes"][-1]["aggregation_method"] == "area_weighted_mean"
        assert body["cache_hit"] is False

        custom_response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "sector_industry",
                "period": "CUSTOM",
                "start": "2024-01-03T00:00:00Z",
                "end": "2024-01-07T00:00:00Z",
                "area_metric": "equal",
                "color_metric": "return",
            },
        )
        assert custom_response.status_code == 200, custom_response.text
        custom_body = custom_response.json()
        assert custom_body["period_start"].startswith("2024-01-03")
        assert custom_body["period_end"].startswith("2024-01-07")
        assert all(cell["area_provenance"]["method"] == "equal_member_area" for cell in custom_body["cells"])

        cached_response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "sector_industry",
                "period": "1W",
                "area_metric": "market_cap",
                "color_metric": "return",
                "end": "2024-01-07T00:00:00Z",
            },
        )
        assert cached_response.status_code == 200, cached_response.text
        cached_body = cached_response.json()
        assert cached_body["cache_hit"] is True
        assert cached_body["cache_key"] == body["cache_key"]
        from app.models.market_map import MarketMapCache

        assert db.query(MarketMapCache).count() == 2
        restored = client.get(
            f"/api/v1/analysis/market-map/cache/{body['cache_key']}", headers=auth_headers
        )
        assert restored.status_code == 200
        assert restored.json()["cache_hit"] is True
        assert restored.json()["source"]["source_id"] == f"watchlist:{watchlist.id}"

        invalid_key = client.get(
            "/api/v1/analysis/market-map/cache/not-a-cache-key", headers=auth_headers
        )
        assert invalid_key.status_code == 422
        foreign = client.get(
            f"/api/v1/analysis/market-map/cache/{body['cache_key']}", headers=admin_headers
        )
        assert foreign.status_code == 404

        created_snapshot = client.post(
            "/api/v1/analysis/market-map/snapshots",
            headers=auth_headers,
            json={"name": "S&P leaders", "cache_key": body["cache_key"]},
        )
        assert created_snapshot.status_code == 200, created_snapshot.text
        snapshot_body = created_snapshot.json()
        assert snapshot_body["name"] == "S&P leaders"
        assert snapshot_body["map"]["source"]["source_id"] == f"watchlist:{watchlist.id}"
        assert snapshot_body["map"]["cache_hit"] is False

        listed_snapshots = client.get(
            "/api/v1/analysis/market-map/snapshots", headers=auth_headers
        )
        assert listed_snapshots.status_code == 200
        assert [item["name"] for item in listed_snapshots.json()] == ["S&P leaders"]

        duplicate = client.post(
            "/api/v1/analysis/market-map/snapshots",
            headers=auth_headers,
            json={"name": "S&P leaders", "cache_key": body["cache_key"]},
        )
        assert duplicate.status_code == 409
        restored_snapshot = client.get(
            f"/api/v1/analysis/market-map/snapshots/{snapshot_body['id']}",
            headers=auth_headers,
        )
        assert restored_snapshot.status_code == 200
        assert restored_snapshot.json()["snapshot_hash"] == snapshot_body["snapshot_hash"]
        assert client.get(
            f"/api/v1/analysis/market-map/snapshots/{snapshot_body['id']}",
            headers=admin_headers,
        ).status_code == 404
        deleted = client.delete(
            f"/api/v1/analysis/market-map/snapshots/{snapshot_body['id']}",
            headers=auth_headers,
        )
        assert deleted.status_code == 204
        assert client.get(
            f"/api/v1/analysis/market-map/snapshots/{snapshot_body['id']}",
            headers=auth_headers,
        ).status_code == 404

    def test_market_map_uses_locked_market_group_source_through_same_contract(
        self, client, auth_headers, db, instrument, instrument_b
    ):
        from app.models.data_source import DataSource
        from app.models.instrument import EquityDetail
        from app.models.instrument_stats import InstrumentStats
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.provider_observation import InstrumentProfileSnapshot

        now = datetime(2024, 1, 1, tzinfo=UTC)
        group = MarketGroup(
            stable_key="locked-sp500-fixture",
            group_type="benchmark_family",
            name="Locked S&P 500 fixture",
            source="controlled_fixture",
            effective_at=now,
            known_at=now,
        )
        db.add(group)
        db.flush()
        db.add_all(
            [
                MarketGroupMember(
                    market_group_id=group.id,
                    instrument_id=instrument.id,
                    position=0,
                    relationship_type="constituent",
                    source="controlled_fixture",
                    verification_state="verified",
                    weight=0.6,
                    effective_at=now,
                    known_at=now,
                ),
                MarketGroupMember(
                    market_group_id=group.id,
                    instrument_id=instrument_b.id,
                    position=1,
                    relationship_type="constituent",
                    source="controlled_fixture",
                    verification_state="verified",
                    weight=0.4,
                    effective_at=now,
                    known_at=now,
                ),
                EquityDetail(instrument_id=instrument.id, sector="Technology", industry="Hardware"),
                EquityDetail(instrument_id=instrument_b.id, sector="Industrials", industry="Machinery"),
                InstrumentStats(instrument_id=instrument.id, market_cap=125),
                InstrumentStats(instrument_id=instrument_b.id, market_cap=75),
            ]
        )
        profile_source = DataSource(
            name="controlled-market-cap-map",
            base_url="controlled://market-cap-map",
            description="Point-in-time market-cap fixture",
        )
        db.add(profile_source)
        db.flush()
        db.add_all(
            [
                InstrumentProfileSnapshot(
                    instrument_id=instrument.id,
                    data_source_id=profile_source.id,
                    provider_symbol=instrument.symbol,
                    observed_at=now + timedelta(days=5),
                    fetched_at=now + timedelta(days=6),
                    profile_hash="market-cap-map-a",
                    payload={"market_cap": 900},
                ),
                InstrumentProfileSnapshot(
                    instrument_id=instrument_b.id,
                    data_source_id=profile_source.id,
                    provider_symbol=instrument_b.symbol,
                    observed_at=now + timedelta(days=5),
                    fetched_at=now + timedelta(days=6),
                    profile_hash="market-cap-map-b",
                    payload={"extra": {"market_cap": 600}},
                ),
            ]
        )
        for offset, price in enumerate((100, 101, 102, 103, 104, 105, 106)):
            for member, multiplier in ((instrument, 1), (instrument_b, 2)):
                db.add(
                    OHLCVBar(
                        instrument_id=member.id,
                        timeframe=Timeframe.D1,
                        ts=now + timedelta(days=offset),
                        open=price * multiplier,
                        high=price * multiplier + 1,
                        low=price * multiplier - 1,
                        close=price * multiplier,
                        volume=1_000_000,
                        is_adjusted=True,
                    )
                )
        db.flush()

        response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": "market-group:locked-sp500-fixture",
                "group_by": "sector_industry",
                "period": "1W",
                "area_metric": "market_cap",
                "color_metric": "return",
                "end": "2024-01-07T00:00:00Z",
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["source"]["source_id"] == "market-group:locked-sp500-fixture"
        assert body["source"]["locked"] is True
        assert body["source"]["can_edit_membership"] is False
        assert body["requested_count"] == 2
        assert body["evaluated_count"] == 2
        assert {cell["symbol"] for cell in body["cells"]} == {"AAPL", "MSFT"}
        cells = {cell["symbol"]: cell for cell in body["cells"]}
        assert cells["AAPL"]["area_value"] == 900
        assert cells["AAPL"]["area_provenance"]["kind"] == "point_in_time_profile_snapshot"
        assert cells["AAPL"]["area_provenance"]["entitlement_verified"] is False
        assert cells["AAPL"]["area_provenance"]["selection"] == "unranked_snapshot_fallback"
        assert cells["MSFT"]["area_value"] == 600
        assert not any(item["code"] == "current_area_not_point_in_time" for item in body["warnings"])
        assert any(item["code"] == "profile_snapshot_unranked_source" for item in body["warnings"])
        assert {node["label"] for node in body["nodes"]} >= {"Technology", "Hardware", "Industrials", "Machinery"}

        weighted = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": "market-group:locked-sp500-fixture",
                "group_by": "none",
                "period": "1W",
                "area_metric": "weight",
                "color_metric": "return",
                "end": "2024-01-07T00:00:00Z",
            },
        )
        assert weighted.status_code == 200, weighted.text
        weighted_cells = {cell["symbol"]: cell for cell in weighted.json()["cells"]}
        assert weighted_cells["AAPL"]["area_value"] == 0.6
        assert weighted_cells["AAPL"]["area_provenance"]["kind"] == "point_in_time_membership"
        assert weighted_cells["AAPL"]["area_provenance"]["known_at"].startswith("2024-01-01")

        # A locked market-group source is still mutable at the ingestion layer:
        # membership weights and lifecycle metadata can be refreshed without
        # touching the parent group row. Its canonical source version and map
        # cache identity must therefore follow the member rows.
        before_version = weighted.json()["membership_version"]
        before_cache_key = weighted.json()["cache_key"]
        group_member = (
            db.query(MarketGroupMember)
            .filter(MarketGroupMember.market_group_id == group.id)
            .order_by(MarketGroupMember.position)
            .first()
        )
        assert group_member is not None
        group_member.weight = 0.7
        db.flush()

        refreshed = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": "market-group:locked-sp500-fixture",
                "group_by": "none",
                "period": "1W",
                "area_metric": "weight",
                "color_metric": "return",
                "end": "2024-01-07T00:00:00Z",
            },
        )
        assert refreshed.status_code == 200, refreshed.text
        refreshed_body = refreshed.json()
        assert refreshed_body["membership_version"] != before_version
        assert refreshed_body["cache_key"] != before_cache_key
        assert {cell["symbol"]: cell["area_value"] for cell in refreshed_body["cells"]}["AAPL"] == 0.7

    def test_market_map_prefers_entitled_profile_provider_precedence_and_invalidates_policy_cache(
        self, client, auth_headers, db, instrument, instrument_b, monkeypatch
    ):
        from app.models.data_source import DataSource
        from app.models.instrument import EquityDetail
        from app.models.instrument_stats import InstrumentStats
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.provider_observation import InstrumentProfileSnapshot
        from app.models.provider_runtime import (
            ProviderCapability,
            ProviderEntitlement,
            ProviderEntitlementRevision,
            ProviderPolicy,
        )

        monkeypatch.setattr(
            "app.services.market_map.list_provider_capabilities",
            lambda name: ["instrument_metadata"] if name in {"fixture-high", "fixture-low"} else [],
        )
        now = datetime(2024, 1, 1, tzinfo=UTC)
        group = MarketGroup(
            stable_key="locked-provider-precedence",
            group_type="benchmark_family",
            name="Locked provider precedence fixture",
            source="controlled_fixture",
            effective_at=now,
            known_at=now,
        )
        db.add(group)
        db.flush()
        db.add_all(
            [
                MarketGroupMember(
                    market_group_id=group.id,
                    instrument_id=instrument.id,
                    position=0,
                    relationship_type="constituent",
                    source="controlled_fixture",
                    verification_state="verified",
                    weight=0.6,
                    effective_at=now,
                    known_at=now,
                ),
                MarketGroupMember(
                    market_group_id=group.id,
                    instrument_id=instrument_b.id,
                    position=1,
                    relationship_type="constituent",
                    source="controlled_fixture",
                    verification_state="verified",
                    weight=0.4,
                    effective_at=now,
                    known_at=now,
                ),
                EquityDetail(instrument_id=instrument.id, sector="Technology", industry="Hardware"),
                EquityDetail(instrument_id=instrument_b.id, sector="Industrials", industry="Machinery"),
                InstrumentStats(instrument_id=instrument.id, market_cap=100),
                InstrumentStats(instrument_id=instrument_b.id, market_cap=50),
            ]
        )
        high_source = DataSource(name="fixture-high", base_url="controlled://high", description="High precedence fixture")
        low_source = DataSource(name="fixture-low", base_url="controlled://low", description="Low precedence fixture")
        db.add_all([high_source, low_source])
        db.flush()
        db.add_all(
            [
                ProviderPolicy(
                    data_source_id=high_source.id,
                    capability=ProviderCapability.INSTRUMENT_METADATA,
                    is_pinned=True,
                    effective_score=1,
                    base_priority=50,
                ),
                ProviderPolicy(
                    data_source_id=low_source.id,
                    capability=ProviderCapability.INSTRUMENT_METADATA,
                    effective_score=90,
                    base_priority=1,
                ),
                ProviderEntitlement(
                    data_source_id=high_source.id,
                    capability=ProviderCapability.INSTRUMENT_METADATA,
                    is_free=True,
                    enabled_environments=[],
                ),
                ProviderEntitlement(
                    data_source_id=low_source.id,
                    capability=ProviderCapability.INSTRUMENT_METADATA,
                    is_free=True,
                    enabled_environments=[],
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                ProviderEntitlementRevision(
                    data_source_id=high_source.id,
                    capability=ProviderCapability.INSTRUMENT_METADATA,
                    revision=1,
                    configured_plan="fixture-high-v1",
                    is_free=True,
                    authentication_required=False,
                    redistribution_allowed=False,
                    effective_at=now - timedelta(days=10),
                    live_probe_status="passed",
                ),
                ProviderEntitlementRevision(
                    data_source_id=low_source.id,
                    capability=ProviderCapability.INSTRUMENT_METADATA,
                    revision=1,
                    configured_plan="fixture-low-v1",
                    is_free=True,
                    authentication_required=False,
                    redistribution_allowed=False,
                    effective_at=now - timedelta(days=10),
                    live_probe_status="passed",
                ),
            ]
        )
        db.flush()
        for offset, price in enumerate((100, 101, 102, 103, 104, 105, 106)):
            for member, multiplier in ((instrument, 1), (instrument_b, 2)):
                db.add(
                    OHLCVBar(
                        instrument_id=member.id,
                        timeframe=Timeframe.D1,
                        ts=now + timedelta(days=offset),
                        open=price * multiplier,
                        high=price * multiplier + 1,
                        low=price * multiplier - 1,
                        close=price * multiplier,
                        volume=1_000_000,
                        is_adjusted=True,
                    )
                )
        db.add_all(
            [
                InstrumentProfileSnapshot(
                    instrument_id=instrument.id,
                    data_source_id=high_source.id,
                    provider_symbol=instrument.symbol,
                    observed_at=now + timedelta(days=2),
                    fetched_at=now + timedelta(days=2),
                    profile_hash="precedence-high-a",
                    payload={"market_cap": 700},
                ),
                InstrumentProfileSnapshot(
                    instrument_id=instrument.id,
                    data_source_id=low_source.id,
                    provider_symbol=instrument.symbol,
                    observed_at=now + timedelta(days=6),
                    fetched_at=now + timedelta(days=6),
                    profile_hash="precedence-low-a",
                    payload={"market_cap": 900},
                ),
                InstrumentProfileSnapshot(
                    instrument_id=instrument_b.id,
                    data_source_id=high_source.id,
                    provider_symbol=instrument_b.symbol,
                    observed_at=now + timedelta(days=2),
                    fetched_at=now + timedelta(days=2),
                    profile_hash="precedence-high-b",
                    payload={"market_cap": 300},
                ),
                InstrumentProfileSnapshot(
                    instrument_id=instrument_b.id,
                    data_source_id=low_source.id,
                    provider_symbol=instrument_b.symbol,
                    observed_at=now + timedelta(days=6),
                    fetched_at=now + timedelta(days=6),
                    profile_hash="precedence-low-b",
                    payload={"market_cap": 500},
                ),
            ]
        )
        db.flush()

        request = {
            "source_id": "market-group:locked-provider-precedence",
            "group_by": "sector_industry",
            "period": "1W",
            "area_metric": "market_cap",
            "color_metric": "return",
            "end": "2024-01-07T00:00:00Z",
        }
        first = client.post("/api/v1/analysis/market-map", headers=auth_headers, json=request)
        assert first.status_code == 200, first.text
        first_body = first.json()
        first_cells = {cell["symbol"]: cell for cell in first_body["cells"]}
        assert first_cells["AAPL"]["area_value"] == 700
        assert first_cells["AAPL"]["area_provenance"]["provider_name"] == "fixture-high"
        assert first_cells["AAPL"]["area_provenance"]["selection"] == "entitled_provider_precedence"
        assert first_cells["AAPL"]["area_provenance"]["provider_precedence_rank"] == 0
        assert first_cells["AAPL"]["area_provenance"]["entitlement_historical"] is True
        assert first_cells["AAPL"]["area_provenance"]["entitlement_revision"] == 1
        assert first_body["cache_hit"] is False

        high_policy = db.query(ProviderPolicy).filter_by(data_source_id=high_source.id).one()
        high_policy.is_pinned = False
        high_policy.effective_score = 1
        high_entitlement = db.query(ProviderEntitlement).filter_by(data_source_id=high_source.id).one()
        high_entitlement.is_free = False
        high_entitlement.revision = 2
        db.add(
            ProviderEntitlementRevision(
                data_source_id=high_source.id,
                capability=ProviderCapability.INSTRUMENT_METADATA,
                revision=2,
                configured_plan="fixture-high-v2",
                is_free=False,
                authentication_required=False,
                redistribution_allowed=False,
                effective_at=now + timedelta(days=8),
                live_probe_status="passed",
            )
        )
        db.flush()
        second = client.post("/api/v1/analysis/market-map", headers=auth_headers, json=request)
        assert second.status_code == 200, second.text
        second_body = second.json()
        second_cells = {cell["symbol"]: cell for cell in second_body["cells"]}
        assert second_cells["AAPL"]["area_value"] == 900
        assert second_cells["AAPL"]["area_provenance"]["provider_name"] == "fixture-low"
        assert second_cells["AAPL"]["area_provenance"]["selection"] == "entitled_provider_precedence"
        assert second_body["cache_key"] != first_body["cache_key"]
        assert second_body["cache_hit"] is False

        future_request = {**request, "end": "2024-01-10T00:00:00Z"}
        future = client.post(
            "/api/v1/analysis/market-map", headers=auth_headers, json=future_request
        )
        assert future.status_code == 200, future.text
        future_cells = {cell["symbol"]: cell for cell in future.json()["cells"]}
        assert future_cells["AAPL"]["area_value"] == 900
        assert future_cells["AAPL"]["area_provenance"]["provider_name"] == "fixture-low"

    def test_market_map_reports_missing_local_data_without_provider_fanout(
        self, client, auth_headers, watchlist, instrument
    ):
        from app.models.watchlist import WatchlistItem

        watchlist.items.append(WatchlistItem(instrument_id=instrument.id, position=0))
        response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "return",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["coverage"] == 0
        assert body["cells"][0]["warnings"][0]["code"] == "no_bars"

    def test_market_map_rejects_relative_colour_without_reference(
        self, client, auth_headers, watchlist
    ):
        response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "color_metric": "relative_return",
            },
        )
        assert response.status_code == 422

    def test_market_map_compares_against_a_reference_watchlist_series(
        self, client, auth_headers, db, user, watchlist, instrument, instrument_b
    ):
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.watchlist import WatchlistItem

        reference_watchlist = Watchlist(user_id=user.id, name="Reference group", position=1)
        db.add(reference_watchlist)
        db.flush()
        watchlist.items.append(WatchlistItem(instrument_id=instrument.id, position=0))
        reference_watchlist.items.append(WatchlistItem(instrument_id=instrument_b.id, position=0))
        base = datetime(2024, 1, 1, tzinfo=UTC)
        for member, closes in ((instrument, (100, 110)), (instrument_b, (200, 210))):
            for offset, close in enumerate(closes):
                db.add(
                    OHLCVBar(
                        instrument_id=member.id,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=offset),
                        open=close,
                        high=close + 1,
                        low=close - 1,
                        close=close,
                        volume=1_000_000,
                        is_adjusted=True,
                    )
                )
        db.flush()

        response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "relative_return",
                "reference_source_id": f"watchlist:{reference_watchlist.id}",
                "end": "2024-01-02T00:00:00Z",
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["reference_source_id"] == f"watchlist:{reference_watchlist.id}"
        assert body["reference_source"]["source_id"] == f"watchlist:{reference_watchlist.id}"
        assert body["reference_series_method"] == "derived_equal_weight_return_index"
        assert body["cells"][0]["color_value"] == pytest.approx(0.05)

    def test_market_map_colours_tiles_by_reusable_breadth_condition(
        self, client, auth_headers, db, watchlist, instrument, instrument_b
    ):
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.watchlist import WatchlistItem

        watchlist.items.extend(
            [
                WatchlistItem(instrument_id=instrument.id, position=0),
                WatchlistItem(instrument_id=instrument_b.id, position=1),
            ]
        )
        base = datetime(2024, 1, 1, tzinfo=UTC)
        for offset, price in enumerate((100, 101, 102, 103, 104, 105)):
            for member, multiplier in ((instrument, 1), (instrument_b, 2)):
                db.add(
                    OHLCVBar(
                        instrument_id=member.id,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=offset),
                        open=price * multiplier,
                        high=price * multiplier + 1,
                        low=price * multiplier - 1,
                        close=price * multiplier,
                        volume=1_000_000,
                        is_adjusted=True,
                    )
                )
        db.flush()

        response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "breadth",
                "condition": {
                    "kind": "above_moving_average",
                    "params": {"period": 3, "average": "sma", "comparator": "above"},
                },
                "end": "2024-01-06T00:00:00Z",
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["color_metric"] == "breadth"
        assert body["condition"]["kind"] == "above_moving_average"
        assert {cell["condition_value"] for cell in body["cells"]} == {True}
        assert all(cell["condition_metric"] > 0 for cell in body["cells"])
        assert all(cell["color_value"] > 0 for cell in body["cells"])

        missing_condition = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "color_metric": "breadth",
            },
        )
        assert missing_condition.status_code == 422

    def test_market_map_colours_tiles_by_cross_sectional_percentile_condition(
        self, client, auth_headers, db, watchlist, instrument, instrument_b
    ):
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.watchlist import WatchlistItem

        watchlist.items.extend(
            [
                WatchlistItem(instrument_id=instrument.id, position=0),
                WatchlistItem(instrument_id=instrument_b.id, position=1),
            ]
        )
        base = datetime(2024, 1, 1, tzinfo=UTC)
        closes_by_member = {
            instrument.id: (100, 101, 102, 103, 104, 110),
            instrument_b.id: (100, 100.5, 101, 101.5, 102, 102.5),
        }
        for member_id, closes in closes_by_member.items():
            for offset, close in enumerate(closes):
                db.add(
                    OHLCVBar(
                        instrument_id=member_id,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=offset),
                        open=close,
                        high=close + 1,
                        low=close - 1,
                        close=close,
                        volume=1_000_000,
                        is_adjusted=True,
                    )
                )
        db.flush()

        response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "breadth",
                "condition": {
                    "kind": "percentile",
                    "target_scope": "cross_sectional",
                    "params": {"field": "return", "operator": "gte", "percentile": 0.8},
                },
                "end": "2024-01-06T00:00:00Z",
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        cells = {cell["instrument_id"]: cell for cell in body["cells"]}
        assert cells[instrument.id]["condition_value"] is True
        assert cells[instrument.id]["condition_metric"] == pytest.approx(1.0)
        assert cells[instrument.id]["color_value"] == pytest.approx(1.0)
        assert cells[instrument_b.id]["condition_value"] is False
        assert cells[instrument_b.id]["condition_metric"] == pytest.approx(0.5)
        assert cells[instrument_b.id]["color_value"] == pytest.approx(-1.0)

        mixed_response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "breadth",
                "condition": {
                    "kind": "all",
                    "params": {
                        "conditions": [
                            {
                                "kind": "percentile",
                                "target_scope": "cross_sectional",
                                "params": {
                                    "field": "return",
                                    "operator": "gte",
                                    "percentile": 0.8,
                                },
                            },
                            {
                                "kind": "comparison",
                                "params": {
                                    "field": "close",
                                    "operator": "gte",
                                    "threshold": 100,
                                },
                            },
                        ]
                    },
                },
                "end": "2024-01-06T00:00:00Z",
            },
        )

        assert mixed_response.status_code == 200, mixed_response.text
        mixed_cells = {
            cell["instrument_id"]: cell for cell in mixed_response.json()["cells"]
        }
        assert mixed_cells[instrument.id]["condition_value"] is True
        assert mixed_cells[instrument_b.id]["condition_value"] is False
        assert mixed_cells[instrument.id]["condition_metric"] is not None
        assert mixed_cells[instrument_b.id]["condition_metric"] is not None

        statistic_response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "breadth",
                "condition": {
                    "kind": "cross_sectional_statistic",
                    "target_scope": "cross_sectional",
                    "params": {
                        "field": "close",
                        "statistic": "mean",
                        "operator": "gte",
                        "threshold": 0,
                    },
                },
                "end": "2024-01-06T00:00:00Z",
            },
        )

        assert statistic_response.status_code == 200, statistic_response.text
        statistic_cells = {
            cell["instrument_id"]: cell for cell in statistic_response.json()["cells"]
        }
        assert statistic_cells[instrument.id]["condition_value"] is True
        assert statistic_cells[instrument_b.id]["condition_value"] is False
        assert statistic_cells[instrument.id]["condition_metric"] == pytest.approx(3.75)
        assert statistic_cells[instrument_b.id]["condition_metric"] == pytest.approx(-3.75)

    def test_market_map_colours_tiles_by_event_predicate_with_loaded_state(
        self, client, auth_headers, db, watchlist, instrument, instrument_b
    ):
        from app.models.instrument_event import (
            InstrumentEvent,
            InstrumentEventFetchState,
            InstrumentEventType,
        )
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.watchlist import WatchlistItem

        watchlist.items.extend(
            [
                WatchlistItem(instrument_id=instrument.id, position=0),
                WatchlistItem(instrument_id=instrument_b.id, position=1),
            ]
        )
        base = datetime(2024, 1, 1, tzinfo=UTC)
        for offset in range(6):
            for member in (instrument, instrument_b):
                price = 100 + offset
                db.add(
                    OHLCVBar(
                        instrument_id=member.id,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=offset),
                        open=price,
                        high=price + 1,
                        low=price - 1,
                        close=price,
                        volume=1_000_000,
                        is_adjusted=True,
                    )
                )
        db.add_all(
            [
                InstrumentEvent(
                    instrument_id=instrument.id,
                    event_type=InstrumentEventType.DIVIDEND,
                    event_time=base + timedelta(days=4),
                    title="Fixture dividend",
                    source="controlled_fixture",
                    source_event_key="div-1",
                    fetched_at=base + timedelta(days=4),
                ),
                InstrumentEventFetchState(
                    instrument_id=instrument.id,
                    source="controlled_fixture",
                    fetched_at=base + timedelta(days=5),
                ),
                InstrumentEventFetchState(
                    instrument_id=instrument_b.id,
                    source="controlled_fixture",
                    fetched_at=base + timedelta(days=5),
                ),
            ]
        )
        db.flush()

        response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "breadth",
                "condition": {
                    "kind": "event",
                    "params": {"event_type": "dividend", "lookback_days": 2},
                },
                "end": "2024-01-06T00:00:00Z",
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        cells = {cell["symbol"]: cell for cell in body["cells"]}
        assert cells["AAPL"]["condition_value"] is True
        assert cells["AAPL"]["color_value"] == 1
        assert cells["MSFT"]["condition_value"] is False
        assert cells["MSFT"]["color_value"] == -1

        db.add(
            InstrumentEvent(
                instrument_id=instrument.id,
                event_type=InstrumentEventType.DIVIDEND,
                event_time=base + timedelta(days=5),
                title="Later fixture dividend",
                source="controlled_fixture",
                source_event_key="div-2",
                fetched_at=base + timedelta(days=6, hours=1),
            )
        )
        db.query(InstrumentEventFetchState).filter(
            InstrumentEventFetchState.instrument_id == instrument.id,
            InstrumentEventFetchState.source == "controlled_fixture",
        ).one().fetched_at = base + timedelta(days=6, hours=1)
        db.flush()
        refreshed = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "breadth",
                "condition": {
                    "kind": "event",
                    "params": {"event_type": "dividend", "lookback_days": 2},
                },
                "end": "2024-01-06T00:00:00Z",
            },
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["cache_hit"] is False
        assert refreshed.json()["cache_key"] != body["cache_key"]

    def test_sources_unify_personal_and_locked_index_universes(
        self, client, auth_headers, db, watchlist, instrument
    ):
        now = datetime(2024, 1, 1, tzinfo=UTC)
        group = MarketGroup(
            stable_key="test-index",
            group_type="benchmark_family",
            name="Test Index",
            source="controlled_fixture",
            effective_at=now,
            known_at=now,
        )
        db.add(group)
        db.flush()
        db.add(
            MarketGroupMember(
                market_group_id=group.id,
                instrument_id=instrument.id,
                position=0,
                relationship_type="constituent",
                source="controlled_fixture",
                verification_state="verified",
                effective_at=now,
                known_at=now,
            )
        )
        db.flush()

        response = client.get("/api/v1/watchlists/sources", headers=auth_headers)

        assert response.status_code == 200
        sources = {item["source_id"]: item for item in response.json()}
        assert sources[f"watchlist:{watchlist.id}"]["source_kind"] == "personal"
        assert sources[f"watchlist:{watchlist.id}"]["can_edit_membership"] is True
        assert sources["market-group:test-index"]["source_kind"] == "index_membership"
        assert sources["market-group:test-index"]["locked"] is True
        assert sources["market-group:test-index"]["can_edit_membership"] is False
        assert sources["market-group:test-index"]["member_count"] == 1

        current = client.get(
            "/api/v1/watchlists/sources/market-group:test-index",
            headers=auth_headers,
            params={"as_of": "2024-01-02T00:00:00Z"},
        )
        assert current.status_code == 200
        assert [member["instrument_id"] for member in current.json()["members"]] == [instrument.id]
        assert current.json()["exclusions"] == []

        historical = client.get(
            "/api/v1/watchlists/sources/market-group:test-index",
            headers=auth_headers,
            params={"as_of": "2023-12-31T00:00:00Z"},
        )
        assert historical.status_code == 200
        assert historical.json()["members"] == []
        assert historical.json()["exclusions"][0]["reason"] == "membership_not_known_at_as_of"

    def test_benchmark_family_leg_sources_feed_the_same_map_and_breadth_contract(
        self, client, auth_headers, db, instrument, instrument_type, ohlcv_bars
    ):
        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument
        from app.models.ohlcv import Timeframe

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200, seeded.text
        mdy = Instrument(
            symbol="MDY",
            name="SPDR S&P MidCap 400 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(mdy)
        db.flush()
        profile = ETFProfile(instrument_id=mdy.id, adapter_status="resolved")
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2024, 1, 1, tzinfo=UTC).date(),
            known_at=datetime(2024, 1, 2, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="controlled_fixture",
            source_quality="issuer_disclosed",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            total_weight=1.0,
            snapshot_hash="family-derived-equal-source",
        )
        db.add(snapshot)
        db.flush()
        db.add(
            ETFHolding(
                snapshot_id=snapshot.id,
                constituent_instrument_id=instrument.id,
                position=0,
                reported_symbol=instrument.symbol,
                reported_name=instrument.name,
                weight=1.0,
                holding_type="equity",
                row_type="security",
                source_row_hash="family-derived-equal-row",
                is_resolved=True,
            )
        )
        db.flush()

        sources = client.get("/api/v1/watchlists/sources", headers=auth_headers)
        assert sources.status_code == 200, sources.text
        source = next(
            item
            for item in sources.json()
            if item["source_id"] == "benchmark-family:sp400:equal_weight"
        )
        assert source["locked"] is True
        assert source["symbol"] == "MDY"
        assert source["provenance"]["derived"] is True
        assert source["provenance"]["availability"] == "available"
        assert source["provenance"]["membership_semantics"] == (
            "derived_equal_weight_point_in_time_membership"
        )

        resolved = client.get(
            "/api/v1/watchlists/sources/benchmark-family:sp400:equal_weight",
            headers=auth_headers,
            params={"as_of": "2024-01-03T00:00:00Z"},
        )
        assert resolved.status_code == 200, resolved.text
        resolved_payload = resolved.json()
        assert resolved_payload["source"]["provenance"]["derived"] is True
        assert resolved_payload["members"][0]["instrument_id"] == instrument.id
        assert resolved_payload["members"][0]["weight"] == 1.0
        assert resolved_payload["members"][0]["relationship_type"] == (
            "derived_equal_weight_constituent"
        )

        market_map = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": "benchmark-family:sp400:equal_weight",
                "period": "1D",
                "area_metric": "weight",
                "color_metric": "return",
                "end": ohlcv_bars[-1].ts.isoformat(),
            },
        )
        assert market_map.status_code == 200, market_map.text
        assert market_map.json()["source"]["source_id"] == (
            "benchmark-family:sp400:equal_weight"
        )
        assert market_map.json()["cells"][0]["area_value"] == 1.0

        breadth = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "version": 1,
                "universe": {
                    "kind": "watchlist",
                    "key": "benchmark-family:sp400:equal_weight",
                    "point_in_time": True,
                },
                "condition": {
                    "kind": "above_moving_average",
                    "params": {"period": 2, "average": "sma", "comparator": "above"},
                },
                "timeframe": Timeframe.D1.value,
                "adjusted": True,
                "as_of": ohlcv_bars[-1].ts.isoformat(),
            },
        )
        assert breadth.status_code == 200, breadth.text
        assert breadth.json()["universe"]["source_id"] == (
            "benchmark-family:sp400:equal_weight"
        )
        assert breadth.json()["universe"]["membership_semantics"] == (
            "locked_source_members"
        )

    def test_every_available_benchmark_family_role_is_a_map_and_breadth_source(
        self, client, auth_headers, db, instrument, instrument_type, ohlcv_bars
    ):
        """The seeded source catalog must exercise every configured family leg, not only SPY."""

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument
        from app.services.top_down_taxonomy import (
            BENCHMARK_FAMILY_REGISTRY,
            benchmark_family_proxy_symbols,
        )

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200, seeded.text
        proxy_symbols = benchmark_family_proxy_symbols()
        instruments = {
            symbol: db.query(Instrument).filter_by(symbol=symbol).one_or_none()
            for symbol in proxy_symbols
        }
        for symbol in proxy_symbols:
            if instruments[symbol] is None:
                instruments[symbol] = Instrument(
                    symbol=symbol,
                    name=f"{symbol} controlled benchmark proxy",
                    currency="USD",
                    instrument_type_id=instrument_type.id,
                    is_active=True,
                )
                db.add(instruments[symbol])
        db.flush()

        composition_date = datetime(2024, 1, 1, tzinfo=UTC).date()
        known_at = datetime(2024, 1, 2, tzinfo=UTC)
        for symbol in proxy_symbols:
            profile = db.query(ETFProfile).filter_by(instrument_id=instruments[symbol].id).one_or_none()
            if profile is None:
                profile = ETFProfile(
                    instrument_id=instruments[symbol].id,
                    adapter_status="resolved",
                )
                db.add(profile)
                db.flush()
            snapshot = ETFHoldingsSnapshot(
                etf_profile_id=profile.id,
                composition_date=composition_date,
                known_at=known_at,
                provenance="controlled_fixture",
                source_provider="controlled_fixture",
                source_quality="issuer_disclosed",
                completeness_status="complete",
                row_count=1,
                resolved_count=1,
                unresolved_count=0,
                total_weight=1.0,
                snapshot_hash=f"family-matrix-{symbol}",
            )
            db.add(snapshot)
            db.flush()
            db.add(
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=instrument.id,
                    position=0,
                    reported_symbol=instrument.symbol,
                    reported_name=instrument.name,
                    weight=1.0,
                    holding_type="equity",
                    row_type="security",
                    source_row_hash=f"family-matrix-{symbol}-row",
                    is_resolved=True,
                )
            )
        db.flush()

        expected_sources: list[str] = []
        for family in BENCHMARK_FAMILY_REGISTRY:
            for role in ("cap_weight", "equal_weight", "value", "growth"):
                mapping = family.get(role) or {}
                if mapping.get("symbol") or (
                    role == "equal_weight"
                    and (family.get("derived_equal_weight") or {}).get("allowed")
                ):
                    expected_sources.append(
                        f"benchmark-family:{family['logical_key']}:{role}"
                    )

        listed = client.get("/api/v1/watchlists/sources", headers=auth_headers)
        assert listed.status_code == 200, listed.text
        listed_by_id = {item["source_id"]: item for item in listed.json()}
        assert set(expected_sources) <= set(listed_by_id)
        assert all(listed_by_id[source_id]["locked"] for source_id in expected_sources)
        assert all(
            listed_by_id[source_id]["provenance"]["availability"] == "available"
            for source_id in expected_sources
        )

        end = ohlcv_bars[-1].ts.isoformat()
        for source_id in expected_sources:
            resolved = client.get(
                f"/api/v1/watchlists/sources/{source_id}",
                headers=auth_headers,
                params={"as_of": end},
            )
            assert resolved.status_code == 200, (source_id, resolved.text)
            assert resolved.json()["members"][0]["instrument_id"] == instrument.id

            market_map = client.post(
                "/api/v1/analysis/market-map",
                headers=auth_headers,
                json={
                    "source_id": source_id,
                    "group_by": "none",
                    "period": "1D",
                    "area_metric": "equal",
                    "color_metric": "return",
                    "end": end,
                },
            )
            assert market_map.status_code == 200, (source_id, market_map.text)
            assert market_map.json()["source"]["source_id"] == source_id
            assert market_map.json()["cells"][0]["instrument_id"] == instrument.id

            breadth = client.post(
                "/api/v1/analysis/breadth",
                headers=auth_headers,
                json={
                    "version": 1,
                    "universe": {
                        "kind": "watchlist",
                        "key": source_id,
                        "point_in_time": True,
                    },
                    "condition": {
                        "kind": "above_moving_average",
                        "params": {"period": 2, "average": "sma", "comparator": "above"},
                    },
                    "timeframe": "D1",
                    "adjusted": True,
                    "as_of": end,
                },
            )
            assert breadth.status_code == 200, (source_id, breadth.text)
            assert breadth.json()["universe"]["source_id"] == source_id

    def test_managed_watchlist_source_respects_departure_at_as_of(
        self, client, auth_headers, db, user, instrument
    ):
        from app.models.watchlist import WatchlistItem

        added_at = datetime(2024, 1, 1, tzinfo=UTC)
        left_at = datetime(2024, 1, 5, tzinfo=UTC)
        managed = Watchlist(
            user_id=user.id,
            name="Managed historical source",
            is_managed=True,
            is_locked=True,
        )
        db.add(managed)
        db.flush()
        db.add(
            WatchlistItem(
                watchlist_id=managed.id,
                instrument_id=instrument.id,
                position=0,
                added_at=added_at,
                left_screener_at=left_at,
            )
        )
        db.flush()

        before_departure = client.get(
            f"/api/v1/watchlists/sources/watchlist:{managed.id}",
            headers=auth_headers,
            params={"as_of": "2024-01-04T00:00:00Z"},
        )
        assert before_departure.status_code == 200, before_departure.text
        assert [member["instrument_id"] for member in before_departure.json()["members"]] == [instrument.id]
        assert before_departure.json()["exclusions"] == []

        after_departure = client.get(
            f"/api/v1/watchlists/sources/watchlist:{managed.id}",
            headers=auth_headers,
            params={"as_of": "2024-01-05T00:00:00Z"},
        )
        assert after_departure.status_code == 200, after_departure.text
        assert after_departure.json()["members"] == []
        assert after_departure.json()["exclusions"][0]["reason"] == "membership_not_active_at_as_of"
        assert after_departure.json()["exclusions"][0]["left_screener_at"].startswith("2024-01-05")

    def test_etf_holdings_source_is_locked_watchlist_for_the_same_market_map_contract(
        self, client, auth_headers, db, instrument, instrument_b
    ):
        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import EquityDetail
        from app.models.instrument_stats import InstrumentStats
        from app.models.ohlcv import OHLCVBar, Timeframe

        composition = datetime(2024, 1, 1, tzinfo=UTC)
        profile = ETFProfile(
            instrument_id=instrument.id,
            issuer="Controlled issuer",
            adapter_key="controlled_fixture",
            adapter_status="resolved",
        )
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=composition.date(),
            known_at=composition,
            provenance="issuer_native",
            source_provider="controlled_fixture",
            source_quality="issuer_disclosed",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            total_weight=1.0,
            snapshot_hash="watchlist-etf-source-fixture",
        )
        db.add(snapshot)
        db.flush()
        db.add(
            ETFHolding(
                snapshot_id=snapshot.id,
                constituent_instrument_id=instrument_b.id,
                position=0,
                reported_symbol=instrument_b.symbol,
                reported_name=instrument_b.name,
                weight=1.0,
                holding_type="equity",
                row_type="security",
                source_row_hash="watchlist-etf-source-row",
                is_resolved=True,
            )
        )
        db.add_all(
            [
                EquityDetail(instrument_id=instrument_b.id, sector="Technology", industry="Software"),
                InstrumentStats(instrument_id=instrument_b.id, market_cap=100),
            ]
        )
        base = datetime(2024, 1, 1, tzinfo=UTC)
        for day, close in enumerate((100, 101, 102)):
            db.add(
                OHLCVBar(
                    instrument_id=instrument_b.id,
                    timeframe=Timeframe.D1,
                    ts=base + timedelta(days=day),
                    open=close,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=1000,
                    is_adjusted=True,
                )
            )
        db.flush()

        source_id = f"etf-holdings:{instrument.symbol}"
        descriptor = client.get("/api/v1/watchlists/sources", headers=auth_headers)
        assert descriptor.status_code == 200
        source = next(item for item in descriptor.json() if item["source_id"] == source_id)
        assert source["source_kind"] == "etf_holdings"
        assert source["locked"] is True
        assert source["can_edit_membership"] is False
        assert source["member_count"] == 1

        resolved = client.get(
            f"/api/v1/watchlists/sources/{source_id}",
            headers=auth_headers,
            params={"as_of": "2024-01-02T00:00:00Z"},
        )
        assert resolved.status_code == 200, resolved.text
        assert [member["instrument_id"] for member in resolved.json()["members"]] == [instrument_b.id]
        assert resolved.json()["members"][0]["weight"] == 1.0

        market_map = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": source_id,
                "period": "1D",
                "area_metric": "weight",
                "color_metric": "return",
                "end": "2024-01-03T00:00:00Z",
            },
        )
        assert market_map.status_code == 200, market_map.text
        body = market_map.json()
        assert body["source"]["source_id"] == source_id
        assert body["source"]["locked"] is True
        assert body["cells"][0]["area_value"] == 1.0
        assert body["cells"][0]["area_provenance"]["kind"] == "point_in_time_membership"

    def test_combo_source_is_locked_derived_universe_for_the_same_market_map_contract(
        self, client, auth_headers, db, instrument, instrument_b
    ):
        from app.models.ohlcv import OHLCVBar, Timeframe

        first = client.post(
            "/api/v1/watchlists", headers=auth_headers, json={"name": "Combo source A"}
        )
        second = client.post(
            "/api/v1/watchlists", headers=auth_headers, json={"name": "Combo source B"}
        )
        assert first.status_code == 200 and second.status_code == 200
        first_id = first.json()["id"]
        second_id = second.json()["id"]
        assert client.post(
            f"/api/v1/watchlists/{first_id}/items",
            headers=auth_headers,
            json={"instrument_id": instrument.id},
        ).status_code == 200
        assert client.post(
            f"/api/v1/watchlists/{second_id}/items",
            headers=auth_headers,
            json={"instrument_id": instrument_b.id},
        ).status_code == 200

        combo = client.put(
            "/api/v1/workspaces/library/items/combo_list/analysis-combo",
            headers=auth_headers,
            json={
                "kind": "combo_list",
                "stable_key": "analysis-combo",
                "name": "Analysis combo",
                "payload": {
                    "union_watchlist_ids": [first_id, second_id],
                    "exclude_watchlist_ids": [second_id],
                },
                "dependency_metadata": {},
            },
        )
        assert combo.status_code == 200, combo.text

        sources = client.get("/api/v1/watchlists/sources", headers=auth_headers)
        assert sources.status_code == 200
        descriptor = next(item for item in sources.json() if item["source_id"] == "combo:analysis-combo")
        assert descriptor["source_kind"] == "combo"
        assert descriptor["locked"] is True
        assert descriptor["can_edit_membership"] is False
        assert descriptor["member_count"] == 1

        resolved = client.get(
            "/api/v1/watchlists/sources/combo:analysis-combo", headers=auth_headers
        )
        assert resolved.status_code == 200, resolved.text
        assert [member["instrument_id"] for member in resolved.json()["members"]] == [instrument.id]

        base = datetime(2024, 1, 1, tzinfo=UTC)
        for offset, member in enumerate((instrument, instrument_b)):
            for day, close in enumerate((100 + offset, 101 + offset)):
                db.add(
                    OHLCVBar(
                        instrument_id=member.id,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=day),
                        open=close,
                        high=close + 1,
                        low=close - 1,
                        close=close,
                        volume=1000,
                        is_adjusted=True,
                    )
                )
        db.flush()
        market_map = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": "combo:analysis-combo",
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "return",
                "end": "2024-01-03T00:00:00Z",
            },
        )
        assert market_map.status_code == 200, market_map.text
        assert market_map.json()["source"]["source_id"] == "combo:analysis-combo"
        assert market_map.json()["requested_count"] == 1
        assert [cell["symbol"] for cell in market_map.json()["cells"]] == [instrument.symbol]

    def test_watchlist_and_combo_membership_versions_follow_membership_changes(
        self, client, auth_headers, db, instrument, instrument_b
    ):
        from app.models.ohlcv import OHLCVBar, Timeframe

        created = client.post(
            "/api/v1/watchlists", headers=auth_headers, json={"name": "Mutable map source"}
        )
        assert created.status_code == 200, created.text
        watchlist_id = created.json()["id"]
        assert client.post(
            f"/api/v1/watchlists/{watchlist_id}/items",
            headers=auth_headers,
            json={"instrument_id": instrument.id, "position": 0},
        ).status_code == 200
        combo = client.put(
            "/api/v1/workspaces/library/items/combo_list/mutable-map-combo",
            headers=auth_headers,
            json={
                "kind": "combo_list",
                "stable_key": "mutable-map-combo",
                "name": "Mutable map combo",
                "payload": {"union_watchlist_ids": [watchlist_id]},
                "dependency_metadata": {},
            },
        )
        assert combo.status_code == 200, combo.text

        base = datetime(2024, 1, 1, tzinfo=UTC)
        for member in (instrument, instrument_b):
            for day, close in enumerate((100, 101, 102)):
                db.add(
                    OHLCVBar(
                        instrument_id=member.id,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=day),
                        open=close,
                        high=close + 1,
                        low=close - 1,
                        close=close,
                        volume=1000,
                        is_adjusted=True,
                    )
                )
        db.flush()

        before = client.get("/api/v1/watchlists/sources", headers=auth_headers)
        assert before.status_code == 200, before.text
        before_sources = {item["source_id"]: item for item in before.json()}
        personal_id = f"watchlist:{watchlist_id}"
        combo_id = "combo:mutable-map-combo"
        personal_version = before_sources[personal_id]["membership_version"]
        combo_version = before_sources[combo_id]["membership_version"]
        assert before_sources[personal_id]["member_count"] == 1
        assert before_sources[combo_id]["member_count"] == 1

        initial_map = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": combo_id,
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "return",
                "end": "2024-01-03T00:00:00Z",
            },
        )
        assert initial_map.status_code == 200, initial_map.text
        initial_body = initial_map.json()
        assert initial_body["requested_count"] == 1

        added = client.post(
            f"/api/v1/watchlists/{watchlist_id}/items",
            headers=auth_headers,
            json={"instrument_id": instrument_b.id, "position": 1},
        )
        assert added.status_code == 200, added.text

        after = client.get("/api/v1/watchlists/sources", headers=auth_headers)
        assert after.status_code == 200, after.text
        after_sources = {item["source_id"]: item for item in after.json()}
        assert after_sources[personal_id]["membership_version"] != personal_version
        assert after_sources[combo_id]["membership_version"] != combo_version
        assert after_sources[combo_id]["member_count"] == 2

        resolved = client.get(f"/api/v1/watchlists/sources/{combo_id}", headers=auth_headers)
        assert resolved.status_code == 200, resolved.text
        assert [member["instrument_id"] for member in resolved.json()["members"]] == [
            instrument.id,
            instrument_b.id,
        ]

        breadth = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "universe": {"kind": "watchlist", "key": combo_id, "point_in_time": True},
                "condition": {
                    "kind": "above_moving_average",
                    "params": {"period": 2, "average": "sma", "comparator": "above"},
                },
                "timeframe": "D1",
                "adjusted": True,
            },
        )
        assert breadth.status_code == 200, breadth.text
        assert breadth.json()["universe"]["source_id"] == combo_id
        assert breadth.json()["requested_count"] == 2

        updated_map = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": combo_id,
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "return",
                "end": "2024-01-03T00:00:00Z",
            },
        )
        assert updated_map.status_code == 200, updated_map.text
        updated_body = updated_map.json()
        assert updated_body["requested_count"] == 2
        assert updated_body["cache_key"] != initial_body["cache_key"]

    def test_combo_source_respects_departure_at_as_of(
        self, client, auth_headers, db, user, instrument
    ):
        from app.models.watchlist import WatchlistItem
        from app.models.workstation import WorkspaceLibraryItem

        base = datetime(2024, 1, 1, tzinfo=UTC)
        departed_at = datetime(2024, 1, 5, tzinfo=UTC)
        managed = Watchlist(
            user_id=user.id,
            name="Managed combo dependency",
            is_managed=True,
            is_locked=True,
        )
        db.add(managed)
        db.flush()
        db.add(
            WatchlistItem(
                watchlist_id=managed.id,
                instrument_id=instrument.id,
                position=0,
                added_at=base,
                left_screener_at=departed_at,
            )
        )
        db.flush()

        combo = client.put(
            "/api/v1/workspaces/library/items/combo_list/historical-combo",
            headers=auth_headers,
            json={
                "kind": "combo_list",
                "stable_key": "historical-combo",
                "name": "Historical combo",
                "payload": {"union_watchlist_ids": [managed.id]},
                "dependency_metadata": {},
            },
        )
        assert combo.status_code == 200, combo.text
        combo_row = (
            db.query(WorkspaceLibraryItem)
            .filter(
                WorkspaceLibraryItem.user_id == user.id,
                WorkspaceLibraryItem.kind == "combo_list",
                WorkspaceLibraryItem.stable_key == "historical-combo",
            )
            .one()
        )
        combo_row.updated_at = base
        db.flush()

        before_departure = client.get(
            "/api/v1/watchlists/sources/combo:historical-combo",
            headers=auth_headers,
            params={"as_of": "2024-01-04T00:00:00Z"},
        )
        assert before_departure.status_code == 200, before_departure.text
        assert [member["instrument_id"] for member in before_departure.json()["members"]] == [instrument.id]
        assert before_departure.json()["exclusions"] == []

        after_departure = client.get(
            "/api/v1/watchlists/sources/combo:historical-combo",
            headers=auth_headers,
            params={"as_of": "2024-01-05T00:00:00Z"},
        )
        assert after_departure.status_code == 200, after_departure.text
        assert after_departure.json()["members"] == []
        assert after_departure.json()["exclusions"][0]["reason"] == "membership_not_active_at_as_of"

    def test_explicit_canonical_selection_is_a_locked_ephemeral_market_map_source(
        self, client, auth_headers, db, instrument, instrument_b
    ):
        from app.models.ohlcv import OHLCVBar, Timeframe

        base = datetime(2024, 1, 1, tzinfo=UTC)
        for member in (instrument, instrument_b):
            for day, close in enumerate((100, 101)):
                db.add(
                    OHLCVBar(
                        instrument_id=member.id,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=day),
                        open=close,
                        high=close + 1,
                        low=close - 1,
                        close=close,
                        volume=1000,
                        is_adjusted=True,
                    )
                )
        db.flush()
        source_id = f"explicit:{instrument.id},{instrument_b.id},{instrument.id}"
        resolved = client.get(
            f"/api/v1/watchlists/sources/{source_id}", headers=auth_headers
        )
        assert resolved.status_code == 200, resolved.text
        payload = resolved.json()
        assert payload["source"]["source_kind"] == "explicit"
        assert payload["source"]["locked"] is True
        assert payload["source"]["provenance"]["point_in_time"] is False
        assert [member["instrument_id"] for member in payload["members"]] == [
            instrument.id,
            instrument_b.id,
        ]

        market_map = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": source_id,
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "return",
                "end": "2024-01-03T00:00:00Z",
            },
        )
        assert market_map.status_code == 200, market_map.text
        assert market_map.json()["source"]["source_kind"] == "explicit"
        assert market_map.json()["requested_count"] == 2

        # Reference universes use the same canonical WatchlistSource contract
        # as the primary map source.  A bounded explicit selection can exceed
        # the length of a ticker-like ID while remaining valid after resolver
        # deduplication; it must not be rejected by a narrower request field.
        long_reference_source_id = "explicit:" + ",".join(
            [str(instrument.id)] * 125
        )
        relative_map = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": source_id,
                "period": "1D",
                "area_metric": "equal",
                "color_metric": "relative_return",
                "reference_source_id": long_reference_source_id,
                "end": "2024-01-03T00:00:00Z",
            },
        )
        assert relative_map.status_code == 200, relative_map.text
        assert relative_map.json()["reference_source_id"] == long_reference_source_id
        assert relative_map.json()["reference_source"]["source_kind"] == "explicit"

        malformed = client.get(
            "/api/v1/watchlists/sources/explicit:NVDA", headers=auth_headers
        )
        assert malformed.status_code == 400
        oversized = client.get(
            "/api/v1/watchlists/sources/explicit:" + ",".join(str(index) for index in range(1, 502)),
            headers=auth_headers,
        )
        assert oversized.status_code == 400

    def test_list_returns_existing_watchlists(self, client, auth_headers, watchlist):
        res = client.get("/api/v1/watchlists", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["name"] == watchlist.name

    def test_create_watchlist_assigns_next_position(self, client, auth_headers, watchlist):
        res = client.post(
            "/api/v1/watchlists",
            headers=auth_headers,
            json={"name": "Momentum", "description": "Daily ideas"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "Momentum"
        assert body["position"] == watchlist.position + 1

    def test_create_watchlist_rejects_duplicate_name_case_insensitive(
        self, client, auth_headers, watchlist
    ):
        res = client.post(
            "/api/v1/watchlists",
            headers=auth_headers,
            json={"name": watchlist.name.upper()},
        )
        assert res.status_code == 409

    def test_create_managed_watchlist_requires_existing_screener(self, client, auth_headers):
        res = client.post(
            "/api/v1/watchlists",
            headers=auth_headers,
            json={"name": "Managed", "screener_id": 99999},
        )
        assert res.status_code == 404

    def test_create_managed_watchlist_sets_is_managed(self, client, auth_headers, db, user):
        screener = ScreenerDefinition(
            user_id=user.id,
            name="Breakout",
            conditions={"conditions": []},
            is_active=True,
        )
        db.add(screener)
        db.flush()

        res = client.post(
            "/api/v1/watchlists",
            headers=auth_headers,
            json={"name": "Managed", "screener_id": screener.id},
        )
        assert res.status_code == 200
        assert res.json()["is_managed"] is True
        assert res.json()["screener_id"] == screener.id

    def test_add_item_to_watchlist(self, client, auth_headers, watchlist, instrument_b):
        res = client.post(
            f"/api/v1/watchlists/{watchlist.id}/items",
            headers=auth_headers,
            json={"instrument_id": instrument_b.id, "position": 2},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["instrument_id"] == instrument_b.id
        assert body["symbol"] == instrument_b.symbol

    def test_add_item_rejects_duplicate(self, client, auth_headers, db, watchlist, instrument):
        from app.models.watchlist import WatchlistItem

        db.add(WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id, position=0))
        db.flush()

        res = client.post(
            f"/api/v1/watchlists/{watchlist.id}/items",
            headers=auth_headers,
            json={"instrument_id": instrument.id},
        )
        assert res.status_code == 409

    def test_transfer_item_copy_and_move_are_atomic(
        self, client, auth_headers, db, user, watchlist, instrument, instrument_b
    ):
        from app.models.watchlist import WatchlistItem

        target = Watchlist(user_id=user.id, name="Destination", position=watchlist.position + 1)
        db.add(target)
        db.flush()
        first = WatchlistItem(
            watchlist_id=watchlist.id,
            instrument_id=instrument.id,
            position=0,
            flagged=True,
            notes="keep this annotation",
        )
        second = WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument_b.id, position=1)
        db.add_all([first, second])
        db.flush()

        copied = client.post(
            f"/api/v1/watchlists/{target.id}/items/transfer",
            headers=auth_headers,
            json={"source_watchlist_id": watchlist.id, "item_id": first.id, "mode": "copy"},
        )
        assert copied.status_code == 200
        assert copied.json()["instrument_id"] == instrument.id
        assert copied.json()["flagged"] is True
        assert copied.json()["symbol"] == instrument.symbol

        moved = client.post(
            f"/api/v1/watchlists/{target.id}/items/transfer",
            headers=auth_headers,
            json={"source_watchlist_id": watchlist.id, "item_id": second.id, "mode": "move"},
        )
        assert moved.status_code == 200
        assert moved.json()["instrument_id"] == instrument_b.id
        assert db.get(WatchlistItem, second.id) is None
        target_items = (
            db.query(WatchlistItem)
            .filter(WatchlistItem.watchlist_id == target.id)
            .order_by(WatchlistItem.position)
            .all()
        )
        assert [item.instrument_id for item in target_items] == [instrument.id, instrument_b.id]

    def test_transfer_item_rejects_locked_destination_and_invalid_mode(
        self, client, auth_headers, db, user, watchlist, instrument
    ):
        from app.models.watchlist import WatchlistItem

        target = Watchlist(
            user_id=user.id,
            name="Locked destination",
            position=watchlist.position + 1,
            is_locked=True,
        )
        db.add(target)
        db.flush()
        item = WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id, position=0)
        db.add(item)
        db.flush()

        locked = client.post(
            f"/api/v1/watchlists/{target.id}/items/transfer",
            headers=auth_headers,
            json={"source_watchlist_id": watchlist.id, "item_id": item.id, "mode": "copy"},
        )
        assert locked.status_code == 403
        invalid = client.post(
            f"/api/v1/watchlists/{watchlist.id}/items/transfer",
            headers=auth_headers,
            json={"source_watchlist_id": target.id, "item_id": item.id, "mode": "merge"},
        )
        assert invalid.status_code == 400

    def test_transfer_items_batch_is_atomic_and_preserves_order_and_metadata(
        self, client, auth_headers, db, user, watchlist, instrument, instrument_b
    ):
        from app.models.watchlist import WatchlistItem

        target = Watchlist(
            user_id=user.id, name="Batch destination", position=watchlist.position + 1
        )
        db.add(target)
        db.flush()
        first = WatchlistItem(
            watchlist_id=watchlist.id,
            instrument_id=instrument.id,
            position=0,
            flagged=True,
            notes="first",
        )
        second = WatchlistItem(
            watchlist_id=watchlist.id, instrument_id=instrument_b.id, position=1, notes="second"
        )
        db.add_all([first, second])
        db.flush()

        copied = client.post(
            f"/api/v1/watchlists/{target.id}/items/transfer-batch",
            headers=auth_headers,
            json={
                "source_watchlist_id": watchlist.id,
                "item_ids": [second.id, first.id],
                "mode": "copy",
            },
        )
        assert copied.status_code == 200
        assert [item["instrument_id"] for item in copied.json()] == [instrument.id, instrument_b.id]
        assert [item["flagged"] for item in copied.json()] == [True, False]
        assert db.get(WatchlistItem, first.id) is not None
        assert db.get(WatchlistItem, second.id) is not None

        missing = client.post(
            "/api/v1/watchlists/999999/items/transfer-batch",
            headers=auth_headers,
            json={
                "source_watchlist_id": watchlist.id,
                "item_ids": [first.id, second.id],
                "mode": "move",
            },
        )
        assert missing.status_code == 404
        assert db.get(WatchlistItem, first.id) is not None
        assert db.get(WatchlistItem, second.id) is not None

    def test_lock_prevents_manual_add_and_remove(
        self, client, auth_headers, db, watchlist, instrument_b
    ):
        lock = client.post(f"/api/v1/watchlists/{watchlist.id}/lock", headers=auth_headers)
        assert lock.status_code == 200

        add = client.post(
            f"/api/v1/watchlists/{watchlist.id}/items",
            headers=auth_headers,
            json={"instrument_id": instrument_b.id},
        )
        assert add.status_code == 403

        from app.models.watchlist import WatchlistItem

        item = WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument_b.id, position=1)
        db.add(item)
        db.flush()

        remove = client.delete(
            f"/api/v1/watchlists/{watchlist.id}/items/{item.id}",
            headers=auth_headers,
        )
        assert remove.status_code == 403

    def test_unlock_managed_watchlist_is_forbidden(self, client, auth_headers, db, user):
        managed = Watchlist(
            user_id=user.id,
            name="Managed",
            is_managed=True,
            is_locked=True,
            position=1,
        )
        db.add(managed)
        db.flush()

        res = client.post(f"/api/v1/watchlists/{managed.id}/unlock", headers=auth_headers)
        assert res.status_code == 403

    def test_rename_watchlist_trims_name(self, client, auth_headers, watchlist):
        res = client.patch(
            f"/api/v1/watchlists/{watchlist.id}",
            headers=auth_headers,
            json={"name": "  New Name  "},
        )
        assert res.status_code == 200
        assert res.json()["name"] == "New Name"

    def test_seed_watchlist_adds_missing_items(
        self, client, auth_headers, watchlist, instrument, instrument_b
    ):
        res = client.post(
            f"/api/v1/watchlists/{watchlist.id}/seed",
            headers=auth_headers,
            json={"instrument_ids": [instrument.id, instrument_b.id]},
        )
        assert res.status_code == 200
        items = res.json()["items"]
        assert {item["instrument_id"] for item in items} == {instrument.id, instrument_b.id}

    def test_copy_watchlist_skips_departed_items(
        self, client, auth_headers, db, watchlist, instrument, instrument_b
    ):
        from app.models.watchlist import WatchlistItem

        active = WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id, position=0)
        departed = WatchlistItem(
            watchlist_id=watchlist.id,
            instrument_id=instrument_b.id,
            position=1,
            left_screener_at=instrument.created_at,
        )
        db.add_all([active, departed])
        db.flush()

        res = client.post(f"/api/v1/watchlists/{watchlist.id}/copy", headers=auth_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["is_managed"] is False
        assert [item["instrument_id"] for item in body["items"]] == [instrument.id]

    def test_reorder_watchlists_updates_positions(self, client, auth_headers, db, user):
        wl1 = Watchlist(user_id=user.id, name="One", position=1)
        wl2 = Watchlist(user_id=user.id, name="Two", position=2)
        db.add_all([wl1, wl2])
        db.flush()

        res = client.post(
            "/api/v1/watchlists/reorder",
            headers=auth_headers,
            json={"ids": [wl2.id, wl1.id]},
        )
        assert res.status_code == 200
        db.refresh(wl1)
        db.refresh(wl2)
        assert wl2.position == 0
        assert wl1.position == 1

    def test_reorder_personal_watchlist_items_updates_positions(
        self, client, auth_headers, db, watchlist, instrument, instrument_b
    ):
        from app.models.watchlist import WatchlistItem

        first = WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id, position=0)
        second = WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument_b.id, position=1)
        db.add_all([first, second])
        db.flush()

        res = client.post(
            f"/api/v1/watchlists/{watchlist.id}/items/reorder",
            headers=auth_headers,
            json={"ids": [second.id, first.id]},
        )
        assert res.status_code == 200
        db.refresh(first)
        db.refresh(second)
        assert second.position == 0
        assert first.position == 1

    def test_reorder_managed_watchlist_items_is_forbidden(
        self, client, auth_headers, db, user, instrument
    ):
        from app.models.watchlist import WatchlistItem

        managed = Watchlist(user_id=user.id, name="Managed order", is_managed=True, position=0)
        db.add(managed)
        db.flush()
        item = WatchlistItem(watchlist_id=managed.id, instrument_id=instrument.id, position=0)
        db.add(item)
        db.flush()

        res = client.post(
            f"/api/v1/watchlists/{managed.id}/items/reorder",
            headers=auth_headers,
            json={"ids": [item.id]},
        )
        assert res.status_code == 403

    def test_delete_locked_watchlist_requires_unlock(self, client, auth_headers, watchlist):
        client.post(f"/api/v1/watchlists/{watchlist.id}/lock", headers=auth_headers)
        res = client.delete(f"/api/v1/watchlists/{watchlist.id}", headers=auth_headers)
        assert res.status_code == 403

    def test_market_map_consumes_completed_isolated_python_output(
        self, client, auth_headers, db, user, watchlist, instrument, instrument_b
    ):
        from app.models.research import CodeAsset, CodeVersion, ResearchArtifact, ResearchRun
        from app.models.watchlist import WatchlistItem

        db.add_all(
            [
                WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id, position=0),
                WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument_b.id, position=1),
            ]
        )
        asset = CodeAsset(user_id=user.id, stable_key="map-colour", name="Map colour", kind="condition")
        db.add(asset)
        db.flush()
        version = CodeVersion(
            code_asset_id=asset.id,
            version_number=1,
            source="return 1.0",
            output_contract="series",
            parameter_schema={},
            default_parameters={},
        )
        db.add(version)
        db.flush()
        run = ResearchRun(
            user_id=user.id,
            code_version_id=version.id,
            status="completed",
            run_config={"output_contract": "series"},
            dataset_manifest={"dataset_version": "test"},
        )
        run.artifacts.append(
            ResearchArtifact(
                artifact_type="batch",
                name="batch_cells",
                payload={
                    "value": {
                        "cells": [
                            {"instrument_id": instrument.id, "status": "completed", "value": 2.5},
                            {"instrument_id": instrument_b.id, "status": "completed", "value": -0.5},
                        ]
                    }
                },
            )
        )
        db.add(run)
        db.flush()

        response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "color_metric": "python",
                "python_run_id": run.id,
                "area_metric": "equal",
                "period": "1D",
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["python_run_id"] == run.id
        assert {cell["color_value"] for cell in body["cells"]} == {2.5, -0.5}
        assert body["coverage"] == 1

        area_response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "color_metric": "return",
                "area_metric": "python",
                "python_run_id": run.id,
                "period": "1D",
            },
        )
        assert area_response.status_code == 200, area_response.text
        area_cells = {cell["symbol"]: cell for cell in area_response.json()["cells"]}
        assert area_cells["AAPL"]["area_value"] == 2.5
        assert area_cells["MSFT"]["area_value"] is None
        assert any(item["code"] == "python_area_non_positive" for item in area_cells["MSFT"]["warnings"])

        boolean_run = ResearchRun(
            user_id=user.id,
            code_version_id=version.id,
            status="completed",
            run_config={"output_contract": "boolean"},
            dataset_manifest={"dataset_version": "test"},
        )
        boolean_run.artifacts.append(
            ResearchArtifact(
                artifact_type="batch",
                name="batch_cells",
                payload={
                    "value": {
                        "cells": [
                            {"instrument_id": instrument.id, "status": "completed", "value": True},
                            {"instrument_id": instrument_b.id, "status": "completed", "value": False},
                        ]
                    }
                },
            )
        )
        db.add(boolean_run)
        db.flush()
        boolean_response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "color_metric": "python",
                "python_run_id": boolean_run.id,
                "area_metric": "equal",
                "period": "1D",
            },
        )
        assert boolean_response.status_code == 200, boolean_response.text
        boolean_cells = {cell["symbol"]: cell for cell in boolean_response.json()["cells"]}
        assert boolean_cells["AAPL"]["condition_value"] is True
        assert boolean_cells["AAPL"]["color_value"] == 1
        assert boolean_cells["MSFT"]["condition_value"] is False
        assert boolean_cells["MSFT"]["color_value"] == -1
        boolean_area_response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "color_metric": "return",
                "area_metric": "python",
                "python_run_id": boolean_run.id,
                "period": "1D",
            },
        )
        assert boolean_area_response.status_code == 422

        invalid = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "color_metric": "python",
                "python_run_id": run.id + 100_000,
            },
        )
        assert invalid.status_code == 404

    def test_market_map_uses_provenance_aware_numeric_area_fields(
        self, client, auth_headers, db, user, watchlist, instrument, instrument_b, monkeypatch
    ):
        from datetime import datetime

        from app.models.data_source import DataSource
        from app.models.instrument_stats import InstrumentStats
        from app.models.provider_observation import InstrumentProfileSnapshot
        from app.models.provider_runtime import (
            ProviderCapability,
            ProviderEntitlement,
            ProviderEntitlementRevision,
            ProviderPolicy,
        )
        from app.models.research import CodeAsset, CodeVersion, ResearchArtifact, ResearchRun
        from app.models.watchlist import WatchlistItem

        monkeypatch.setattr(
            "app.services.market_map.list_provider_capabilities",
            lambda name: ["instrument_metadata"] if name == "fixture-field" else [],
        )

        db.add_all(
            [
                WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id, position=0),
                WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument_b.id, position=1),
                InstrumentStats(
                    instrument_id=instrument.id,
                    avg_volume_30d=2500,
                    field_provenance={"avg_volume_30d": {"source": "fixture", "observed_at": "2024-01-05T00:00:00Z"}},
                ),
                InstrumentStats(instrument_id=instrument_b.id, avg_volume_30d=1500, field_provenance={}),
            ]
        )
        field_source = DataSource(
            name="fixture-field", base_url="controlled://field", description="Field fixture"
        )
        db.add(field_source)
        db.flush()
        db.add_all(
            [
                ProviderPolicy(
                    data_source_id=field_source.id,
                    capability=ProviderCapability.INSTRUMENT_METADATA,
                    is_pinned=True,
                    effective_score=10,
                ),
                ProviderEntitlement(
                    data_source_id=field_source.id,
                    capability=ProviderCapability.INSTRUMENT_METADATA,
                    is_free=True,
                    enabled_environments=[],
                ),
                ProviderEntitlementRevision(
                    data_source_id=field_source.id,
                    capability=ProviderCapability.INSTRUMENT_METADATA,
                    revision=1,
                    configured_plan="fixture-field-v1",
                    is_free=True,
                    authentication_required=False,
                    redistribution_allowed=False,
                    effective_at=datetime(2023, 12, 1, tzinfo=UTC),
                    live_probe_status="passed",
                ),
                InstrumentProfileSnapshot(
                    instrument_id=instrument.id,
                    data_source_id=field_source.id,
                    provider_symbol=instrument.symbol,
                    observed_at=datetime(2024, 1, 5, tzinfo=UTC),
                    fetched_at=datetime(2024, 1, 5, tzinfo=UTC),
                    profile_hash="field-profile-a",
                    payload={"extra": {"average_volume": 4500}},
                ),
            ]
        )
        asset = CodeAsset(user_id=user.id, stable_key="map-field-colour", name="Map field", kind="condition")
        db.add(asset)
        db.flush()
        version = CodeVersion(
            code_asset_id=asset.id,
            version_number=1,
            source="return 1.0",
            output_contract="series",
            parameter_schema={},
            default_parameters={},
        )
        db.add(version)
        db.flush()
        run = ResearchRun(
            user_id=user.id,
            code_version_id=version.id,
            status="completed",
            run_config={"output_contract": "series"},
            dataset_manifest={"dataset_version": "test"},
        )
        run.artifacts.append(
            ResearchArtifact(
                artifact_type="batch",
                name="batch_cells",
                payload={"value": {"cells": [{"instrument_id": instrument.id, "status": "completed", "value": 1.0}, {"instrument_id": instrument_b.id, "status": "completed", "value": 1.0}]}},
            )
        )
        db.add(run)
        db.flush()

        response = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "group_by": "none",
                "color_metric": "python",
                "python_run_id": run.id,
                "area_metric": "field",
                "area_field": "avg_volume_30d",
                "period": "1D",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["area_metric"] == "field"
        assert body["area_field"] == "avg_volume_30d"
        cells = {cell["symbol"]: cell for cell in body["cells"]}
        assert cells["AAPL"]["area_value"] == 4500
        assert cells["AAPL"]["area_provenance"]["kind"] == "point_in_time_profile_snapshot"
        assert cells["AAPL"]["area_provenance"]["field"] == "avg_volume_30d"
        assert cells["AAPL"]["area_provenance"]["entitlement_historical"] is True
        assert cells["MSFT"]["area_value"] is None
        assert cells["AAPL"]["color_coverage"] == 1
        assert cells["AAPL"]["area_coverage"] == 1
        assert cells["MSFT"]["coverage"] == 0
        assert cells["MSFT"]["area_coverage"] == 0
        assert body["area_coverage"] == 0.5
        assert any(item["code"] == "unproven_area_field" for item in cells["MSFT"]["warnings"])

        invalid = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={"source_id": f"watchlist:{watchlist.id}", "area_metric": "field", "period": "1D"},
        )
        assert invalid.status_code == 422
