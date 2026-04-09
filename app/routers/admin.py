import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.audit import add_operation_log
from app.auth import get_current_user, get_password_hash
from app.coerce import coerce_boolish
from app.database import get_db
from app.deps import require_admin
from app.models import Config, OperationLog, User
from app.schemas import (
    ConfigUpdate,
    OperationLogListResponse,
    OperationLogResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["管理"])

DEFAULT_CONFIGS = {"default_authorization": True}


@router.get("/config")
async def get_configs(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    config = db.query(Config).filter(Config.key == "default_authorization").first()
    if not config:
        return DEFAULT_CONFIGS.copy()
    return {"default_authorization": coerce_boolish(config.value)}


@router.put("/config")
async def update_configs(
    config_update: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed_keys = set(DEFAULT_CONFIGS.keys())
    normalized = {}
    for key, value in config_update.configs.items():
        if key not in allowed_keys:
            continue
        if key == "default_authorization":
            normalized[key] = coerce_boolish(value)

    for key, value in normalized.items():
        config = db.query(Config).filter(Config.key == key).first()
        if config:
            config.value = value
        else:
            new_config = Config(key=key, value=value)
            db.add(new_config)

    add_operation_log(
        db,
        username=current_user.username,
        action="update_config",
        target_type="config",
        target_id=None,
        detail={"configs": normalized},
    )

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"更新配置失败: {e}")
        raise HTTPException(status_code=500, detail="保存配置失败") from e

    return {"message": "配置已更新"}


@router.get("/users", response_model=list[UserResponse])
async def get_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return db.query(User).all()


@router.get("/logs", response_model=OperationLogListResponse)
async def get_operation_logs(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))
    query = db.query(OperationLog)
    total = query.count()
    logs = (
        query.order_by(OperationLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "logs": [OperationLogResponse.model_validate(item) for item in logs],
    }


@router.delete("/logs")
async def cleanup_operation_logs(
    days: int = Query(..., ge=0, description="清理天数，0 表示全部清空"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if days <= 0:
        deleted_count = db.query(OperationLog).delete()
        mode = "all"
    else:
        cutoff = datetime.now() - timedelta(days=days)
        deleted_count = (
            db.query(OperationLog).filter(OperationLog.created_at < cutoff).delete()
        )
        mode = "older_than_days"

    add_operation_log(
        db,
        username=current_user.username,
        action="cleanup_logs",
        target_type="operation_log",
        target_id=None,
        detail={"mode": mode, "days": days, "deleted_count": deleted_count},
    )
    db.commit()
    if days <= 0:
        message = "已清空全部审计日志"
    else:
        message = f"已清理 {days} 天前日志"
    return {"message": message, "deleted_count": deleted_count, "days": days}


@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    new_user = User(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        is_admin=user_data.is_admin,
        is_active=user_data.is_active,
    )
    db.add(new_user)
    add_operation_log(
        db,
        username=current_user.username,
        action="create_user",
        target_type="user",
        target_id=user_data.username,
        detail={"is_admin": user_data.is_admin, "is_active": user_data.is_active},
    )
    db.commit()
    db.refresh(new_user)
    return new_user


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user_data.password:
        db_user.password_hash = get_password_hash(user_data.password)

    for key, value in user_data.model_dump(
        exclude_unset=True, exclude={"password"}
    ).items():
        setattr(db_user, key, value)
    add_operation_log(
        db,
        username=current_user.username,
        action="update_user",
        target_type="user",
        target_id=db_user.username,
        detail={
            "updated_fields": list(user_data.model_dump(exclude_unset=True).keys()),
            "user_id": user_id,
        },
    )
    db.commit()
    db.refresh(db_user)
    return db_user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    username = db_user.username
    db.delete(db_user)
    add_operation_log(
        db,
        username=current_user.username,
        action="delete_user",
        target_type="user",
        target_id=username,
        detail={"user_id": user_id},
    )
    db.commit()
    return {"message": "用户已删除"}
