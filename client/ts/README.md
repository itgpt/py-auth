# TypeScript 客户端 SDK

适用于 Node.js 环境。

## 依赖关系

| 文档 | 说明 |
|------|------|
| [client/README.md](/e:/py-auth/client/README.md) | SDK 总览与三端方法对照 |
| [docs/dev/client-storage.md](/e:/py-auth/docs/dev/client-storage.md) | 存储、`device_id`、状态文件与加解密约定 |

## 安装

```bash
npm i py-auth-client
```

## `AuthClientConfig` 字段

| 字段 | 是否必需 | 说明 |
|------|----------|------|
| `serverUrl` | 必填 | 服务地址 |
| `softwareName` | 必填 | 产品名称 |
| `softwareVersion` | 可选 | 软件版本 |
| `deviceId` | 可选 | 省略时自动生成或复用 |
| `deviceInfo` | 可选 | 省略时自动采集 |
| `clientSecret` | 条件必填 | 参数可省略，但运行时必须通过参数或环境变量 `CLIENT_SECRET` 提供 |
| `cacheValidityDays` | 可选 | 本地缓存有效期，默认 `7` |
| `checkIntervalDays` | 可选 | 检查间隔，默认 `2` |
| `debug` | 可选 | 是否输出调试日志 |

## 示例

### 启动时要求授权通过

```ts
import { AuthClient, AuthorizationError } from "py-auth-client";

async function main() {
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
}

void main();
```

### 检查授权并按结果处理

```ts
const result = await client.checkAuthorization();

if (result.success && result.authorized) {
  console.log(result.from_cache ? "已授权，来自缓存" : "已授权，在线刷新");
} else {
  console.warn("未授权或校验失败：", result.message);
}
```

### 仅读取本地授权信息

```ts
const info = await client.getAuthorizationInfo();
console.log(info.authorized, info.message, info.device_id, info.remaining_time);
```

### 清除本地缓存

```ts
client.clearCache();
```

开发构建说明见 [docs/dev/client-ts-build.md](/e:/py-auth/docs/dev/client-ts-build.md)。
