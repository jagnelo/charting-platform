"""
Integration tests for /screeners endpoints + the screener engine
running against a real Postgres DB.
"""


class TestScreenerCRUD:
    def test_create_screener(self, client, auth_headers):
        res = client.post(
            "/api/v1/screeners/",
            headers=auth_headers,
            json={
                "name": "Oversold RSI",
                "logic": "and",
                "conditions": [
                    {
                        "position": 0,
                        "subject": "indicator",
                        "timeframe": "D1",
                        "operator": "lt",
                        "indicator_type": "rsi",
                        "indicator_params": {"period": 14},
                        "threshold_value": "30",
                    }
                ],
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Oversold RSI"
        assert data["logic"] == "and"
        assert len(data["conditions"]) == 1
        assert data["conditions"][0]["indicator_type"] == "rsi"

    def test_list_screeners(self, client, auth_headers, screener):
        res = client.get("/api/v1/screeners/", headers=auth_headers)
        assert res.status_code == 200
        ids = [s["id"] for s in res.json()]
        assert screener.id in ids

    def test_get_screener(self, client, auth_headers, screener):
        res = client.get(f"/api/v1/screeners/{screener.id}", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["id"] == screener.id

    def test_get_screener_not_found(self, client, auth_headers):
        res = client.get("/api/v1/screeners/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_screener_user_isolation(self, client, db, screener):
        from app.models.user import User
        from app.services.auth import create_access_token, hash_password

        other = User(
            username="screener_other",
            email="screener_other@test.com",
            hashed_password=hash_password("x"),
            is_active=True,
        )
        db.add(other)
        db.flush()
        headers = {"Authorization": f"Bearer {create_access_token(other.id, 'screener_other')}"}
        res = client.get(f"/api/v1/screeners/{screener.id}", headers=headers)
        assert res.status_code == 404

    def test_delete_screener(self, client, auth_headers, screener):
        res = client.delete(f"/api/v1/screeners/{screener.id}", headers=auth_headers)
        assert res.status_code == 204

    def test_screener_requires_auth(self, client):
        res = client.get("/api/v1/screeners/")
        assert res.status_code == 403


class TestScreenerRun:
    def test_run_screener_empty_conditions_returns_result(self, client, auth_headers, screener):
        res = client.post(f"/api/v1/screeners/{screener.id}/run", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "matched_instrument_ids" in data
        assert "total_scanned" in data
        assert "duration_ms" in data

    def test_run_screener_price_condition_matches(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        """Screener with price > 0 should match our AAPL instrument."""
        create_res = client.post(
            "/api/v1/screeners/",
            headers=auth_headers,
            json={
                "name": "Any Price",
                "logic": "and",
                "conditions": [
                    {
                        "position": 0,
                        "subject": "price",
                        "timeframe": "D1",
                        "operator": "gt",
                        "threshold_value": "0",
                    }
                ],
            },
        )
        screener_id = create_res.json()["id"]
        run_res = client.post(f"/api/v1/screeners/{screener_id}/run", headers=auth_headers)
        assert run_res.status_code == 200
        data = run_res.json()
        assert instrument.id in data["matched_instrument_ids"]

    def test_run_screener_impossible_condition_no_matches(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        """Price > 999999 should match nothing."""
        create_res = client.post(
            "/api/v1/screeners/",
            headers=auth_headers,
            json={
                "name": "Impossible",
                "logic": "and",
                "conditions": [
                    {
                        "position": 0,
                        "subject": "price",
                        "timeframe": "D1",
                        "operator": "gt",
                        "threshold_value": "999999",
                    }
                ],
            },
        )
        screener_id = create_res.json()["id"]
        run_res = client.post(f"/api/v1/screeners/{screener_id}/run", headers=auth_headers)
        assert run_res.status_code == 200
        assert run_res.json()["matched_instrument_ids"] == []

    def test_run_saves_result(self, client, auth_headers, screener):
        client.post(f"/api/v1/screeners/{screener.id}/run", headers=auth_headers)
        results_res = client.get(
            f"/api/v1/screeners/{screener.id}/results", headers=auth_headers, params={"limit": 5}
        )
        assert results_res.status_code == 200
        assert len(results_res.json()) >= 1

    def test_or_logic_screener(self, client, auth_headers, instrument, ohlcv_bars):
        """OR screener: either impossible OR definitely-true → should match."""
        create_res = client.post(
            "/api/v1/screeners/",
            headers=auth_headers,
            json={
                "name": "OR Test",
                "logic": "or",
                "conditions": [
                    {
                        "position": 0,
                        "subject": "price",
                        "timeframe": "D1",
                        "operator": "gt",
                        "threshold_value": "999999",  # impossible
                    },
                    {
                        "position": 1,
                        "subject": "price",
                        "timeframe": "D1",
                        "operator": "gt",
                        "threshold_value": "0",  # always true
                    },
                ],
            },
        )
        screener_id = create_res.json()["id"]
        run_res = client.post(f"/api/v1/screeners/{screener_id}/run", headers=auth_headers)
        assert instrument.id in run_res.json()["matched_instrument_ids"]

    def test_and_logic_requires_all_conditions(self, client, auth_headers, instrument, ohlcv_bars):
        """AND screener with one impossible condition → no matches."""
        create_res = client.post(
            "/api/v1/screeners/",
            headers=auth_headers,
            json={
                "name": "AND Test",
                "logic": "and",
                "conditions": [
                    {
                        "position": 0,
                        "subject": "price",
                        "timeframe": "D1",
                        "operator": "gt",
                        "threshold_value": "0",  # true
                    },
                    {
                        "position": 1,
                        "subject": "price",
                        "timeframe": "D1",
                        "operator": "gt",
                        "threshold_value": "999999",  # impossible
                    },
                ],
            },
        )
        screener_id = create_res.json()["id"]
        run_res = client.post(f"/api/v1/screeners/{screener_id}/run", headers=auth_headers)
        assert run_res.json()["matched_instrument_ids"] == []
