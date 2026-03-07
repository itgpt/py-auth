from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from app.database import engine, Base, SessionLocal
from app.routers import auth, admin
from app.routers import ws as ws_router
from app.routers import user as user_router
from app.auth import init_admin_user
from app.middleware import setup_cors
import logging
import os
import sys

# 加载 .env 文件
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_database():
    """初始化数据库（使用文件锁确保多 worker 只执行一次）"""
    if sys.platform != "win32":
        import fcntl
        lock_file = "/tmp/py_auth_init.lock"
        try:
            with open(lock_file, "w") as f:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    _do_init()
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except BlockingIOError:
            pass
        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}")
    else:
        _do_init()

def _do_init():
    """执行数据库初始化"""
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表创建成功")
    db = SessionLocal()
    try:
        admin_username, admin_password = init_admin_user(db)
        logger.info(f"默认管理员账户: {admin_username} / {admin_password}")
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield

app = FastAPI(
    title="Python授权服务",
    description="软件授权管理系统",
    version="1.0.0",
    lifespan=lifespan
)

# CORS配置
setup_cors(app)

# 注册路由
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(user_router.router)
app.include_router(ws_router.router)

# 静态文件服务
web_dist_path = os.path.join(os.path.dirname(__file__), "web", "dist")
if os.path.exists(web_dist_path):
    # 挂载静态资源（JS、CSS、图片等）
    assets_path = os.path.join(web_dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    
    # 根路径返回前端页面
    @app.get("/")
    async def root():
        index_path = os.path.join(web_dist_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "前端文件未找到"}
    
    # SPA 路由支持：所有非 API 路径都返回 index.html
    # 注意：这个路由必须放在最后，因为 FastAPI 按顺序匹配路由
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # 排除 API 和文档路径（这些路由已经在上面注册了）
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path == "openapi.json":
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        
        # 检查是否是静态资源文件
        file_path = os.path.join(web_dist_path, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        
        # 其他路径返回 index.html（支持前端路由）
        index_path = os.path.join(web_dist_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not Found")
else:
    @app.get("/")
    async def root():
        """根路径"""
        return {"message": "启动成功，前端文件未构建"}

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=8000,
        reload=True
    )

