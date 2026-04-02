# py-auth

`py-auth` 是一个基于 FastAPI 的软件授权服务，包含管理后台、授权接口和多语言客户端 SDK。

适合用于：

- 管理设备授权状态
- 提供客户端心跳校验接口
- 维护后台用户与操作日志
- 为 Python、Go、TypeScript 客户端提供统一接入能力

## 功能概览

- 设备注册与心跳校验
- 授权开关管理
- 管理员登录与用户管理
- 操作日志审计
- Web 管理后台
- Python / Go / TypeScript 客户端 SDK
- 支持 SQLite 与 MySQL

## 快速开始

### 方式一：本地运行

本项目分为前后端两部分：

- 后端：FastAPI 服务
- 前端：Vue 管理后台

如果你希望本地直接通过后端访问完整页面，需要先构建前端，再启动后端。

1. 创建并激活虚拟环境

```bash
python -m venv .venv
.venv\Scripts\activate
```

2. 安装依赖

```bash
pip install -e .
```

3. 准备环境变量

```bash
copy env.example .env
```

4. 构建前端

```bash
cd web
pnpm install
pnpm build
cd ..
```

5. 启动后端服务

```bash
python main.py
```

默认地址：

- 服务端：`http://127.0.0.1:8000`
- 接口文档：`http://127.0.0.1:8000/docs`

首次启动会自动创建数据库表，并按 `.env` 中的 `ADMIN_USERNAME`、`ADMIN_PASSWORD` 初始化管理员账号。
如果未先构建前端，根路径只能返回后端状态信息，无法直接使用管理后台页面。

### 方式二：Docker 运行

直接启动：

```bash
docker compose up -d
```

默认使用 SQLite，并将数据库持久化到 Docker 卷 `auth_data`。

## 运行模式

自动运行时需要区分前后端模式，避免前端和后端各自启动但没有正确联通。

### 模式一：集成运行

适用于 Docker、部署环境或本地一体化启动。

- 后端运行在 `8000`
- 前端需要先执行 `pnpm build`
- 后端会自动托管 `web/dist`
- 访问入口为 `http://127.0.0.1:8000`

这种模式下只需要启动后端容器或 Python 服务，不需要单独启动 Vite。

### 模式二：前端开发模式

适用于本地联调。

- 后端运行在 `http://127.0.0.1:8000`
- 前端运行在 `http://127.0.0.1:3000`
- Vite 会将 `/api` 代理到 `8000`
- Vite 会将 `/ws` 代理到 `ws://127.0.0.1:8000`

建议启动顺序：

1. 先启动后端 `python main.py`
2. 再进入 `web` 目录执行 `pnpm dev`

这种模式下应访问 `http://127.0.0.1:3000`，不要直接访问 `8000` 根路径调试前端页面。

## 环境变量

常用配置如下：

- `DATABASE_TYPE`：数据库类型，`sqlite` 或 `mysql`
- `SQLITE_PATH`：SQLite 文件路径
- `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE`
- `SECRET_KEY`：服务端 JWT 密钥
- `CLIENT_SECRET`：客户端请求加密密钥，客户端与服务端必须一致
- `ACCESS_TOKEN_EXPIRE_MINUTES`：登录令牌过期时间
- `ADMIN_USERNAME` / `ADMIN_PASSWORD`：默认管理员账号

示例见 `env.example`。

## 项目结构

```text
.
├─app/            FastAPI 服务端代码
├─web/            Web 管理后台
├─client/         Python / Go / TypeScript 客户端 SDK
├─tools/          辅助工具脚本
├─main.py         服务入口
├─docker-compose.yaml
└─Dockerfile
```

## 主要接口

- `/api/auth/heartbeat`：客户端心跳与授权校验
- `/api/user/login`：后台用户登录
- `/api/user/me`：获取当前用户信息
- `/api/admin/users`：后台用户管理
- `/api/admin/config`：授权配置管理
- `/api/admin/logs`：操作日志查询与清理

## 前端说明

`web/dist` 存在时，服务会自动托管前端静态文件并在根路径提供后台页面。

前端本地开发：

```bash
cd web
pnpm install
pnpm dev
```

前端构建：

```bash
cd web
pnpm build
```

## 客户端 SDK

仓库内已包含多语言客户端：

- `client/python`
- `client/go`
- `client/ts`

详细使用说明见：

- `client/README.md`
- `client/python/README.md`

## 技术栈

- FastAPI
- SQLAlchemy
- SQLite / MySQL
- Vue 3 + Vite + Element Plus

## 备注

- 默认可直接使用 SQLite 启动
- 生产环境请替换 `SECRET_KEY`、`CLIENT_SECRET` 和默认管理员密码
- 仓库内的 `auth.db` 为本地开发数据库文件
