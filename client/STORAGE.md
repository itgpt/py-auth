# 客户端本地存储说明（Python / Go / TypeScript）

存储根目录与 `device_id`、状态文件共用；API 不提供单独指定缓存目录，由各端 `get_client_storage_root` / `DefaultClientStorageRoot` / `getClientStorageRoot` 决定。

## 1. 默认存储根

| 系统 | 路径 |
|------|------|
| Windows | `%ProgramData%\.RuntimeRepository` |
| Linux / macOS 等 | 系统临时目录下 `.runtime-repository`（随 `TMPDIR` 等变化） |

首次写入前会尝试创建。客户端构造时只解析一次该根路径，避免与 `device_id` 持久化不一致。调试模式下会在首次检查前打印状态包路径与是否存在等信息。

## 2. 状态文件 `state_{serverHash12}_default.dat`

- **规范化 `server_url`：** `strip` 后去尾 `/`，三端一致。
- **文件名：** `state_` + 上述字符串 UTF-8 的 SHA256 十六进制**前 12 位** + `_default.dat`。
- **密钥：** 同一规范化 URL 的 UTF-8 → SHA256 取 **32 字节** 作为 AES-256 密钥（与 `device_id`、`software_name` 无关）。
- **磁盘格式：** 整份根对象 JSON（UTF-8）→ AES-256-GCM：**12 字节 nonce ‖ 密文 ‖ 16 字节 tag**；不对 JSON 内部再加密。
- **明文根对象：** 键为各产品 `software_name`，值为该产品条目。根级保留键（不可作产品名）：`apps`、`heartbeat_times`、`device_id`、`last_success_at`。读盘后去掉顶层误存的 `device_id`；写盘时去掉根上 `apps`（若存在）。

| 条目内键 | 含义 |
|----------|------|
| `device_id` | 与请求一致 |
| `last_success_at` | 末次成功落盘 Unix 时间（秒，浮点） |
| `heartbeat_times` | 成功心跳累计 |
| `device_info_snapshot` | 上次成功时的 `device_info`（结构同心跳，不含当次 `sdk.heartbeat_times`）；冷启动可复用。`clear_cache` 等会清除 |

`cache_validity_days` 只影响解密后是否信任快照，不参与加解密。

## 3. `device_id`

与 Python `build_device_id` 对齐（含 `software_name`、硬件与系统字段、`SHA256` 前 32 位十六进制等）。三端尽量对齐采集细节，仍可能因 OS/API 有微小差异；需字节级一致请显式传入同一 `device_id`。

## 4. 其它

| 位置 | 内容 |
|------|------|
| `CLIENT_SECRET` | 心跳请求体加解密，不在上述目录 |
| 服务端 SQLite | 默认 `auth.db` 等，非客户端文件 |

## 5. 多客户端共用同一状态文件

同一规范化 `server_url`、同一存储根、同一状态文件名即可；各产品各占根对象上一个 `software_name` 键。衔接旧数据时确认条目内 `device_id` 与服务端一致。强一致建议显式传同一 `device_id`。

## 6. 解密工具

仓库根执行：`python tools/decrypt_state_bundle.py`（可选密文路径参数）。依赖 `cryptography`；`server_url` 从环境或 `.env` 推断，须与客户端完全一致。详见脚本内说明。

## 7. 心跳与 API（摘要）

每次 `check_*` / `require_*`：单次读盘 → 发心跳 → 成功则写回（含 `heartbeat_times`、`device_info_snapshot`）。`get_*_authorization_info` 只读盘、不联网。`device_info.sdk` 内放 `heartbeat_times`；`system` / `network` / `memory` / `cpu` / `disk` 等结构三端对齐，以实际上报为准。

## 8. 运行环境

Python：CPython 3.x，`psutil`、`cryptography`。Go：标准 `GOOS`。TypeScript：Node 18+，`node:*`。未列平台以实现代码为准。
