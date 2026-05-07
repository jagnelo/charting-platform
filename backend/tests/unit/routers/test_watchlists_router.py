from app.models.watchlist import WatchlistItem


class TestWatchlistsRouter:
    def test_requires_auth(self, client):
        res = client.get("/api/v1/watchlists")
        assert res.status_code == 401

    def test_create_add_item_and_lock_flow(self, client, auth_headers, watchlist, instrument_b):
        create = client.post(
            "/api/v1/watchlists",
            headers=auth_headers,
            json={"name": "Momentum", "description": "Ideas"},
        )
        assert create.status_code == 200
        watchlist_id = create.json()["id"]

        add = client.post(
            f"/api/v1/watchlists/{watchlist_id}/items",
            headers=auth_headers,
            json={"instrument_id": instrument_b.id, "position": 1},
        )
        assert add.status_code == 200
        assert add.json()["symbol"] == instrument_b.symbol

        lock = client.post(f"/api/v1/watchlists/{watchlist_id}/lock", headers=auth_headers)
        assert lock.status_code == 200

        blocked = client.post(
            f"/api/v1/watchlists/{watchlist_id}/items",
            headers=auth_headers,
            json={"instrument_id": instrument_b.id},
        )
        assert blocked.status_code == 403

    def test_copy_watchlist_omits_departed_items(
        self, client, auth_headers, db, watchlist, instrument, instrument_b
    ):
        db.add_all(
            [
                WatchlistItem(watchlist_id=watchlist.id, instrument_id=instrument.id, position=0),
                WatchlistItem(
                    watchlist_id=watchlist.id,
                    instrument_id=instrument_b.id,
                    position=1,
                    left_screener_at=instrument.created_at,
                ),
            ]
        )
        db.flush()

        copy = client.post(f"/api/v1/watchlists/{watchlist.id}/copy", headers=auth_headers)
        assert copy.status_code == 200
        assert [item["instrument_id"] for item in copy.json()["items"]] == [instrument.id]
