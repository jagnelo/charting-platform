class TestProvidersAuth:
    def test_endpoints_require_auth(self, client):
        assert client.get("/api/v1/providers").status_code == 401
        assert client.get("/api/v1/providers/policies").status_code == 401
        assert client.get("/api/v1/providers/health").status_code == 401


class TestProvidersApi:
    def test_list_providers_returns_seeded_rows(self, client, auth_headers):
        res = client.get("/api/v1/providers", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert data
        assert "provider" in data[0]
        assert "supported_capabilities" in data[0]
        assert "capabilities" in data[0]

    def test_policies_and_health_return_rows(self, client, auth_headers):
        policies = client.get("/api/v1/providers/policies", headers=auth_headers)
        health = client.get("/api/v1/providers/health", headers=auth_headers)
        assert policies.status_code == 200
        assert health.status_code == 200
        assert isinstance(policies.json(), list)
        assert isinstance(health.json(), list)
        assert policies.json()
        assert health.json()

    def test_patch_invalid_capability_rejected(self, client, auth_headers):
        res = client.patch(
            "/api/v1/providers/policies/yfinance/not-a-capability",
            headers=auth_headers,
            json={"is_enabled": False},
        )
        assert res.status_code == 400

    def test_patch_unknown_provider_rejected(self, client, auth_headers):
        res = client.patch(
            "/api/v1/providers/policies/nope/price_history",
            headers=auth_headers,
            json={"is_enabled": False},
        )
        assert res.status_code == 404

    def test_patch_existing_policy_updates_value(self, client, auth_headers):
        policies = client.get("/api/v1/providers/policies", headers=auth_headers).json()
        target = policies[0]
        provider = target["provider"]
        capability = target["capability"]
        new_priority = (target.get("base_priority") or 0) + 3

        patch = client.patch(
            f"/api/v1/providers/policies/{provider}/{capability}",
            headers=auth_headers,
            json={"base_priority": new_priority, "auto_weight_enabled": False},
        )
        assert patch.status_code == 200

        refreshed = client.get("/api/v1/providers/policies", headers=auth_headers).json()
        updated = next(
            row for row in refreshed if row["provider"] == provider and row["capability"] == capability
        )
        assert updated["base_priority"] == new_priority
        assert updated["auto_weight_enabled"] is False

