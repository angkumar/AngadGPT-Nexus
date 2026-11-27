import json
from typing import Dict, List

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        connections = self.active_connections.get(user_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.active_connections.pop(user_id, None)

    async def broadcast(self, message: Dict, user_id: str) -> None:
        data = json.dumps(message)
        stale: List[WebSocket] = []
        for conn in list(self.active_connections.get(user_id, [])):
            try:
                await conn.send_text(data)
            except Exception:
                # One closed socket must not stop delivery to the others.
                stale.append(conn)
        for conn in stale:
            self.disconnect(conn, user_id)

