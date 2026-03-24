# 客户端 SDK（Python / Go / TypeScript）

本地状态包格式、默认存储路径与 `device_id` 规则见 [STORAGE.md](./STORAGE.md)。管理端展示的 `device_info` 字段见 [web/src/docs/usage.md](../web/src/docs/usage.md)。

**三端一致：** 检查类方法（`check_authorization` / `CheckAuthorization` / `checkAuthorization` 及 `require_*`）每次会先请求在线心跳，成功则更新加密状态包；`get_authorization_info` 等只读本地、不联网。在线失败时，若在 `cache_validity_days`（默认 7 天）内仍信任上次成功快照。`check_interval_days` 仅影响 `needs_check` 类自检，不跳过心跳。网络请求体加密用 `CLIENT_SECRET`；磁盘状态包密钥由规范化后的 `server_url` 派生（见 STORAGE）。

示例程序：`client/python/example.py`、`client/go/examples/main.go`、`client/ts/example.ts` 从仓库根 `.env` 读 `CLIENT_SECRET`（相对路径向上级数因目录深度不同）。

---

## Python

```bash
pip install py-auth-client --extra-index-url https://www.geekery.cn/pip/simple/
```

```python
from py_auth_client import AuthClient, AuthorizationError

client = AuthClient(
    server_url="http://localhost:8000",
    software_name="我的软件",
    client_secret="your-secret",  # 可省略，读环境变量 CLIENT_SECRET
)
try:
    client.require_authorization()
except AuthorizationError as e:
    raise SystemExit(str(e))
```

**参数：** 必填 `server_url`、`software_name`、`client_secret`（可环境变量）。可选 `device_id`、`device_info`、`cache_validity_days`（默认 7）、`check_interval_days`（默认 2）、`debug`、`software_version`。心跳里自动带 `device_info.sdk` 与 `heartbeat_times`。

**存储：** `get_client_storage_root()`；若直接用 `AuthCache`，根目录须与 `AuthClient` 一致且传入相同 `software_name`。

### 维护者：构建与发布

```bash
pip install build && cd client/python && python -m build
```

产物在 `client/python/dist/`。上传到私有 PyPI 静态源时按 PEP 503 布局放置 wheel/sdist，并在 `simple/py-auth-client/index.html` 中链到对应文件名（版本以 `pyproject.toml` 为准）。安装指定版本：`pip install py-auth-client==<版本> --extra-index-url https://www.geekery.cn/pip/simple/`。

---

## Go

```bash
go get github.com/Paper-Dragon/py-auth/client/go
```

```go
package main

import (
    "log"

    authclient "github.com/Paper-Dragon/py-auth/client/go"
)

func main() {
    client, err := authclient.NewAuthClient(authclient.AuthClientConfig{
        ServerURL: "http://localhost:8000", SoftwareName: "我的软件",
        ClientSecret: "your-secret", // 可省略，读 CLIENT_SECRET
    })
    if err != nil {
        log.Fatal(err)
    }
    if err := client.RequireAuthorization(); err != nil {
        log.Fatal(err)
    }
}
```

**配置：** 同上；`CacheValidityDays`、`CheckIntervalDays`、`Debug`、`DeviceID`、`DeviceInfo` 可选。错误类型 `*AuthorizationError` 含 `IsNetworkError` / `IsUnauthorized` / `IsValidationError`。

**API：** `CheckAuthorization`、`RequireAuthorization`、`GetAuthorizationInfo`（仅本地）、`ClearCache`。不传 `DeviceInfo` 则自动采集。

---

## TypeScript

```bash
npm i py-auth-client
```

```ts
import { AuthClient, AuthorizationError } from "py-auth-client";

const client = new AuthClient({
  serverUrl: "http://localhost:8000",
  softwareName: "我的软件",
  clientSecret: process.env.CLIENT_SECRET ?? "",
});
await client.requireAuthorization(); // 失败抛 AuthorizationError
```

**API：** `checkAuthorization`、`requireAuthorization`、`getAuthorizationInfo`（仅本地）、`clearCache`、`getClientStorageRoot`。心跳为 Fernet（`CLIENT_SECRET`）；本地状态包仍为 AES-GCM，见 STORAGE。

发包构建：`client/ts` 下用 `tsconfig.build.json`（仅 `src/`）。
