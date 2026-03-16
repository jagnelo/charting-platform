"""
Integration tests for the WebSocket alert notification system.
"""


class TestWebSocketConnection:
    def test_websocket_connects(self, client):
        """WebSocket endpoint accepts connections."""
        with client.websocket_connect("/api/v1/alerts/ws") as ws:
            # Send a ping
            ws.send_text("ping")
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_websocket_multiple_clients(self, client):
        """Multiple clients can connect simultaneously."""
        with client.websocket_connect("/api/v1/alerts/ws") as ws1:
            with client.websocket_connect("/api/v1/alerts/ws") as ws2:
                ws1.send_text("ping")
                ws2.send_text("ping")
                d1 = ws1.receive_json()
                d2 = ws2.receive_json()
                assert d1["type"] == "pong"
                assert d2["type"] == "pong"


class TestWebSocketBroadcast:
    def test_broadcast_reaches_connected_client(self, client):
        """Messages broadcast by the alert engine reach connected clients."""
        import asyncio

        from app.websocket.manager import ws_manager

        with client.websocket_connect("/api/v1/alerts/ws") as ws:
            # Broadcast a simulated alert trigger
            asyncio.get_event_loop().run_until_complete(
                ws_manager.broadcast(
                    {
                        "type": "alert_triggered",
                        "symbol": "AAPL",
                        "condition": "crosses_above",
                        "threshold": 200.0,
                        "current_price": 205.0,
                        "alert_id": 1,
                        "user_id": 1,
                    }
                )
            )
            msg = ws.receive_json()
            assert msg["type"] == "alert_triggered"
            assert msg["symbol"] == "AAPL"

    def test_disconnect_removes_client(self, client):
        """After disconnect, client is removed from the manager."""
        from app.websocket.manager import ws_manager

        initial_count = len(ws_manager.active_connections)
        with client.websocket_connect("/api/v1/alerts/ws"):
            assert len(ws_manager.active_connections) == initial_count + 1
        assert len(ws_manager.active_connections) == initial_count
