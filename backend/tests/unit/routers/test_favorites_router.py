class TestFavoritesRouter:
    def test_favorites_are_user_scoped_and_idempotent(self, client, auth_headers, db, instrument):
        from app.models.favorite_instrument import FavoriteInstrument
        from app.models.user import User
        from app.services.auth import hash_password

        initial = client.get("/api/v1/favorites", headers=auth_headers)
        assert initial.status_code == 200
        assert initial.json() == []

        added = client.put(f"/api/v1/favorites/instruments/{instrument.id}", headers=auth_headers)
        assert added.status_code == 200
        assert added.json()["symbol"] == instrument.symbol
        assert added.json()["instrument_id"] == instrument.id

        repeated = client.put(
            f"/api/v1/favorites/instruments/{instrument.id}", headers=auth_headers
        )
        assert repeated.status_code == 200
        assert repeated.json()["id"] == added.json()["id"]

        second_user = User(
            username="other-favorites-user",
            email="other-favorites@example.com",
            hashed_password=hash_password("Password123!"),
            is_active=True,
        )
        db.add(second_user)
        db.flush()
        other_favorite = FavoriteInstrument(
            user_id=second_user.id,
            instrument_id=instrument.id,
            position=0,
        )
        db.add(other_favorite)
        db.flush()
        visible_to_first_user = client.get("/api/v1/favorites", headers=auth_headers).json()
        assert [item["id"] for item in visible_to_first_user] == [added.json()["id"]]

        removed = client.delete(
            f"/api/v1/favorites/instruments/{instrument.id}", headers=auth_headers
        )
        assert removed.status_code == 204
        assert client.get("/api/v1/favorites", headers=auth_headers).json() == []
        assert (
            client.delete(
                f"/api/v1/favorites/instruments/{instrument.id}", headers=auth_headers
            ).status_code
            == 204
        )
        db.refresh(other_favorite)
        assert other_favorite.user_id == second_user.id

    def test_favorites_reject_unknown_instruments(self, client, auth_headers):
        response = client.put("/api/v1/favorites/instruments/2147483647", headers=auth_headers)
        assert response.status_code == 404
