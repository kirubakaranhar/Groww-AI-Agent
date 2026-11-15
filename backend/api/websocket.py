"""
Groww AI Trading Agent - Real-time WebSocket Manager
Maintains active UI clients and broadcasts agent events, market data, and portfolio telemetry.
"""

import asyncio
import json
from typing import List
from fastapi import WebSocket, WebSocketDisconnect
from backend.core.logger import logger

class WebSocketConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.debug(f"WebSocket client connected. Active clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.debug(f"WebSocket client disconnected. Remaining: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        payload = json.dumps(message)
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.append(connection)

        for dc in dead_connections:
            self.disconnect(dc)

ws_manager = WebSocketConnectionManager()
