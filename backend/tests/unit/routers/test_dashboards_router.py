class TestDashboardsRouter:
    def test_default_dashboard_is_created(self, client, auth_headers):
        res = client.get("/api/v1/dashboards/default", headers=auth_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["is_default"] is True
        assert len(body["tabs"]) == 1

    def test_widget_crud_and_layout_patch(self, client, auth_headers, db):
        from app.models.dashboard import DashboardWidget

        dashboard = client.get("/api/v1/dashboards/default", headers=auth_headers).json()
        tab = dashboard["tabs"][0]

        widget = client.post(
            f"/api/v1/dashboards/tabs/{tab['id']}/widgets",
            headers=auth_headers,
            json={
                "widget_type": "quote",
                "title": "Quote",
                "layout": {"x": 0, "y": 0, "w": 4, "h": 3},
                "config": {"symbol": "AAPL"},
                "style": {},
                "position": 0,
            },
        )
        assert widget.status_code == 201
        widget_id = widget.json()["id"]

        patch = client.patch(
            f"/api/v1/dashboards/tabs/{tab['id']}/widgets/layout",
            headers=auth_headers,
            json={"widgets": [{"id": widget_id, "layout": {"x": 3, "y": 4, "w": 5, "h": 6}}]},
        )
        assert patch.status_code == 200

        stored = db.get(DashboardWidget, widget_id)
        assert stored is not None
        assert stored.layout == {"x": 3, "y": 4, "w": 5, "h": 6}

    def test_cannot_delete_last_tab(self, client, auth_headers):
        dashboard = client.get("/api/v1/dashboards/default", headers=auth_headers).json()
        only_tab = dashboard["tabs"][0]
        res = client.delete(f"/api/v1/dashboards/tabs/{only_tab['id']}", headers=auth_headers)
        assert res.status_code == 400
