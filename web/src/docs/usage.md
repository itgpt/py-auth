## 设备字段说明

### 设备 ID (`device_id`)

由客户端按与 Python 参考实现一致的规则生成（MAC、磁盘/根分区、CPU/内存/磁盘容量、系统与架构字符串等；含 `software_name`）。同一 `server_url` 与存储根下三端共用单个加密状态文件，各产品以 `software_name` 为键分条目存储；详见 `client/STORAGE.md`。

### 设备详情 (`device_info`) 与 `sdk`

管理端以 JSON 展示。官方客户端自动附带 `device_info.sdk`：

| 字段（`device_info.sdk`） | 说明 |
|---------------------------|------|
| `language` | `python` / `go` / `typescript` |
| `sdk_name` / `sdk_version` / `runtime` | 包名、版本、运行时版本 |
| `heartbeat_times` | 仅心跳请求：累计成功次数；与状态包条目内 `heartbeat_times` 同义 |

授权成功落盘 `device_info_snapshot`（不含当次 `sdk.heartbeat_times`），下次冷启动可复用。各子对象概要：

| 字段 | 说明 |
|------|------|
| `system` | 主机名、OS、内核/机器信息、用户名、运行时时长等 |
| `network` | 优选 MAC/IP、`interfaces`、`public_ip`（外网探测失败可缺省） |
| `memory` | `total_gb`、`free_gb`、`available_gb` 等 |
| `cpu` | `model`、`count`、`physical_count`、`freq_*` 等 |
| `disk` | 根卷摘要；有明细时为 `models` → `volumes`（`mount`、`total_gb`、`free_gb` 等）。历史数据可能有旧字段名 |

---

### 时间类字段

| 字段 | 何时更新 | 用途 |
|------|----------|------|
| `created_at` | 设备首次请求后不变 | 注册时间 |
| `updated_at` | 管理员改授权/备注或设备信息变更 | 管理变更追踪 |
| `last_check` | 每次**成功**心跳/授权校验 | 活跃度 |

列表默认可按上述字段排序（点击表头切换升降序）。

---

## 客户端缓存（与列表字段的关系）

检查类 API 会先在线心跳，成功则更新本地加密状态包；仅读接口不联网、不增心跳计数。在线失败时，若在本地快照有效期内（默认 7 天）仍可使用上次成功结果。检查间隔（默认 2 天）只用于客户端 `needs_check` 类提示，不用于跳过心跳。默认存储与文件命名见 `client/STORAGE.md`。

---

## 常见问题

**活跃度（`last_check`）为什么常变？** 每次成功心跳/授权校验都会刷新。本地 7 天窗口是离线容错，不是减少心跳。

**管理变更追踪与活跃度？** `updated_at` 在管理员改授权/备注或设备 `software_name`/`device_info` 变更时刷新；`last_check` 表示最近一次成功校验。

**注册时间（`created_at`）能改吗？** 不能，设备首次请求写入后固定。
