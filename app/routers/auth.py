import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import decrypt_request_data, encrypt_response_data
from app.coerce import coerce_boolish
from app.database import get_db
from app.models import Config, Device
from app.schemas import DeviceAuthRequest, EncryptedRequest, EncryptedResponse
from app.ws_manager import device_ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["授权"])


def _process_device(request: DeviceAuthRequest, db: Session) -> tuple[Device, bool]:
    device = db.query(Device).filter(Device.device_id == request.device_id).first()

    created = False

    if device:
        trackable_changed = False
        if (
            request.software_name is not None
            and request.software_name != device.software_name
        ):
            device.software_name = request.software_name
            trackable_changed = True
        if (
            request.device_info is not None
            and request.device_info != device.device_info
        ):
            device.device_info = request.device_info
            trackable_changed = True
        if trackable_changed:
            device.updated_at = datetime.now()
    else:

        default_auth_config = (
            db.query(Config).filter(Config.key == "default_authorization").first()
        )
        is_authorized = True
        if default_auth_config is not None:
            is_authorized = coerce_boolish(default_auth_config.value, if_none=True)

        device = Device(
            device_id=request.device_id,
            software_name=request.software_name,
            device_info=request.device_info,
            is_authorized=is_authorized,
        )
        db.add(device)
        created = True

    device.last_check = datetime.now()
    db.commit()
    db.refresh(device)

    return device, created


@router.post("/heartbeat", response_model=EncryptedResponse)
async def heartbeat(request: EncryptedRequest, db: Session = Depends(get_db)):
    """设备心跳接口：检查授权状态、注册/更新设备（请求和响应都使用AES加密）"""
    data = decrypt_request_data(request.encrypted_data)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="解密失败，无法验证设备"
        )
    auth_request = DeviceAuthRequest(**data)
    device, created = _process_device(auth_request, db)

    await device_ws_manager.broadcast(
        {
            "type": "devices_changed",
            "action": "created" if created else "heartbeat",
            "device_id": device.device_id,
        }
    )

    response_data = {
        "authorized": device.is_authorized,
        "message": "设备已授权" if device.is_authorized else "设备未授权",
    }

    encrypted = encrypt_response_data(response_data)
    if not encrypted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="加密响应失败"
        )

    return EncryptedResponse(encrypted_data=encrypted)
