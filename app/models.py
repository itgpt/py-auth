from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text

from app.database import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(255), unique=True, index=True, nullable=False)
    software_name = Column(String(255), nullable=True)
    device_info = Column(JSON, nullable=True)
    remark = Column(Text, nullable=True)
    is_authorized = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
    last_check = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Device(id={self.id}, device_id={self.device_id}, authorized={self.is_authorized})>"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return (
            f"<User(id={self.id}, username={self.username}, is_admin={self.is_admin})>"
        )


class Config(Base):
    __tablename__ = "config"

    key = Column(String(255), primary_key=True, index=True)
    value = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<Config(key={self.key}, value={self.value})>"


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    target_type = Column(String(50), nullable=False, index=True)
    target_id = Column(String(255), nullable=True, index=True)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    def __repr__(self):
        return (
            f"<OperationLog(id={self.id}, username={self.username}, "
            f"action={self.action}, target_type={self.target_type}, target_id={self.target_id})>"
        )
