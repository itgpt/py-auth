from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import logging
from app.database import get_db
from app.models import Device, Config
from app.schemas import DeviceAuthRequest, EncryptedRequest, EncryptedResponse
from app.auth import decrypt_request_data, encrypt_response_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["授权"])


def _to_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _decrypt_request_or_raise(encrypted_data: str) -> dict:
    """解密请求数据，失败则抛出异常"""
    data = decrypt_request_data(encrypted_data)
    if not data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="解密失败，无法验证设备")
    return data


def _process_device(request: DeviceAuthRequest, db: Session) -> Device:
    """
    统一处理设备逻辑：设备存在则更新信息，不存在则创建
    
    Args:
        request: 设备授权请求
        db: 数据库会话
        
    Returns:
        处理后的设备对象
    """
    device = db.query(Device).filter(Device.device_id == request.device_id).first()
    
    if device:
        # 设备存在：更新设备信息
        if request.software_name is not None:
            device.software_name = request.software_name
        if request.device_info is not None:
            device.device_info = request.device_info
    else:
        # 获取默认授权配置
        default_auth_config = db.query(Config).filter(Config.key == "default_authorization").first()
        is_authorized = True
        if default_auth_config is not None:
            is_authorized = _to_bool(default_auth_config.value, default=True)

        # 设备不存在：创建新设备
        device = Device(
            device_id=request.device_id,
            software_name=request.software_name,
            device_info=request.device_info,
            is_authorized=is_authorized
        )
        db.add(device)
    
    # 更新最后检查时间（使用本地时间，与 created_at 和 updated_at 保持一致）
    device.last_check = datetime.now()
    db.commit()
    db.refresh(device)
    
    return device


@router.post("/heartbeat", response_model=EncryptedResponse)
async def heartbeat(request: EncryptedRequest, db: Session = Depends(get_db)):
    """设备心跳接口：检查授权状态、注册/更新设备（请求和响应都使用AES加密）"""
    auth_request = DeviceAuthRequest(**_decrypt_request_or_raise(request.encrypted_data))
    device = _process_device(auth_request, db)
    
    response_data = {
        "authorized": device.is_authorized,
        "message": "设备已授权" if device.is_authorized else "设备未授权"
    }
    
    encrypted = encrypt_response_data(response_data)
    if not encrypted:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="加密响应失败")
    
    return EncryptedResponse(encrypted_data=encrypted)

