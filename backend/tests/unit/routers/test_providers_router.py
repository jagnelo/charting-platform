from datetime import UTC, datetime, timedelta

from app.models.data_source import DataSource
from app.models.provider_observation import (
    DatasetStatus,
    InstrumentDatasetState,
    LatestPriceSnapshot,
)
from app.models.provider_runtime import ProviderCapability, ProviderHealthState


class TestProvidersRouter:
    def test_requires_auth(self, client):
        assert client.get("/api/v1/providers").status_code == 401
        assert client.get("/api/v1/providers/observations/summary").status_code == 401
        assert client.get("/api/v1/providers/datasets/stale").status_code == 401
        assert client.get("/api/v1/providers/usage").status_code == 401
        assert client.get("/api/v1/providers/reconciliation/issues").status_code == 401

    def test_provider_governance_requires_admin(self, client, auth_headers):
        assert (
            client.get(
                "/api/v1/providers/reconciliation/issues",
                headers=auth_headers,
            ).status_code
            == 403
        )
        assert (
            client.patch(
                "/api/v1/providers/reconciliation/issues/1",
                headers=auth_headers,
                json={"status": "ignored"},
            ).status_code
            == 403
        )
        assert (
            client.patch(
                "/api/v1/providers/policies/alpaca/price_history",
                headers=auth_headers,
                json={"is_enabled": False},
            ).status_code
            == 403
        )
        assert (
            client.patch(
                "/api/v1/providers/entitlements/alpaca/price_history",
                headers=auth_headers,
                json={"is_free": False},
            ).status_code
            == 403
        )

    def test_reconciliation_issue_is_listed_and_resolvable(self, client, admin_headers, db):
        from app.models.instrument_reconciliation import InstrumentReconciliationIssue

        source = DataSource(name="edgar", is_active=True)
        db.add(source)
        db.flush()
        issue = InstrumentReconciliationIssue(
            data_source_id=source.id,
            provider_symbol="ABC",
            issue_type="ambiguous_ticker_issuer",
            fingerprint="fingerprint-abc",
            status="open",
            candidates=[{"cik": "1", "name": "One"}, {"cik": "2", "name": "Two"}],
            payload={"symbol": "ABC", "quote_type": "EQUITY"},
            observed_at=datetime.now(UTC),
        )
        db.add(issue)
        db.flush()

        listed = client.get("/api/v1/providers/reconciliation/issues", headers=admin_headers)
        assert listed.status_code == 200
        assert listed.json()[0]["provider_symbol"] == "ABC"
        assert listed.json()[0]["provider"] == "edgar"

        updated = client.patch(
            f"/api/v1/providers/reconciliation/issues/{issue.id}",
            headers=admin_headers,
            json={"status": "resolved", "resolution": {"canonical_cik": "1"}},
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "resolved"
        assert updated.json()["resolved_by"]["username"]

        resolved = client.get(
            "/api/v1/providers/reconciliation/issues?status=resolved", headers=admin_headers
        )
        assert resolved.status_code == 200
        resolved_issue = next(row for row in resolved.json() if row["provider_symbol"] == "ABC")
        assert resolved_issue["resolution"]["canonical_cik"] == "1"

    def test_list_and_patch_policy(self, client, admin_headers):
        res = client.get("/api/v1/providers/policies", headers=admin_headers)
        assert res.status_code == 200
        rows = res.json()
        assert rows

        unreviewed = next(row for row in rows if row["provider"] == "finnhub")
        assert unreviewed["entitlement_state"] == "unreviewed"
        assert unreviewed["routing_eligible"] is False
        assert "quota_contract" in unreviewed["quota_missing_dimensions"]

        target = rows[0]
        provider = target["provider"]
        capability = target["capability"]

        invalid = client.patch(
            f"/api/v1/providers/policies/{provider}/nope",
            headers=admin_headers,
            json={"is_enabled": False},
        )
        assert invalid.status_code == 400

        update = client.patch(
            f"/api/v1/providers/policies/{provider}/{capability}",
            headers=admin_headers,
            json={"auto_weight_enabled": False},
        )
        assert update.status_code == 200

        refreshed = client.get("/api/v1/providers/policies", headers=admin_headers).json()
        changed = next(
            r for r in refreshed if r["provider"] == provider and r["capability"] == capability
        )
        assert changed["auto_weight_enabled"] is False

    def test_entitlements_are_seeded_and_patchable(self, client, admin_headers):
        rows = client.get("/api/v1/providers/entitlements", headers=admin_headers)
        assert rows.status_code == 200
        assert rows.json()
        target = rows.json()[0]
        updated = client.patch(
            f"/api/v1/providers/entitlements/{target['provider']}/{target['capability']}",
            headers=admin_headers,
            json={
                "configured_plan": "free-reviewed",
                "freshness_semantics": "delayed",
                "effective_at": "2026-01-01T00:00:00Z",
                "review_due_at": "2030-01-01T00:00:00Z",
            },
        )
        assert updated.status_code == 200
        refreshed = client.get("/api/v1/providers/entitlements", headers=admin_headers).json()
        changed = next(
            row
            for row in refreshed
            if row["provider"] == target["provider"] and row["capability"] == target["capability"]
        )
        assert changed["configured_plan"] == "free-reviewed"
        assert changed["freshness_semantics"] == "delayed"
        assert changed["effective_at"].startswith("2026-01-01T00:00:00")
        assert changed["review_due_at"].startswith("2030-01-01T00:00:00")
        assert changed["revision"] == target["revision"] + 1

        history = client.get(
            f"/api/v1/providers/entitlements/history/{target['provider']}/{target['capability']}",
            headers=admin_headers,
        )
        assert history.status_code == 200
        revisions = history.json()
        assert [row["revision"] for row in revisions] == sorted(
            (row["revision"] for row in revisions), reverse=True
        )
        assert revisions[0]["revision"] == changed["revision"]
        assert revisions[0]["change_reason"] == "api_patch"
        assert revisions[-1]["revision"] == target["revision"]

    def test_observation_summary_and_prune(self, client, auth_headers, db, instrument):
        data_source = DataSource(name="yfinance", is_active=True)
        db.add(data_source)
        db.flush()
        old_snapshot = LatestPriceSnapshot(
            instrument_id=instrument.id,
            data_source_id=data_source.id,
            provider_symbol="AAPL",
            observed_at=datetime.now(UTC) - timedelta(days=40),
            fetched_at=datetime.now(UTC) - timedelta(days=40),
            price=123.45,
            payload={"price": 123.45},
        )
        db.add(old_snapshot)
        db.commit()

        summary = client.get("/api/v1/providers/observations/summary", headers=auth_headers)
        assert summary.status_code == 200
        latest_prices = next(
            row for row in summary.json() if row["dataset"] == "latest_price_snapshot"
        )
        assert latest_prices["rows"] >= 1

        prune = client.post("/api/v1/providers/maintenance/prune", headers=auth_headers)
        assert prune.status_code == 200
        assert prune.json()["deleted"]["latest_price_snapshot"] >= 1

    def test_stale_datasets_and_health_reset(self, client, auth_headers, db, instrument):
        data_source = DataSource(name="yfinance", is_active=True)
        db.add(data_source)
        db.flush()
        state = InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=data_source.id,
            dataset_type="option_chain",
            dataset_key="2026-06-19",
            status=DatasetStatus.FRESH,
            stale_after=datetime.now(UTC) - timedelta(hours=1),
            observed_at=datetime.now(UTC) - timedelta(hours=2),
            fetched_at=datetime.now(UTC) - timedelta(hours=2),
        )
        health = ProviderHealthState(
            data_source_id=data_source.id,
            capability=ProviderCapability.PRICE_HISTORY,
            failure_streak=4,
            last_error_type="TimeoutError",
            last_error_message="timed out",
            circuit_open_until=datetime.now(UTC) + timedelta(minutes=5),
        )
        db.add(state)
        db.add(health)
        db.commit()

        stale = client.get("/api/v1/providers/datasets/stale", headers=auth_headers)
        assert stale.status_code == 200
        assert any(row["symbol"] == "AAPL" for row in stale.json())

        reset = client.post(
            "/api/v1/providers/health/yfinance/price_history/reset",
            headers=auth_headers,
        )
        assert reset.status_code == 200
        db.refresh(health)
        assert health.failure_streak == 0
        assert health.circuit_open_until is None
        assert health.last_error_type is None

    def test_provider_usage_summary(self, client, auth_headers, db):
        data_source = DataSource(
            name="yfinance",
            is_active=True,
            config={
                "usage_tracking": {
                    "mode": "call_count",
                    "unit_label": "requests",
                    "limit_kind": "unknown",
                }
            },
        )
        db.add(data_source)
        db.flush()
        now = datetime.now(UTC)
        from app.models.provider_runtime import ProviderRequestLog

        db.add(
            ProviderRequestLog(
                data_source_id=data_source.id,
                capability=ProviderCapability.INSTRUMENT_SEARCH,
                operation="search_instruments",
                operation_family="search_instruments",
                requested_at=now - timedelta(minutes=10),
                completed_at=now - timedelta(minutes=10),
                success=True,
                usage_mode="call_count",
                usage_unit_label="requests",
                usage_units=1,
                latency_ms=100,
            )
        )
        db.commit()

        usage = client.get("/api/v1/providers/usage", headers=auth_headers)
        assert usage.status_code == 200
        row = next(item for item in usage.json() if item["provider"] == "yfinance")
        assert row["requests_24h"] >= 1
        assert row["usage_unit_label"] == "requests"
