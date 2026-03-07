from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from datetime import datetime
from app.database import get_db
from app.models import Device, User, Config
from app.schemas import (
    DeviceResponse, DeviceUpdate,
    ConfigItem, ConfigUpdate,
    UserResponse, UserCreate, UserUpdate
)
from app.auth import get_current_user, get_password_hash
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["管理"])

def get_device_or_404(device_id: str, db: Session) -> Device:
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    return device

@router.get("/devices")
async def get_devices(
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Device)
    total = query.count()
    devices = query.order_by(Device.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "devices": [DeviceResponse.model_validate(d) for d in devices]}

@router.get("/devices/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return get_device_or_404(device_id, db)

@router.put("/devices/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    device_update: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    update_data = device_update.model_dump(exclude_unset=True)
    if not update_data:
        return get_device_or_404(device_id, db)
    
    try:
        device = get_device_or_404(device_id, db)
        for key, value in update_data.items():
            setattr(device, key, value)
        device.updated_at = datetime.now()
        db.flush()
        db.commit()
        db.refresh(device)
        return device
    except HTTPException:
        raise
    except OperationalError as e:
        db.rollback()
        logger.error(f"数据库锁定，更新设备失败: {e}")
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if device:
            return device
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")
    except Exception as e:
        db.rollback()
        logger.error(f"更新设备时发生错误: {e}")
        raise HTTPException(status_code=500, detail="更新失败，请稍后重试")

@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    deleted_count = db.query(Device).filter(Device.device_id == device_id).delete()
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="设备不存在")
    db.commit()
    return {"message": "已删除"}

@router.get("/config")
async def get_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    configs = db.query(Config).all()
    return {c.key: c.value for c in configs}

@router.put("/config")
async def update_configs(
    config_update: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    for key, value in config_update.configs.items():
        config = db.query(Config).filter(Config.key == key).first()
        if config:
            config.value = value
        else:
            new_config = Config(key=key, value=value)
            db.add(new_config)
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"更新配置失败: {e}")
        raise HTTPException(status_code=500, detail="保存配置失败")
        
    return {"message": "配置已更新"}


def check_admin(current_user: User):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="没有权限")

@router.get("/users", response_model=list[UserResponse])
async def get_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)
    return db.query(User).all()

@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    new_user = User(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        is_admin=user_data.is_admin,
        is_active=user_data.is_active
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    if user_data.password:
        db_user.password_hash = get_password_hash(user_data.password)
    
    for key, value in user_data.model_dump(exclude_unset=True, exclude={'password'}).items():
        setattr(db_user, key, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    db.delete(db_user)
    db.commit()
    return {"message": "用户已删除"}

