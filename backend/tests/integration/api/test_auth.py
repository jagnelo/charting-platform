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
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_register_returns_no_sensitive_fields(self, client):
        res = client.post(
            "/api/v1/auth/register",
            json={
                "username": "safeuser",
                "email": "safeuser@example.com",
                "password": "Password123!",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert "hashed_password" not in data
        assert "password" not in data

    def test_register_token_grants_access(self, client):
        """The returned access token should authenticate subsequent requests."""
        res = client.post(
            "/api/v1/auth/register",
            json={
                "username": "tokenuser",
                "email": "tokenuser@example.com",
                "password": "Password123!",
            },
        )
        assert res.status_code == 201
        token = res.json()["access_token"]
        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["username"] == "tokenuser"

    def test_register_duplicate_username_fails(self, client, user):
        res = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",  # same as fixture
                "email": "other@example.com",
                "password": "Password123!",
            },
        )
        assert res.status_code == 409

    def test_register_duplicate_email_fails(self, client, user):
        res = client.post(
            "/api/v1/auth/register",
            json={
                "username": "otherusername",
                "email": "test@example.com",  # same as fixture
                "password": "Password123!",
            },
        )
        assert res.status_code == 409


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
        assert res.status_code == 401

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


class TestUserSettings:
    def test_get_settings_empty(self, client, auth_headers):
        res = client.get("/api/v1/auth/settings", headers=auth_headers)
        assert res.status_code == 200
        assert isinstance(res.json(), dict)

    def test_patch_settings_merges(self, client, auth_headers):
        client.patch(
            "/api/v1/auth/settings",
            headers=auth_headers,
            json={"settings": {"theme": "dark", "locale": "en"}},
        )
        res = client.patch(
            "/api/v1/auth/settings",
            headers=auth_headers,
            json={"settings": {"theme": "light"}},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["theme"] == "light"
        assert data["locale"] == "en"  # preserved from first patch
