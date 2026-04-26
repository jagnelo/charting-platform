class TestProvidersRouter:
    def test_requires_auth(self, client):
        assert client.get("/api/v1/providers").status_code == 401

    def test_list_and_patch_policy(self, client, auth_headers):
        res = client.get("/api/v1/providers/policies", headers=auth_headers)
        assert res.status_code == 200
        rows = res.json()
        assert rows

        target = rows[0]
        provider = target["provider"]
        capability = target["capability"]

        invalid = client.patch(
            f"/api/v1/providers/policies/{provider}/nope",
            headers=auth_headers,
            json={"is_enabled": False},
        )
        assert invalid.status_code == 400

        update = client.patch(
            f"/api/v1/providers/policies/{provider}/{capability}",
            headers=auth_headers,
            json={"auto_weight_enabled": False},
        )
        assert update.status_code == 200

        refreshed = client.get("/api/v1/providers/policies", headers=auth_headers).json()
        changed = next(r for r in refreshed if r["provider"] == provider and r["capability"] == capability)
        assert changed["auto_weight_enabled"] is False
