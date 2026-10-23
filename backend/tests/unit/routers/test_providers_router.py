import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import settings
from app.models.data_source import DataSource
from app.models.provider_observation import (
    DatasetStatus,
    InstrumentDatasetState,
    LatestPriceSnapshot,
)
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderHealthState,
)


class TestProvidersRouter:
    def test_requires_auth(self, client):
        assert client.get("/api/v1/providers").status_code == 401
        assert client.get("/api/v1/providers/observations/summary").status_code == 401
        assert client.get("/api/v1/providers/datasets/stale").status_code == 401
        assert client.get("/api/v1/providers/usage").status_code == 401
        assert client.get("/api/v1/providers/usage/account").status_code == 401
        assert client.post("/api/v1/providers/usage/account/refresh").status_code == 401
        assert client.get("/api/v1/providers/reconciliation/issues").status_code == 401

    def test_provider_governance_requires_admin(self, client, auth_headers):
        assert (
            client.get("/api/v1/providers/usage/account", headers=auth_headers).status_code == 403
        )
        assert (
            client.post("/api/v1/providers/usage/account/refresh", headers=auth_headers).status_code
            == 403
        )
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
        assert (
            client.post(
                "/api/v1/providers/etf-publishers",
                headers=auth_headers,
                json={},
            ).status_code
            == 403
        )

    def test_etf_publisher_provisioning_stores_attestation_but_never_activates(
        self, client, admin_headers, auth_headers, db, monkeypatch
    ):
        from app.config import settings
        from app.models.provider_runtime import (
            ProviderEntitlementRevision,
            ProviderPolicy,
            ProviderRequestLog,
        )

        now = datetime.now(UTC)
        account_scope = "spdr-test-account"
        monkeypatch.setattr(
            settings,
            "PROVIDER_QUOTA_ACCOUNT_SCOPES",
            {"spdr:issuer_account": account_scope},
        )
        payload = {
            "provider_name": "spdr",
            "description": "Synthetic unit-test publisher record; not live evidence.",
            "https_hosts": ["www.ssga.com"],
            "operations": {
                "fetch_etf_holdings_latest": {
                    "evidence_source": "synthetic-unit-test-only",
                    "evidence_version": "fixture-v1",
                    "reviewed_at": now.isoformat(),
                }
            },
            "publisher_evidence_source": "synthetic-unit-test-only",
            "publisher_evidence_version": "fixture-v1",
            "publisher_reviewed_at": now.isoformat(),
            "quota_scope": "issuer_account",
            "quota_source": "synthetic-unit-test-only",
            "quota_evidence_version": "fixture-v1",
            "quota_contract": {
                "reset": "rolling",
                "dimensions": [
                    {
                        "name": "request",
                        "limit": 5,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "test-account",
                        "source": "synthetic-unit-test-only",
                    }
                ],
            },
            "quota_verified_at": now.isoformat(),
            "max_concurrency": 1,
            "tokens_per_minute": 5,
            "burst_capacity": 1,
            "freshness_seconds": 3600,
            "account_scope": account_scope,
            "usage_tracking": {
                "mode": "call_count",
                "unit_label": "requests",
                "operation_costs": {"fetch_etf_holdings_latest": 1},
                "dimension_costs": {},
            },
            "entitlement": {
                "evidence_source": "synthetic-unit-test-only",
                "evidence_version": "fixture-v1",
                "reviewed_at": now.isoformat(),
                "configured_plan": "synthetic-test-plan",
                "is_free": True,
                "authentication_required": False,
                "usage_terms": "Synthetic fixture only; not a publisher terms claim.",
                "redistribution_allowed": False,
                "quota_policy": {},
                "history_depth": "test-only",
                "venue_coverage": "test-only",
                "freshness_semantics": "test-only",
                "enabled_environments": ["test"],
                "effective_at": now.isoformat(),
                "review_due_at": (now + timedelta(days=1)).isoformat(),
            },
        }

        missing_costs = deepcopy(payload)
        missing_costs["usage_tracking"]["operation_costs"] = {}
        denied = client.post(
            "/api/v1/providers/etf-publishers",
            headers=admin_headers,
            json=missing_costs,
        )
        assert denied.status_code == 422
        assert db.scalar(select(DataSource).where(DataSource.name == "spdr")) is None

        generic_provider = deepcopy(payload)
        generic_provider["provider_name"] = "alpaca"
        denied_generic = client.post(
            "/api/v1/providers/etf-publishers",
            headers=admin_headers,
            json=generic_provider,
        )
        assert denied_generic.status_code == 409
        assert db.scalar(select(DataSource).where(DataSource.name == "alpaca")) is None

        unknown_operation = deepcopy(payload)
        unknown_operation["operations"] = {
            "discover_everything": {
                "evidence_source": "synthetic-unit-test-only",
                "evidence_version": "fixture-v1",
                "reviewed_at": now.isoformat(),
            }
        }
        denied_operation = client.post(
            "/api/v1/providers/etf-publishers",
            headers=admin_headers,
            json=unknown_operation,
        )
        assert denied_operation.status_code == 422
        assert db.scalar(select(DataSource).where(DataSource.name == "spdr")) is None

        wildcard_host = deepcopy(payload)
        wildcard_host["https_hosts"] = ["*.ssga.com"]
        denied_host = client.post(
            "/api/v1/providers/etf-publishers",
            headers=admin_headers,
            json=wildcard_host,
        )
        assert denied_host.status_code == 422
        assert db.scalar(select(DataSource).where(DataSource.name == "spdr")) is None

        response = client.post(
            "/api/v1/providers/etf-publishers", headers=admin_headers, json=payload
        )
        assert response.status_code == 201, response.text
        assert response.json()["routable"] is False
        assert response.json()["policy_enabled"] is False
        assert response.json()["live_probe_status"] == "not_run"

        source = db.scalar(select(DataSource).where(DataSource.name == "spdr"))
        assert source is not None
        assert source.is_active is True
        assert source.supported_capabilities == [ProviderCapability.ETF_HOLDINGS.value]
        assert source.config["etf_holdings_review"]["https_hosts"] == ["www.ssga.com"]
        assert (
            source.config["etf_holdings_review"]["entitlement_review"]["evidence_source"]
            == "synthetic-unit-test-only"
        )
        assert source.config["usage_tracking"]["operation_costs"] == {
            "fetch_etf_holdings_latest": 1
        }
        policy = db.scalar(
            select(ProviderPolicy).where(
                ProviderPolicy.data_source_id == source.id,
                ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        entitlement = db.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == source.id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        health = db.scalar(
            select(ProviderHealthState).where(
                ProviderHealthState.data_source_id == source.id,
                ProviderHealthState.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        revision = db.scalar(
            select(ProviderEntitlementRevision).where(
                ProviderEntitlementRevision.data_source_id == source.id,
                ProviderEntitlementRevision.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert policy is not None and policy.is_enabled is False
        assert entitlement is not None and entitlement.live_probe_status == "not_run"
        assert health is not None
        assert health.last_success_at is None and health.last_failure_at is None
        assert health.observed_score == 0
        assert revision is not None and revision.revision == entitlement.revision == 1
        assert db.query(ProviderRequestLog).count() == 0

        duplicate = client.post(
            "/api/v1/providers/etf-publishers", headers=admin_headers, json=payload
        )
        assert duplicate.status_code == 409
        assert db.scalar(select(DataSource).where(DataSource.name == "spdr")).id == source.id

        # The normal shared seeder must preserve this ETF-owned disabled row;
        # it must not infer activation from the new entitlement/health rows.
        providers = client.get("/api/v1/providers", headers=auth_headers)
        assert providers.status_code == 200
        db.refresh(policy)
        assert policy.is_enabled is False
        assert db.query(ProviderRequestLog).count() == 0

    def test_etf_publisher_provisioning_rejects_missing_scope_before_writes(
        self, client, admin_headers, db, monkeypatch
    ):
        from app.config import settings

        monkeypatch.setattr(settings, "PROVIDER_QUOTA_ACCOUNT_SCOPES", {})
        response = client.post(
            "/api/v1/providers/etf-publishers",
            headers=admin_headers,
            json={"provider_name": "spdr"},
        )
        assert response.status_code == 422
        assert db.scalar(select(DataSource).where(DataSource.name == "spdr")) is None

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

    def test_list_and_patch_policy(self, client, admin_headers, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_otc_query_api")
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
        )
        monkeypatch.setattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", 86400)
        res = client.get("/api/v1/providers/policies", headers=admin_headers)
        assert res.status_code == 200
        rows = res.json()
        assert rows

        unreviewed = next(
            row
            for row in rows
            if row["provider"] == "finnhub" and row["capability"] == "price_history"
        )
        assert unreviewed["entitlement_state"] == "unreviewed"
        assert unreviewed["routing_eligible"] is False
        assert unreviewed["live_probe_status"] == "passed"
        assert unreviewed["required_environment_variables"]
        assert all(
            value.isupper() and " " not in value
            for value in unreviewed["required_environment_variables"]
        )
        assert all(
            value.isupper() and " " not in value
            for value in unreviewed["missing_environment_variables"]
        )
        assert "required_routing_control_variables" in unreviewed
        assert "missing_routing_control_variables" in unreviewed
        assert all(
            value.isupper() and " " not in value
            for value in unreviewed["missing_routing_control_variables"]
        )

        otc = next(
            row
            for row in rows
            if row["provider"] == "finra_otc_directory"
            and row["capability"] == "universe_discovery"
        )
        assert otc["routing_eligible"] is False
        assert "FINRA_OTC_SYMBOL_DIRECTORY_URL" in otc["required_routing_control_variables"]
        assert "FINRA_OTC_POLL_INTERVAL_SECONDS" in otc["required_routing_control_variables"]
        assert "FINRA_OTC_OPERATION_COSTS" not in otc["missing_routing_control_variables"]

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

        quota_target = next(
            row
            for row in refreshed
            if row["provider"] == "finnhub" and row["capability"] == "price_history"
        )
        quota_url = "/api/v1/providers/policies/finnhub/price_history"
        missing_contract = client.patch(
            quota_url,
            headers=admin_headers,
            json={"tokens_per_minute": 60},
        )
        assert missing_contract.status_code == 400
        assert "explicit replacement" in missing_contract.json()["detail"]

        reviewed_replacement = deepcopy(quota_target["quota_contract"])
        # The seeded Finnhub policy intentionally keeps its minute/second
        # reset boundary provider-defined. A complete admin replacement must
        # supply an explicit boundary for every dimension before admission.
        for dimension in reviewed_replacement["dimensions"]:
            dimension["reset"] = "rolling"
        complete_contract = client.patch(
            quota_url,
            headers=admin_headers,
            json={
                "tokens_per_minute": 60,
                "quota_contract": reviewed_replacement,
                "quota_source": quota_target["quota_source"],
            },
        )
        assert complete_contract.status_code == 200

        clear_scope = client.patch(
            quota_url,
            headers=admin_headers,
            json={"quota_scope": None},
        )
        assert clear_scope.status_code == 200
        cleared_row = next(
            row
            for row in client.get("/api/v1/providers/policies", headers=admin_headers).json()
            if row["provider"] == "finnhub" and row["capability"] == "price_history"
        )
        assert cleared_row["quota_verified_at"] is None
        assert cleared_row["routing_eligible"] is False

        clear_contract = client.patch(
            quota_url,
            headers=admin_headers,
            json={"quota_contract": None},
        )
        assert clear_contract.status_code == 200
        cleared_contract_row = next(
            row
            for row in client.get("/api/v1/providers/policies", headers=admin_headers).json()
            if row["provider"] == "finnhub" and row["capability"] == "price_history"
        )
        assert cleared_contract_row["quota_contract"] is None
        assert cleared_contract_row["quota_verified_at"] is None
        assert cleared_contract_row["routing_eligible"] is False

        restore_contract = client.patch(
            quota_url,
            headers=admin_headers,
            json={
                "quota_contract": reviewed_replacement,
                "quota_scope": quota_target["quota_scope"],
                "quota_source": quota_target["quota_source"],
            },
        )
        assert restore_contract.status_code == 200

        invalid_contract = client.patch(
            quota_url,
            headers=admin_headers,
            json={
                "tokens_per_minute": 60,
                "quota_contract": {"dimensions": []},
                "quota_source": "test",
            },
        )
        assert invalid_contract.status_code == 400
        assert "quota_contract is incomplete" in invalid_contract.json()["detail"]

        missing_scope_contract = client.patch(
            quota_url,
            headers=admin_headers,
            json={
                "quota_contract": quota_target["quota_contract"],
                "quota_scope": None,
                "quota_source": quota_target["quota_source"],
            },
        )
        assert missing_scope_contract.status_code == 400
        assert "quota_scope" in missing_scope_contract.json()["detail"]

        unverified_contract = client.patch(
            quota_url,
            headers=admin_headers,
            json={
                "quota_contract": {
                    "reset": "provider_defined",
                    "unknown_dimensions": ["provider_terms"],
                    "dimensions": [
                        {
                            "name": "requests_per_minute",
                            "limit": 60,
                            "window_seconds": 60,
                            "unit": "requests",
                            "scope": "account",
                            "source": "https://provider.example/limits",
                        }
                    ],
                },
                "quota_source": "provider documentation pending terms review",
            },
        )
        assert unverified_contract.status_code == 200
        unverified_row = next(
            row
            for row in client.get("/api/v1/providers/policies", headers=admin_headers).json()
            if row["provider"] == "finnhub" and row["capability"] == "price_history"
        )
        assert unverified_row["quota_verified_at"] is None
        assert unverified_row["routing_eligible"] is False

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
        assert prune.json()["deleted"]["latest_price_snapshot"] == 0
        assert db.get(LatestPriceSnapshot, old_snapshot.id) is not None

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

    def test_provider_usage_summary(self, client, auth_headers, db, monkeypatch, tmp_path):
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
        ledger = tmp_path / "provider-live-usage.jsonl"
        ledger.write_text(
            json.dumps(
                {
                    "at": now.isoformat(),
                    "provider": "yfinance",
                    "operations": 1,
                    "http_requests": 2,
                    "response_bytes": 128,
                    "exit_status": 0,
                }
            )
            + "\n"
        )
        monkeypatch.setattr(settings, "PROVIDER_LIVE_USAGE_LEDGER", str(ledger))

        usage = client.get("/api/v1/providers/usage", headers=auth_headers)
        assert usage.status_code == 200
        row = next(item for item in usage.json() if item["provider"] == "yfinance")
        assert row["requests_24h"] >= 1
        assert row["usage_unit_label"] == "requests"
        assert "live_usage_ledger" in row
        assert "live_test_usage" in row
        assert row["live_usage_ledger"]["status"] == "available"
        assert row["live_test_usage"]["http_requests"] == 2
        assert row["live_test_usage"]["response_bytes"] == 128
