"""
Integration tests for /auth endpoints.

These run against a real Postgres container via the `client` fixture.
"""


class TestRegister:
    def test_register_success(self, client):
        res = client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "Password123!",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert "hashed_password" not in data

    def test_register_creates_default_watchlist(self, client, db):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "wluser",
                "email": "wluser@example.com",
                "password": "Password123!",
            },
        )
        from sqlalchemy import select

        from app.models.user import User
        from app.models.watchlist import Watchlist

        user = db.execute(select(User).where(User.username == "wluser")).scalar_one_or_none()
        assert user is not None
        wl = db.execute(select(Watchlist).where(Watchlist.user_id == user.id)).scalar_one_or_none()
        assert wl is not None
        assert wl.is_default is True

    def test_register_duplicate_username_fails(self, client, user):
        res = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",  # same as fixture
                "email": "other@example.com",
                "password": "Password123!",
            },
        )
        assert res.status_code == 400

    def test_register_duplicate_email_fails(self, client, user):
        res = client.post(
            "/api/v1/auth/register",
            json={
                "username": "otherusername",
                "email": "test@example.com",  # same as fixture
                "password": "Password123!",
            },
        )
        assert res.status_code == 400


class TestLogin:
    def test_login_success_returns_tokens(self, client, user):
        res = client.post(
            "/api/v1/auth/login",
            json={
                "username": "testuser",
                "password": "Password123!",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client, user):
        res = client.post(
            "/api/v1/auth/login",
            json={
                "username": "testuser",
                "password": "wrongpassword",
            },
        )
        assert res.status_code == 401

    def test_login_unknown_user(self, client):
        res = client.post(
            "/api/v1/auth/login",
            json={
                "username": "nobody",
                "password": "Password123!",
            },
        )
        assert res.status_code == 401


class TestGetMe:
    def test_get_me_authenticated(self, client, user, auth_headers):
        res = client.get("/api/v1/auth/me", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["username"] == "testuser"
        assert data["id"] == user.id

    def test_get_me_unauthenticated(self, client):
        res = client.get("/api/v1/auth/me")
        assert res.status_code == 403  # HTTPBearer returns 403 when no header

    def test_get_me_invalid_token(self, client):
        res = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer badtoken"})
        assert res.status_code == 401


class TestRefreshToken:
    def test_refresh_returns_new_access_token(self, client, user):
        # Login to get tokens
        login = client.post(
            "/api/v1/auth/login", json={"username": "testuser", "password": "Password123!"}
        )
        refresh_token = login.json()["refresh_token"]

        res = client.post(f"/api/v1/auth/refresh?refresh_token={refresh_token}")
        assert res.status_code == 200
        assert "access_token" in res.json()

    def test_refresh_with_access_token_fails(self, client, user, auth_headers):
        access_token = auth_headers["Authorization"].split()[1]
        res = client.post(f"/api/v1/auth/refresh?refresh_token={access_token}")
        assert res.status_code == 401


class TestChangePassword:
    def test_change_password_success(self, client, user, auth_headers):
        res = client.post(
            "/api/v1/auth/change-password",
            params={"old_password": "Password123!", "new_password": "NewPass456!"},
            headers=auth_headers,
        )
        assert res.status_code == 204

        # Old password no longer works
        login = client.post(
            "/api/v1/auth/login", json={"username": "testuser", "password": "Password123!"}
        )
        assert login.status_code == 401

        # New password works
        login2 = client.post(
            "/api/v1/auth/login", json={"username": "testuser", "password": "NewPass456!"}
        )
        assert login2.status_code == 200

    def test_change_password_wrong_old(self, client, auth_headers):
        res = client.post(
            "/api/v1/auth/change-password",
            params={"old_password": "wrongold", "new_password": "NewPass456!"},
            headers=auth_headers,
        )
        assert res.status_code == 400
