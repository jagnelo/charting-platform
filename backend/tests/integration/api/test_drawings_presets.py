"""Integration tests for /drawings and /presets endpoints."""


class TestDrawings:
    def test_create_trendline(self, client, auth_headers, instrument):
        res = client.post(
            "/api/v1/drawings",
            headers=auth_headers,
            json={
                "instrument_id": instrument.id,
                "timeframe": "D1",
                "drawing_type": "trendline",
                "data": {
                    "points": [
                        {"time": 1700000000, "price": 180.0},
                        {"time": 1701000000, "price": 185.0},
                    ]
                },
                "style": {"color": "#64b5f6", "lineWidth": 1.5},
                "is_visible": True,
                "is_locked": False,
                "pin_to_all": False,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["drawing_type"] == "trendline"
        assert data["is_visible"] is True

    def test_create_pinned_drawing(self, client, auth_headers, instrument):
        res = client.post(
            "/api/v1/drawings",
            headers=auth_headers,
            json={
                "instrument_id": instrument.id,
                "timeframe": None,
                "drawing_type": "horizontal_line",
                "data": {"price": 200.0},
                "style": {"color": "#ffb74d"},
                "is_visible": True,
                "is_locked": False,
                "pin_to_all": True,
            },
        )
        assert res.status_code == 201
        assert res.json()["pin_to_all"] is True

    def test_list_drawings_by_instrument_and_timeframe(self, client, auth_headers, instrument):
        # Create two drawings: one D1, one H1
        client.post(
            "/api/v1/drawings",
            headers=auth_headers,
            json={
                "instrument_id": instrument.id,
                "timeframe": "D1",
                "drawing_type": "trendline",
                "data": {},
                "style": {},
                "is_visible": True,
                "is_locked": False,
                "pin_to_all": False,
            },
        )
        client.post(
            "/api/v1/drawings",
            headers=auth_headers,
            json={
                "instrument_id": instrument.id,
                "timeframe": "H1",
                "drawing_type": "horizontal_line",
                "data": {},
                "style": {},
                "is_visible": True,
                "is_locked": False,
                "pin_to_all": False,
            },
        )
        res = client.get(
            "/api/v1/drawings",
            params={"instrument_id": instrument.id, "timeframe": "D1"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        tfs = [d["timeframe"] for d in res.json()]
        assert all(tf in ("D1", None) for tf in tfs)

    def test_list_drawings_includes_pinned(self, client, auth_headers, instrument):
        """pin_to_all drawings should appear regardless of requested timeframe."""
        client.post(
            "/api/v1/drawings",
            headers=auth_headers,
            json={
                "instrument_id": instrument.id,
                "timeframe": None,
                "drawing_type": "horizontal_line",
                "data": {},
                "style": {},
                "is_visible": True,
                "is_locked": False,
                "pin_to_all": True,
            },
        )
        for tf in ("D1", "H1", "M15"):
            res = client.get(
                "/api/v1/drawings",
                params={"instrument_id": instrument.id, "timeframe": tf},
                headers=auth_headers,
            )
            pinned = [d for d in res.json() if d["pin_to_all"]]
            assert len(pinned) >= 1

    def test_update_drawing_style(self, client, auth_headers, instrument):
        create = client.post(
            "/api/v1/drawings",
            headers=auth_headers,
            json={
                "instrument_id": instrument.id,
                "timeframe": "D1",
                "drawing_type": "trendline",
                "data": {},
                "style": {"color": "#fff"},
                "is_visible": True,
                "is_locked": False,
                "pin_to_all": False,
            },
        )
        drawing_id = create.json()["id"]
        res = client.patch(
            f"/api/v1/drawings/{drawing_id}",
            headers=auth_headers,
            json={
                "style": {"color": "#ff0000", "lineWidth": 2},
                "is_locked": True,
            },
        )
        assert res.status_code == 200
        assert res.json()["style"]["color"] == "#ff0000"
        assert res.json()["is_locked"] is True

    def test_delete_drawing(self, client, auth_headers, instrument):
        create = client.post(
            "/api/v1/drawings",
            headers=auth_headers,
            json={
                "instrument_id": instrument.id,
                "timeframe": "D1",
                "drawing_type": "trendline",
                "data": {},
                "style": {},
                "is_visible": True,
                "is_locked": False,
                "pin_to_all": False,
            },
        )
        drawing_id = create.json()["id"]
        res = client.delete(f"/api/v1/drawings/{drawing_id}", headers=auth_headers)
        assert res.status_code == 204

    def test_drawing_user_isolation(self, client, db, instrument, auth_headers):
        """User A cannot delete or update User B's drawings."""
        from app.models.user import User
        from app.services.auth import create_access_token, hash_password

        user_b = User(
            username="drawing_user_b",
            email="drawing_user_b@test.com",
            hashed_password=hash_password("x"),
            is_active=True,
        )
        db.add(user_b)
        db.flush()
        headers_b = {"Authorization": f"Bearer {create_access_token(user_b.id, 'drawing_user_b')}"}

        # User B creates a drawing
        create = client.post(
            "/api/v1/drawings",
            headers=headers_b,
            json={
                "instrument_id": instrument.id,
                "timeframe": "D1",
                "drawing_type": "trendline",
                "data": {},
                "style": {},
                "is_visible": True,
                "is_locked": False,
                "pin_to_all": False,
            },
        )
        assert create.status_code == 201
        drawing_id = create.json()["id"]

        # User A (auth_headers) should get 404 when deleting User B's drawing
        res = client.delete(f"/api/v1/drawings/{drawing_id}", headers=auth_headers)
        assert res.status_code == 404

        # User A should also get 404 when updating User B's drawing
        res2 = client.patch(
            f"/api/v1/drawings/{drawing_id}",
            headers=auth_headers,
            json={"is_locked": True},
        )
        assert res2.status_code == 404

    def test_create_freehand_drawing(self, client, auth_headers, instrument):
        """Freehand drawings store multiple points in the data field."""
        res = client.post(
            "/api/v1/drawings",
            headers=auth_headers,
            json={
                "instrument_id": instrument.id,
                "timeframe": "D1",
                "drawing_type": "freehand",
                "data": {
                    "points": [
                        {"time": 1700000000, "price": 180.0},
                        {"time": 1700003600, "price": 181.5},
                        {"time": 1700007200, "price": 179.0},
                        {"time": 1700010800, "price": 182.0},
                    ]
                },
                "style": {"color": "#80cbc4", "lineWidth": 2},
                "is_visible": True,
                "is_locked": False,
                "pin_to_all": False,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["drawing_type"] == "freehand"
        assert len(data["data"]["points"]) == 4

    def test_freehand_drawing_indicator_pane(self, client, auth_headers, instrument):
        """Freehand drawings can be attached to a specific indicator sub-pane."""
        res = client.post(
            "/api/v1/drawings",
            headers=auth_headers,
            json={
                "instrument_id": instrument.id,
                "timeframe": "D1",
                "drawing_type": "freehand",
                "indicator_key": "rsi_14",
                "data": {
                    "points": [
                        {"time": 1700000000, "price": 35.0},
                        {"time": 1700003600, "price": 40.0},
                    ]
                },
                "style": {"color": "#ef9a9a", "lineWidth": 1.5},
                "is_visible": True,
                "is_locked": False,
                "pin_to_all": False,
            },
        )
        assert res.status_code == 201
        assert res.json()["indicator_key"] == "rsi_14"


class TestIndicatorPresets:
    def test_create_preset(self, client, auth_headers):
        res = client.post(
            "/api/v1/presets",
            headers=auth_headers,
            json={
                "name": "Day Trading Setup",
                "indicators": [
                    {"type": "ema", "params": {"period": 9}, "style": {"color": "#26a69a"}},
                    {"type": "ema", "params": {"period": 21}, "style": {"color": "#ef5350"}},
                    {"type": "rsi", "params": {"period": 14}, "style": {"color": "#ba68c8"}},
                ],
                "is_default": False,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Day Trading Setup"
        assert len(data["indicators"]) == 3

    def test_list_presets(self, client, auth_headers):
        client.post(
            "/api/v1/presets",
            headers=auth_headers,
            json={
                "name": "Test Preset",
                "indicators": [],
                "is_default": False,
            },
        )
        res = client.get("/api/v1/presets", headers=auth_headers)
        assert res.status_code == 200
        assert len(res.json()) >= 1

    def test_only_one_default_preset(self, client, auth_headers):
        """Setting is_default=True should unset any previous default."""
        client.post(
            "/api/v1/presets",
            headers=auth_headers,
            json={
                "name": "First",
                "indicators": [],
                "is_default": True,
            },
        )
        client.post(
            "/api/v1/presets",
            headers=auth_headers,
            json={
                "name": "Second",
                "indicators": [],
                "is_default": True,
            },
        )
        res = client.get("/api/v1/presets", headers=auth_headers)
        defaults = [p for p in res.json() if p["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["name"] == "Second"

    def test_delete_preset(self, client, auth_headers):
        create = client.post(
            "/api/v1/presets",
            headers=auth_headers,
            json={
                "name": "To Delete",
                "indicators": [],
                "is_default": False,
            },
        )
        preset_id = create.json()["id"]
        res = client.delete(f"/api/v1/presets/{preset_id}", headers=auth_headers)
        assert res.status_code == 204

    def test_presets_user_isolation(self, client, db):
        from app.models.user import User
        from app.services.auth import create_access_token, hash_password

        u1 = User(
            username="preset_u1",
            email="pu1@test.com",
            hashed_password=hash_password("x"),
            is_active=True,
        )
        u2 = User(
            username="preset_u2",
            email="pu2@test.com",
            hashed_password=hash_password("x"),
            is_active=True,
        )
        db.add_all([u1, u2])
        db.flush()
        h1 = {"Authorization": f"Bearer {create_access_token(u1.id, 'preset_u1')}"}
        h2 = {"Authorization": f"Bearer {create_access_token(u2.id, 'preset_u2')}"}

        client.post(
            "/api/v1/presets",
            headers=h1,
            json={
                "name": "User1 Preset",
                "indicators": [],
                "is_default": False,
            },
        )
        res = client.get("/api/v1/presets", headers=h2)
        names = [p["name"] for p in res.json()]
        assert "User1 Preset" not in names
