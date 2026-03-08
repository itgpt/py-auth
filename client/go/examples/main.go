package main

import (
	"fmt"
	"log"
	"os"

	authclient "github.com/Paper-Dragon/py-auth/client/go"
)

func main() {
	// 初始化客户端
	client, err := authclient.NewAuthClient(authclient.AuthClientConfig{
		ServerURL:         "http://localhost:8000",
		SoftwareName:      "我的软件",
		SoftwareVersion:   "0.0.1",
		ClientSecret:      "your-client-secret-key-change-in-production",
		EnableCache:       true,
		CacheValidityDays: 7,
		CheckIntervalDays: 2,
		Debug:             true, // 开启调试日志
	})

	if err != nil {
		log.Fatalf("初始化客户端失败: %v", err)
	}

	// 检查授权
	err = client.RequireAuthorization()
	if err != nil {
		if authErr, ok := err.(*authclient.AuthorizationError); ok {
			fmt.Printf("❌ 授权失败: %s\n", authErr.Message)

			if authErr.IsNetworkError() {
				fmt.Println("错误类型: 网络连接错误")
			} else if authErr.IsUnauthorized() {
				fmt.Println("错误类型: 设备未授权")
			} else if authErr.IsValidationError() {
				fmt.Println("错误类型: 验证错误")
			}
		} else {
			fmt.Printf("❌ 授权失败: %v\n", err)
		}
		os.Exit(1)
	}

	fmt.Println("✅ 设备已授权")

	// 获取授权信息
	info := client.GetAuthorizationInfo()
	fmt.Printf("授权信息: %+v\n", info)

	// 你的软件代码...
}
