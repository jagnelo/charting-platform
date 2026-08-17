from datetime import UTC, datetime, timedelta

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
        assert {node["label"] for node in body["nodes"]} >= {"Technology", "Hardware", "Software"}
        assert body["nodes"][-1]["aggregation_method"] == "area_weighted_mean"
        assert body["cache_hit"] is False

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

        assert db.query(MarketMapCache).count() == 1
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

        invalid = client.post(
            "/api/v1/analysis/market-map",
            headers=auth_headers,
            json={
                "source_id": f"watchlist:{watchlist.id}",
                "color_metric": "python",
                "python_run_id": run.id + 100_000,
            },
        )
        assert invalid.status_code == 422
