import json

import pytest

from app.websocket.manager import WebSocketManager


class FakeWebSocket:
    def __init__(self):
        self.messages: list[str] = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, message: str):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_broadcast_to_user_does_not_cross_user_connections():
    manager = WebSocketManager()
    first = FakeWebSocket()
    second = FakeWebSocket()
    anonymous = FakeWebSocket()
    await manager.connect(first, user_id=11)
    await manager.connect(second, user_id=22)
    await manager.connect(anonymous)

    await manager.broadcast_to_user(11, {"type": "alert_triggered", "alert_id": 7})

    assert json.loads(first.messages[0]) == {"type": "alert_triggered", "alert_id": 7}
    assert second.messages == []
    assert anonymous.messages == []


@pytest.mark.asyncio
async def test_disconnect_removes_connection_from_user_index():
    manager = WebSocketManager()
    socket = FakeWebSocket()
    await manager.connect(socket, user_id=11)
    manager.disconnect(socket)

    await manager.broadcast_to_user(11, {"type": "alert_triggered"})

    assert socket.messages == []
    assert manager.active_connections == []
