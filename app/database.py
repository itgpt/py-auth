from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pydantic_settings import BaseSettings, SettingsConfigDict
import urllib.parse
import os

class Settings(BaseSettings):
                          
    database_type: str = "sqlite"
               
    sqlite_path: str = "auth.db"
                                         
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "password"
    mysql_database: str = "auth_db"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,              
        extra="ignore"             
    )

settings = Settings()

             
if settings.database_type.lower() == "mysql":
              
    encoded_password = urllib.parse.quote_plus(settings.mysql_password)
    DATABASE_URL = f"mysql+pymysql://{settings.mysql_user}:{encoded_password}@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}?charset=utf8mb4"
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=10,
        max_overflow=20,
        echo=False
    )
else:
                 
    if os.path.isabs(settings.sqlite_path):
                      
        sqlite_path = settings.sqlite_path
    else:
                          
        sqlite_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), settings.sqlite_path)
    
            
    sqlite_dir = os.path.dirname(sqlite_path)
    if sqlite_dir and not os.path.exists(sqlite_dir):
        os.makedirs(sqlite_dir, exist_ok=True)
    
    DATABASE_URL = f"sqlite:///{sqlite_path}"
    engine = create_engine(
        DATABASE_URL,
        connect_args={
            "check_same_thread": False,                 
            "timeout": 20.0                   
        },
        pool_pre_ping=True,               
        echo=False
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

