# py-auth

`py-auth` 是一个基于 FastAPI 的软件授权服务，包含：

- 授权服务接口
- Web 管理后台
- Python / Go / TypeScript 客户端 SDK

适用于设备授权校验、后台管理、操作审计和多语言客户端接入。

## 功能概览

- 设备注册与心跳校验
- 授权状态管理
- 管理员登录与用户管理
- 操作日志审计
- Web 管理后台
- 支持 SQLite 和 MySQL

## 快速开始

### 方式一：Docker 运行

使用默认编排文件启动：

```bash
docker compose up -d
```

说明：

- 使用 [docker-compose.yaml](/e:/py-auth/docker-compose.yaml)
- 默认使用 SQLite
- 数据持久化到 Docker 卷 `auth_data`
- 服务地址：`http://127.0.0.1:8000`
- 接口文档：`http://127.0.0.1:8000/docs`

### 方式二：本地运行

本项目分为前后端两部分：

- 后端：FastAPI 服务
- 前端：Vue 管理后台

如果你希望通过后端统一访问完整页面，需要先构建前端，再启动后端。

1. 创建并激活虚拟环境

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. 安装后端依赖

```powershell
pip install -e .
```

3. 准备环境变量

```powershell
Copy-Item env.example .env
```

4. 构建前端

```powershell
Set-Location web
pnpm install
pnpm build
Set-Location ..
```

5. 启动后端

```powershell
python main.py
```

说明：

- 本地运行默认地址：`http://127.0.0.1:8000`
- 接口文档：`http://127.0.0.1:8000/docs`
- 首次启动会自动创建数据库表，并按 `.env` 中的 `ADMIN_USERNAME`、`ADMIN_PASSWORD` 初始化管理员账号
- 如果未先构建前端，根路径只能返回后端状态信息，无法直接使用管理后台页面

## 运行模式

### 集成运行

适用于 Docker、部署环境或本地一体化运行。

- 访问入口：`http://127.0.0.1:8000`
- 后端直接托管 `web/dist`
- 本地一体化运行前需要先执行 `pnpm build`
- Docker 镜像构建时会自动完成前端构建

### 前端开发模式

适用于本地联调。

- 后端地址：`http://127.0.0.1:8000`
- 前端地址：`http://127.0.0.1:3000`
- Vite 会将 `/api` 代理到 `8000`
- Vite 会将 `/ws` 代理到 `ws://127.0.0.1:8000`

建议启动顺序：

1. 启动后端：`python main.py`
2. 进入 `web` 目录执行：`pnpm dev`

在该模式下，应访问 `http://127.0.0.1:3000` 调试前端页面。

## 环境变量

| 变量 | 说明 |
|------|------|
| `DATABASE_TYPE` | 数据库类型，`sqlite` 或 `mysql` |
| `SQLITE_PATH` | SQLite 文件路径 |
| `MYSQL_HOST` | MySQL 主机 |
| `MYSQL_PORT` | MySQL 端口 |
| `MYSQL_USER` | MySQL 用户名 |
| `MYSQL_PASSWORD` | MySQL 密码 |
| `MYSQL_DATABASE` | MySQL 数据库名 |
| `SECRET_KEY` | 服务端 JWT 密钥 |
| `CLIENT_SECRET` | 客户端与服务端共享的请求加密密钥，必须保持一致 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 登录令牌过期时间，单位为分钟 |
| `ADMIN_USERNAME` | 默认管理员用户名 |
| `ADMIN_PASSWORD` | 默认管理员密码 |

示例见 [env.example](/e:/py-auth/env.example)。

## 项目结构

```text
.
├─ app/                  FastAPI 服务端代码
├─ client/               多语言客户端 SDK
├─ docs/dev/             开发文档
├─ tools/                辅助工具脚本
├─ web/                  Web 管理后台
├─ main.py               服务入口
├─ docker-compose.yaml   Docker 编排文件
└─ Dockerfile            Docker 镜像构建文件
```

## 主要接口

- `/api/auth/heartbeat`：客户端心跳与授权校验
- `/api/user/login`：后台用户登录
- `/api/user/me`：获取当前用户信息
- `/api/admin/users`：后台用户管理
- `/api/admin/config`：授权配置管理
- `/api/admin/logs`：操作日志查询与清理
- `/ws`：后台设备列表的实时更新 WebSocket，需要携带登录令牌

## 前端说明

当 `web/dist` 存在时，后端会自动托管前端静态文件，并在根路径提供后台页面。

前端开发：

```powershell
Set-Location web
pnpm install
pnpm dev
```

前端构建：

```powershell
Set-Location web
pnpm build
```

## 客户端 SDK

用户文档：

| 文档 | 说明 |
|------|------|
| [client/README.md](/e:/py-auth/client/README.md) | 客户端 SDK 总览 |
| [client/python/README.md](/e:/py-auth/client/python/README.md) | Python 客户端 SDK 使用说明 |
| [client/go/README.md](/e:/py-auth/client/go/README.md) | Go 客户端 SDK 使用说明 |
| [client/ts/README.md](/e:/py-auth/client/ts/README.md) | TypeScript 客户端 SDK 使用说明 |
| [web/src/docs/usage.md](/e:/py-auth/web/src/docs/usage.md) | 管理后台设备字段说明 |

开发文档：

| 文档 | 说明 |
|------|------|
| [docs/dev/client-storage.md](/e:/py-auth/docs/dev/client-storage.md) | 客户端本地存储、状态文件与加解密约定 |
| [docs/dev/client-python-release.md](/e:/py-auth/docs/dev/client-python-release.md) | Python 客户端构建与发布 |
| [docs/dev/client-ts-build.md](/e:/py-auth/docs/dev/client-ts-build.md) | TypeScript 客户端构建说明 |

## 备注

- 默认可以直接使用 SQLite 启动
- 生产环境必须替换 `SECRET_KEY`、`CLIENT_SECRET` 和默认管理员密码
- 仓库中的 `auth.db` 是本地开发数据库文件
