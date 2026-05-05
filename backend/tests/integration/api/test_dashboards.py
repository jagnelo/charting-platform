class TestDashboardsAuth:
    def test_list_requires_auth(self, client):
        res = client.get("/api/v1/dashboards")
        assert res.status_code == 401


class TestDashboardsFlow:
    def test_get_default_creates_dashboard_and_tab(self, client, auth_headers):
        res = client.get("/api/v1/dashboards/default", headers=auth_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["is_default"] is True
        assert len(body["tabs"]) == 1
        assert body["tabs"][0]["name"] == "Home"

    def test_create_dashboard_with_default_switches_existing_default(self, client, auth_headers):
        first = client.get("/api/v1/dashboards/default", headers=auth_headers).json()
        second = client.post(
            "/api/v1/dashboards",
            headers=auth_headers,
            json={"name": "Research", "is_default": True},
        )
        assert second.status_code == 201
        created = second.json()
        assert created["is_default"] is True

        listed = client.get("/api/v1/dashboards", headers=auth_headers).json()
        first_after = next(d for d in listed if d["id"] == first["id"])
        second_after = next(d for d in listed if d["id"] == created["id"])
        assert first_after["is_default"] is False
        assert second_after["is_default"] is True

    def test_update_dashboard_trims_name(self, client, auth_headers):
        dashboard = client.get("/api/v1/dashboards/default", headers=auth_headers).json()
        res = client.patch(
            f"/api/v1/dashboards/{dashboard['id']}",
            headers=auth_headers,
            json={"name": "  Custom Dashboard  "},
        )
        assert res.status_code == 200
        assert res.json()["name"] == "Custom Dashboard"

    def test_create_update_and_delete_tab(self, client, auth_headers):
        dashboard = client.get("/api/v1/dashboards/default", headers=auth_headers).json()
        create = client.post(
            f"/api/v1/dashboards/{dashboard['id']}/tabs",
            headers=auth_headers,
            json={"name": "Second", "position": 1, "layout_settings": {"columns": 2}},
        )
        assert create.status_code == 201
        tab = create.json()
        assert tab["name"] == "Second"

        update = client.patch(
            f"/api/v1/dashboards/tabs/{tab['id']}",
            headers=auth_headers,
            json={"name": "  Renamed Tab  "},
        )
        assert update.status_code == 200
        assert update.json()["name"] == "Renamed Tab"

        delete = client.delete(f"/api/v1/dashboards/tabs/{tab['id']}", headers=auth_headers)
        assert delete.status_code == 204

    def test_cannot_delete_last_tab(self, client, auth_headers):
        dashboard = client.get("/api/v1/dashboards/default", headers=auth_headers).json()
        only_tab = dashboard["tabs"][0]
        res = client.delete(f"/api/v1/dashboards/tabs/{only_tab['id']}", headers=auth_headers)
        assert res.status_code == 400

    def test_reorder_tabs_updates_positions(self, client, auth_headers):
        dashboard = client.get("/api/v1/dashboards/default", headers=auth_headers).json()
        tab1 = client.post(
            f"/api/v1/dashboards/{dashboard['id']}/tabs",
            headers=auth_headers,
            json={"name": "One", "position": 1, "layout_settings": {}},
        ).json()
        tab2 = client.post(
            f"/api/v1/dashboards/{dashboard['id']}/tabs",
            headers=auth_headers,
            json={"name": "Two", "position": 2, "layout_settings": {}},
        ).json()

        res = client.post(
            f"/api/v1/dashboards/{dashboard['id']}/tabs/reorder",
            headers=auth_headers,
            json={"ids": [tab2["id"], tab1["id"], dashboard["tabs"][0]["id"]]},
        )
        assert res.status_code == 200

        listed = client.get("/api/v1/dashboards", headers=auth_headers).json()
        refreshed = next(d for d in listed if d["id"] == dashboard["id"])
        positions = {tab["id"]: tab["position"] for tab in refreshed["tabs"]}
        assert positions[tab2["id"]] == 0
        assert positions[tab1["id"]] == 1

    def test_widget_crud_and_layout_patch(self, client, auth_headers):
        dashboard = client.get("/api/v1/dashboards/default", headers=auth_headers).json()
        tab = dashboard["tabs"][0]

        create = client.post(
            f"/api/v1/dashboards/tabs/{tab['id']}/widgets",
            headers=auth_headers,
            json={
                "widget_type": "quote",
                "title": "NVDA",
                "layout": {"x": 0, "y": 0, "w": 4, "h": 3},
                "config": {"symbol": "NVDA"},
                "style": {"density": "compact"},
                "position": 0,
            },
        )
        assert create.status_code == 201
        widget = create.json()
        assert widget["config"]["symbol"] == "NVDA"

        patch = client.patch(
            f"/api/v1/dashboards/widgets/{widget['id']}",
            headers=auth_headers,
            json={"title": "NVIDIA Quote", "config": {"symbol": "AAPL"}},
        )
        assert patch.status_code == 200
        assert patch.json()["title"] == "NVIDIA Quote"
        assert patch.json()["config"]["symbol"] == "AAPL"

        layout = client.patch(
            f"/api/v1/dashboards/tabs/{tab['id']}/widgets/layout",
            headers=auth_headers,
            json={"widgets": [{"id": widget["id"], "layout": {"x": 2, "y": 3, "w": 6, "h": 4}}]},
        )
        assert layout.status_code == 200

        refreshed = client.get("/api/v1/dashboards/default", headers=auth_headers).json()
        refreshed_widget = next(
            w for w in refreshed["tabs"][0]["widgets"] if w["id"] == widget["id"]
        )
        assert refreshed_widget["layout"] == {"x": 2, "y": 3, "w": 6, "h": 4}

        delete = client.delete(f"/api/v1/dashboards/widgets/{widget['id']}", headers=auth_headers)
        assert delete.status_code == 204
