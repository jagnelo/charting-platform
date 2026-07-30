class TestWorkspaces:
    def test_default_workspace_is_top_down_and_revisioned(self, client, auth_headers):
        response = client.get("/api/v1/workspaces/default", headers=auth_headers)
        assert response.status_code == 200
        workspace = response.json()
        assert workspace["name"] == "US Top Down"
        assert workspace["revision"] == 1
        assert workspace["tabs"][0]["stable_key"] == "us-top-down"
        assert workspace["tabs"][0]["layout_config"]["root"]["type"] == "row"
        assert workspace["tabs"][0]["layout_config"]["version"] == 7
        assert workspace["settings"]["factory_version"] == 7
        assert {window["tool_type"] for window in workspace["tabs"][0]["windows"]} >= {
            "watchlist",
            "chart",
            "breadth",
            "coverage",
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
        assert {tab["stable_key"] for tab in workspace["tabs"]} >= {
            "tc-classic",
            "drill-down",
            "four-timeframe",
            "study-lab",
        }
        four_timeframe = next(tab for tab in workspace["tabs"] if tab["stable_key"] == "four-timeframe")
        configurations = {
            window["instance_key"]: window["configuration"] for window in four_timeframe["windows"]
        }
        assert {key: value["timeframe"] for key, value in configurations.items()} == {
            "m15": "M15", "daily": "D1", "weekly": "W1", "monthly": "MN",
        }
        assert {value["timeframe_link_group"] for value in configurations.values()} == {
            "red", "green", "purple", "orange",
        }
        assert {window["link_group"] for window in four_timeframe["windows"]} == {"blue"}
        assert four_timeframe["layout_config"]["root"]["type"] == "row"
        assert [column["type"] for column in four_timeframe["layout_config"]["root"]["content"]] == [
            "column", "column"
        ]
        tc_classic = next(tab for tab in workspace["tabs"] if tab["stable_key"] == "tc-classic")
        assert {window["tool_type"] for window in tc_classic["windows"]} >= {"chart", "watchlist", "notes"}

    def test_factory_reset_recreates_latest_factory_layout(self, client, auth_headers):
        workspace = client.get("/api/v1/workspaces/default", headers=auth_headers).json()
        response = client.post(
            f"/api/v1/workspaces/{workspace['id']}/reset-factory",
            headers=auth_headers,
        )

        assert response.status_code == 200
        reset = response.json()
        assert reset["revision"] == workspace["revision"] + 1
        assert reset["settings"]["factory_version"] == 7
        four_timeframe = next(tab for tab in reset["tabs"] if tab["stable_key"] == "four-timeframe")
        assert {
            window["configuration"]["timeframe"] for window in four_timeframe["windows"]
        } == {"M15", "D1", "W1", "MN"}

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

    def test_snapshot_can_replace_factory_tabs_with_the_same_stable_keys(self, client, auth_headers):
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
        assert db.query(Workspace).filter_by(user_id=default["user_id"], is_default=True).count() == 1

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
            {"industry": "Semiconductors", "constituent_count": 1, "resolved_count": 1}
        ]
        constituents = client.get(
            "/api/v1/market-groups/etf/INDX/industries/Semiconductors",
            headers=auth_headers,
        )
        assert constituents.status_code == 200
        assert [item["id"] for item in constituents.json()["constituents"]] == [instrument.id]

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
            params={"benchmark": instrument.symbol, "lookback": 20, "tail_length": 3},
        )
        assert rotation.status_code == 200
        row = rotation.json()["rows"][0]
        assert row["state"] == "leading"
        assert len(row["tail"]) == 3
        assert row["coverage"] == 1

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
            params={"benchmark": instrument.symbol},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["group_key"] == "etf-proxy:XLK"
        assert payload["membership_version"] == snapshot.id
        assert payload["composition_date"] == "2024-05-30"
        assert payload["provenance"] == "issuer_native"
        assert payload["source_provider"] == "issuer"
        assert payload["coverage"] == 1
        assert payload["rows"][0]["symbol"] == instrument.symbol
        assert payload["rows"][0]["relative_to_benchmark"]["value"] == 1

    def test_industry_proxy_requires_curated_candidate_and_holdings_evidence(
        self, client, auth_headers, db, instrument, instrument_type
    ):
        from datetime import UTC, datetime
        from decimal import Decimal

        from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
        from app.models.instrument import EquityDetail, Instrument
        from app.models.ohlcv import OHLCVBar, Timeframe

        db.add(EquityDetail(instrument_id=instrument.id, industry="Semiconductors"))
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
