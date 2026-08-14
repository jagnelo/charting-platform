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
        assert row["coverage"] == 1

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
