from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any

class EncryptedRequest(BaseModel):
    """加密的请求数据"""
    encrypted_data: str                    

class DeviceAuthRequest(BaseModel):
    """设备授权请求（检查/注册共用）"""
    device_id: str
    software_name: Optional[str] = None       
    device_info: Optional[Dict[str, Any]] = None                                                                                             

class DeviceResponse(BaseModel):
    id: int
    device_id: str
    software_name: Optional[str]       
    device_info: Optional[Dict[str, Any]]                                      
    remark: Optional[str]
    is_authorized: bool
    created_at: datetime = Field(description="注册时间：设备首次请求后不变")
    updated_at: Optional[datetime] = Field(
        default=None,
        description="管理变更追踪：管理员改授权/备注或设备信息（software_name、device_info）变更时刷新",
    )
    last_check: Optional[datetime] = Field(
        default=None,
        description="活跃度：每次成功心跳/授权校验时刷新",
    )

    class Config:
        from_attributes = True

class EncryptedResponse(BaseModel):
    """加密的响应数据"""
    encrypted_data: str                    

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
