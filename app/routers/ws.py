import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import get_user_by_username, verify_token
from app.database import SessionLocal
from app.models import Device, OperationLog
from app.schemas import DeviceResponse
from app.ws_manager import device_ws_manager

router = APIRouter(tags=["管理"])


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
    actor = None
    if token:
        payload = verify_token(token)
        if payload:
            username = payload.get("sub")
            if username:
                db = SessionLocal()
                try:
                    user = get_user_by_username(db, username)
                    if user and user.is_active:
                        actor = user.username
                finally:
                    db.close()
    if not actor:
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

                    db = SessionLocal()
                    try:
                        device = db.query(Device).filter(Device.device_id == device_id).first()
                        if not device:
                            raise ValueError("设备不存在")
                        original_created_at = device.created_at

                        if "remark" in allowed:
                            device.remark = allowed.get("remark")
                        if "is_authorized" in allowed:
                            device.is_authorized = bool(allowed.get("is_authorized"))

                        device.updated_at = datetime.now()
                        # created_at 由后端创建时写入，后续更新强制保持不变
                        device.created_at = original_created_at
                        db.add(OperationLog(
                            username=actor,
                            action="update_device",
                            target_type="device",
                            target_id=device.device_id,
                            detail=allowed
                        ))
                        db.commit()
                        db.refresh(device)
                        payload = {"device": DeviceResponse.model_validate(device).model_dump(mode="json")}
                    finally:
                        db.close()
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
                    db = SessionLocal()
                    try:
                        deleted_count = db.query(Device).filter(Device.device_id == device_id).delete()
                        if deleted_count == 0:
                            raise ValueError("设备不存在")
                        db.add(OperationLog(
                            username=actor,
                            action="delete_device",
                            target_type="device",
                            target_id=device_id,
                            detail=None
                        ))
                        db.commit()
                        payload = {"device_id": device_id}
                    finally:
                        db.close()
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
