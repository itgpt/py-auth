from fastapi import Depends, HTTPException

from app.auth import get_current_user
from app.models import User


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="没有权限")
    return current_user
