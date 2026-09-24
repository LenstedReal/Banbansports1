"""WebSocket connection manager."""
from typing import List, Optional
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.last_score_data: Optional[dict] = None

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)
        if self.last_score_data:
            try:
                await ws.send_json(self.last_score_data)
            except Exception:
                pass

    def disconnect(self, ws: WebSocket):
        if ws in self.active_connections:
            self.active_connections.remove(ws)

    async def broadcast(self, data: dict):
        self.last_score_data = data
        dead = []
        for c in self.active_connections:
            try:
                await c.send_json(data)
            except Exception:
                dead.append(c)
        for c in dead:
            self.disconnect(c)

    @property
    def has_clients(self) -> bool:
        return len(self.active_connections) > 0


manager = ConnectionManager()
