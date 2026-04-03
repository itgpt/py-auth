# Python 客户端 SDK

## 依赖关系

| 文档 | 说明 |
|------|------|
| [client/README.md](/e:/py-auth/client/README.md) | SDK 总览与三端方法对照 |
| [docs/dev/client-storage.md](/e:/py-auth/docs/dev/client-storage.md) | 存储、`device_id`、状态文件与加解密约定 |

## 安装

```bash
pip install py-auth-client --extra-index-url https://www.geekery.cn/pip/simple/
```

## `AuthClient` 参数

| 参数 | 是否必需 | 说明 |
|------|----------|------|
| `server_url` | 必填 | 服务地址 |
| `software_name` | 必填 | 产品名称 |
| `client_secret` | 条件必填 | 参数可省略，但运行时必须通过参数或环境变量 `CLIENT_SECRET` 提供 |
| `device_id` | 可选 | 省略时自动生成或复用 |
| `device_info` | 可选 | 省略时自动采集 |
| `cache_validity_days` | 可选 | 本地缓存有效期，默认 `7` |
| `check_interval_days` | 可选 | 检查间隔，默认 `2` |
| `debug` | 可选 | 是否输出调试日志 |
| `software_version` | 可选 | 软件版本 |

## 示例

### 启动时要求授权通过

```python
from py_auth_client import AuthClient, AuthorizationError

client = AuthClient(
    server_url="http://localhost:8000",
    software_name="我的软件",
    client_secret="your-secret",
)

try:
    client.require_authorization()
except AuthorizationError as e:
    raise SystemExit(f"授权失败: {e}")
```

### 检查授权并按结果处理

```python
result = client.check_authorization()

if result.get("success") and result.get("authorized"):
    print("已授权")
else:
    print("未授权或校验失败：", result.get("message", ""))
```

### 仅读取本地授权信息

```python
info = client.get_authorization_info()
print(
    info.get("authorized"),
    info.get("message"),
    info.get("device_id"),
    info.get("remaining_time"),
)
```

常见字段包括：

- `authorized`
- `message`
- `device_id`
- `server_url`
- `remaining_time`
- `cache_valid`

### 清除本地缓存

```python
client.clear_cache()
```

### 不抛异常，直接返回布尔值

```python
ok = client.require_authorization(raise_exception=False)
print(ok)
```

开发与发布说明见 [docs/dev/client-python-release.md](/e:/py-auth/docs/dev/client-python-release.md)。
