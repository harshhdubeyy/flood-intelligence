# Placeholder for backend/api/websocket.py
"""
Real-Time WebSocket Streaming Manager for GIS Dashboard & Ward Operations.
Enables low-latency bidirectional push for:
1. Ward risk level recalculations (15-minute intervals)
2. Ingested citizen ground reports with CV depth tags
3. Dispatched CAP flood alerts
4. Social media triage distress updates
5. IoT water level / tidal gauge telemetry
"""

import json
import asyncio
import logging
from typing import Dict, List, Set, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("fip.websocket")

websocket_router = APIRouter(tags=["WebSocket"])


class WebSocketManager:
    """
    Manages active WebSocket connections with channel filtering and heartbeat keepalives.
    """

    def __init__(self):
        # All active connections mapped to subscribed topics
        self.active_connections: Dict[WebSocket, Set[str]] = {}
        # Ward-specific listeners: ward_id -> set of WebSockets
        self.ward_subscribers: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, initial_channels: Optional[List[str]] = None):
        """Accepts connection and registers subscriber."""
        await websocket.accept()
        channels = set(initial_channels) if initial_channels else {"all", "risk", "reports", "alerts", "signals", "social"}
        async with self._lock:
            self.active_connections[websocket] = channels
            logger.info(f"WebSocket client connected. Active subscribers: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Removes connection from all registries."""
        async with self._lock:
            if websocket in self.active_connections:
                del self.active_connections[websocket]

            for ward_id, listeners in list(self.ward_subscribers.items()):
                listeners.discard(websocket)
                if not listeners:
                    del self.ward_subscribers[ward_id]

        logger.info(f"WebSocket client disconnected. Remaining: {len(self.active_connections)}")

    async def subscribe_ward(self, websocket: WebSocket, ward_id: str):
        """Subscribes a client to a specific ward stream."""
        async with self._lock:
            if ward_id not in self.ward_subscribers:
                self.ward_subscribers[ward_id] = set()
            self.ward_subscribers[ward_id].add(websocket)
            if websocket in self.active_connections:
                self.active_connections[websocket].add(f"ward:{ward_id}")

    async def broadcast(self, event_type: str, data: Any, ward_id: Optional[str] = None):
        """
        Broadcasts an event payload to matching subscribers.
        """
        payload = {
            "type": event_type,
            "ward_id": ward_id,
            "payload": data
        }
        message_str = json.dumps(payload, default=str)

        async with self._lock:
            recipients = set()
            for ws, channels in self.active_connections.items():
                if "all" in channels or event_type in channels:
                    recipients.add(ws)
                elif ward_id and f"ward:{ward_id}" in channels:
                    recipients.add(ws)

            if ward_id and ward_id in self.ward_subscribers:
                recipients.update(self.ward_subscribers[ward_id])

        # Push asynchronously to all targeted recipients
        dead_connections = []
        for ws in recipients:
            try:
                await ws.send_text(message_str)
            except Exception:
                dead_connections.append(ws)

        if dead_connections:
            for dead_ws in dead_connections:
                await self.disconnect(dead_ws)

    # Specific broadcast helpers
    async def broadcast_risk(self, ward_id: str, risk_score: float, risk_tier: str, details: Dict[str, Any]):
        await self.broadcast("risk", {
            "ward_id": ward_id,
            "risk_score": risk_score,
            "risk_tier": risk_tier,
            "details": details
        }, ward_id=ward_id)

    async def broadcast_report(self, report_data: Dict[str, Any]):
        await self.broadcast("reports", report_data, ward_id=report_data.get("ward_id"))

    async def broadcast_alert(self, alert_data: Dict[str, Any]):
        await self.broadcast("alerts", alert_data, ward_id=alert_data.get("ward_id"))

    async def broadcast_social(self, signal_data: Dict[str, Any]):
        await self.broadcast("social", signal_data, ward_id=signal_data.get("ward_id"))

    async def broadcast_sensor(self, sensor_data: Dict[str, Any]):
        await self.broadcast("signals", sensor_data, ward_id=sensor_data.get("ward_id"))


ws_manager = WebSocketManager()


@websocket_router.websocket("/ws/live")
async def websocket_live_feed(websocket: WebSocket):
    """
    General real-time WebSocket connection for GIS operations.
    Receives risk updates, alerts, reports, and social triage in real time.
    """
    await ws_manager.connect(websocket)
    try:
        # Send initial confirmation message
        await websocket.send_text(json.dumps({
            "type": "connection_ack",
            "message": "Connected to Mumbai Flood Intelligence Live WebSocket Stream",
            "channels": ["risk", "reports", "alerts", "signals", "social"]
        }))

        while True:
            # Listen for client keepalives / subscription adjustments
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
                action = msg.get("action")
                if action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif action == "subscribe_ward":
                    ward_id = msg.get("ward_id")
                    if ward_id:
                        await ws_manager.subscribe_ward(websocket, ward_id)
                        await websocket.send_text(json.dumps({"type": "subscribed", "ward_id": ward_id}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.warning(f"WebSocket client error: {exc}")
        await ws_manager.disconnect(websocket)


@websocket_router.websocket("/ws/wards/{ward_id}")
async def websocket_ward_feed(websocket: WebSocket, ward_id: str):
    """
    Dedicated ward telemetry stream for localized field operations.
    """
    await ws_manager.connect(websocket, initial_channels=[f"ward:{ward_id}", "alerts"])
    await ws_manager.subscribe_ward(websocket, ward_id)
    try:
        await websocket.send_text(json.dumps({
            "type": "ward_connection_ack",
            "ward_id": ward_id,
            "message": f"Connected to Ward {ward_id} stream"
        }))
        while True:
            text = await websocket.receive_text()
            if text == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)
