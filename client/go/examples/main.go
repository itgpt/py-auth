package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"runtime"
	"strings"

	authclient "github.com/Paper-Dragon/py-auth/client/go"
)

func clientSecret() string {
	_, file, _, _ := runtime.Caller(0)
	data, _ := os.ReadFile(filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".env")))
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, val, _ := strings.Cut(line, "=")
		if strings.TrimSpace(key) != "CLIENT_SECRET" {
			continue
		}
		return strings.Trim(strings.TrimSpace(val), `"'`)
	}
	return ""
}

func main() {
	cfg := authclient.AuthClientConfig{
		ServerURL:         "http://localhost:8000",
		SoftwareName:      "软件go示例",
		SoftwareVersion:   "0.0.1",
		ClientSecret:      clientSecret(),
		CacheValidityDays: 7,
		CheckIntervalDays: 2,
		Debug:             true,
	}
	client, err := authclient.NewAuthClient(cfg)

	if err != nil {
		log.Fatalf("初始化客户端失败: %v", err)
	}

	err = client.RequireAuthorization(false)
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

	info := client.GetAuthorizationInfo()
	if !cfg.Debug {
		if b, err := json.MarshalIndent(info, "", "  "); err == nil {
			fmt.Println(string(b))
		}
	}
}
