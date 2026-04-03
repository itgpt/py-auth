## 设备字段说明

本文说明管理后台设备列表和详情页中的主要字段含义。

### 设备 ID `device_id`

`device_id` 由客户端生成，管理后台仅负责展示，用于区分不同设备。

### 设备详情 `device_info`

管理后台以 JSON 形式展示 `device_info`。官方客户端会自动附带 `device_info.sdk`。

| 字段 | 说明 |
|------|------|
| `language` | SDK 语言，取值通常为 `python`、`go`、`typescript` |
| `sdk_name` | SDK 名称 |
| `sdk_version` | SDK 版本 |
| `runtime` | 运行时版本 |
| `heartbeat_times` | 当前设备累计成功心跳次数 |

设备快照 `device_info_snapshot` 会在授权成功后落盘，不包含当次 `sdk.heartbeat_times`。

### 常见子对象

| 字段 | 说明 |
|------|------|
| `system` | 主机名、操作系统、内核、机器信息、用户名、运行时长等 |
| `network` | MAC、IP、网络接口、公网 IP 等 |
| `memory` | 内存总量、空闲量、可用量 |
| `cpu` | CPU 型号、核心数、频率等 |
| `disk` | 磁盘摘要与卷信息 |

旧版本数据中的字段名可能不同，应以实际返回的 JSON 结构为准。

## 时间字段

| 字段 | 更新时机 | 含义 |
|------|----------|------|
| `created_at` | 设备首次请求时写入，之后不再改变 | 注册时间 |
| `updated_at` | 管理员修改授权、备注，或设备上报的 `software_name`、`device_info` 发生变化时更新 | 最近一次设备记录变更时间 |
| `last_check` | 每次成功心跳或授权校验时更新 | 最近一次成功校验时间 |

## 常见问题

**为什么 `last_check` 经常变化？**  
因为每次成功心跳或授权校验都会刷新该字段。

**`updated_at` 和 `last_check` 有什么区别？**  
`updated_at` 表示设备记录发生变更的时间，`last_check` 表示最近一次成功校验的时间。

**`created_at` 可以修改吗？**  
不可以。该字段在设备首次写入时确定。
