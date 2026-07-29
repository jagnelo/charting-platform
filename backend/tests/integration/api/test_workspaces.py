class TestWorkspaces:
    def test_default_workspace_is_top_down_and_revisioned(self, client, auth_headers):
        response = client.get("/api/v1/workspaces/default", headers=auth_headers)
        assert response.status_code == 200
        workspace = response.json()
        assert workspace["name"] == "US Top Down"
        assert workspace["revision"] == 1
        assert workspace["tabs"][0]["stable_key"] == "us-top-down"
        assert workspace["tabs"][0]["layout_config"]["root"]["type"] == "row"
        assert workspace["tabs"][0]["layout_config"]["version"] == 4
        assert {window["tool_type"] for window in workspace["tabs"][0]["windows"]} >= {
            "watchlist",
            "chart",
            "breadth",
            "coverage",
            "alerts",
            "scan",
        }
        assert "alerts" in {window["instance_key"] for window in workspace["tabs"][0]["windows"]}
        assert "easy-scan" in {window["instance_key"] for window in workspace["tabs"][0]["windows"]}
        assert {tab["stable_key"] for tab in workspace["tabs"]} >= {
            "tc-classic",
            "drill-down",
            "four-timeframe",
            "study-lab",
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
