# py-auth-client

Python 客户端 SDK，用于设备授权校验与本地加密状态包（与 Go / TypeScript 客户端协议一致）。

**完整多语言文档、存储说明与示例**见仓库：  
<https://github.com/Paper-Dragon/py-auth/blob/main/client/README.md>

## 安装

```bash
pip install py-auth-client --extra-index-url https://www.geekery.cn/pip/simple/
```

## 示例

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
    raise SystemExit(str(e))
```

维护者本地构建：`pip install build && cd client/python && python -m build`
