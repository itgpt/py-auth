from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Config, OperationLog
from app.schemas import (
    ConfigUpdate,
    UserResponse, UserCreate, UserUpdate, OperationLogResponse, OperationLogListResponse
)
from app.auth import get_current_user, get_password_hash
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["管理"])

DEFAULT_CONFIGS = {
    "default_authorization": True
}


def _normalize_config_value(key: str, value):
    """规范化配置值，确保关键配置类型稳定。"""
    if key == "default_authorization":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    return value


def _merged_configs(db: Session) -> dict:
    db_configs = {c.key: c.value for c in db.query(Config).all()}
    merged = DEFAULT_CONFIGS.copy()
    for key in DEFAULT_CONFIGS.keys():
        if key in db_configs:
            merged[key] = db_configs[key]
    for key in ("default_authorization",):
        merged[key] = _normalize_config_value(key, merged.get(key))
    return merged


def _add_operation_log(
    db: Session,
    username: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    detail: dict | None = None
):
    db.add(OperationLog(
        username=username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail
    ))

@router.get("/config")
async def get_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return _merged_configs(db)

@router.put("/config")
async def update_configs(
    config_update: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    allowed_keys = set(DEFAULT_CONFIGS.keys())
    normalized = {}
    for key, value in config_update.configs.items():
        if key not in allowed_keys:
            continue
        normalized[key] = _normalize_config_value(key, value)

    for key, value in normalized.items():
        config = db.query(Config).filter(Config.key == key).first()
        if config:
            config.value = value
        else:
            new_config = Config(key=key, value=value)
            db.add(new_config)

    _add_operation_log(
        db,
        username=current_user.username,
        action="update_config",
        target_type="config",
        target_id=None,
        detail={"configs": normalized}
    )
    
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


@router.get("/logs", response_model=OperationLogListResponse)
async def get_operation_logs(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_admin(current_user)
    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))
    query = db.query(OperationLog)
    total = query.count()
    logs = (
        query
        .order_by(OperationLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "logs": [OperationLogResponse.model_validate(item) for item in logs]
    }

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
    _add_operation_log(
        db,
        username=current_user.username,
        action="create_user",
        target_type="user",
        target_id=user_data.username,
        detail={"is_admin": user_data.is_admin, "is_active": user_data.is_active}
    )
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
    _add_operation_log(
        db,
        username=current_user.username,
        action="update_user",
        target_type="user",
        target_id=db_user.username,
        detail={
            "updated_fields": list(user_data.model_dump(exclude_unset=True).keys()),
            "user_id": user_id
        }
    )
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
    
    username = db_user.username
    db.delete(db_user)
    _add_operation_log(
        db,
        username=current_user.username,
        action="delete_user",
        target_type="user",
        target_id=username,
        detail={"user_id": user_id}
    )
    db.commit()
    return {"message": "用户已删除"}
