"""Real stream boundaries. Missing providers fail closed."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Query, WebSocket
from sse_starlette.sse import EventSourceResponse


router = APIRouter(tags=["stream"])


@router.websocket("/ws/v1/stream/ticks")
async def websocket_ticks(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.close(code=1013, reason="REAL_L2_FEED_UNAVAILABLE")


@router.get("/sse/v1/events/system")
async def sse_system_events(limit: int = Query(default=0, ge=0, le=1000)) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[dict[str, Any], None]:
        count = 0
        while limit == 0 or count < limit:
            payload = {
                "event": "HEARTBEAT",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "node": "omega_api_gateway",
            }
            yield {"event": "HEARTBEAT", "data": json.dumps(payload)}
            count += 1
            await asyncio.sleep(15)

    return EventSourceResponse(event_generator())
