"""WebSocket — live score broadcast channel."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.ws_manager import manager
from ..services.livescore import fetch_live_scores

router = APIRouter(prefix="/api", tags=["ws"])


@router.websocket("/ws/scores")
async def websocket_scores(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        score = await fetch_live_scores()
        if score:
            await websocket.send_json(score)
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
