from fastapi import WebSocket
from typing import Dict, List
import asyncio
import json

class LogConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, log_id: str):
        await websocket.accept()
        if log_id not in self.active_connections:
            self.active_connections[log_id] = []
        self.active_connections[log_id].append(websocket)

    def disconnect(self, websocket: WebSocket, log_id: str):
        if log_id in self.active_connections:
            self.active_connections[log_id].remove(websocket)
            if not self.active_connections[log_id]:
                del self.active_connections[log_id]

    async def broadcast_log(self, log_id: str, log_entry: dict):
        if log_id in self.active_connections:
            dead_connections = []
            for connection in self.active_connections[log_id]:
                try:
                    await connection.send_json(log_entry)
                except:
                    dead_connections.append(connection)
            
            # Clean up dead connections
            for dead_connection in dead_connections:
                self.active_connections[log_id].remove(dead_connection)
            
            if not self.active_connections[log_id]:
                del self.active_connections[log_id]

log_manager = LogConnectionManager() 