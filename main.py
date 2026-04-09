import datetime
import logging
import os
import sys
import tempfile
import traceback
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import init_admin_user
from app.database import Base, SessionLocal, engine
from app.middleware import setup_cors
from app.routers import admin, auth
from app.routers import user as user_router
from app.routers import ws as ws_router

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_database() -> None:
    """
    初始化数据库（使用文件锁确保多 worker 只执行一次）

    使用跨平台的文件锁机制，避免多进程/多worker重复初始化数据库。
    """
    lock_file = os.path.join(tempfile.gettempdir(), "py_auth_init.lock")

    try:
        # 跨平台文件锁实现
        if sys.platform == "win32":
            # Windows 平台使用 msvcrt 锁定
            import msvcrt

            lock_handle = open(lock_file, "w")
            try:
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
                _do_init()
            finally:
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
                lock_handle.close()
        else:
            # Unix/Linux 平台使用 fcntl 锁定
            import fcntl

            with open(lock_file, "w") as f:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    _do_init()
                except BlockingIOError:
                    # 另一个进程正在初始化，跳过
                    logger.debug("数据库初始化已由其他进程执行，跳过")
                    pass
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}", exc_info=True)
        # 记录详细错误信息但不中断启动
        logger.debug(f"初始化失败详情: {traceback.format_exc()}")


def _do_init() -> None:
    """执行数据库初始化"""
    try:
        # 创建数据库表
        Base.metadata.create_all(bind=engine)
        logger.info("数据库表创建成功")

        # 初始化管理员账户
        db = SessionLocal()
        try:
            admin_username, admin_password = init_admin_user(db)
            if admin_username and admin_password:
                logger.info(f"默认管理员账户: {admin_username}")
                # 生产环境建议记录密码到安全位置，这里只记录用户名
                logger.debug("管理员密码已设置，请查看环境变量 ADMIN_PASSWORD")
            else:
                logger.warning("管理员账户初始化失败或已存在")
        except Exception as e:
            logger.error(f"管理员账户初始化失败: {str(e)}", exc_info=True)
        finally:
            db.close()

    except Exception as e:
        logger.error(f"数据库初始化过程中发生错误: {str(e)}", exc_info=True)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    在应用启动时初始化数据库，在关闭时执行清理操作。
    """
    logger.info("应用启动中...")
    try:
        init_database()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"应用启动失败: {str(e)}")
        # 可以选择是否抛出异常中断启动
        # raise
    yield
    logger.info("应用关闭中...")
    # 这里可以添加清理逻辑，如关闭数据库连接池等


def create_application() -> FastAPI:
    """创建并配置 FastAPI 应用实例"""
    app = FastAPI(
        title="Python授权服务",
        description="软件授权管理系统",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 配置 CORS
    setup_cors(app)

    # 注册路由
    app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
    app.include_router(admin.router, prefix="/api/admin", tags=["管理"])
    app.include_router(user_router.router, prefix="/api/user", tags=["用户"])
    app.include_router(ws_router.router, prefix="/ws", tags=["WebSocket"])

    # 配置静态文件服务（前端）
    web_dist_path = os.path.join(os.path.dirname(__file__), "web", "dist")
    configure_static_files(app, web_dist_path)

    # 添加健康检查端点
    @app.get("/health", tags=["健康检查"])
    async def health_check():
        """健康检查端点"""
        return {
            "status": "healthy",
            "service": "py-auth",
            "version": "1.0.0",
            "timestamp": datetime.datetime.now().isoformat(),
        }

    return app


def configure_static_files(app: FastAPI, web_dist_path: str) -> None:
    """配置静态文件服务"""
    if not os.path.exists(web_dist_path):
        logger.warning(f"前端构建目录不存在: {web_dist_path}")
        logger.info("前端未构建，仅提供API服务")

        @app.get("/")
        async def root():
            return {
                "message": "Python授权服务后端运行中",
                "docs": "/docs",
                "api_endpoints": ["/api/auth", "/api/admin", "/api/user", "/ws"],
            }

        return

    # 挂载静态资源
    assets_path = os.path.join(web_dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
        logger.info(f"静态资源目录已挂载: {assets_path}")

    # 配置 SPA 路由
    index_path = os.path.join(web_dist_path, "index.html")
    if os.path.exists(index_path):

        @app.get("/")
        async def serve_index():
            """服务前端首页"""
            return FileResponse(index_path)

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """
            单页应用路由处理

            将所有非API和非WebSocket的请求重定向到前端首页，
            由前端路由处理。
            """
            # 排除API和WebSocket路径
            if full_path.startswith(
                ("api/", "ws/", "docs", "redoc", "openapi.json", "health")
            ):
                raise HTTPException(status_code=404, detail="Not found")

            # 检查是否为静态文件请求
            static_extensions = (
                ".css",
                ".js",
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".svg",
                ".ico",
                ".woff",
                ".woff2",
                ".ttf",
            )
            if full_path.endswith(static_extensions):
                # 让 FastAPI 的静态文件处理
                raise HTTPException(status_code=404, detail="Static file not found")

            return FileResponse(index_path)

        logger.info(f"SPA前端已配置，首页: {index_path}")
    else:
        logger.warning(f"前端首页文件不存在: {index_path}")


# 创建应用实例
app = create_application()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
