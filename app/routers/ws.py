import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import get_user_by_username, verify_token
from app.database import SessionLocal
from app.models import Device
from app.schemas import DeviceResponse
from app.ws_manager import device_ws_manager

router = APIRouter(tags=["管理"])


def _is_valid_token(token: str) -> bool:
    payload = verify_token(token)
    if not payload:
        return False

    username = payload.get("sub")
    if not username:
        return False

    db = SessionLocal()
    try:
        user = get_user_by_username(db, username)
        return bool(user and user.is_active)
    finally:
        db.close()


def _load_devices_payload(page: int, page_size: int) -> dict:
    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))

    db = SessionLocal()
    try:
        query = db.query(Device)
        total = query.count()
        devices = (
            query.order_by(Device.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {"total": total, "devices": [DeviceResponse.model_validate(d).model_dump(mode="json") for d in devices]}
    finally:
        db.close()


@router.websocket("/ws")
async def device_events(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if not token or not _is_valid_token(token):
        await websocket.close(code=4401, reason="unauthorized")
        return

    await device_ws_manager.connect(websocket)
    await websocket.send_json({"type": "connected"})
    initial_payload = _load_devices_payload(page=1, page_size=50)
    initial_payload.update({"type": "devices_list"})
    await websocket.send_json(initial_payload)
    try:
        while True:
            text = await websocket.receive_text()
            try:
                data = json.loads(text)
            except Exception:
                continue

            if data.get("type") == "get_devices":
                request_id = data.get("request_id")
                page = data.get("page", 1)
                page_size = data.get("page_size", 50)
                payload = _load_devices_payload(page, page_size)
                payload.update({"type": "devices_list", "request_id": request_id})
                await websocket.send_json(payload)
    except WebSocketDisconnect:
        device_ws_manager.disconnect(websocket)
    except Exception:
        device_ws_manager.disconnect(websocket)
