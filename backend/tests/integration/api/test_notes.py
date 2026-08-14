"""Integration coverage for per-user instrument notes."""


def _headers_for(user):
    from app.services.auth import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user.id, user.username)}"}


class TestInstrumentNotes:
    def test_notes_require_authentication(self, client, instrument):
        response = client.get(f"/api/v1/notes/instruments/{instrument.id}")
        assert response.status_code == 401

    def test_notes_round_trip_is_scoped_to_canonical_instrument(
        self, client, auth_headers, instrument
    ):
        created = client.put(
            f"/api/v1/notes/instruments/{instrument.id}",
            headers=auth_headers,
            json={"content": "SPY relative-strength review"},
        )
        assert created.status_code == 200
        assert created.json()["instrument_id"] == instrument.id
        assert created.json()["content"] == "SPY relative-strength review"

        updated = client.put(
            f"/api/v1/notes/instruments/{instrument.id}",
            headers=auth_headers,
            json={"content": "SPY relative-strength review updated"},
        )
        assert updated.status_code == 200
        assert updated.json()["content"] == "SPY relative-strength review updated"
        assert updated.json()["updated_at"]

        loaded = client.get(f"/api/v1/notes/instruments/{instrument.id}", headers=auth_headers)
        assert loaded.status_code == 200
        assert loaded.json()["content"] == "SPY relative-strength review updated"

    def test_notes_are_isolated_between_users(self, client, db, instrument, auth_headers):
        from app.models.user import User
        from app.services.auth import hash_password

        user_b = User(
            username="notes-user-b",
            email="notes-b@test.com",
            hashed_password=hash_password("Password123!"),
            is_active=True,
        )
        db.add(user_b)
        db.flush()
        headers_b = _headers_for(user_b)

        saved = client.put(
            f"/api/v1/notes/instruments/{instrument.id}",
            headers=auth_headers,
            json={"content": "User A private note"},
        )
        assert saved.status_code == 200

        own = client.get(f"/api/v1/notes/instruments/{instrument.id}", headers=headers_b)
        assert own.status_code == 200
        assert own.json() is None

        saved_b = client.put(
            f"/api/v1/notes/instruments/{instrument.id}",
            headers=headers_b,
            json={"content": "User B private note"},
        )
        assert saved_b.status_code == 200

        user_a_view = client.get(f"/api/v1/notes/instruments/{instrument.id}", headers=auth_headers)
        assert user_a_view.status_code == 200
        assert user_a_view.json()["content"] == "User A private note"
        user_b_view = client.get(f"/api/v1/notes/instruments/{instrument.id}", headers=headers_b)
        assert user_b_view.status_code == 200
        assert user_b_view.json()["content"] == "User B private note"

    def test_notes_reject_unknown_instrument(self, client, auth_headers):
        response = client.put(
            "/api/v1/notes/instruments/999999",
            headers=auth_headers,
            json={"content": "orphan"},
        )
        assert response.status_code == 404
