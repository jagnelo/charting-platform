"""
WebSocket connection manager.
Maintains a set of active connections and broadcasts messages to all.
"""

import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._user_connections: dict[int, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int | None = None) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        if user_id is not None:
            self._user_connections.setdefault(user_id, set()).add(websocket)
        logger.info(f"WS connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        for user_id, connections in list(self._user_connections.items()):
            connections.discard(websocket)
            if not connections:
                self._user_connections.pop(user_id, None)
        logger.info(f"WS disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict) -> None:
        if not self.active_connections:
            return
        text = json.dumps(message)
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(text)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)

    async def broadcast_to_user(self, user_id: int, message: dict) -> None:
        """Send a notification only to authenticated connections for one user."""
        text = json.dumps(message)
        dead = []
        for connection in list(self._user_connections.get(user_id, ())):
            try:
                await connection.send_text(text)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"WS send failed: {e}")
            self.disconnect(websocket)


ws_manager = WebSocketManager()
