import json
from datetime import datetime

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


def _update_device_payload(device_id: str, update_data: dict) -> dict:
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if not device:
            raise ValueError("设备不存在")

        if "remark" in update_data:
            device.remark = update_data.get("remark")
        if "is_authorized" in update_data:
            device.is_authorized = bool(update_data.get("is_authorized"))

        device.updated_at = datetime.now()
        db.commit()
        db.refresh(device)
        return {"device": DeviceResponse.model_validate(device).model_dump(mode="json")}
    finally:
        db.close()


def _delete_device_payload(device_id: str) -> dict:
    db = SessionLocal()
    try:
        deleted_count = db.query(Device).filter(Device.device_id == device_id).delete()
        if deleted_count == 0:
            raise ValueError("设备不存在")
        db.commit()
        return {"device_id": device_id}
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
                continue

            if data.get("type") == "update_device":
                request_id = data.get("request_id")
                try:
                    device_id = str(data.get("device_id", "")).strip()
                    if not device_id:
                        raise ValueError("缺少 device_id")
                    raw_update = data.get("data") or {}
                    if not isinstance(raw_update, dict):
                        raise ValueError("data 格式错误")

                    allowed = {}
                    if "remark" in raw_update:
                        allowed["remark"] = raw_update.get("remark")
                    if "is_authorized" in raw_update:
                        allowed["is_authorized"] = raw_update.get("is_authorized")
                    if not allowed:
                        raise ValueError("缺少可更新字段")

                    payload = _update_device_payload(device_id, allowed)
                    payload.update({"type": "device_updated", "request_id": request_id})
                    await websocket.send_json(payload)
                    await device_ws_manager.broadcast({
                        "type": "devices_changed",
                        "action": "updated",
                        "device_id": device_id
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "request_id": request_id,
                        "message": str(e) or "更新失败"
                    })
                continue

            if data.get("type") == "delete_device":
                request_id = data.get("request_id")
                try:
                    device_id = str(data.get("device_id", "")).strip()
                    if not device_id:
                        raise ValueError("缺少 device_id")
                    payload = _delete_device_payload(device_id)
                    payload.update({"type": "device_deleted", "request_id": request_id})
                    await websocket.send_json(payload)
                    await device_ws_manager.broadcast({
                        "type": "devices_changed",
                        "action": "deleted",
                        "device_id": device_id
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "request_id": request_id,
                        "message": str(e) or "删除失败"
                    })
    except WebSocketDisconnect:
        device_ws_manager.disconnect(websocket)
    except Exception:
        device_ws_manager.disconnect(websocket)
