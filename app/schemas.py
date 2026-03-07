from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any

class EncryptedRequest(BaseModel):
    """加密的请求数据"""
    encrypted_data: str  # AES加密后的base64字符串

class DeviceAuthRequest(BaseModel):
    """设备授权请求（检查/注册共用）"""
    device_id: str
    software_name: Optional[str] = None  # 软件名
    device_info: Optional[Dict[str, Any]] = None  # 设备信息（JSON格式，包含hostname等）

class DeviceResponse(BaseModel):
    id: int
    device_id: str
    software_name: Optional[str]  # 软件名
    device_info: Optional[Dict[str, Any]]  # 设备信息（JSON格式，包含hostname等）
    remark: Optional[str]
    is_authorized: bool
    created_at: datetime
    updated_at: Optional[datetime]
    last_check: Optional[datetime]
    
    class Config:
        from_attributes = True

class EncryptedResponse(BaseModel):
    """加密的响应数据"""
    encrypted_data: str  # AES加密后的base64字符串

class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: Optional[bool] = False
    is_active: Optional[bool] = True

class UserUpdate(BaseModel):
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    is_admin: bool

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class ConfigUpdate(BaseModel):
    configs: Dict[str, Any]


class OperationLogResponse(BaseModel):
    id: int
    username: str
    action: str
    target_type: str
    target_id: Optional[str]
    detail: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class OperationLogListResponse(BaseModel):
    total: int
    logs: list[OperationLogResponse]
