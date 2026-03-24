# py-auth-client（TypeScript / Node.js）

与仓库内 Python、Go 客户端协议一致。安装与最小示例见下；**完整文档（配置、缓存、存储、`device_info`）见上一级 [client/README.md](../README.md#typescript)**（与 [STORAGE.md](../STORAGE.md) 对照阅读）。

## 安装

```bash
npm i py-auth-client
```

## 最小示例

```ts
import { AuthClient, AuthorizationError } from "py-auth-client";

const client = new AuthClient({
  serverUrl: "http://localhost:8000",
  softwareName: "我的软件",
  clientSecret: process.env.CLIENT_SECRET ?? "",
});

try {
  await client.requireAuthorization();
} catch (e) {
  if (e instanceof AuthorizationError) {
    console.error(e.message);
    process.exit(1);
  }
  throw e;
}
```
