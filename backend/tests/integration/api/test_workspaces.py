class TestWorkspaces:
    def test_default_workspace_is_top_down_and_revisioned(self, client, auth_headers):
        response = client.get("/api/v1/workspaces/default", headers=auth_headers)
        assert response.status_code == 200
        workspace = response.json()
        assert workspace["name"] == "US Top Down"
        assert workspace["revision"] == 1
        assert workspace["tabs"][0]["stable_key"] == "us-top-down"
        assert workspace["tabs"][0]["layout_config"]["root"]["type"] == "row"
        assert workspace["tabs"][0]["layout_config"]["version"] == 8
        assert workspace["settings"]["factory_version"] == 8
        assert {window["tool_type"] for window in workspace["tabs"][0]["windows"]} >= {
            "watchlist",
            "chart",
            "breadth",
            "coverage",
            "technical_summary",
            "relative_rotation",
            "alerts",
            "scan",
            "gauge",
        }
        assert "alerts" in {window["instance_key"] for window in workspace["tabs"][0]["windows"]}
        assert "easy-scan" in {window["instance_key"] for window in workspace["tabs"][0]["windows"]}
        assert "market-gauge" in {
            window["instance_key"] for window in workspace["tabs"][0]["windows"]
        }
        assert "relative-rotation" in {
            window["instance_key"] for window in workspace["tabs"][0]["windows"]
        }
        rotation = next(
            window
            for window in workspace["tabs"][0]["windows"]
            if window["instance_key"] == "relative-rotation"
        )
        assert rotation["configuration"] == {
            "group_key": "sp500-sectors",
            "benchmark": "SPY",
            "timeframe": "D1",
            "sampling": 1,
            "lookback": 20,
            "tail_length": 10,
            "adjusted": True,
        }
        assert {tab["stable_key"] for tab in workspace["tabs"]} >= {
            "tc-classic",
            "drill-down",
            "four-timeframe",
            "study-lab",
        }
        four_timeframe = next(
            tab for tab in workspace["tabs"] if tab["stable_key"] == "four-timeframe"
        )
        configurations = {
            window["instance_key"]: window["configuration"] for window in four_timeframe["windows"]
        }
        assert {key: value["timeframe"] for key, value in configurations.items()} == {
            "m15": "M15",
            "daily": "D1",
            "weekly": "W1",
            "monthly": "MN",
        }
        assert {value["timeframe_link_group"] for value in configurations.values()} == {
            "red",
            "green",
            "purple",
            "orange",
        }
        assert {window["link_group"] for window in four_timeframe["windows"]} == {"blue"}
        assert four_timeframe["layout_config"]["root"]["type"] == "row"
        assert [
            column["type"] for column in four_timeframe["layout_config"]["root"]["content"]
        ] == ["column", "column"]
        tc_classic = next(tab for tab in workspace["tabs"] if tab["stable_key"] == "tc-classic")
        assert {window["tool_type"] for window in tc_classic["windows"]} >= {
            "chart",
            "watchlist",
            "notes",
        }
        drill_down = next(tab for tab in workspace["tabs"] if tab["stable_key"] == "drill-down")
        drill_keys = {window["instance_key"] for window in drill_down["windows"]}
        assert {"selected-chart", "sector-comparison"} <= drill_keys
        assert drill_down["layout_config"]["version"] == 8
        drill_comparison = next(
            window
            for window in drill_down["windows"]
            if window["instance_key"] == "sector-comparison"
        )
        assert drill_comparison["configuration"]["comparison_symbols"] == ["RSP"]
        drill_root = drill_down["layout_config"]["root"]
        assert any(
            item.get("type") == "stack" and len(item.get("content", [])) == 2
            for item in drill_root["content"]
        )
        sector_by_year = next(
            tab for tab in workspace["tabs"] if tab["stable_key"] == "sector-by-year"
        )
        assert {"selected-chart", "normalized-comparison"} <= {
            window["instance_key"] for window in sector_by_year["windows"]
        }
        assert sector_by_year["layout_config"]["version"] == 8
        normalized = next(
            window
            for window in sector_by_year["windows"]
            if window["instance_key"] == "normalized-comparison"
        )
        assert normalized["configuration"]["comparison_symbols"] == ["RSP"]

    def test_factory_reset_recreates_latest_factory_layout(self, client, auth_headers):
        workspace = client.get("/api/v1/workspaces/default", headers=auth_headers).json()
        response = client.post(
            f"/api/v1/workspaces/{workspace['id']}/reset-factory",
            headers=auth_headers,
        )

        assert response.status_code == 200
        reset = response.json()
        assert reset["revision"] == workspace["revision"] + 1
        assert reset["settings"]["factory_version"] == 8
        top_down = next(tab for tab in reset["tabs"] if tab["stable_key"] == "us-top-down")
        assert [column["size"] for column in top_down["layout_config"]["root"]["content"]] == [
            22,
            23,
            55,
        ]
        four_timeframe = next(tab for tab in reset["tabs"] if tab["stable_key"] == "four-timeframe")
        assert {window["configuration"]["timeframe"] for window in four_timeframe["windows"]} == {
            "M15",
            "D1",
            "W1",
            "MN",
        }
        drill_down = next(tab for tab in reset["tabs"] if tab["stable_key"] == "drill-down")
        assert {"selected-chart", "sector-comparison"} <= {
            window["instance_key"] for window in drill_down["windows"]
        }

    def test_snapshot_is_revision_checked(self, client, auth_headers):
        workspace = client.get("/api/v1/workspaces/default", headers=auth_headers).json()
        payload = {
            "base_revision": workspace["revision"],
            "name": "Morning Review",
            "settings": {"factory_id": "us-top-down"},
            "schema_version": 1,
            "tabs": [
                {
                    "stable_key": "morning",
                    "name": "Morning",
                    "position": 0,
                    "layout_config": {"root": "row"},
                    "windows": [
                        {
                            "instance_key": "chart",
                            "tool_type": "chart",
                            "configuration": {"symbol": "SPY"},
                        }
                    ],
                }
            ],
        }
        saved = client.put(
            f"/api/v1/workspaces/{workspace['id']}/snapshot",
            headers=auth_headers,
            json=payload,
        )
        assert saved.status_code == 200
        assert saved.json()["revision"] == 2
        assert saved.json()["tabs"][0]["windows"][0]["configuration"]["symbol"] == "SPY"

        stale = client.put(
            f"/api/v1/workspaces/{workspace['id']}/snapshot",
            headers=auth_headers,
            json=payload,
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "workspace_revision_conflict"

    def test_snapshot_can_replace_factory_tabs_with_the_same_stable_keys(
        self, client, auth_headers
    ):
        workspace = client.get("/api/v1/workspaces/default", headers=auth_headers).json()
        payload = {
            "base_revision": workspace["revision"],
            "name": workspace["name"],
            "settings": workspace["settings"],
            "schema_version": workspace["schema_version"],
            "tabs": [
                {
                    "stable_key": tab["stable_key"],
                    "name": tab["name"],
                    "position": tab["position"],
                    "layout_config": tab["layout_config"],
                    "active_window_key": tab["active_window_key"],
                    "windows": [
                        {
                            "instance_key": window["instance_key"],
                            "tool_type": window["tool_type"],
                            "title": window["title"],
                            "link_group": window["link_group"],
                            "configuration": window["configuration"],
                            "style": window["style"],
                            "state_schema_version": window["state_schema_version"],
                            "position": window["position"],
                        }
                        for window in tab["windows"]
                    ],
                }
                for tab in workspace["tabs"]
            ],
        }

        saved = client.put(
            f"/api/v1/workspaces/{workspace['id']}/snapshot",
            headers=auth_headers,
            json=payload,
        )

        assert saved.status_code == 200
        assert [tab["stable_key"] for tab in saved.json()["tabs"]] == [
            tab["stable_key"] for tab in workspace["tabs"]
        ]

    def test_default_workspace_repairs_legacy_duplicate_defaults(self, client, auth_headers, db):
        from app.models.workstation import Workspace

        default = client.get("/api/v1/workspaces/default", headers=auth_headers).json()
        db.add(
            Workspace(
                user_id=default["user_id"],
                name="Interrupted Recovery",
                is_default=True,
                position=99,
                schema_version=1,
                settings={},
            )
        )
        db.flush()

        resolved = client.get("/api/v1/workspaces/default", headers=auth_headers)

        assert resolved.status_code == 200
        assert resolved.json()["id"] == default["id"]
        assert (
            db.query(Workspace).filter_by(user_id=default["user_id"], is_default=True).count() == 1
        )

    def test_library_item_is_versioned(self, client, auth_headers):
        payload = {
            "kind": "chart_template",
            "stable_key": "daily-strength",
            "name": "Daily Strength",
            "payload": {"timeframe": "D1"},
            "dependency_metadata": {"sdk_version": "1"},
        }
        first = client.put(
            "/api/v1/workspaces/library/items/chart_template/daily-strength",
            headers=auth_headers,
            json=payload,
        )
        assert first.status_code == 200
        assert first.json()["version"] == 1
        payload["name"] = "Daily Strength Updated"
        second = client.put(
            "/api/v1/workspaces/library/items/chart_template/daily-strength",
            headers=auth_headers,
            json=payload,
        )
        assert second.status_code == 200
        assert second.json()["version"] == 2

    def test_library_item_rename_returns_updated_timestamp(self, client, auth_headers):
        payload = {
            "kind": "chart_template",
            "stable_key": "rename-me",
            "name": "Original name",
            "payload": {"configuration": {"bar_type": "line"}},
            "dependency_metadata": {"contract": "workstation_chart_template_v1"},
        }
        created = client.put(
            "/api/v1/workspaces/library/items/chart_template/rename-me",
            headers=auth_headers,
            json=payload,
        )
        assert created.status_code == 200
        renamed = client.put(
            "/api/v1/workspaces/library/items/chart_template/rename-me",
            headers=auth_headers,
            json={**payload, "name": "Renamed template"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Renamed template"
        assert renamed.json()["stable_key"] == "rename-me"
        assert renamed.json()["version"] == 2
        assert renamed.json()["updated_at"]

    def test_combo_library_item_preserves_canonical_membership_sets(self, client, auth_headers):
        payload = {
            "kind": "combo_list",
            "stable_key": "tech-leaders",
            "name": "Tech leaders",
            "payload": {
                "union_watchlist_ids": [11, 12],
                "intersection_watchlist_ids": [12],
                "exclude_watchlist_ids": [13],
            },
            "dependency_metadata": {
                "watchlist_ids": [11, 12, 13],
                "membership_contract": "canonical_instrument_ids_v1",
            },
        }
        created = client.put(
            "/api/v1/workspaces/library/items/combo_list/tech-leaders",
            headers=auth_headers,
            json=payload,
        )
        assert created.status_code == 200
        assert created.json()["payload"] == payload["payload"]
        listed = client.get(
            "/api/v1/workspaces/library/items?kind=combo_list",
            headers=auth_headers,
        )
        assert listed.status_code == 200
        assert listed.json()[0]["dependency_metadata"] == payload["dependency_metadata"]

    def test_library_item_delete_is_user_isolated(self, client, auth_headers, admin_headers):
        payload = {
            "kind": "chart_template",
            "stable_key": "delete-me",
            "name": "Delete me",
            "payload": {"configuration": {"timeframe": "W1"}},
            "dependency_metadata": {"contract": "workstation_chart_template_v1"},
        }
        created = client.put(
            "/api/v1/workspaces/library/items/chart_template/delete-me",
            headers=auth_headers,
            json=payload,
        )
        assert created.status_code == 200

        hidden = client.delete(
            "/api/v1/workspaces/library/items/chart_template/delete-me",
            headers=admin_headers,
        )
        assert hidden.status_code == 404

        deleted = client.delete(
            "/api/v1/workspaces/library/items/chart_template/delete-me",
            headers=auth_headers,
        )
        assert deleted.status_code == 204
        assert (
            client.delete(
                "/api/v1/workspaces/library/items/chart_template/delete-me",
                headers=auth_headers,
            ).status_code
            == 404
        )

    def test_condition_assets_are_versioned_and_user_isolated(self, client, auth_headers):
        payload = {
            "name": "Close above 100",
            "description": "Reusable price condition",
            "condition": {
                "operator": "AND",
                "conditions": [
                    {"type": "price_threshold", "field": "close", "op": "gt", "value": 100}
                ],
            },
            "dependency_metadata": {"visual_editor": "v25"},
        }
        first = client.put(
            "/api/v1/workspaces/library/conditions/close-above-100",
            headers=auth_headers,
            json=payload,
        )
        assert first.status_code == 200
        assert first.json()["kind"] == "condition"
        assert first.json()["payload"]["condition"] == payload["condition"]
        assert isinstance(first.json()["payload"]["python_code_version_id"], int)
        assert "output.boolean('match'" in first.json()["payload"]["python_source"]
        assert first.json()["version"] == 1

        payload["name"] = "Close above 100 updated"
        second = client.put(
            "/api/v1/workspaces/library/conditions/close-above-100",
            headers=auth_headers,
            json=payload,
        )
        assert second.status_code == 200
        assert second.json()["version"] == 2
        listed = client.get("/api/v1/workspaces/library/conditions", headers=auth_headers)
        assert [item["stable_key"] for item in listed.json()] == ["close-above-100"]
        assert (
            client.delete(
                "/api/v1/workspaces/library/conditions/close-above-100", headers=auth_headers
            ).status_code
            == 204
        )

    def test_market_group_roots_are_source_labelled(self, client, auth_headers):
        response = client.get("/api/v1/market-groups", headers=auth_headers)
        assert response.status_code == 200
        roots = {group["stable_key"]: group for group in response.json()}
        assert roots["us-benchmarks"]["provenance"]["official_index_constituents"] is False
        assert roots["us-benchmarks"]["provenance"]["benchmark_identities"]["sp500"] == {
            "logical_key": "sp500",
            "official_index_symbol": "SPX",
            "default_tradable_proxy": "SPY",
            "proxy_label": "S&P 500 proxy (SPY)",
            "official_series_policy": "use_only_when_entitled",
        }
        assert (
            roots["sp500-sectors"]["provenance"]["membership_semantics"]
            == "ETF proxy where applicable"
        )

    def test_benchmark_family_children_expose_cap_equal_style_registry_without_fallback(
        self, client, auth_headers
    ):
        roots = {
            group["stable_key"]: group
            for group in client.get("/api/v1/market-groups", headers=auth_headers).json()
        }
        families = roots["us-benchmarks"]["provenance"]["benchmark_families"]
        assert [family["logical_key"] for family in families] == [
            "sp500",
            "sp400",
            "sp600",
            "sp1500",
            "russell1000",
            "russell2000",
            "russell3000",
            "nasdaq100",
        ]
        nasdaq = next(family for family in families if family["logical_key"] == "nasdaq100")
        assert nasdaq["cap_weight"]["symbol"] == "QQQ"
        assert nasdaq["equal_weight"]["symbol"] == "QQQE"
        sp1500 = next(family for family in families if family["logical_key"] == "sp1500")
        assert sp1500["value"]["label"] == "No verified mapped proxy"
        assert sp1500["growth"]["label"] == "No verified mapped proxy"

        children = client.get("/api/v1/market-groups/us-benchmarks/children", headers=auth_headers)
        assert children.status_code == 200
        child_by_key = {group["stable_key"]: group for group in children.json()}
        assert set(child_by_key) == {family["logical_key"] for family in families}
        # This integration fixture intentionally seeds only the original
        # workstation identities.  The taxonomy must preserve the family
        # mappings without fabricating missing canonical instruments or
        # silently substituting QQQ/SPY.
        assert child_by_key["nasdaq100"]["representative_instrument_id"] is None
        assert child_by_key["nasdaq100"]["equal_weight_instrument_id"] is None
        assert child_by_key["sp1500"]["equal_weight_instrument_id"] is None
        assert child_by_key["nasdaq100"]["members"] == []
        assert child_by_key["sp500"]["members"] == []
        assert set(child_by_key["sp500"]["provenance"]["proxy_mappings"]) == {
            "cap_weight",
            "equal_weight",
            "value",
            "growth",
        }

    def test_benchmark_family_overview_preserves_mapping_gaps_without_spy_fallback(
        self, client, auth_headers
    ):
        # The taxonomy is normally materialised by startup/maintenance.  Prime
        # the empty integration database through its supported read bootstrap
        # before exercising the analytics endpoint; the overview itself must
        # remain read-only and must not seed or substitute another benchmark.
        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        response = client.get(
            "/api/v1/analysis/benchmark-families/nasdaq100/overview",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["family_key"] == "nasdaq100"
        assert payload["official_index_symbol"] == "NDX"
        assert payload["coverage"] == 0
        assert payload["rows"] == []
        assert payload["universe_provenance"]["cap_proxy_symbol"] == "QQQ"
        assert payload["universe_provenance"]["cap_proxy_available"] is False
        assert payload["exclusions"][0]["code"] == "cap_proxy_unavailable"
        mappings = {mapping["role"]: mapping for mapping in payload["mappings"]}
        assert mappings["cap_weight"]["symbol"] == "QQQ"
        assert mappings["cap_weight"]["available"] is False
        assert mappings["equal_weight"]["symbol"] == "QQQE"
        assert mappings["equal_weight"]["label"] == "Nasdaq-100 equal-weight ETF proxy"

    def test_benchmark_family_coverage_exposes_role_dates_and_point_in_time_filter(
        self, client, auth_headers, db, instrument_type
    ):
        from datetime import UTC, datetime
        from decimal import Decimal

        from app.models.etf_holdings import ETFHoldingsAdapterState, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(spy)
        db.flush()
        profile = ETFProfile(
            instrument_id=spy.id,
            adapter_key="spdr",
            adapter_status="failure",
            adapter_confidence=Decimal("0.9900"),
        )
        db.add(profile)
        db.flush()
        db.add(
            ETFHoldingsAdapterState(
                etf_profile_id=profile.id,
                adapter_key="spdr",
                status="failure",
                last_checked_at=datetime(2026, 7, 2, tzinfo=UTC),
                last_failure_at=datetime(2026, 7, 2, tzinfo=UTC),
                failure_reason="issuer endpoint unavailable",
            )
        )
        db.flush()
        first = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
            known_at=datetime(2026, 7, 1, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="issuer",
            source_quality="issuer_disclosed",
            completeness_status="complete",
            row_count=10,
            resolved_count=9,
            unresolved_count=1,
            total_weight=0.99,
            snapshot_hash="test-family-coverage-first",
        )
        second = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2027, 6, 30, tzinfo=UTC).date(),
            known_at=datetime(2027, 7, 1, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="issuer",
            source_quality="issuer_disclosed",
            completeness_status="complete",
            row_count=11,
            resolved_count=11,
            unresolved_count=0,
            total_weight=1.0,
            snapshot_hash="test-family-coverage-second",
        )
        db.add_all([first, second])
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/coverage",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        roles = {role["role"]: role for role in payload["roles"]}
        assert roles["cap_weight"]["status"] == "available"
        assert roles["cap_weight"]["adapter_key"] == "spdr"
        assert roles["cap_weight"]["adapter_status"] == "failure"
        assert Decimal(roles["cap_weight"]["adapter_confidence"]) == Decimal("0.9900")
        assert roles["cap_weight"]["entitlement_status"] == "unknown"
        assert roles["cap_weight"]["holdings_refresh_status"] == "failure"
        assert roles["cap_weight"]["holdings_refresh_provider"] == "issuer"
        assert (
            roles["cap_weight"]["holdings_refresh_failure_reason"] == "issuer endpoint unavailable"
        )
        assert roles["cap_weight"]["composite_readiness_status"] == "partial"
        assert roles["cap_weight"]["point_in_time_supported"] is True
        assert [row["composition_date"] for row in roles["cap_weight"]["snapshots"]] == [
            "2027-06-30",
            "2026-06-30",
        ]
        assert roles["cap_weight"]["continuity_status"] == "gapped"
        assert roles["cap_weight"]["continuity_gap_count"] == 1
        assert roles["cap_weight"]["continuity_max_interval_days"] == 365
        assert roles["cap_weight"]["continuity_gaps"] == [
            {"from_date": "2026-06-30", "to_date": "2027-06-30", "interval_days": 365}
        ]
        assert roles["cap_weight"]["continuity_snapshot_limit_reached"] is False
        assert roles["equal_weight"]["status"] == "mapping_unavailable"
        assert roles["value"]["status"] == "mapping_unavailable"
        assert roles["growth"]["status"] == "mapping_unavailable"
        assert payload["coverage"] == 0.25

        historical = client.get(
            "/api/v1/analysis/benchmark-families/sp500/coverage",
            headers=auth_headers,
            params={"as_of": "2026-12-31T00:00:00Z"},
        )
        assert historical.status_code == 200, historical.text
        historical_cap = next(
            role for role in historical.json()["roles"] if role["role"] == "cap_weight"
        )
        assert [row["composition_date"] for row in historical_cap["snapshots"]] == ["2026-06-30"]
        assert historical_cap["continuity_status"] == "single_snapshot"
        assert historical_cap["continuity_gap_count"] == 0
        assert historical.json()["universe_provenance"]["point_in_time"] is True
        assert (
            historical.json()["universe_provenance"]["continuity_policy"]
            == "observed_snapshot_intervals_gt_45_days"
        )

    def test_benchmark_family_coverage_resolves_entitlements_by_snapshot_provider(
        self, client, auth_headers, db, instrument_type
    ):
        from datetime import UTC, datetime

        from app.models.data_source import DataSource
        from app.models.etf_holdings import ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument
        from app.models.provider_runtime import ProviderCapability, ProviderEntitlement

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="S&P 500 provider-entitlement fixture",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(spy)
        db.flush()
        profile = ETFProfile(instrument_id=spy.id, adapter_key="spdr", adapter_status="success")
        db.add(profile)
        provider_source = DataSource(
            name="spdr",
            base_url="https://issuer.example/spdr",
            description="Provider entitlement fixture",
            is_active=True,
        )
        db.add(provider_source)
        db.flush()
        db.add_all(
            [
                ProviderEntitlement(
                    data_source_id=provider_source.id,
                    capability=ProviderCapability.UNIVERSE_DISCOVERY,
                    configured_plan="free",
                    is_free=True,
                    authentication_required=False,
                    live_probe_status="passed",
                ),
                ProviderEntitlement(
                    data_source_id=provider_source.id,
                    capability=ProviderCapability.PRICE_HISTORY,
                    configured_plan="free",
                    is_free=True,
                    authentication_required=False,
                    live_probe_status="passed",
                ),
            ]
        )
        db.add(
            ETFHoldingsSnapshot(
                etf_profile_id=profile.id,
                data_source_id=None,
                composition_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
                known_at=datetime(2026, 7, 1, tzinfo=UTC),
                provenance="issuer_native",
                source_provider="spdr",
                source_quality="issuer_disclosed",
                completeness_status="complete",
                row_count=1,
                resolved_count=1,
                unresolved_count=0,
                snapshot_hash="test-family-provider-entitlement",
            )
        )
        value_proxy = Instrument(
            symbol="SPYV",
            name="S&P 500 value provider-entitlement fixture",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(value_proxy)
        db.flush()
        db.add(ETFProfile(instrument_id=value_proxy.id, adapter_key="spdr"))
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/coverage",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        cap = next(role for role in response.json()["roles"] if role["role"] == "cap_weight")
        assert cap["entitlement_status"] == "verified"
        assert cap["entitlement_provider"] == "spdr"
        assert cap["entitlement_capabilities"] == {
            "universe_discovery": "verified",
            "price_history": "verified",
        }
        value = next(role for role in response.json()["roles"] if role["role"] == "value")
        assert value["status"] == "no_snapshot"
        assert value["entitlement_status"] == "verified"
        assert value["entitlement_provider"] == "spdr"

    def test_benchmark_family_coverage_reports_member_bar_and_technical_readiness(
        self, client, auth_headers, db, instrument_type, instrument, instrument_b
    ):
        from datetime import UTC, datetime, timedelta

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import EquityDetail, Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(spy)
        db.flush()
        profile = ETFProfile(instrument_id=spy.id, adapter_key="spdr", adapter_status="resolved")
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2024, 1, 1, tzinfo=UTC).date(),
            known_at=datetime(2024, 1, 2, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="issuer",
            source_quality="issuer_disclosed",
            completeness_status="complete",
            row_count=2,
            resolved_count=2,
            unresolved_count=0,
            total_weight=1.0,
            snapshot_hash="test-family-member-bars",
        )
        db.add(snapshot)
        db.flush()
        db.add_all(
            [
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=instrument.id,
                    position=0,
                    reported_symbol=instrument.symbol,
                    reported_name=instrument.name,
                    weight=0.5,
                    holding_type="equity",
                    row_type="security",
                    source_row_hash="family-member-bars-a",
                    is_resolved=True,
                ),
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=instrument_b.id,
                    position=1,
                    reported_symbol=instrument_b.symbol,
                    reported_name=instrument_b.name,
                    weight=0.5,
                    holding_type="equity",
                    row_type="security",
                    source_row_hash="family-member-bars-b",
                    is_resolved=True,
                ),
            ]
        )
        base = datetime(2024, 1, 2, 21, tzinfo=UTC)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=base + timedelta(days=offset),
                    open=100,
                    high=101,
                    low=99,
                    close=100,
                    volume=1_000,
                    is_adjusted=True,
                )
                for offset in range(252)
            ]
            + [
                OHLCVBar(
                    instrument_id=instrument_b.id,
                    timeframe=Timeframe.D1,
                    ts=base,
                    open=100,
                    high=101,
                    low=99,
                    close=100,
                    volume=1_000,
                    is_adjusted=True,
                )
            ]
        )
        db.add_all(
            [
                EquityDetail(
                    instrument_id=instrument.id,
                    industry="Technology",
                    field_provenance={"industry": {"observed_at": "2027-03-01T00:00:00Z"}},
                ),
                EquityDetail(
                    instrument_id=instrument_b.id,
                    industry="Software",
                    field_provenance={"industry": {"observed_at": "2027-03-01T00:00:00Z"}},
                ),
            ]
        )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/coverage",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        cap = next(role for role in response.json()["roles"] if role["role"] == "cap_weight")
        history = cap["member_bar_history"]
        assert history["status"] == "partial"
        assert history["snapshot_id"] == snapshot.id
        assert cap["member_count"] == 2
        assert cap["weighted_member_count"] == 2
        assert cap["weights_status"] == "ready"
        assert cap["classified_member_count"] == 2
        assert cap["classification_status"] == "ready"
        historical = client.get(
            "/api/v1/analysis/benchmark-families/sp500/coverage",
            headers=auth_headers,
            # Exercise the offset-less ISO form accepted by FastAPI; the
            # readiness classifier must normalize it before comparing stored
            # UTC provenance timestamps.
            params={"as_of": "2026-12-01T00:00:00"},
        )
        assert historical.status_code == 200, historical.text
        historical_cap = next(
            role for role in historical.json()["roles"] if role["role"] == "cap_weight"
        )
        assert historical_cap["member_count"] == 2
        assert historical_cap["classified_member_count"] == 0
        assert historical_cap["classification_status"] == "pending"
        daily = next(item for item in history["timeframes"] if item["timeframe"] == "D1")
        assert daily["member_count"] == 2
        assert daily["covered_member_count"] == 2
        assert daily["coverage_percent"] == 100.0
        assert daily["required_bar_count"] == 252
        assert daily["analysis_ready_member_count"] == 1
        assert daily["analysis_ready_percent"] == 50.0
        assert daily["bar_count"] == 253
        weekly = next(item for item in history["timeframes"] if item["timeframe"] == "W1")
        assert weekly["covered_member_count"] == 0
        assert weekly["analysis_ready_member_count"] == 0

    def test_benchmark_family_readiness_excludes_placeholder_members_from_canonical_counts(
        self, client, auth_headers, db, instrument_type, instrument
    ):
        from datetime import UTC, datetime

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        placeholder = Instrument(
            symbol="HOLDING-ABC123",
            name="Unresolved example security",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add_all([spy, placeholder])
        db.flush()
        profile = ETFProfile(instrument_id=spy.id, adapter_key="spdr", adapter_status="resolved")
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2025, 12, 31, tzinfo=UTC).date(),
            known_at=datetime(2026, 1, 2, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="issuer",
            source_quality="issuer_disclosed",
            completeness_status="partial",
            row_count=2,
            # The ingestion count preserves the materialized placeholder row;
            # readiness must still expose only canonical members.
            resolved_count=2,
            unresolved_count=0,
            total_weight=1.0,
            snapshot_hash="test-family-placeholder-readiness",
        )
        db.add(snapshot)
        db.flush()
        db.add_all(
            [
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=instrument.id,
                    position=0,
                    reported_symbol=instrument.symbol,
                    reported_name=instrument.name,
                    weight=0.75,
                    holding_type="equity",
                    row_type="security",
                    source_row_hash="placeholder-readiness-canonical",
                    is_resolved=True,
                ),
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=placeholder.id,
                    position=1,
                    reported_name=placeholder.name,
                    weight=0.25,
                    holding_type="equity",
                    row_type="security",
                    source_row_hash="placeholder-readiness-placeholder",
                    is_resolved=True,
                ),
            ]
        )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/coverage",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        cap = next(role for role in response.json()["roles"] if role["role"] == "cap_weight")
        assert cap["member_count"] == 1
        assert cap["placeholder_member_count"] == 1
        assert cap["weighted_member_count"] == 1
        assert cap["weights_status"] == "ready"
        history = cap["member_bar_history"]
        assert history["placeholder_member_count"] == 1
        daily = next(item for item in history["timeframes"] if item["timeframe"] == "D1")
        assert daily["member_count"] == 1


    def test_benchmark_family_coverage_marks_canonical_role_without_profile_as_pending(
        self, client, auth_headers, db, instrument_type
    ):
        from app.models.instrument import Instrument

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        db.add(
            Instrument(
                symbol="SPYV",
                name="S&P 500 value proxy without profile",
                currency="USD",
                instrument_type_id=instrument_type.id,
                is_active=True,
                is_synthetic=False,
            )
        )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/coverage",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        value_role = next(role for role in response.json()["roles"] if role["role"] == "value")
        assert value_role["symbol"] == "SPYV"
        assert value_role["available"] is True
        assert value_role["status"] == "profile_not_loaded"
        assert value_role["holdings_route_adapter_key"] == "spdr"
        assert value_role["holdings_route_provider"] == "spdr"
        assert value_role["holdings_route_status"] == "configured"
        assert value_role["snapshots"] == []
        assert any(
            warning["code"] == "family_role_profile_unavailable"
            for warning in response.json()["exclusions"]
        )

    def test_benchmark_family_coverage_uses_historical_profile_snapshot_for_classification(
        self, client, auth_headers, db, instrument_type, instrument, instrument_b
    ):
        from datetime import UTC, datetime

        from app.models.data_source import DataSource
        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import EquityDetail, Instrument
        from app.models.provider_observation import InstrumentProfileSnapshot

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(spy)
        db.flush()
        profile = ETFProfile(instrument_id=spy.id, adapter_key="spdr", adapter_status="resolved")
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2025, 12, 31, tzinfo=UTC).date(),
            known_at=datetime(2026, 1, 2, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="issuer",
            source_quality="issuer_disclosed",
            completeness_status="complete",
            row_count=2,
            resolved_count=2,
            unresolved_count=0,
            total_weight=1.0,
            snapshot_hash="test-family-historical-profile",
        )
        db.add(snapshot)
        db.flush()
        db.add_all(
            [
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=instrument.id,
                    position=0,
                    reported_symbol=instrument.symbol,
                    reported_name=instrument.name,
                    weight=0.6,
                    holding_type="equity",
                    row_type="security",
                    source_row_hash="historical-profile-a",
                    is_resolved=True,
                ),
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=instrument_b.id,
                    position=1,
                    reported_symbol=instrument_b.symbol,
                    reported_name=instrument_b.name,
                    weight=0.4,
                    holding_type="equity",
                    row_type="security",
                    source_row_hash="historical-profile-b",
                    is_resolved=True,
                ),
                EquityDetail(
                    instrument_id=instrument.id,
                    industry="Current Technology",
                    field_provenance={"industry": {"observed_at": "2027-01-01T00:00:00Z"}},
                ),
                EquityDetail(
                    instrument_id=instrument_b.id,
                    industry="Current Software",
                    field_provenance={"industry": {"observed_at": "2027-01-01T00:00:00Z"}},
                ),
            ]
        )
        profile_source = DataSource(
            name="historical-family-profile",
            base_url="controlled://historical-family-profile",
            description="Historical family classification fixture",
            is_active=True,
        )
        db.add(profile_source)
        db.flush()
        db.add(
            InstrumentProfileSnapshot(
                instrument_id=instrument.id,
                data_source_id=profile_source.id,
                provider_symbol=instrument.symbol,
                observed_at=datetime(2025, 12, 30, tzinfo=UTC),
                fetched_at=datetime(2026, 1, 3, tzinfo=UTC),
                profile_hash="historical-family-profile-a",
                payload={"extra": {"industry": "Historical Technology"}},
            )
        )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/coverage",
            headers=auth_headers,
            params={"as_of": "2026-12-31T00:00:00Z"},
        )
        assert response.status_code == 200, response.text
        cap = next(role for role in response.json()["roles"] if role["role"] == "cap_weight")
        assert cap["member_count"] == 2
        assert cap["classified_member_count"] == 1
        assert cap["classification_status"] == "partial"

    def test_benchmark_family_coverage_does_not_infer_point_in_time_from_requested_cutoff(
        self, client, auth_headers, db, instrument_type
    ):
        from app.models.etf_holdings import ETFProfile
        from app.models.instrument import Instrument

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200, seeded.text
        value_proxy = Instrument(
            symbol="SPYV",
            name="S&P 500 value proxy without dated holdings",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            is_synthetic=False,
        )
        db.add(value_proxy)
        db.flush()
        db.add(ETFProfile(instrument_id=value_proxy.id, adapter_key="spdr"))
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/coverage",
            headers=auth_headers,
            params={"as_of": "2030-01-01T00:00:00Z"},
        )
        assert response.status_code == 200, response.text
        value_role = next(role for role in response.json()["roles"] if role["role"] == "value")
        assert value_role["status"] == "no_snapshot"
        assert value_role["point_in_time_supported"] is False
        assert "point_in_time_unavailable" in value_role["composite_readiness_reasons"]

    def test_benchmark_family_readiness_returns_all_registry_families_without_fallback(
        self, client, auth_headers
    ):
        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200, seeded.text

        response = client.get(
            "/api/v1/analysis/benchmark-families/readiness",
            headers=auth_headers,
            params={"as_of": "2026-08-01T00:00:00Z", "limit": 8},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["family_count"] == 8
        assert payload["role_count"] == 32
        assert payload["ready_family_count"] == 0
        assert payload["ready_role_count"] == 0
        assert payload["readiness_status"] == "coverage_limited"
        assert payload["as_of"] == "2026-08-01T00:00:00Z"
        assert payload["snapshot_limit"] == 8
        assert payload["universe_provenance"]["provider_calls"] is False
        assert payload["universe_provenance"]["provider_probe_count"] == len(
            payload["provider_probe_evidence"]
        )
        assert {family["family_key"] for family in payload["families"]} == {
            "sp500",
            "sp400",
            "sp600",
            "sp1500",
            "russell1000",
            "russell2000",
            "russell3000",
            "nasdaq100",
        }
        assert all(len(family["roles"]) == 4 for family in payload["families"])
        assert all(
            role["composite_readiness_status"] == "unavailable"
            for family in payload["families"]
            for role in family["roles"]
        )

    def test_benchmark_family_coverage_marks_unresolved_snapshot_as_pending(
        self, client, auth_headers, db, instrument_type
    ):
        from datetime import UTC, datetime

        from app.models.etf_holdings import ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200, seeded.text
        value_proxy = Instrument(
            symbol="SPYV",
            name="S&P 500 value proxy with unresolved holdings",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            is_synthetic=False,
        )
        db.add(value_proxy)
        db.flush()
        profile = ETFProfile(instrument_id=value_proxy.id, adapter_status="failure")
        db.add(profile)
        db.flush()
        db.add(
            ETFHoldingsSnapshot(
                etf_profile_id=profile.id,
                composition_date=datetime(2024, 1, 1, tzinfo=UTC).date(),
                known_at=datetime(2024, 1, 2, tzinfo=UTC),
                provenance="issuer_native",
                source_provider="controlled_fixture",
                source_quality="issuer_disclosed",
                completeness_status="partial",
                row_count=3,
                resolved_count=0,
                unresolved_count=3,
                snapshot_hash="family-unresolved-value-snapshot",
            )
        )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/coverage",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        value_role = next(role for role in response.json()["roles"] if role["role"] == "value")
        assert value_role["available"] is True
        assert value_role["status"] == "holdings_snapshot_unresolved"
        assert value_role["snapshots"][0]["resolved_count"] == 0
        assert value_role["point_in_time_supported"] is False
        assert response.json()["coverage"] == 0
        assert any(
            warning["code"] == "family_role_holdings_unresolved"
            for warning in response.json()["exclusions"]
        )

    def test_benchmark_family_constituent_route_preserves_leg_and_proxy_errors(
        self, client, auth_headers, db, instrument, instrument_type, ohlcv_bars
    ):
        from datetime import UTC, datetime
        from decimal import Decimal

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(spy)
        db.flush()
        profile = ETFProfile(instrument_id=spy.id, adapter_status="resolved")
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2024, 5, 30, tzinfo=UTC).date(),
            known_at=datetime(2024, 5, 31, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="issuer",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            total_weight=Decimal("0.25"),
            snapshot_hash="test-family-spy-snapshot",
        )
        db.add(snapshot)
        db.flush()
        db.add(
            ETFHolding(
                snapshot_id=snapshot.id,
                constituent_instrument_id=instrument.id,
                position=0,
                reported_symbol=instrument.symbol,
                reported_name=instrument.name,
                weight=Decimal("0.25"),
                shares=Decimal("12"),
                market_value=Decimal("1234.50"),
                source_row_hash="test-family-spy-aapl",
                is_resolved=True,
            )
        )
        db.flush()
        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/constituents",
            headers=auth_headers,
            params={"role": "cap_weight", "as_of": "2024-06-01T00:00:00Z"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["group_key"] == "benchmark-family:sp500:cap_weight"
        assert payload["etf_symbol"] == "SPY"
        assert payload["benchmark"] == "SPY"
        assert payload["universe_provenance"]["mapping_role"] == "cap_weight"
        assert payload["universe_provenance"]["membership_semantics"] == "etf_proxy_membership"
        assert payload["rows"][0]["symbol"] == instrument.symbol
        assert payload["rows"][0]["position"] == 0
        assert payload["rows"][0]["weight"] == "0.25000000"
        assert payload["rows"][0]["shares"] == "12.00000000"
        assert payload["rows"][0]["market_value"] == "1234.500000"

        overview = client.get(
            "/api/v1/analysis/benchmark-families/sp500/overview",
            headers=auth_headers,
        )
        assert overview.status_code == 200, overview.text
        cap_mapping = next(
            mapping for mapping in overview.json()["mappings"] if mapping["role"] == "cap_weight"
        )
        assert cap_mapping["holdings_available"] is True
        assert cap_mapping["holdings_composition_date"] == "2024-05-30"
        assert cap_mapping["holdings_source_provider"] == "issuer"
        assert cap_mapping["holdings_row_count"] == 1
        assert cap_mapping["holdings_resolved_count"] == 1
        assert Decimal(cap_mapping["holdings_total_weight"]) == Decimal("0.25")

        missing = client.get(
            "/api/v1/analysis/benchmark-families/sp500/constituents",
            headers=auth_headers,
            params={"role": "value"},
        )
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "benchmark_proxy_unavailable"

    def test_benchmark_family_concentration_reports_weight_hhi_and_dispersion(
        self, client, auth_headers, db, instrument, instrument_type, ohlcv_bars
    ):
        from datetime import UTC, datetime
        from decimal import Decimal

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(spy)
        db.flush()
        profile = ETFProfile(instrument_id=spy.id, adapter_status="resolved")
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2024, 6, 30, tzinfo=UTC).date(),
            known_at=datetime(2024, 7, 1, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="fixture",
            source_quality="issuer_disclosed",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            total_weight=Decimal("0.25"),
            snapshot_hash="test-family-concentration-spy",
        )
        db.add(snapshot)
        db.flush()
        db.add(
            ETFHolding(
                snapshot_id=snapshot.id,
                constituent_instrument_id=instrument.id,
                position=1,
                reported_symbol=instrument.symbol,
                reported_name=instrument.name,
                weight=Decimal("0.25"),
                source_row_hash="test-family-concentration-aapl",
                is_resolved=True,
            )
        )
        for index, bar in enumerate(ohlcv_bars):
            close = Decimal(str(100 + index))
            db.add(
                OHLCVBar(
                    instrument_id=spy.id,
                    timeframe=Timeframe.D1,
                    ts=bar.ts,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=Decimal("1"),
                    is_adjusted=True,
                )
            )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/concentration",
            headers=auth_headers,
            params={"rank_period": "1M", "top_n": 5},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        roles = {role["role"]: role for role in payload["roles"]}
        cap = roles["cap_weight"]
        assert cap["available"] is True
        assert cap["weight_method"] == "reported_holdings_weights"
        assert cap["top_n_weight"] == 0.25
        assert cap["hhi"] == 1
        assert cap["effective_constituents"] == 1
        assert cap["eligible_count"] == 1
        assert cap["covered_count"] == 1
        assert cap["coverage"] == 1
        assert cap["dispersion"] == 0
        assert cap["members"][0]["symbol"] == instrument.symbol
        assert roles["equal_weight"]["available"] is False

    def test_benchmark_family_concentration_history_uses_known_at_snapshots(
        self, client, auth_headers, db, instrument, instrument_type, ohlcv_bars
    ):
        from datetime import UTC, datetime
        from decimal import Decimal

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(spy)
        db.flush()
        profile = ETFProfile(instrument_id=spy.id, adapter_status="resolved")
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2024, 1, 1, tzinfo=UTC).date(),
            known_at=datetime(2024, 1, 2, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="fixture",
            source_quality="issuer_disclosed",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            total_weight=Decimal("0.25"),
            snapshot_hash="test-family-concentration-history-spy",
        )
        db.add(snapshot)
        db.flush()
        db.add(
            ETFHolding(
                snapshot_id=snapshot.id,
                constituent_instrument_id=instrument.id,
                position=1,
                reported_symbol=instrument.symbol,
                reported_name=instrument.name,
                weight=Decimal("0.25"),
                source_row_hash="test-family-concentration-history-aapl",
                is_resolved=True,
            )
        )
        later_snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2024, 3, 1, tzinfo=UTC).date(),
            known_at=datetime(2024, 3, 2, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="fixture",
            source_quality="issuer_disclosed",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            total_weight=Decimal("0.50"),
            snapshot_hash="test-family-concentration-history-spy-later",
        )
        db.add(later_snapshot)
        db.flush()
        db.add(
            ETFHolding(
                snapshot_id=later_snapshot.id,
                constituent_instrument_id=instrument.id,
                position=1,
                reported_symbol=instrument.symbol,
                reported_name=instrument.name,
                weight=Decimal("0.50"),
                source_row_hash="test-family-concentration-history-aapl-later",
                is_resolved=True,
            )
        )
        for index, bar in enumerate(ohlcv_bars):
            close = Decimal(str(100 + index))
            db.add(
                OHLCVBar(
                    instrument_id=spy.id,
                    timeframe=Timeframe.D1,
                    ts=bar.ts,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=Decimal("1"),
                    is_adjusted=True,
                )
            )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/concentration/history",
            headers=auth_headers,
            params={"rank_period": "1D", "top_n": 5, "limit": 100},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        roles = {role["role"]: role for role in payload["roles"]}
        cap = roles["cap_weight"]
        assert cap["available"] is True
        assert cap["points"]
        point = cap["points"][-1]
        assert cap["points"][0]["snapshot_id"] == snapshot.id
        assert point["snapshot_id"] == later_snapshot.id
        assert point["composition_date"] == "2024-03-01"
        assert point["known_at"].startswith("2024-03-02")
        assert point["weight_method"] == "reported_holdings_weights"
        assert point["top_n_weight"] == 0.50
        assert point["hhi"] == 1
        assert point["effective_constituents"] == 1
        assert point["coverage"] == 1
        assert {item["snapshot_id"] for item in cap["points"]} == {snapshot.id, later_snapshot.id}
        assert roles["equal_weight"]["available"] is False

    def test_benchmark_family_concentration_history_supports_derived_equal_membership(
        self, client, auth_headers, db, instrument, instrument_b, ohlcv_bars
    ):
        from datetime import UTC, datetime
        from decimal import Decimal

        from sqlalchemy import select

        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.workstation import MarketGroup, MarketGroupMember

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        family = db.execute(
            select(MarketGroup).where(MarketGroup.stable_key == "sp400")
        ).scalar_one()
        db.add_all(
            [
                MarketGroupMember(
                    market_group_id=family.id,
                    instrument_id=instrument.id,
                    relationship_type="constituent",
                    position=1,
                    source="controlled_fixture",
                    verification_state="point_in_time_verified",
                    effective_at=datetime(2024, 1, 1, tzinfo=UTC),
                    known_at=datetime(2024, 1, 2, tzinfo=UTC),
                    provenance={"membership_semantics": "official_constituent"},
                ),
                MarketGroupMember(
                    market_group_id=family.id,
                    instrument_id=instrument_b.id,
                    relationship_type="constituent",
                    position=2,
                    source="controlled_fixture",
                    verification_state="point_in_time_verified",
                    effective_at=datetime(2024, 3, 1, tzinfo=UTC),
                    known_at=datetime(2024, 3, 2, tzinfo=UTC),
                    provenance={"membership_semantics": "official_constituent"},
                ),
            ]
        )
        for index, bar in enumerate(ohlcv_bars):
            close = Decimal(str(220 + index))
            db.add(
                OHLCVBar(
                    instrument_id=instrument_b.id,
                    timeframe=Timeframe.D1,
                    ts=bar.ts,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=Decimal("1"),
                    is_adjusted=True,
                )
            )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp400/concentration/history",
            headers=auth_headers,
            params={"rank_period": "YTD", "top_n": 5, "limit": 500},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        roles = {role["role"]: role for role in payload["roles"]}
        equal = roles["equal_weight"]
        assert equal["available"] is True
        assert equal["symbol"] is None
        assert equal["verification_state"] == "derived_policy"
        assert equal["membership_semantics"] == "point_in_time_group_membership"
        assert equal["points"]
        assert {point["snapshot_id"] for point in equal["points"]} == {None}
        assert {point["membership_semantics"] for point in equal["points"]} == {
            "point_in_time_group_membership"
        }
        before_rebalance = [
            point for point in equal["points"] if point["timestamp"] < "2024-03-02T00:00:00+00:00"
        ][-1]
        after_rebalance = [
            point for point in equal["points"] if point["timestamp"] >= "2024-03-02T00:00:00+00:00"
        ][0]
        assert before_rebalance["eligible_count"] == 1
        assert before_rebalance["hhi"] == 1
        assert before_rebalance["composition_date"] == "2024-01-01"
        assert before_rebalance["known_at"].startswith("2024-01-02")
        assert after_rebalance["eligible_count"] == 2
        assert after_rebalance["hhi"] == 0.5
        assert after_rebalance["composition_date"] == "2024-03-01"
        assert after_rebalance["known_at"].startswith("2024-03-02")
        assert equal["points"][-1]["weight_method"] == (
            "equal_start_weight_point_in_time_membership_rebalanced_on_declared_schedule"
        )

    def test_benchmark_family_ratios_align_selected_leg_to_cap_and_market(
        self, client, auth_headers, db, instrument_type
    ):
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal

        from app.models.instrument import Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        rsp = Instrument(
            symbol="RSP",
            name="Invesco S&P 500 Equal Weight ETF",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add_all([spy, rsp])
        db.flush()
        base = datetime(2025, 1, 1, tzinfo=UTC)
        for index, (spy_close, rsp_close) in enumerate(((100, 50), (101, 51), (102, 53))):
            timestamp = base + timedelta(days=index)
            for current, close in ((spy, spy_close), (rsp, rsp_close)):
                value = Decimal(str(close))
                db.add(
                    OHLCVBar(
                        instrument_id=current.id,
                        timeframe=Timeframe.D1,
                        ts=timestamp,
                        open=value,
                        high=value,
                        low=value,
                        close=value,
                        volume=Decimal("1"),
                        is_adjusted=True,
                    )
                )
        db.flush()
        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/ratios",
            headers=auth_headers,
            params={"role": "equal_weight", "market_benchmark": "SPY"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["universe_provenance"]["ratio_semantics"] == (
            "aligned_close_ratio_without_forward_fill"
        )
        assert [(item["benchmark_role"], item["benchmark"]) for item in payload["ratios"]] == [
            ("cap_weight", "SPY"),
            ("market", "SPY"),
        ]
        assert len(payload["ratios"][0]["points"]) == 3
        assert payload["ratios"][0]["points"][-1]["value"] == 53 / 102

        batch_response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/ratios",
            headers=auth_headers,
            params={
                "roles": "equal_weight,cap_weight",
                "market_benchmark": "SPY",
            },
        )
        assert batch_response.status_code == 200, batch_response.text
        batch_payload = batch_response.json()
        assert batch_payload["universe_provenance"]["requested_roles"] == [
            "equal_weight",
            "cap_weight",
        ]
        assert {(item["role"], item["benchmark_role"]) for item in batch_payload["ratios"]} == {
            ("equal_weight", "cap_weight"),
            ("equal_weight", "market"),
            ("cap_weight", "market"),
        }

    def test_benchmark_family_technicals_return_independent_role_states_without_fallback(
        self, client, auth_headers, db, instrument_type
    ):
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal

        from app.models.instrument import Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(spy)
        db.flush()
        base = datetime(2026, 6, 25, tzinfo=UTC)
        for index, close in enumerate((100, 101, 102)):
            timestamp = base + timedelta(days=index)
            value = Decimal(str(close))
            db.add(
                OHLCVBar(
                    instrument_id=spy.id,
                    timeframe=Timeframe.D1,
                    ts=timestamp,
                    open=value,
                    high=value,
                    low=value,
                    close=value,
                    volume=Decimal("1"),
                    is_adjusted=True,
                )
            )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/technicals",
            headers=auth_headers,
            params={"as_of": "2026-12-31T23:59:59Z"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        roles = {role["role"]: role for role in payload["roles"]}
        assert roles["cap_weight"]["symbol"] == "SPY"
        assert roles["cap_weight"]["available"] is True
        assert roles["cap_weight"]["last"] == 102
        assert roles["cap_weight"]["as_of"] == "2026-12-31T23:59:59Z"
        assert roles["cap_weight"]["sma200"] is None
        assert roles["equal_weight"]["symbol"] == "RSP"
        assert roles["equal_weight"]["available"] is False
        assert roles["equal_weight"]["warnings"][0]["code"] == "benchmark_proxy_unavailable"
        assert payload["universe_provenance"]["technical_semantics"] == (
            "role_independent_local_ohlcv_snapshot"
        )
        assert payload["freshness"] == "current"

    def test_benchmark_family_breadth_batches_role_participation_without_fallback(
        self, client, auth_headers, db, instrument, instrument_type, ohlcv_bars
    ):
        from datetime import UTC, datetime
        from decimal import Decimal

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        rsp = Instrument(
            symbol="RSP",
            name="Invesco S&P 500 Equal Weight ETF",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(rsp)
        db.flush()
        profile = ETFProfile(instrument_id=rsp.id, adapter_status="resolved")
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2024, 6, 28, tzinfo=UTC).date(),
            known_at=datetime(2024, 6, 29, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="fixture",
            source_quality="issuer_disclosed",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            total_weight=Decimal("1"),
            snapshot_hash="test-family-breadth-rsp",
        )
        db.add(snapshot)
        db.flush()
        db.add(
            ETFHolding(
                snapshot_id=snapshot.id,
                constituent_instrument_id=instrument.id,
                position=0,
                reported_symbol=instrument.symbol,
                reported_name=instrument.name,
                weight=Decimal("1"),
                source_row_hash="test-family-breadth-aapl",
                is_resolved=True,
            )
        )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/breadth",
            headers=auth_headers,
            params={"near_threshold": "0.02", "new_high_lookback": "20"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        roles = {role["role"]: role for role in payload["roles"]}
        assert roles["cap_weight"]["available"] is False
        assert roles["equal_weight"]["available"] is True
        assert roles["equal_weight"]["symbol"] == "RSP"
        assert roles["equal_weight"]["above_ma"]["ma20"]["requested_count"] == 1
        assert roles["equal_weight"]["above_ma"]["ma20"]["eligible_count"] == 1
        assert roles["equal_weight"]["near_52w_high"]["percentage"] is None
        assert payload["near_threshold"] == 0.02
        assert payload["universe_provenance"]["breadth_semantics"] == (
            "standard_role_participation_batch_over_point_in_time_holdings"
        )

    def test_benchmark_family_breadth_history_keeps_role_lineage_and_missing_roles_explicit(
        self, client, auth_headers, db, instrument, instrument_type, ohlcv_bars
    ):
        from datetime import UTC, datetime
        from decimal import Decimal

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        rsp = Instrument(
            symbol="RSP",
            name="Invesco S&P 500 Equal Weight ETF",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(rsp)
        db.flush()
        profile = ETFProfile(instrument_id=rsp.id, adapter_status="resolved")
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2024, 6, 28, tzinfo=UTC).date(),
            known_at=datetime(2024, 6, 29, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="fixture",
            source_quality="issuer_disclosed",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            total_weight=Decimal("1"),
            snapshot_hash="test-family-breadth-history-rsp",
        )
        db.add(snapshot)
        db.flush()
        db.add(
            ETFHolding(
                snapshot_id=snapshot.id,
                constituent_instrument_id=instrument.id,
                position=0,
                reported_symbol=instrument.symbol,
                reported_name=instrument.name,
                weight=Decimal("1"),
                source_row_hash="test-family-breadth-history-aapl",
                is_resolved=True,
            )
        )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/breadth/history",
            headers=auth_headers,
            params={"limit": 30},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        roles = {role["role"]: role for role in payload["roles"]}
        assert roles["cap_weight"]["available"] is False
        assert roles["cap_weight"]["exclusions"][0]["code"] == "instrument_not_found"
        assert roles["equal_weight"]["available"] is True
        assert roles["equal_weight"]["membership_version"] is not None
        assert len(roles["equal_weight"]["points"]) == 30
        assert set(roles["equal_weight"]["points"][-1]["above_ma"]) == {
            "ma20",
            "ma50",
            "ma200",
        }
        assert payload["limit"] == 30

    def test_benchmark_family_ranking_preserves_cap_relative_role_performance(
        self, client, auth_headers, db, instrument_type
    ):
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal

        from app.models.instrument import Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        symbols = ("SPY", "RSP")
        instruments = {}
        for symbol in symbols:
            item = Instrument(
                symbol=symbol,
                name=symbol,
                currency="USD",
                instrument_type_id=instrument_type.id,
                is_active=True,
            )
            db.add(item)
            db.flush()
            instruments[symbol] = item
        base = datetime(2024, 1, 1, tzinfo=UTC)
        for index in range(30):
            for symbol, value in (("SPY", 100 + index), ("RSP", 100 + (2 * index))):
                close = Decimal(str(value))
                db.add(
                    OHLCVBar(
                        instrument_id=instruments[symbol].id,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=index),
                        open=close,
                        high=close,
                        low=close,
                        close=close,
                        volume=Decimal("1"),
                        is_adjusted=True,
                    )
                )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/ranking",
            headers=auth_headers,
            params={"rank_period": "1M"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        roles = {role["role"]: role for role in payload["roles"]}
        assert roles["cap_weight"]["available"] is True
        assert roles["equal_weight"]["available"] is True
        assert roles["equal_weight"]["rank"] == 1
        assert roles["cap_weight"]["rank"] == 2
        assert roles["equal_weight"]["relative_performance"]["1M"] > 0
        assert roles["value"]["available"] is False
        assert payload["benchmark"] == "SPY"

    def test_cross_family_ranking_keeps_unavailable_cap_legs_explicit(
        self, client, auth_headers, db, instrument_type
    ):
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal

        from app.models.instrument import Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="SPY",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(spy)
        db.flush()
        base = datetime(2024, 1, 1, tzinfo=UTC)
        for index in range(30):
            close = Decimal(str(100 + index))
            db.add(
                OHLCVBar(
                    instrument_id=spy.id,
                    timeframe=Timeframe.D1,
                    ts=base + timedelta(days=index),
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=Decimal("1"),
                    is_adjusted=True,
                )
            )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/ranking",
            headers=auth_headers,
            params={"families": "sp500,sp400", "benchmark": "SPY", "rank_period": "1M"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        rows = {row["family_key"]: row for row in payload["rows"]}
        assert rows["sp500"]["available"] is True
        assert rows["sp500"]["rank"] == 1
        assert rows["sp500"]["relative_performance"]["1M"] == 0
        assert rows["sp400"]["available"] is False
        assert rows["sp400"]["warnings"][0]["code"] == "family_cap_unavailable"
        assert payload["benchmark"] == "SPY"

    def test_cross_family_ranking_history_preserves_point_in_time_rank_and_as_of(
        self, client, auth_headers, db, instrument_type
    ):
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal

        from app.models.instrument import Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        instruments = {}
        for symbol in ("SPY", "MDY"):
            instrument = Instrument(
                symbol=symbol,
                name=symbol,
                currency="USD",
                instrument_type_id=instrument_type.id,
                is_active=True,
            )
            db.add(instrument)
            db.flush()
            instruments[symbol] = instrument
        base = datetime(2024, 1, 1, tzinfo=UTC)
        for index in range(40):
            for symbol, value in (
                ("SPY", 100 + index),
                ("MDY", 100 + (2 * index)),
            ):
                close = Decimal(str(value))
                db.add(
                    OHLCVBar(
                        instrument_id=instruments[symbol].id,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=index),
                        open=close,
                        high=close,
                        low=close,
                        close=close,
                        volume=Decimal("1"),
                        is_adjusted=True,
                    )
                )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/ranking/history",
            headers=auth_headers,
            params={
                "families": "sp500,sp400",
                "benchmark": "SPY",
                "rank_period": "1M",
                "limit": 8,
                "as_of": (base + timedelta(days=35)).isoformat(),
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        rows = {row["family_key"]: row for row in payload["rows"]}
        assert payload["limit"] == 8
        assert payload["benchmark"] == "SPY"
        assert len(rows["sp500"]["points"]) == 8
        assert len(rows["sp400"]["points"]) == 8
        assert rows["sp400"]["points"][-1]["rank"] == 1
        assert rows["sp500"]["points"][-1]["rank"] == 2
        assert rows["sp500"]["points"][-1]["relative_performance"]["1M"] == 0
        observed = datetime.fromisoformat(
            rows["sp400"]["points"][-1]["timestamp"].replace("Z", "+00:00")
        )
        assert observed <= base + timedelta(days=35)

    def test_benchmark_family_relative_rotation_returns_role_tails_without_fallback(
        self, client, auth_headers, db, instrument_type
    ):
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal

        from app.models.instrument import Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        instruments = {}
        for symbol in ("SPY", "RSP"):
            instrument = Instrument(
                symbol=symbol,
                name=symbol,
                currency="USD",
                instrument_type_id=instrument_type.id,
                is_active=True,
            )
            db.add(instrument)
            db.flush()
            instruments[symbol] = instrument
        base = datetime(2024, 1, 1, tzinfo=UTC)
        for index in range(35):
            for symbol, value in (
                ("SPY", 100 + index),
                ("RSP", 100 + (2 * index)),
            ):
                close = Decimal(str(value))
                db.add(
                    OHLCVBar(
                        instrument_id=instruments[symbol].id,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=index),
                        open=close,
                        high=close,
                        low=close,
                        close=close,
                        volume=Decimal("1"),
                        is_adjusted=True,
                    )
                )
        db.flush()

        response = client.get(
            "/api/v1/analysis/benchmark-families/sp500/relative-rotation",
            headers=auth_headers,
            params={"lookback": 5, "tail_length": 3, "history_length": 7},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        roles = {role["role"]: role for role in payload["roles"]}
        assert payload["benchmark"] == "SPY"
        assert roles["cap_weight"]["available"] is True
        assert roles["cap_weight"]["tail"][-1]["trend"] == 0
        assert roles["equal_weight"]["available"] is True
        assert len(roles["equal_weight"]["tail"]) == 3
        assert payload["history_length"] == 7
        assert len(roles["equal_weight"]["history"]) == 7
        assert roles["equal_weight"]["trend"] > 0
        assert roles["equal_weight"]["state"] in {"leading", "weakening"}
        assert roles["value"]["available"] is False
        assert roles["value"]["warnings"][0]["code"] == "role_mapping_unavailable"

    def test_benchmark_family_derived_equal_weight_requires_constituent_membership(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        from datetime import UTC, datetime

        from sqlalchemy import select

        from app.models.workstation import MarketGroup, MarketGroupMember

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        family = db.execute(
            select(MarketGroup).where(MarketGroup.stable_key == "sp1500")
        ).scalar_one()
        db.add(
            MarketGroupMember(
                market_group_id=family.id,
                instrument_id=instrument.id,
                relationship_type="etf_proxy_constituent",
                position=0,
                source="controlled_fixture",
                verification_state="proxy_verified",
                effective_at=datetime(2024, 1, 1, tzinfo=UTC),
                known_at=datetime(2024, 1, 2, tzinfo=UTC),
                provenance={"membership_semantics": "etf_proxy_membership"},
            )
        )
        db.flush()
        available = client.get(
            "/api/v1/analysis/benchmark-families/sp1500/derived-equal-weight",
            headers=auth_headers,
        )
        assert available.status_code == 200, available.text
        available_payload = available.json()
        assert available_payload["member_count"] == 1
        assert available_payload["covered_member_count"] == 1
        assert available_payload["coverage"] == 1
        assert len(available_payload["points"]) == len(ohlcv_bars)
        assert available_payload["universe_provenance"]["membership_semantics"] == (
            "point_in_time_constituent_derived_equal_weight"
        )
        historical = client.get(
            "/api/v1/analysis/benchmark-families/sp1500/derived-equal-weight",
            headers=auth_headers,
            params={"as_of": "2024-01-03T00:00:00Z"},
        )
        assert historical.status_code == 200, historical.text
        assert historical.json()["member_count"] == 1
        assert historical.json()["universe_provenance"]["membership_as_of"].startswith("2024-01-03")

        unavailable = client.get(
            "/api/v1/analysis/benchmark-families/sp400/derived-equal-weight",
            headers=auth_headers,
        )
        assert unavailable.status_code == 200, unavailable.text
        payload = unavailable.json()
        assert payload["family_key"] == "sp400"
        assert payload["member_count"] == 0
        assert payload["points"] == []
        assert payload["exclusions"][0]["code"] == "derived_equal_membership_unavailable"

        not_allowed = client.get(
            "/api/v1/analysis/benchmark-families/nasdaq100/derived-equal-weight",
            headers=auth_headers,
        )
        assert not_allowed.status_code == 422
        assert not_allowed.json()["detail"]["code"] == "derived_equal_weight_not_allowed"

    def test_etf_industries_are_derived_from_point_in_time_holdings(
        self, client, admin_headers, auth_headers, db, instrument
    ):
        from app.models.instrument import EquityDetail

        db.add(
            EquityDetail(
                instrument_id=instrument.id,
                sector="Technology",
                industry="Semiconductors",
                field_provenance={
                    "sector": {
                        "classification_system": "provider_native",
                        "observed_at": "2026-06-30T00:00:00+00:00",
                    },
                    "industry": {
                        "classification_system": "provider_native",
                        "observed_at": "2026-06-30T00:00:00+00:00",
                    },
                },
            )
        )
        db.flush()
        ingested = client.post(
            "/api/v1/etf-holdings/INDX/ingest",
            headers=admin_headers,
            json={
                "composition_date": "2026-07-01",
                "source_provider": "manual-test",
                "rows": [
                    {
                        "symbol": instrument.symbol,
                        "name": instrument.name,
                        "weight": "0.05000000",
                        "currency": "USD",
                        "holding_type": "equity",
                        "row_type": "security",
                    }
                ],
            },
        )
        assert ingested.status_code == 200

        response = client.get("/api/v1/market-groups/etf/INDX/industries", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["composition_date"] == "2026-07-01"
        assert payload["industries"] == [
            {
                "industry": "Semiconductors",
                "constituent_count": 1,
                "resolved_count": 1,
                "classification_systems": ["provider_native"],
            }
        ]
        assert payload["classification_systems"] == ["provider_native"]
        assert payload["classification_coverage"] == 1
        constituents = client.get(
            "/api/v1/market-groups/etf/INDX/industries/Semiconductors",
            headers=auth_headers,
        )
        assert constituents.status_code == 200
        assert [item["id"] for item in constituents.json()["constituents"]] == [instrument.id]
        assert constituents.json()["classification_systems"] == ["provider_native"]
        assert constituents.json()["classification_coverage"] == 1

    def test_etf_industry_exclusions_are_explicit_for_cash_derivative_and_unresolved_rows(
        self, client, admin_headers, auth_headers, db, instrument, instrument_b
    ):
        from datetime import UTC, date, datetime

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import EquityDetail, Instrument

        detail = EquityDetail(
            instrument_id=instrument.id,
            industry="Semiconductors",
            field_provenance={"industry": {"classification_system": "provider_native"}},
        )
        sector_only_detail = EquityDetail(
            instrument_id=instrument_b.id,
            sector="Information Technology",
            field_provenance={"sector": {"classification_system": "provider_native"}},
        )
        db.add_all([detail, sector_only_detail])
        cash = Instrument(
            symbol="CASH-TEST",
            name="Cash",
            currency="USD",
            instrument_type_id=instrument.instrument_type_id,
            is_active=True,
        )
        derivative = Instrument(
            symbol="DERIV-TEST",
            name="Future contract",
            currency="USD",
            instrument_type_id=instrument.instrument_type_id,
            is_active=True,
        )
        db.add_all([cash, derivative])
        db.flush()
        profile = ETFProfile(instrument_id=instrument.id)
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=date(2026, 8, 12),
            known_at=datetime(2026, 8, 13, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="manual-test",
            completeness_status="partial",
            row_count=4,
            resolved_count=3,
            unresolved_count=1,
            snapshot_hash="explicit-exclusions",
        )
        db.add(snapshot)
        db.flush()
        db.add_all(
            [
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=instrument.id,
                    position=0,
                    source_row_hash="equity-row",
                    is_resolved=True,
                    holding_type="equity",
                    row_type="security",
                ),
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=instrument_b.id,
                    position=1,
                    source_row_hash="unclassified-equity-row",
                    is_resolved=True,
                    holding_type="equity",
                    row_type="security",
                ),
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=cash.id,
                    position=2,
                    source_row_hash="cash-row",
                    is_resolved=True,
                    holding_type="cash",
                    row_type="cash",
                ),
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=derivative.id,
                    position=3,
                    source_row_hash="derivative-row",
                    is_resolved=True,
                    holding_type="derivative",
                    row_type="other",
                ),
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=None,
                    position=4,
                    source_row_hash="unresolved-row",
                    is_resolved=False,
                    holding_type="equity",
                    row_type="security",
                ),
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=None,
                    position=5,
                    source_row_hash="inconsistent-resolved-row",
                    is_resolved=True,
                    holding_type="equity",
                    row_type="security",
                ),
            ]
        )
        db.flush()
        response = client.get(
            f"/api/v1/market-groups/etf/{instrument.symbol}/industries",
            headers=auth_headers,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["classification_coverage"] == 0.5
        assert payload["exclusions"] == [
            "cash_holding",
            "derivative_holding",
            "unclassified_constituent",
            "unresolved_holding",
        ]
        constituents = client.get(
            f"/api/v1/market-groups/etf/{instrument.symbol}/industries/Semiconductors",
            headers=auth_headers,
        )
        assert constituents.status_code == 200
        assert [item["id"] for item in constituents.json()["constituents"]] == [instrument.id]
        assert constituents.json()["classification_coverage"] == 0.5
        assert constituents.json()["exclusions"] == payload["exclusions"]

    def test_relative_strength_uses_only_aligned_local_bars(
        self, client, auth_headers, db, instrument, instrument_b, ohlcv_bars
    ):
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal

        from app.models.ohlcv import OHLCVBar, Timeframe

        base = datetime(2024, 1, 1, tzinfo=UTC)
        for index in range(150):
            if index == 42:
                continue
            price = Decimal(str(100 + index))
            db.add(
                OHLCVBar(
                    instrument_id=instrument_b.id,
                    timeframe=Timeframe.D1,
                    ts=base + timedelta(days=index),
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=Decimal("1"),
                    is_adjusted=True,
                )
            )
        db.flush()
        response = client.get(
            "/api/v1/analysis/relative-strength",
            headers=auth_headers,
            params={"symbol": instrument.symbol, "benchmark": instrument_b.symbol},
        )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["points"]) == 149
        assert payload["coverage"] < 1
        assert payload["warnings"][0]["code"] == "partial_overlap"

    def test_relative_strength_applies_point_in_time_cutoff(
        self, client, auth_headers, db, instrument, instrument_b, ohlcv_bars
    ):
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal

        from app.models.ohlcv import OHLCVBar, Timeframe

        base = datetime(2025, 1, 1, tzinfo=UTC)
        for index in range(4):
            value = Decimal(str(100 + index))
            for current in (instrument.id, instrument_b.id):
                db.add(
                    OHLCVBar(
                        instrument_id=current,
                        timeframe=Timeframe.D1,
                        ts=base + timedelta(days=index),
                        open=value,
                        high=value,
                        low=value,
                        close=value,
                        volume=Decimal("1"),
                        is_adjusted=True,
                    )
                )
        db.flush()
        response = client.get(
            "/api/v1/analysis/relative-strength",
            headers=auth_headers,
            params={
                "symbol": instrument.symbol,
                "benchmark": instrument_b.symbol,
                "as_of": "2025-01-02T23:59:59Z",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["as_of"] == "2025-01-02T23:59:59Z"
        assert len(payload["points"]) == 2

    def test_analysis_freshness_matches_adjusted_dataset_state(
        self, client, auth_headers, db, instrument, instrument_b, ohlcv_bars
    ):
        """Analysis must not report unavailable when adjusted bars are fresh locally."""
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal

        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.provider_observation import DatasetStatus, InstrumentDatasetState

        timestamp = datetime(2026, 1, 2, tzinfo=UTC)
        db.add(
            OHLCVBar(
                instrument_id=instrument_b.id,
                timeframe=Timeframe.D1,
                ts=timestamp,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=Decimal("1"),
                is_adjusted=True,
            )
        )
        for current in (instrument, instrument_b):
            db.add(
                InstrumentDatasetState(
                    instrument_id=current.id,
                    data_source_id=None,
                    dataset_type="ohlcv",
                    dataset_key="D1:adj",
                    status=DatasetStatus.FRESH,
                    observed_at=timestamp,
                    fetched_at=timestamp,
                    stale_after=datetime.now(UTC) + timedelta(days=1),
                )
            )
        db.flush()

        response = client.get(
            "/api/v1/analysis/relative-strength",
            headers=auth_headers,
            params={"symbol": instrument.symbol, "benchmark": instrument_b.symbol},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["freshness"] == "current"
        assert payload["freshness_detail"] == {
            "requested": 2,
            "current": 2,
            "stale": 0,
            "other": 0,
        }

    def test_local_chart_route_never_needs_provider_fetch(
        self, client, auth_headers, instrument, ohlcv_bars
    ):
        response = client.get(f"/api/v1/ohlcv/local/{instrument.symbol}/D1", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()) == len(ohlcv_bars)

    def test_technical_snapshot_uses_only_local_adjusted_bars(
        self, client, auth_headers, db, instrument
    ):
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal

        from app.models.ohlcv import OHLCVBar, Timeframe

        start = datetime(2025, 1, 1, tzinfo=UTC)
        for index in range(252):
            close = Decimal(100 + index)
            db.add(
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=start + timedelta(days=index),
                    open=close,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=Decimal(1000 + index),
                    is_adjusted=True,
                )
            )
        db.flush()
        response = client.get(
            f"/api/v1/analysis/instruments/{instrument.symbol}/technical",
            headers=auth_headers,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["last"] == 351
        assert payload["rsi14"] == 100
        assert payload["sma20"] == 341.5
        assert payload["sma50"] == 326.5
        assert payload["sma200"] == 251.5
        assert payload["position_52w"] == 1
        assert payload["volume_ratio_50"] > 1

    def test_indicator_batch_returns_local_latest_values_and_exclusions(
        self, client, auth_headers, instrument, ohlcv_bars
    ):
        response = client.post(
            "/api/v1/analysis/indicator-batch",
            headers=auth_headers,
            json={
                "symbols": [instrument.symbol, "UNKNOWN"],
                "indicator": "sma",
                "params": {"period": 2},
                "timeframe": "D1",
                "adjusted": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["data_provenance"] == "canonical_local_database"
        assert payload["universe_provenance"] == {"type": "explicit_symbols", "symbol_count": 2}
        assert payload["requested_count"] == 2
        assert payload["evaluated_count"] == 1
        assert payload["coverage"] == 0.5
        assert payload["values"][instrument.symbol]["value"] is not None
        assert payload["values"][instrument.symbol]["warning"] is None
        assert payload["values"]["UNKNOWN"]["warning"]["code"] == "instrument_not_found"
        assert any(item["code"] == "instrument_not_found" for item in payload["exclusions"])

    def test_group_snapshot_exposes_bounded_calendar_year_returns(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        from datetime import UTC, datetime
        from decimal import Decimal

        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.workstation import MarketGroup, MarketGroupMember

        for year, first_close, last_close in (
            (2025, "100", "125"),
            (2026, "200", "220"),
        ):
            for month, close in ((1, first_close), (12, last_close)):
                price = Decimal(close)
                db.add(
                    OHLCVBar(
                        instrument_id=instrument.id,
                        timeframe=Timeframe.D1,
                        ts=datetime(year, month, 2, tzinfo=UTC),
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        volume=Decimal("100"),
                        is_adjusted=True,
                    )
                )
        group = MarketGroup(
            stable_key="calendar-year-test", group_type="test", name="Calendar year test"
        )
        db.add(group)
        db.flush()
        db.add(MarketGroupMember(market_group_id=group.id, instrument_id=instrument.id, position=0))
        db.flush()

        response = client.get(
            "/api/v1/analysis/groups/calendar-year-test/snapshot", headers=auth_headers
        )
        assert response.status_code == 200
        cells = response.json()["rows"][0]["calendar_year_performance"]
        assert list(cells) == ["2022", "2023", "2024", "2025", "2026"]
        assert cells["2025"]["value"] == 0.25
        assert cells["2026"]["value"] == 0.1
        assert cells["2023"]["value"] is None
        assert cells["2023"]["warning"]["code"] == "no_calendar_year_bars"

    def test_historical_breadth_uses_only_each_constituents_available_bar_dates(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        from app.models.workstation import MarketGroup, MarketGroupMember

        group = MarketGroup(
            stable_key="breadth-history-test", group_type="test", name="Breadth test"
        )
        db.add(group)
        db.flush()
        db.add(MarketGroupMember(market_group_id=group.id, instrument_id=instrument.id, position=0))
        db.flush()

        response = client.get(
            "/api/v1/analysis/groups/breadth-history-test/breadth/history",
            headers=auth_headers,
            params={"limit": 10},
        )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["points"]) == 10
        assert payload["points"][0]["above_ma"]["ma20"] is not None
        assert payload["points"][-1]["above_ma"]["ma200"] is None
        assert payload["points"][-1]["coverage"]["ma20"] == 1
        assert payload["points"][-1]["coverage"]["ma200"] == 0

        rotation = client.get(
            "/api/v1/analysis/groups/breadth-history-test/relative-rotation",
            headers=auth_headers,
            params={
                "benchmark": instrument.symbol,
                "sampling": 2,
                "lookback": 20,
                "tail_length": 3,
                "history_length": 8,
            },
        )
        assert rotation.status_code == 200
        row = rotation.json()["rows"][0]
        assert rotation.json()["sampling"] == 2
        assert row["heading"] is not None
        assert row["distance"] is not None
        assert row["time_in_state"] >= 1
        assert row["state"] == "leading"
        assert len(row["tail"]) == 3
        assert rotation.json()["history_length"] == 8
        assert len(row["history"]) == 8
        assert row["coverage"] == 1

        extended = client.get(
            "/api/v1/analysis/groups/breadth-history-test/relative-rotation",
            headers=auth_headers,
            params={
                "benchmark": instrument.symbol,
                "lookback": 20,
                "tail_length": 3,
                "history_length": 1001,
            },
        )
        assert extended.status_code == 200
        assert extended.json()["history_length"] == 1001

    def test_relative_rotation_respects_point_in_time_membership_and_bars(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        from datetime import UTC, datetime

        from app.models.workstation import MarketGroup, MarketGroupMember

        group = MarketGroup(
            stable_key="point-in-time-rotation-test",
            group_type="test",
            name="Point-in-time rotation",
        )
        db.add(group)
        db.flush()
        db.add(
            MarketGroupMember(
                market_group_id=group.id,
                instrument_id=instrument.id,
                position=0,
                effective_at=datetime(2024, 3, 15, tzinfo=UTC),
                known_at=datetime(2024, 3, 20, tzinfo=UTC),
            )
        )
        db.flush()

        before_membership = client.get(
            "/api/v1/analysis/groups/point-in-time-rotation-test/relative-rotation",
            headers=auth_headers,
            params={
                "benchmark": instrument.symbol,
                "as_of": "2024-03-10T23:59:59Z",
                "lookback": 20,
                "tail_length": 3,
            },
        )
        assert before_membership.status_code == 200
        assert before_membership.json()["rows"] == []

        after_membership = client.get(
            "/api/v1/analysis/groups/point-in-time-rotation-test/relative-rotation",
            headers=auth_headers,
            params={
                "benchmark": instrument.symbol,
                "as_of": "2024-04-30T23:59:59Z",
                "lookback": 20,
                "tail_length": 3,
            },
        )
        assert after_membership.status_code == 200
        payload = after_membership.json()
        assert payload["as_of"] == "2024-04-30T23:59:59Z"
        assert payload["universe_provenance"]["membership_selection"] == (
            "effective_at_and_known_at"
        )
        assert payload["rows"]
        assert all(
            point["timestamp"] <= "2024-04-30T23:59:59Z" for point in payload["rows"][0]["tail"]
        )

    def test_group_snapshot_and_breadth_apply_the_same_point_in_time_cutoff(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        from datetime import UTC, datetime

        from app.models.workstation import MarketGroup, MarketGroupMember

        group = MarketGroup(
            stable_key="point-in-time-batch-test", group_type="test", name="Point-in-time batch"
        )
        db.add(group)
        db.flush()
        db.add(
            MarketGroupMember(
                market_group_id=group.id,
                instrument_id=instrument.id,
                position=0,
                effective_at=datetime(2024, 3, 15, tzinfo=UTC),
                known_at=datetime(2024, 3, 20, tzinfo=UTC),
            )
        )
        db.flush()

        before = client.get(
            "/api/v1/analysis/groups/point-in-time-batch-test/snapshot",
            headers=auth_headers,
            params={"as_of": "2024-03-10T23:59:59Z"},
        )
        assert before.status_code == 200
        assert before.json()["rows"] == []

        params = {"as_of": "2024-03-31T23:59:59Z"}
        snapshot = client.get(
            "/api/v1/analysis/groups/point-in-time-batch-test/snapshot",
            headers=auth_headers,
            params=params,
        )
        assert snapshot.status_code == 200
        snapshot_payload = snapshot.json()
        assert snapshot_payload["rows"]
        assert snapshot_payload["coverage"] == 1
        assert snapshot_payload["universe_provenance"]["membership_as_of"] == params["as_of"]
        assert snapshot_payload["rows"][0]["last"]["observation_time"] <= params["as_of"]

        breadth = client.get(
            "/api/v1/analysis/groups/point-in-time-batch-test/breadth",
            headers=auth_headers,
            params={**params, "new_high_lookback": 10, "near_threshold": 0.1},
        )
        assert breadth.status_code == 200
        breadth_payload = breadth.json()
        assert breadth_payload["evaluated_count"] == 1
        assert breadth_payload["universe_provenance"]["membership_as_of"] == params["as_of"]
        assert breadth_payload["new_high_lookback"] == 10
        assert breadth_payload["near_threshold"] == 0.1
        assert set(breadth_payload["near_52w"]) == {"high", "low"}
        assert set(breadth_payload["trend"]) == {"uptrend", "downtrend"}
        assert {
            "ma20",
            "ma50",
            "ma200",
            "near_52w",
            "new_high_low",
            "trend",
            "distance_ma20",
            "distance_ma50",
            "distance_ma200",
        } <= set(breadth_payload["coverage_detail"])
        member_metrics = breadth_payload["member_metrics"]
        assert member_metrics
        assert {
            "above_ma20",
            "above_ma50",
            "above_ma200",
            "near_52w_high",
            "near_52w_low",
            "new_high",
            "new_low",
            "uptrend",
            "downtrend",
        } <= set(next(iter(member_metrics.values())))

        history = client.get(
            "/api/v1/analysis/groups/point-in-time-batch-test/breadth/history",
            headers=auth_headers,
            params={**params, "limit": 50},
        )
        assert history.status_code == 200
        assert all(point["timestamp"] <= params["as_of"] for point in history.json()["points"])

    def test_generic_breadth_accepts_a_reusable_condition_and_explicit_symbols(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        from app.models.workstation import MarketGroup, MarketGroupMember

        group = MarketGroup(
            stable_key="generic-breadth-test", group_type="test", name="Generic breadth"
        )
        db.add(group)
        db.flush()
        db.add(MarketGroupMember(market_group_id=group.id, instrument_id=instrument.id, position=0))
        db.flush()

        response = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "version": 1,
                "universe": {"kind": "group", "key": group.stable_key},
                "condition": {
                    "kind": "above_moving_average",
                    "params": {"period": 20, "average": "sma", "comparator": "above"},
                },
                "timeframe": "D1",
                "adjusted": True,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["definition_version"] == 1
        assert len(payload["definition_hash"]) == 64
        assert payload["universe"]["membership_semantics"] == "curated_group_members"
        assert payload["requested_count"] == 1
        assert payload["eligible_count"] == 1
        assert payload["coverage"] == 1
        assert payload["members"][0]["symbol"] == instrument.symbol
        assert payload["members"][0]["value"] in {True, False}

        saved_condition = client.put(
            "/api/v1/workspaces/library/conditions/breadth-sma",
            headers=auth_headers,
            json={
                "name": "Breadth above SMA",
                "condition": {
                    "operator": "AND",
                    "conditions": [
                        {
                            "type": "price_indicator",
                            "field": "close",
                            "indicator": "sma",
                            "params": {"period": 20},
                            "op": "gt",
                        }
                    ],
                },
            },
        )
        assert saved_condition.status_code == 200
        saved_python_version = saved_condition.json()["payload"]["python_code_version_id"]
        saved = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "condition_asset_key": "breadth-sma",
            },
        )
        assert saved.status_code == 200
        saved_payload = saved.json()
        assert saved_payload["condition_asset_key"] == "breadth-sma"
        assert saved_payload["condition_library_version"] == 1
        assert saved_payload["python_code_version_id"] == saved_python_version
        assert saved_payload["condition"]["kind"] == "all"
        assert saved_payload["condition"]["params"]["conditions"][0]["kind"] == (
            "above_moving_average"
        )

        explicit = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "universe": {
                    "kind": "symbols",
                    "symbols": [instrument.symbol, "MISSING"],
                },
                "condition": {"kind": "above_moving_average", "params": {"period": 20}},
            },
        )
        assert explicit.status_code == 200
        explicit_payload = explicit.json()
        assert explicit_payload["requested_count"] == 2
        assert explicit_payload["excluded_count"] == 1
        assert explicit_payload["coverage"] == 0.5
        assert any(
            item["code"] == "instrument_not_found" for item in explicit_payload["exclusions"]
        )

        composite = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "condition": {
                    "kind": "all",
                    "params": {
                        "conditions": [
                            {
                                "kind": "comparison",
                                "params": {"field": "return", "operator": ">", "threshold": -1},
                            },
                            {
                                "kind": "not",
                                "params": {
                                    "conditions": [
                                        {
                                            "kind": "comparison",
                                            "params": {
                                                "field": "close",
                                                "operator": "<",
                                                "threshold": 0,
                                            },
                                        }
                                    ]
                                },
                            },
                        ]
                    },
                },
            },
        )
        assert composite.status_code == 200
        composite_payload = composite.json()
        assert composite_payload["eligible_count"] == 1
        assert composite_payload["members"][0]["value"] is True
        assert [item["path"] for item in composite_payload["members"][0]["diagnostics"]] == [
            "$",
            "$.conditions[0]",
            "$.conditions[1]",
            "$.conditions[1].conditions[0]",
        ]
        assert composite_payload["members"][0]["diagnostics"][0]["status"] == "pass"

        bounded = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "condition": {
                    "kind": "range",
                    "params": {"field": "return", "lower": -1, "upper": 1},
                },
            },
        )
        assert bounded.status_code == 200
        bounded_payload = bounded.json()
        assert bounded_payload["condition"]["kind"] == "range"
        assert bounded_payload["eligible_count"] == 1

        prior_extreme = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "condition": {
                    "kind": "prior_high_low",
                    "params": {
                        "direction": "high",
                        "lookback": 20,
                        "operator": ">=",
                        "threshold": -1,
                    },
                },
            },
        )
        assert prior_extreme.status_code == 200
        prior_extreme_payload = prior_extreme.json()
        assert prior_extreme_payload["condition"]["kind"] == "prior_high_low"
        assert prior_extreme_payload["members"][0]["diagnostics"][0]["kind"] == "prior_high_low"

        percentile = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "condition": {
                    "kind": "percentile",
                    "params": {
                        "field": "close",
                        "period": 20,
                        "percentile": 0.5,
                        "operator": ">=",
                    },
                },
            },
        )
        assert percentile.status_code == 200
        percentile_payload = percentile.json()
        assert percentile_payload["condition"]["kind"] == "percentile"
        assert percentile_payload["eligible_count"] == 1

        cross_sectional = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "condition": {
                    "kind": "percentile",
                    "target_scope": "cross_sectional",
                    "params": {
                        "field": "close",
                        "percentile": 0.5,
                        "operator": ">=",
                    },
                },
            },
        )
        assert cross_sectional.status_code == 200
        cross_payload = cross_sectional.json()
        assert cross_payload["condition"]["target_scope"] == "cross_sectional"
        assert cross_payload["eligible_count"] == 1
        assert cross_payload["members"][0]["metric"] == 1.0

        series_comparison = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "benchmark": instrument.symbol,
                "condition": {
                    "kind": "series_comparison",
                    "params": {
                        "field": "return",
                        "target_field": "return",
                        "relation": "difference",
                        "operator": ">=",
                        "threshold": 0,
                    },
                },
            },
        )
        assert series_comparison.status_code == 200
        series_payload = series_comparison.json()
        assert series_payload["condition"]["kind"] == "series_comparison"
        assert series_payload["condition"]["reference_symbol"] == instrument.symbol
        assert series_payload["members"][0]["value"] is True
        series_history = client.post(
            "/api/v1/analysis/breadth/history",
            headers=auth_headers,
            json={
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "benchmark": instrument.symbol,
                "condition": {
                    "kind": "series_comparison",
                    "params": {
                        "field": "return",
                        "target_field": "return",
                        "operator": ">=",
                        "threshold": 0,
                    },
                },
                "limit": 20,
            },
        )
        assert series_history.status_code == 200
        assert series_history.json()["condition"]["reference_symbol"] == instrument.symbol
        assert series_history.json()["points"]

        reference_group = MarketGroup(
            stable_key="generic-breadth-reference-group",
            group_type="test",
            name="Generic breadth reference group",
        )
        db.add(reference_group)
        db.flush()
        db.add(
            MarketGroupMember(
                market_group_id=reference_group.id,
                instrument_id=instrument.id,
                position=0,
            )
        )
        db.flush()
        group_reference = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "reference_universe": {
                    "kind": "group",
                    "key": reference_group.stable_key,
                    "point_in_time": True,
                },
                "condition": {
                    "kind": "series_comparison",
                    "params": {
                        "field": "return",
                        "target_field": "return",
                        "relation": "difference",
                        "operator": ">=",
                        "threshold": 0,
                    },
                },
                "limit": 20,
            },
        )
        assert group_reference.status_code == 200, group_reference.text
        group_reference_payload = group_reference.json()
        assert (
            group_reference_payload["condition"]["reference_universe"]["key"]
            == reference_group.stable_key
        )
        assert (
            group_reference_payload["condition"]["reference_target"]["method"]
            == "derived_equal_weight_return_index"
        )
        assert (
            group_reference_payload["condition"]["reference_target"]["alignment"]
            == "exact_timestamp_no_forward_fill"
        )
        assert group_reference_payload["members"][0]["value"] is True
        group_reference_history = client.post(
            "/api/v1/analysis/breadth/history",
            headers=auth_headers,
            json={
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "reference_universe": {
                    "kind": "group",
                    "key": reference_group.stable_key,
                    "point_in_time": True,
                },
                "condition": {
                    "kind": "series_comparison",
                    "params": {
                        "field": "return",
                        "target_field": "return",
                        "operator": ">=",
                        "threshold": 0,
                    },
                },
                "limit": 20,
            },
        )
        assert group_reference_history.status_code == 200, group_reference_history.text
        history_payload = group_reference_history.json()
        assert history_payload["condition"]["reference_target"]["member_count"] == 1
        assert history_payload["points"]

        from app.models.instrument_event import (
            InstrumentEvent,
            InstrumentEventFetchState,
            InstrumentEventType,
        )

        event_time = ohlcv_bars[-1].ts
        db.add(
            InstrumentEvent(
                instrument_id=instrument.id,
                event_type=InstrumentEventType.DIVIDEND,
                event_time=event_time,
                title="Test dividend",
                source="test",
                source_event_key="generic-breadth-event",
                fetched_at=event_time,
            )
        )
        db.add(
            InstrumentEventFetchState(
                instrument_id=instrument.id,
                source="test",
                fetched_at=event_time,
                event_count=1,
                earnings_count=0,
                fetch_version=2,
            )
        )
        db.flush()
        event_definition = {
            "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
            "condition": {
                "kind": "event",
                "params": {
                    "event_type": "dividend",
                    "lookback_days": 0,
                    "operator": ">=",
                    "threshold": 1,
                },
            },
        }
        event_current = client.post(
            "/api/v1/analysis/breadth", headers=auth_headers, json=event_definition
        )
        assert event_current.status_code == 200, event_current.text
        event_payload = event_current.json()
        assert event_payload["condition"]["kind"] == "event"
        assert event_payload["condition"]["event_target"]["loaded_member_count"] == 1
        assert event_payload["members"][0]["value"] is True
        event_history = client.post(
            "/api/v1/analysis/breadth/history",
            headers=auth_headers,
            json={**event_definition, "limit": 20},
        )
        assert event_history.status_code == 200, event_history.text
        event_history_payload = event_history.json()
        assert event_history_payload["condition"]["event_target"]["event_count"] == 1
        assert event_history_payload["points"]

    def test_generic_breadth_accepts_a_user_watchlist_source_without_provider_fanout(
        self, client, auth_headers, instrument, ohlcv_bars
    ):
        created = client.post(
            "/api/v1/watchlists",
            headers=auth_headers,
            json={"name": "Breadth watchlist source"},
        )
        assert created.status_code == 200
        watchlist_id = created.json()["id"]
        added = client.post(
            f"/api/v1/watchlists/{watchlist_id}/items",
            headers=auth_headers,
            json={"instrument_id": instrument.id},
        )
        assert added.status_code == 200

        response = client.post(
            "/api/v1/analysis/breadth",
            headers=auth_headers,
            json={
                "universe": {
                    "kind": "watchlist",
                    "key": f"watchlist:{watchlist_id}",
                    "point_in_time": True,
                },
                "condition": {"kind": "above_moving_average", "params": {"period": 20}},
                "timeframe": "D1",
                "adjusted": True,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["universe"]["kind"] == "watchlist"
        assert payload["universe"]["watchlist_id"] == watchlist_id
        assert payload["universe"]["membership_semantics"] == "user_watchlist_members"
        assert payload["requested_count"] == 1
        assert payload["members"][0]["instrument_id"] == instrument.id

    def test_generic_breadth_resolves_benchmark_family_style_leg_from_holdings_snapshot(
        self, client, auth_headers, db, instrument, instrument_type, ohlcv_bars
    ):
        from datetime import UTC, datetime

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument

        seeded = client.get("/api/v1/market-groups", headers=auth_headers)
        assert seeded.status_code == 200
        spy = Instrument(
            symbol="SPY",
            name="SPDR S&P 500 ETF Trust",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(spy)
        db.flush()
        profile = ETFProfile(instrument_id=spy.id, adapter_status="resolved")
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2024, 5, 30, tzinfo=UTC).date(),
            known_at=datetime(2024, 5, 31, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="issuer",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            snapshot_hash="test-family-breadth-spy-snapshot",
        )
        db.add(snapshot)
        db.flush()
        db.add(
            ETFHolding(
                snapshot_id=snapshot.id,
                constituent_instrument_id=instrument.id,
                position=0,
                reported_symbol=instrument.symbol,
                reported_name=instrument.name,
                source_row_hash="test-family-breadth-member",
                is_resolved=True,
            )
        )
        db.flush()

        body = {
            "version": 1,
            "universe": {
                "kind": "benchmark_family",
                "key": "sp500",
                "role": "cap_weight",
                "point_in_time": True,
            },
            "condition": {
                "kind": "above_moving_average",
                "params": {"period": 2, "average": "sma", "comparator": "above"},
            },
            "timeframe": "D1",
            "adjusted": True,
            "as_of": "2024-06-01T00:00:00Z",
        }
        response = client.post("/api/v1/analysis/breadth", headers=auth_headers, json=body)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["universe"]["kind"] == "benchmark_family"
        assert payload["universe"]["family_key"] == "sp500"
        assert payload["universe"]["role"] == "cap_weight"
        assert payload["universe"]["proxy_symbol"] == "SPY"
        assert payload["universe"]["membership_semantics"] == "etf_proxy_membership"
        assert payload["members"][0]["symbol"] == instrument.symbol

        sources = client.get("/api/v1/watchlists/sources", headers=auth_headers)
        assert sources.status_code == 200, sources.text
        family_source = next(
            item
            for item in sources.json()
            if item["source_id"] == "benchmark-family:sp500:cap_weight"
        )
        assert family_source["locked"] is True
        assert family_source["can_edit_membership"] is False
        assert family_source["member_count"] == 1
        assert family_source["provenance"]["membership_semantics"] == "etf_proxy_holdings"
        resolved = client.get(
            "/api/v1/watchlists/sources/benchmark-family:sp500:cap_weight",
            headers=auth_headers,
            params={"as_of": "2024-06-01T00:00:00Z"},
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["source"]["locked"] is True
        assert [member["instrument_id"] for member in resolved.json()["members"]] == [instrument.id]

        history = client.post(
            "/api/v1/analysis/breadth/history",
            headers=auth_headers,
            json={**body, "limit": 20},
        )
        assert history.status_code == 200, history.text
        history_payload = history.json()
        assert history_payload["universe"]["family_key"] == "sp500"
        assert history_payload["universe"]["proxy_symbol"] == "SPY"
        assert history_payload["points"]

    def test_generic_breadth_history_uses_the_same_condition_without_forward_fill(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        from app.models.workstation import MarketGroup, MarketGroupMember

        group = MarketGroup(
            stable_key="generic-breadth-history-test",
            group_type="test",
            name="Generic breadth history",
        )
        db.add(group)
        db.flush()
        db.add(MarketGroupMember(market_group_id=group.id, instrument_id=instrument.id, position=0))
        db.flush()

        saved_condition = client.put(
            "/api/v1/workspaces/library/conditions/breadth-history-sma",
            headers=auth_headers,
            json={
                "name": "Historical breadth above SMA",
                "condition": {
                    "type": "price_indicator",
                    "field": "close",
                    "indicator": "sma",
                    "params": {"period": 20},
                    "op": "gt",
                },
            },
        )
        assert saved_condition.status_code == 200
        saved_python_version = saved_condition.json()["payload"]["python_code_version_id"]

        response = client.post(
            "/api/v1/analysis/breadth/history",
            headers=auth_headers,
            json={
                "universe": {"kind": "group", "key": group.stable_key},
                "condition_asset_key": "breadth-history-sma",
                "timeframe": "D1",
                "limit": 20,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert len(payload["points"]) == 20
        assert payload["points"][-1]["eligible_count"] == 1
        assert payload["points"][-1]["coverage"] == 1
        assert payload["points"][-1]["members"][0]["value"] in {True, False}
        assert payload["points"][-1]["members"][0]["diagnostics"][0]["path"] == "$"
        assert payload["points"][-1]["members"][0]["diagnostics"][0]["status"] in {
            "pass",
            "fail",
            "excluded",
        }
        assert isinstance(payload["occurrences"], list)
        assert payload["definition_hash"]
        assert payload["condition_asset_key"] == "breadth-history-sma"
        assert payload["condition_library_version"] == 1
        assert payload["python_code_version_id"] == saved_python_version

    def test_python_breadth_queues_isolated_current_and_history_and_promotes_to_scan(
        self, client, auth_headers, instrument, ohlcv_bars, tmp_path, monkeypatch
    ):
        import json

        from research_runner.runner import execute_job

        monkeypatch.setattr(
            "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
        )
        monkeypatch.setattr(
            "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
        )
        source = (
            "condition = parameters['condition']\n"
            "snapshot = research.breadth_condition({'datasets': [dataset]}, condition)\n"
            "row = snapshot['rows'][0]\n"
            "output.boolean('match', row['value'] is True, metric=row['metric'], exclusion=row.get('exclusion'))"
        )
        asset_response = client.post(
            "/api/v1/code/assets",
            headers=auth_headers,
            json={
                "stable_key": "python-breadth-condition",
                "name": "Python breadth condition",
                "kind": "condition",
                "initial_version": {
                    "source": source,
                    "output_contract": "boolean",
                    "output_name": "match",
                },
            },
        )
        assert asset_response.status_code == 201
        version_id = asset_response.json()["versions"][0]["id"]

        promotion = client.post(
            f"/api/v1/screeners/from-python-condition/{version_id}",
            headers=auth_headers,
            json={"name": "Python breadth EasyScan"},
        )
        assert promotion.status_code == 201
        assert promotion.json()["conditions"] == {
            "type": "python_condition",
            "code_version_id": version_id,
        }

        for history in (False, True):
            queued = client.post(
                "/api/v1/analysis/breadth/python",
                headers=auth_headers,
                json={
                    "code_version_id": version_id,
                    "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                    "parameters": {
                        "condition": {"kind": "above_moving_average", "params": {"period": 2}}
                    },
                    "session": "all",
                    "history": history,
                    "history_limit": 20,
                },
            )
            assert queued.status_code == 202
            queued_payload = queued.json()
            assert queued_payload["execution_mode"] == (
                "breadth_history" if history else "breadth_current"
            )
            job_path = tmp_path / "jobs" / f"{queued_payload['run_id']}.json"
            job = json.loads(job_path.read_text())
            assert job["execution_mode"] == queued_payload["execution_mode"]
            result = execute_job(job)
            (tmp_path / "results").mkdir(exist_ok=True)
            (tmp_path / "results" / f"{queued_payload['run_id']}.json").write_text(
                json.dumps(result)
            )
            collected = client.get(
                f"/api/v1/analysis/breadth/python/runs/{queued_payload['run_id']}",
                headers=auth_headers,
            )
            assert collected.status_code == 200
            collected_payload = collected.json()
            assert collected_payload["status"] == "completed"
            assert collected_payload["code_version_id"] == version_id
            if history:
                assert collected_payload["points"], collected_payload
                assert collected_payload["current"] is not None
                research_detail = client.get(
                    f"/api/v1/research/runs/{queued_payload['run_id']}",
                    headers=auth_headers,
                )
                assert research_detail.status_code == 200
                history_artifact = next(
                    item
                    for item in research_detail.json()["artifacts"]
                    if item["artifact_type"] == "breadth_history"
                )
                assert (
                    history_artifact["payload"]["value"]["occurrences"]
                    == collected_payload["occurrences"]
                )
                promoted = client.post(
                    f"/api/v1/analysis/breadth/python/runs/{queued_payload['run_id']}/promote-scan",
                    headers=auth_headers,
                    json={"name": "Historical Python breadth scan"},
                )
                assert promoted.status_code == 201, promoted.text
                promoted_payload = promoted.json()
                assert promoted_payload["universe_type"] == "custom"
                assert promoted_payload["universe_instrument_ids"] == [instrument.id]
                assert promoted_payload["conditions"]["type"] == "python_condition"
                assert promoted_payload["conditions"]["code_version_id"] == version_id
                source = promoted_payload["conditions"]["provenance"]
                assert source["type"] == "python_breadth_research_run"
                assert source["source_run_id"] == queued_payload["run_id"]
                assert source["source_execution_mode"] == "breadth_history"
                assert source["point_in_time_source_preserved"] is True
                assert len(source["source_dataset_manifest_sha256"]) == 64
                duplicate = client.post(
                    f"/api/v1/analysis/breadth/python/runs/{queued_payload['run_id']}/promote-scan",
                    headers=auth_headers,
                    json={"name": "Historical Python breadth scan"},
                )
                assert duplicate.status_code == 409
            else:
                assert collected_payload["current"]["requested_count"] == 1
                not_history = client.post(
                    f"/api/v1/analysis/breadth/python/runs/{queued_payload['run_id']}/promote-scan",
                    headers=auth_headers,
                    json={"name": "Current Python breadth scan"},
                )
                assert not_history.status_code == 422
                assert not_history.json()["detail"]["code"] == "breadth_promotion_requires_history"

    def test_python_breadth_accepts_numeric_series_targets(
        self, client, auth_headers, instrument, ohlcv_bars, tmp_path, monkeypatch
    ):
        import json

        from research_runner.runner import execute_job

        monkeypatch.setattr(
            "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
        )
        monkeypatch.setattr(
            "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
        )
        asset_response = client.post(
            "/api/v1/code/assets",
            headers=auth_headers,
            json={
                "stable_key": "python-breadth-derived-series",
                "name": "Python breadth derived series",
                "kind": "condition",
                "initial_version": {
                    "source": "output.series('target', market.close())",
                    "output_contract": "series",
                    "output_name": "target",
                },
            },
        )
        assert asset_response.status_code == 201, asset_response.text
        version_id = asset_response.json()["versions"][0]["id"]
        comparison_asset_response = client.post(
            "/api/v1/code/assets",
            headers=auth_headers,
            json={
                "stable_key": "python-breadth-comparison-series",
                "name": "Python breadth comparison series",
                "kind": "condition",
                "initial_version": {
                    "source": "output.series('reference', market.close())",
                    "output_contract": "series",
                    "output_name": "reference",
                },
            },
        )
        assert comparison_asset_response.status_code == 201, comparison_asset_response.text
        comparison_version_id = comparison_asset_response.json()["versions"][0]["id"]

        queued = client.post(
            "/api/v1/analysis/breadth/python",
            headers=auth_headers,
            json={
                "code_version_id": version_id,
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "output_contract": "series",
                "series_target": {"operator": "gte", "threshold": 0},
                "session": "all",
                "history": True,
                "history_limit": 20,
            },
        )
        assert queued.status_code == 202, queued.text
        queued_payload = queued.json()
        assert queued_payload["output_contract"] == "series"
        assert queued_payload["series_target"] == {"operator": "gte", "threshold": 0.0}
        job_path = tmp_path / "jobs" / f"{queued_payload['run_id']}.json"
        job = json.loads(job_path.read_text())
        assert job["output_contract"] == "series"
        assert job["series_target"] == {"operator": "gte", "threshold": 0.0}
        result = execute_job(job)
        assert result["status"] == "completed", result
        assert result["artifacts"]["breadth_history"]["value"]["points"], job["dataset"].get(
            "exclusions"
        )
        (tmp_path / "results").mkdir(exist_ok=True)
        (tmp_path / "results" / f"{queued_payload['run_id']}.json").write_text(json.dumps(result))

        collected = client.get(
            f"/api/v1/analysis/breadth/python/runs/{queued_payload['run_id']}",
            headers=auth_headers,
        )
        assert collected.status_code == 200, collected.text
        payload = collected.json()
        assert payload["status"] == "completed"
        assert payload["output_contract"] == "series"
        assert payload["series_target"] == {"operator": "gte", "threshold": 0.0}
        assert payload["points"]
        assert payload["points"][-1]["members"][0]["value"] is True
        assert payload["points"][-1]["members"][0]["metric"] is not None

        promoted_plot = client.post(
            f"/api/v1/analysis/breadth/python/runs/{queued_payload['run_id']}/promote-plot",
            headers=auth_headers,
            json={"name": "Historical Python breadth plot"},
        )
        assert promoted_plot.status_code == 201, promoted_plot.text
        promoted_plot_payload = promoted_plot.json()
        assert promoted_plot_payload["kind"] == "plot"
        assert promoted_plot_payload["versions"][0]["output_contract"] == "series"
        lineage = next(
            item["promotion_lineage"]
            for item in promoted_plot_payload["versions"][0]["diagnostics"]
            if isinstance(item, dict) and "promotion_lineage" in item
        )
        assert lineage["source_run_id"] == queued_payload["run_id"]
        assert lineage["semantics"] == "re_evaluate_member_numeric_series_on_selected_symbol"
        duplicate_plot = client.post(
            f"/api/v1/analysis/breadth/python/runs/{queued_payload['run_id']}/promote-plot",
            headers=auth_headers,
            json={"name": "Duplicate historical Python breadth plot"},
        )
        assert duplicate_plot.status_code == 409
        promoted_column = client.post(
            f"/api/v1/analysis/breadth/python/runs/{queued_payload['run_id']}/promote-column",
            headers=auth_headers,
            json={"name": "Historical Python breadth column"},
        )
        assert promoted_column.status_code == 201, promoted_column.text
        promoted_column_payload = promoted_column.json()
        assert promoted_column_payload["kind"] == "column"
        assert promoted_column_payload["versions"][0]["output_contract"] == "scalar"
        assert any(
            item.get("output_adapter") == "latest_series_to_scalar"
            for item in promoted_column_payload["versions"][0]["diagnostics"]
            if isinstance(item, dict)
        )
        column_duplicate = client.post(
            f"/api/v1/analysis/breadth/python/runs/{queued_payload['run_id']}/promote-column",
            headers=auth_headers,
            json={"name": "Duplicate historical Python breadth column"},
        )
        assert column_duplicate.status_code == 409
        promoted_scan = client.post(
            f"/api/v1/analysis/breadth/python/runs/{queued_payload['run_id']}/promote-scan",
            headers=auth_headers,
            json={"name": "Historical Python numeric breadth scan"},
        )
        assert promoted_scan.status_code == 201, promoted_scan.text
        promoted_scan_payload = promoted_scan.json()
        assert promoted_scan_payload["conditions"]["type"] == "python_condition"
        assert promoted_scan_payload["conditions"]["code_version_id"] != version_id
        scan_lineage = promoted_scan_payload["conditions"]["provenance"]
        assert scan_lineage["output_adapter"] == "series_target_to_boolean"
        assert scan_lineage["series_target"] == {"operator": "gte", "threshold": 0.0}

        tree_queued = client.post(
            "/api/v1/analysis/breadth/python",
            headers=auth_headers,
            json={
                "code_version_id": version_id,
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "output_contract": "boolean",
                "condition_tree": {
                    "kind": "all",
                    "params": {
                        "conditions": [
                            {
                                "kind": "python_series",
                                "params": {
                                    "code_version_id": version_id,
                                    "operator": "gte",
                                    "threshold": 0,
                                },
                            },
                            {
                                "kind": "comparison",
                                "params": {"field": "close", "operator": "gte", "threshold": 0},
                            },
                        ]
                    },
                },
                "history": True,
                "history_limit": 20,
            },
        )
        assert tree_queued.status_code == 202, tree_queued.text
        tree_job = json.loads(
            (tmp_path / "jobs" / f"{tree_queued.json()['run_id']}.json").read_text()
        )
        assert tree_job["condition_tree"]["params"]["conditions"][0]["params"]["source"]
        tree_result = execute_job(tree_job)
        assert tree_result["status"] == "completed", tree_result
        assert (
            tree_result["artifacts"]["breadth_history"]["value"]["points"][-1]["cells"][0]["value"]
            is True
        )
        (tmp_path / "results" / f"{tree_queued.json()['run_id']}.json").write_text(
            json.dumps(tree_result)
        )
        tree_collected = client.get(
            f"/api/v1/analysis/breadth/python/runs/{tree_queued.json()['run_id']}",
            headers=auth_headers,
        )
        assert tree_collected.status_code == 200, tree_collected.text
        assert tree_collected.json()["status"] == "completed"
        promoted_tree_aggregate_plot = client.post(
            f"/api/v1/analysis/breadth/python/runs/{tree_queued.json()['run_id']}/promote-plot",
            headers=auth_headers,
            json={"name": "Historical Python tree aggregate plot", "aggregate": True},
        )
        assert promoted_tree_aggregate_plot.status_code == 201, promoted_tree_aggregate_plot.text
        promoted_tree_aggregate_payload = promoted_tree_aggregate_plot.json()
        assert promoted_tree_aggregate_payload["kind"] == "plot"
        assert promoted_tree_aggregate_payload["versions"][0]["output_contract"] == "series"
        assert promoted_tree_aggregate_payload["versions"][0]["output_name"] == "percentage_history"
        tree_aggregate_lineage = next(
            item["promotion_lineage"]
            for item in promoted_tree_aggregate_payload["versions"][0]["diagnostics"]
            if isinstance(item, dict) and "promotion_lineage" in item
        )
        assert tree_aggregate_lineage["source_run_id"] == tree_queued.json()["run_id"]
        assert tree_aggregate_lineage["source_condition_tree"]["kind"] == "all"
        assert (
            tree_aggregate_lineage["semantics"]
            == "re_evaluate_breadth_as_aggregate_percentage_plot"
        )
        tree_aggregate_plot_run = client.post(
            "/api/v1/research/runs",
            headers=auth_headers,
            json={
                "code_version_id": promoted_tree_aggregate_payload["versions"][0]["id"],
                "run_config": {
                    "symbols": [instrument.symbol],
                    "timeframe": "D1",
                    "adjustment": "split_adjusted",
                    "session": "all",
                },
                "dataset_manifest": {"source": "canonical_database"},
            },
        )
        assert tree_aggregate_plot_run.status_code == 202, tree_aggregate_plot_run.text
        tree_aggregate_plot_run_id = tree_aggregate_plot_run.json()["id"]
        tree_aggregate_plot_job = json.loads(
            (tmp_path / "jobs" / f"{tree_aggregate_plot_run_id}.json").read_text()
        )
        tree_aggregate_plot_result = execute_job(tree_aggregate_plot_job)
        assert tree_aggregate_plot_result["status"] == "completed", tree_aggregate_plot_result
        assert tree_aggregate_plot_result["artifacts"]["percentage_history"]["value"]["values"]
        promoted_tree_scan = client.post(
            f"/api/v1/analysis/breadth/python/runs/{tree_queued.json()['run_id']}/promote-scan",
            headers=auth_headers,
            json={"name": "Historical Python tree scan"},
        )
        assert promoted_tree_scan.status_code == 201, promoted_tree_scan.text
        promoted_tree_payload = promoted_tree_scan.json()
        assert promoted_tree_payload["conditions"]["type"] == "python_condition"
        assert "condition_tree" in promoted_tree_payload["conditions"]
        tree_lineage = promoted_tree_payload["conditions"]["provenance"]
        assert tree_lineage["output_adapter"] == "condition_tree_to_boolean"
        assert tree_lineage["condition_tree"]["kind"] == "all"
        tree_run = client.post(
            f"/api/v1/screeners/{promoted_tree_payload['id']}/run",
            headers=auth_headers,
        )
        assert tree_run.status_code == 200, tree_run.text
        tree_screener_job = json.loads(
            (
                tmp_path
                / "jobs"
                / f"{tree_run.json()['result_data']['_python_research_run_id']}.json"
            ).read_text()
        )
        assert tree_screener_job["condition_tree"]["kind"] == "all"
        tree_screener_result = execute_job(tree_screener_job)
        assert tree_screener_result["status"] == "completed"
        assert (
            tree_screener_result["artifacts"]["batch_cells"]["value"]["cells"][0]["value"] is True
        )

        cross_tree_queued = client.post(
            "/api/v1/analysis/breadth/python",
            headers=auth_headers,
            json={
                "code_version_id": version_id,
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "output_contract": "boolean",
                "condition_tree": {
                    "kind": "all",
                    "params": {
                        "conditions": [
                            {
                                "kind": "python_series",
                                "params": {
                                    "code_version_id": version_id,
                                    "scope": "cross_sectional",
                                    "statistic": "mean",
                                    "operator": "gte",
                                    "threshold": 0,
                                },
                            },
                        ]
                    },
                },
            },
        )
        assert cross_tree_queued.status_code == 202, cross_tree_queued.text
        cross_tree_job = json.loads(
            (tmp_path / "jobs" / f"{cross_tree_queued.json()['run_id']}.json").read_text()
        )
        assert (
            cross_tree_job["condition_tree"]["params"]["conditions"][0]["params"]["scope"]
            == "cross_sectional"
        )
        cross_tree_result = execute_job(cross_tree_job)
        assert cross_tree_result["status"] == "completed", cross_tree_result
        assert cross_tree_result["artifacts"]["batch_cells"]["value"]["cells"][0]["value"] is True

        comparison_tree_queued = client.post(
            "/api/v1/analysis/breadth/python",
            headers=auth_headers,
            json={
                "code_version_id": version_id,
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "output_contract": "boolean",
                "condition_tree": {
                    "kind": "python_series_comparison",
                    "params": {
                        "left_code_version_id": version_id,
                        "right_code_version_id": comparison_version_id,
                        "relation": "difference",
                        "right_scope": "benchmark",
                        "scope": "cross_sectional",
                        "statistic": "median",
                        "operator": "gte",
                        "threshold": 0,
                    },
                },
                "benchmark": instrument.symbol,
            },
        )
        assert comparison_tree_queued.status_code == 202, comparison_tree_queued.text
        comparison_tree_job = json.loads(
            (tmp_path / "jobs" / f"{comparison_tree_queued.json()['run_id']}.json").read_text()
        )
        comparison_leaf = comparison_tree_job["condition_tree"]["params"]
        assert comparison_leaf["left_code_version_id"] == version_id
        assert comparison_leaf["right_code_version_id"] == comparison_version_id
        assert comparison_leaf["right_scope"] == "benchmark"
        assert comparison_leaf["scope"] == "cross_sectional"
        assert comparison_leaf["statistic"] == "median"
        assert comparison_leaf["left_source"] and comparison_leaf["right_source"]
        comparison_tree_result = execute_job(comparison_tree_job)
        assert comparison_tree_result["status"] == "completed", comparison_tree_result
        assert (
            comparison_tree_result["artifacts"]["batch_cells"]["value"]["cells"][0]["value"] is True
        )

        cross_queued = client.post(
            "/api/v1/analysis/breadth/python",
            headers=auth_headers,
            json={
                "code_version_id": version_id,
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "output_contract": "series",
                "series_target": {
                    "scope": "cross_sectional",
                    "statistic": "mean",
                    "operator": "gte",
                    "threshold": 0,
                },
                "session": "all",
            },
        )
        assert cross_queued.status_code == 202, cross_queued.text
        cross_job = json.loads(
            (tmp_path / "jobs" / f"{cross_queued.json()['run_id']}.json").read_text()
        )
        cross_result = execute_job(cross_job)
        assert cross_result["status"] == "completed", cross_result
        (tmp_path / "results" / f"{cross_queued.json()['run_id']}.json").write_text(
            json.dumps(cross_result)
        )
        cross_collected = client.get(
            f"/api/v1/analysis/breadth/python/runs/{cross_queued.json()['run_id']}",
            headers=auth_headers,
        )
        assert cross_collected.status_code == 200, cross_collected.text
        cross_artifact = cross_result["artifacts"]["batch_cells"]["value"]
        assert cross_artifact["group_value"] is not None
        assert cross_artifact["cells"][0]["metric"] == 0.0
        cross_plot = client.post(
            f"/api/v1/analysis/breadth/python/runs/{cross_queued.json()['run_id']}/promote-plot",
            headers=auth_headers,
            json={"name": "Cross-sectional breadth plot"},
        )
        assert cross_plot.status_code == 422
        assert cross_plot.json()["detail"]["code"] == "breadth_plot_promotion_requires_member_scope"
        cross_column = client.post(
            f"/api/v1/analysis/breadth/python/runs/{cross_queued.json()['run_id']}/promote-column",
            headers=auth_headers,
            json={"name": "Cross-sectional breadth column"},
        )
        assert cross_column.status_code == 422
        assert (
            cross_column.json()["detail"]["code"]
            == "breadth_column_promotion_requires_member_scope"
        )

        cross_history_queued = client.post(
            "/api/v1/analysis/breadth/python",
            headers=auth_headers,
            json={
                "code_version_id": version_id,
                "universe": {"kind": "symbols", "symbols": [instrument.symbol]},
                "output_contract": "series",
                "series_target": {
                    "scope": "cross_sectional",
                    "statistic": "mean",
                    "operator": "gte",
                    "threshold": 0,
                },
                "session": "all",
                "history": True,
                "history_limit": 20,
            },
        )
        assert cross_history_queued.status_code == 202, cross_history_queued.text
        cross_history_run_id = cross_history_queued.json()["run_id"]
        cross_history_job = json.loads(
            (tmp_path / "jobs" / f"{cross_history_run_id}.json").read_text()
        )
        cross_history_result = execute_job(cross_history_job)
        assert cross_history_result["status"] == "completed", cross_history_result
        (tmp_path / "results" / f"{cross_history_run_id}.json").write_text(
            json.dumps(cross_history_result)
        )
        cross_history_collected = client.get(
            f"/api/v1/analysis/breadth/python/runs/{cross_history_run_id}",
            headers=auth_headers,
        )
        assert cross_history_collected.status_code == 200, cross_history_collected.text
        promoted_aggregate_plot = client.post(
            f"/api/v1/analysis/breadth/python/runs/{cross_history_run_id}/promote-plot",
            headers=auth_headers,
            json={"name": "Cross-sectional breadth aggregate plot", "aggregate": True},
        )
        assert promoted_aggregate_plot.status_code == 201, promoted_aggregate_plot.text
        promoted_aggregate_plot_payload = promoted_aggregate_plot.json()
        assert promoted_aggregate_plot_payload["kind"] == "plot"
        assert promoted_aggregate_plot_payload["versions"][0]["output_contract"] == "series"
        assert promoted_aggregate_plot_payload["versions"][0]["output_name"] == "percentage_history"
        aggregate_lineage = next(
            item["promotion_lineage"]
            for item in promoted_aggregate_plot_payload["versions"][0]["diagnostics"]
            if isinstance(item, dict) and "promotion_lineage" in item
        )
        assert aggregate_lineage["source_run_id"] == cross_history_run_id
        assert aggregate_lineage["semantics"] == "re_evaluate_breadth_as_aggregate_percentage_plot"
        aggregate_plot_run = client.post(
            "/api/v1/research/runs",
            headers=auth_headers,
            json={
                "code_version_id": promoted_aggregate_plot_payload["versions"][0]["id"],
                "run_config": {
                    "symbols": [instrument.symbol],
                    "timeframe": "D1",
                    "adjustment": "split_adjusted",
                    "session": "all",
                },
                "dataset_manifest": {"source": "canonical_database"},
            },
        )
        assert aggregate_plot_run.status_code == 202, aggregate_plot_run.text
        aggregate_plot_run_id = aggregate_plot_run.json()["id"]
        aggregate_plot_job = json.loads(
            (tmp_path / "jobs" / f"{aggregate_plot_run_id}.json").read_text()
        )
        aggregate_plot_result = execute_job(aggregate_plot_job)
        assert aggregate_plot_result["status"] == "completed", aggregate_plot_result
        assert aggregate_plot_result["artifacts"]["percentage_history"]["value"]["values"]
        duplicate_aggregate_plot = client.post(
            f"/api/v1/analysis/breadth/python/runs/{cross_history_run_id}/promote-plot",
            headers=auth_headers,
            json={"name": "Duplicate cross-sectional breadth aggregate plot", "aggregate": True},
        )
        assert duplicate_aggregate_plot.status_code == 409
        promoted_study = client.post(
            f"/api/v1/analysis/breadth/python/runs/{cross_history_run_id}/promote-study",
            headers=auth_headers,
            json={"name": "Cross-sectional breadth Study Lab study"},
        )
        assert promoted_study.status_code == 201, promoted_study.text
        promoted_study_payload = promoted_study.json()
        assert promoted_study_payload["kind"] == "study"
        assert promoted_study_payload["versions"][0]["output_contract"] == "study"
        assert "research.breadth_python" in promoted_study_payload["versions"][0]["source"]
        study_lineage = next(
            item["promotion_lineage"]
            for item in promoted_study_payload["versions"][0]["diagnostics"]
            if isinstance(item, dict) and "promotion_lineage" in item
        )
        assert study_lineage["source_run_id"] == cross_history_run_id
        assert study_lineage["source_series_target"]["scope"] == "cross_sectional"
        assert (
            study_lineage["semantics"] == "re_evaluate_isolated_member_predicate_as_aggregate_study"
        )
        promoted_study_run = client.post(
            "/api/v1/research/runs",
            headers=auth_headers,
            json={
                "code_version_id": promoted_study_payload["versions"][0]["id"],
                "run_config": {
                    "symbols": [instrument.symbol],
                    "timeframe": "D1",
                    "adjustment": "split_adjusted",
                    "session": "all",
                },
                "dataset_manifest": {"source": "canonical_database"},
            },
        )
        assert promoted_study_run.status_code == 202, promoted_study_run.text
        promoted_study_run_id = promoted_study_run.json()["id"]
        promoted_study_job = json.loads(
            (tmp_path / "jobs" / f"{promoted_study_run_id}.json").read_text()
        )
        promoted_study_result = execute_job(promoted_study_job)
        assert promoted_study_result["status"] == "completed", promoted_study_result
        assert promoted_study_result["artifacts"]["percentage_history"]["value"]["values"]
        assert promoted_study_result["artifacts"]["current_percentage"]["value"] == 1.0
        duplicate_study = client.post(
            f"/api/v1/analysis/breadth/python/runs/{cross_history_run_id}/promote-study",
            headers=auth_headers,
            json={"name": "Duplicate cross-sectional Study Lab study"},
        )
        assert duplicate_study.status_code == 409

    def test_etf_constituent_snapshot_is_point_in_time_and_source_labelled(
        self, client, auth_headers, db, instrument, instrument_type, ohlcv_bars
    ):
        from datetime import UTC, datetime

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument

        etf = Instrument(
            symbol="XLK",
            name="Technology Select Sector SPDR Fund",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add(etf)
        db.flush()
        profile = ETFProfile(instrument_id=etf.id, adapter_status="resolved")
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2024, 5, 30, tzinfo=UTC).date(),
            known_at=datetime(2024, 5, 31, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="issuer",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            snapshot_hash="test-xlk-snapshot",
        )
        db.add(snapshot)
        db.flush()
        db.add(
            ETFHolding(
                snapshot_id=snapshot.id,
                constituent_instrument_id=instrument.id,
                position=0,
                reported_symbol=instrument.symbol,
                reported_name=instrument.name,
                source_row_hash="test-xlk-aapl",
                is_resolved=True,
            )
        )
        db.flush()

        response = client.get(
            "/api/v1/analysis/etf/XLK/constituents/snapshot",
            headers=auth_headers,
            params={"benchmark": instrument.symbol, "as_of": "2024-06-01T00:00:00Z"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["group_key"] == "etf-proxy:XLK"
        assert payload["membership_version"] == snapshot.id
        assert payload["composition_date"] == "2024-05-30"
        assert payload["provenance"] == "issuer_native"
        assert payload["source_provider"] == "issuer"
        assert payload["as_of"] == "2024-06-01T00:00:00Z"
        assert payload["universe_provenance"]["requested_as_of"] == "2024-06-01T00:00:00+00:00"
        assert payload["coverage"] == 1
        assert payload["rows"][0]["symbol"] == instrument.symbol
        assert payload["rows"][0]["relative_to_benchmark"]["value"] == 1

    def test_etf_constituent_snapshot_discloses_excluded_holdings_and_coverage(
        self, client, auth_headers, db, instrument, instrument_type, ohlcv_bars
    ):
        """The constituent batch must not hide non-equity disclosure rows."""
        from datetime import UTC, date, datetime

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import Instrument

        etf = Instrument(
            symbol="MIXD",
            name="Mixed Disclosure ETF",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        cash = Instrument(
            symbol="CASH-MIXD",
            name="Cash balance",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add_all([etf, cash])
        db.flush()
        profile = ETFProfile(instrument_id=etf.id)
        db.add(profile)
        db.flush()
        snapshot = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=date(2026, 8, 12),
            known_at=datetime(2026, 8, 13, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="mixed-disclosure-test",
            completeness_status="partial",
            row_count=3,
            resolved_count=2,
            unresolved_count=1,
            snapshot_hash="mixed-disclosure-snapshot",
        )
        db.add(snapshot)
        db.flush()
        db.add_all(
            [
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=instrument.id,
                    position=0,
                    source_row_hash="mixed-equity",
                    is_resolved=True,
                    holding_type="equity",
                    row_type="security",
                ),
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=cash.id,
                    position=1,
                    source_row_hash="mixed-cash",
                    is_resolved=True,
                    holding_type="cash",
                    row_type="cash",
                ),
                ETFHolding(
                    snapshot_id=snapshot.id,
                    constituent_instrument_id=None,
                    position=2,
                    source_row_hash="mixed-unresolved",
                    is_resolved=False,
                    holding_type="equity",
                    row_type="security",
                ),
            ]
        )
        db.flush()

        response = client.get(
            "/api/v1/analysis/etf/MIXD/constituents/snapshot",
            headers=auth_headers,
            params={"benchmark": instrument.symbol},
        )
        assert response.status_code == 200
        payload = response.json()
        assert [row["symbol"] for row in payload["rows"]] == [instrument.symbol]
        assert payload["coverage"] == 1 / 3
        assert [item["code"] for item in payload["exclusions"]] == [
            "cash_holding",
            "unresolved_holding",
        ]

    def test_industry_proxy_requires_curated_candidate_and_holdings_evidence(
        self, client, auth_headers, db, instrument, instrument_type
    ):
        from datetime import UTC, datetime
        from decimal import Decimal

        from app.models.data_source import DataSource
        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import EquityDetail, Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe
        from app.models.provider_observation import InstrumentProfileSnapshot

        db.add(
            EquityDetail(
                instrument_id=instrument.id,
                industry="Semiconductors",
                field_provenance={
                    "industry": {
                        "classification_system": "provider_native",
                        "observed_at": "2026-08-12T00:00:00+00:00",
                    }
                },
            )
        )
        profile_source = DataSource(
            name="historical-profile-fixture",
            base_url="controlled://historical-profile",
            description="Point-in-time classification fixture",
            is_active=True,
        )
        db.add(profile_source)
        db.flush()
        db.add(
            InstrumentProfileSnapshot(
                instrument_id=instrument.id,
                data_source_id=profile_source.id,
                provider_symbol=instrument.symbol,
                observed_at=datetime(2024, 5, 29, tzinfo=UTC),
                fetched_at=datetime(2024, 5, 30, tzinfo=UTC),
                profile_hash="historical-semis-profile",
                payload={
                    "provider": "historical-profile-fixture",
                    "symbol": instrument.symbol,
                    "extra": {
                        "industry": "Semiconductors",
                        "classification_system": "provider_native",
                    },
                },
            )
        )
        source = Instrument(
            symbol="XLK",
            name="Technology Select Sector SPDR Fund",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        proxy = Instrument(
            symbol="SMH",
            name="VanEck Semiconductor ETF",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
        )
        db.add_all([source, proxy])
        db.flush()
        source_profile, proxy_profile = (
            ETFProfile(instrument_id=source.id),
            ETFProfile(instrument_id=proxy.id),
        )
        db.add_all([source_profile, proxy_profile])
        db.flush()
        source_snapshot = ETFHoldingsSnapshot(
            etf_profile_id=source_profile.id,
            composition_date=datetime(2024, 5, 30, tzinfo=UTC).date(),
            known_at=datetime(2024, 5, 31, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="source_issuer",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            snapshot_hash="test-source-semis",
        )
        proxy_snapshot = ETFHoldingsSnapshot(
            etf_profile_id=proxy_profile.id,
            composition_date=datetime(2024, 5, 29, tzinfo=UTC).date(),
            known_at=datetime(2024, 5, 30, tzinfo=UTC),
            provenance="issuer_native",
            source_provider="proxy_issuer",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            snapshot_hash="test-proxy-semis",
        )
        db.add_all([source_snapshot, proxy_snapshot])
        db.flush()
        db.add_all(
            [
                ETFHolding(
                    snapshot_id=source_snapshot.id,
                    constituent_instrument_id=instrument.id,
                    position=0,
                    source_row_hash="source-aapl",
                    is_resolved=True,
                ),
                ETFHolding(
                    snapshot_id=proxy_snapshot.id,
                    constituent_instrument_id=instrument.id,
                    position=0,
                    source_row_hash="proxy-aapl",
                    is_resolved=True,
                ),
            ]
        )
        db.flush()
        controlled_proxy_snapshot = ETFHoldingsSnapshot(
            etf_profile_id=proxy_profile.id,
            composition_date=datetime(2024, 6, 2, tzinfo=UTC).date(),
            known_at=datetime(2024, 6, 3, tzinfo=UTC),
            provenance="controlled_fixture",
            source_provider="e2e_reference",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            snapshot_hash="test-proxy-controlled",
        )
        db.add(controlled_proxy_snapshot)
        db.flush()
        db.add(
            ETFHolding(
                snapshot_id=controlled_proxy_snapshot.id,
                constituent_instrument_id=instrument.id,
                position=0,
                source_row_hash="proxy-controlled-aapl",
                is_resolved=True,
            )
        )
        db.flush()

        # The newer controlled browser fixture must not replace the latest
        # canonical disclosure in normal (non-E2E) API reads.
        composition = client.get("/api/v1/market-groups/etf/SMH/industries", headers=auth_headers)
        assert composition.status_code == 200
        assert composition.json()["composition_date"] == "2024-05-29"
        constituents = client.get(
            "/api/v1/market-groups/etf/SMH/industries/Semiconductors",
            headers=auth_headers,
        )
        assert constituents.status_code == 200
        assert constituents.json()["composition_date"] == "2024-05-29"

        response = client.get(
            "/api/v1/market-groups/etf/XLK/industries/Semiconductors/proxies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["candidate_symbols"] == ["SOXX", "SMH"]
        assert payload["proxies"] == [
            {
                "symbol": "SMH",
                "name": "VanEck Semiconductor ETF",
                "composition_date": "2024-05-29",
                "known_at": "2024-05-30T00:00:00Z",
                "provenance": "issuer_native",
                "source_provider": "proxy_issuer",
                "matching_constituent_count": 1,
                "classified_constituent_count": 1,
                "classification_coverage": 1,
                "source": "curated_industry_proxy_registry_v1",
                "verification_state": "holdings_classification_verified",
            }
        ]
        assert "candidate_not_canonical:SOXX" in payload["exclusions"]

        timestamp = datetime(2024, 6, 3, tzinfo=UTC)
        for item, close in ((source, "100"), (proxy, "200"), (instrument, "50")):
            price = Decimal(close)
            db.add(
                OHLCVBar(
                    instrument_id=item.id,
                    timeframe=Timeframe.D1,
                    ts=timestamp,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=Decimal("100"),
                    is_adjusted=True,
                )
            )
        db.flush()
        ranked = client.get(
            "/api/v1/analysis/etf/XLK/industries/Semiconductors/proxies/snapshot",
            headers=auth_headers,
            params={"market_benchmark": instrument.symbol},
        )
        assert ranked.status_code == 200
        ranked_payload = ranked.json()
        assert ranked_payload["group_key"] == "industry-proxy:XLK:Semiconductors"
        assert ranked_payload["market_benchmark"] == instrument.symbol
        assert (
            ranked_payload["proxy_evidence"][0]["verification_state"]
            == "holdings_classification_verified"
        )
        assert ranked_payload["rows"][0]["symbol"] == "SMH"
        assert ranked_payload["rows"][0]["relative_to_benchmark"]["value"] == 2
        assert ranked_payload["rows"][0]["relative_to_market"]["value"] == 4

        industries_ranked = client.get(
            "/api/v1/analysis/etf/XLK/industries/snapshot",
            headers=auth_headers,
            params={"market_benchmark": instrument.symbol},
        )
        assert industries_ranked.status_code == 200
        industries_payload = industries_ranked.json()
        assert industries_payload["group_key"] == "industry:XLK"
        assert industries_payload["market_benchmark"] == instrument.symbol
        assert industries_payload["rows"][0]["industry"] == "Semiconductors"
        assert set(industries_payload["rows"][0]["performance"]) == {
            "1D",
            "1W",
            "1M",
            "3M",
            "6M",
            "YTD",
            "1Y",
        }
        assert industries_payload["rows"][0]["relative_to_benchmark"]["value"] == 1
        assert industries_payload["rows"][0]["relative_to_market"]["value"] == 1

        future_timestamp = datetime(2024, 6, 4, tzinfo=UTC)
        for item, close in ((source, "100"), (proxy, "300"), (instrument, "50")):
            price = Decimal(close)
            db.add(
                OHLCVBar(
                    instrument_id=item.id,
                    timeframe=Timeframe.D1,
                    ts=future_timestamp,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=Decimal("100"),
                    is_adjusted=True,
                )
            )
        db.flush()
        point_in_time = client.get(
            "/api/v1/analysis/etf/XLK/industries/Semiconductors/proxies/snapshot",
            headers=auth_headers,
            params={"market_benchmark": instrument.symbol, "as_of": timestamp.isoformat()},
        )
        assert point_in_time.status_code == 200
        assert point_in_time.json()["rows"][0]["last"]["value"] == 200
        historical_industries = client.get(
            "/api/v1/market-groups/etf/SMH/industries",
            headers=auth_headers,
            params={"as_of": timestamp.isoformat()},
        )
        assert historical_industries.status_code == 200
        historical_payload = historical_industries.json()
        assert historical_payload["industries"] == [
            {
                "industry": "Semiconductors",
                "constituent_count": 1,
                "resolved_count": 1,
                "classification_systems": ["provider_native"],
            }
        ]
        assert historical_payload["classification_coverage"] == 1

    def test_instrument_notes_are_user_scoped_and_autosave_ready(
        self, client, auth_headers, instrument
    ):
        assert (
            client.get(f"/api/v1/notes/instruments/{instrument.id}", headers=auth_headers).json()
            is None
        )
        saved = client.put(
            f"/api/v1/notes/instruments/{instrument.id}",
            headers=auth_headers,
            json={"content": "Watch relative strength against XLK."},
        )
        assert saved.status_code == 200
        assert saved.json()["content"] == "Watch relative strength against XLK."
        reloaded = client.get(f"/api/v1/notes/instruments/{instrument.id}", headers=auth_headers)
        assert reloaded.json()["content"] == "Watch relative strength against XLK."
