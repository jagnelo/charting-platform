from app.models.screener import ScreenerDefinition
from app.models.watchlist import Watchlist


class TestWatchlistsAuth:
    def test_list_requires_auth(self, client):
        res = client.get("/api/v1/watchlists")
        assert res.status_code == 401


class TestWatchlistsCrud:
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

    def test_delete_locked_watchlist_requires_unlock(self, client, auth_headers, watchlist):
        client.post(f"/api/v1/watchlists/{watchlist.id}/lock", headers=auth_headers)
        res = client.delete(f"/api/v1/watchlists/{watchlist.id}", headers=auth_headers)
        assert res.status_code == 403
