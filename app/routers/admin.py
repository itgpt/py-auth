from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from datetime import datetime
from app.database import get_db
from app.models import Device, User, Config
from app.schemas import DeviceResponse, DeviceUpdate, ConfigItem, ConfigUpdate
from app.auth import get_current_user
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["管理"])


def get_device_or_404(device_id: str, db: Session) -> Device:
    """获取设备，不存在则抛出404异常"""
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
    """获取所有设备列表（需要登录），按更新时间降序排列"""
    total = db.query(Device).count()
    devices = db.query(Device).order_by(Device.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "devices": [DeviceResponse.model_validate(d) for d in devices]}

@router.get("/devices/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取单个设备信息（需要登录）"""
    return get_device_or_404(device_id, db)

@router.put("/devices/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    device_update: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新设备信息（需要登录）"""
    update_data = device_update.model_dump(exclude_unset=True)
    
    if not update_data:
        # 没有要更新的数据，直接返回设备信息
        return get_device_or_404(device_id, db)
    
    try:
        # 使用 get_device_or_404 获取设备，减少重复代码
        device = get_device_or_404(device_id, db)
        
        # 更新对象属性（直接修改对象，避免批量更新的锁竞争）
        for key, value in update_data.items():
            setattr(device, key, value)
        
        # 无论更新什么字段，都更新 updated_at 时间戳
        device.updated_at = datetime.now()
        
        # 提交更改（使用 flush 然后 commit，减少锁持有时间）
        db.flush()
        db.commit()
        db.refresh(device)  # 刷新对象以获取最新数据（包括数据库触发器的更新）
        
        return device
    except HTTPException:
        raise
    except OperationalError as e:
        db.rollback()
        logger.error(f"数据库锁定，更新设备失败: {e}")
        # 数据库锁定时，返回当前设备状态（不包含更新）
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
    """删除设备（需要登录）"""
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
    """获取所有配置（需要登录）"""
    configs = db.query(Config).all()
    return {c.key: c.value for c in configs}

@router.put("/config")
async def update_configs(
    config_update: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新配置（需要登录）"""
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

