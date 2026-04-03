# Go 客户端 SDK

## 依赖关系

| 文档 | 说明 |
|------|------|
| [client/README.md](/e:/py-auth/client/README.md) | SDK 总览与三端方法对照 |
| [docs/dev/client-storage.md](/e:/py-auth/docs/dev/client-storage.md) | 存储、状态文件、加解密与 `device_id` 约定 |

## 安装

```bash
go get github.com/Paper-Dragon/py-auth/client/go
```

## `AuthClientConfig` 字段

| 字段 | 是否必需 | 说明 |
|------|----------|------|
| `ServerURL` | 必填 | 服务地址 |
| `SoftwareName` | 必填 | 产品名称 |
| `SoftwareVersion` | 可选 | 软件版本 |
| `DeviceID` | 可选 | 省略时自动生成或复用 |
| `DeviceInfo` | 可选 | 为 `nil` 时自动采集 |
| `ClientSecret` | 条件必填 | 参数可为空，但运行时必须通过参数或环境变量 `CLIENT_SECRET` 提供 |
| `CacheValidityDays` | 可选 | 默认 `7`，建议传正整数；`0` 使用默认值 |
| `CheckIntervalDays` | 可选 | 默认 `2`，建议传正整数；`0` 使用默认值 |
| `Debug` | 可选 | 是否输出调试日志 |

## 示例

### 启动时要求授权通过

```go
package main

import (
	"log"

	authclient "github.com/Paper-Dragon/py-auth/client/go"
)

func main() {
	c, err := authclient.NewAuthClient(authclient.AuthClientConfig{
		ServerURL:    "http://localhost:8000",
		SoftwareName: "我的软件",
		ClientSecret: "your-secret",
	})
	if err != nil {
		log.Fatal(err)
	}
	if err := c.RequireAuthorization(false); err != nil {
		log.Fatal(err)
	}
}
```

### 检查授权并按结果处理

```go
r := c.CheckAuthorization(false)
if r != nil && r.Success && r.Authorized {
	// 已授权
} else if r != nil {
	// 未授权或校验失败：r.Message
}
```

### 仅读取本地授权信息

```go
info := c.GetAuthorizationInfo()
if info != nil {
	// info.Authorized, info.Message, info.DeviceID, info.RemainingTime
}
```

### 清除本地缓存

```go
if err := c.ClearCache(); err != nil {
	log.Fatal(err)
}
```
