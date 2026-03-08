package authclient

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/go-resty/resty/v2"
)

// AuthResult 授权检查结果
type AuthResult struct {
	Authorized bool   `json:"authorized"`
	Message    string `json:"message"`
	Success    bool   `json:"success"`
	FromCache  bool   `json:"from_cache"`
}

// AuthorizationInfo 授权信息
type AuthorizationInfo struct {
	Authorized       bool    `json:"authorized"`
	Success          bool    `json:"success"`
	FromCache        bool    `json:"from_cache"`
	Message          string  `json:"message"`
	DeviceID         string  `json:"device_id"`
	ServerURL        string  `json:"server_url"`
	RemainingTime    string  `json:"remaining_time,omitempty"`
	CacheValid       bool    `json:"cache_valid,omitempty"`
	CachedAt         float64 `json:"cached_at,omitempty"`
	CachedAtReadable string  `json:"cached_at_readable,omitempty"`
}

// AuthorizationError 授权错误
type AuthorizationError struct {
	Message   string
	Result    *AuthResult
	DeviceID  string
	ServerURL string
}

func (e *AuthorizationError) Error() string {
	return e.Message
}

// IsNetworkError 判断是否为网络错误
func (e *AuthorizationError) IsNetworkError() bool {
	message := e.Message
	if e.Result != nil {
		message = e.Result.Message
	}
	keywords := []string{"连接失败", "连接", "network", "timeout", "connection"}
	lowerMessage := strings.ToLower(message)
	for _, keyword := range keywords {
		if strings.Contains(lowerMessage, strings.ToLower(keyword)) {
			return true
		}
	}
	return false
}

// IsUnauthorized 判断是否为未授权错误
func (e *AuthorizationError) IsUnauthorized() bool {
	if e.Result != nil {
		return !e.Result.Authorized && e.Result.Success
	}
	return strings.Contains(e.Message, "未授权") || strings.Contains(e.Message, "禁用")
}

// IsValidationError 判断是否为验证错误
func (e *AuthorizationError) IsValidationError() bool {
	if e.Result != nil {
		return !e.Result.Success
	}
	return strings.Contains(e.Message, "无法验证授权") || strings.Contains(e.Message, "验证失败")
}

// AuthClient 授权客户端
type AuthClient struct {
	serverURL         string
	softwareName      string
	softwareVersion   string
	deviceID          string
	deviceInfo        DeviceInfo
	clientSecret      string
	cache             *AuthCache
	enableCache       bool
	cacheValidityDays int
	checkIntervalDays int
	debug             bool
}

// AuthClientConfig 客户端配置
type AuthClientConfig struct {
	ServerURL         string
	SoftwareName      string
	SoftwareVersion   string
	DeviceID          string
	DeviceInfo        *DeviceInfo
	ClientSecret      string
	CacheDir          string
	EnableCache       bool
	CacheValidityDays int
	CheckIntervalDays int
	Debug             bool
}

// NewAuthClient 创建新的授权客户端
func NewAuthClient(config AuthClientConfig) (*AuthClient, error) {
	if config.ServerURL == "" {
		return nil, errors.New("server_url不能为空")
	}
	if config.SoftwareName == "" {
		return nil, errors.New("software_name不能为空")
	}
	if config.ClientSecret == "" {
		// 尝试从环境变量读取
		config.ClientSecret = os.Getenv("CLIENT_SECRET")
		if config.ClientSecret == "" {
			return nil, errors.New("client_secret未配置！请在初始化时传入client_secret参数，或设置环境变量CLIENT_SECRET")
		}
	}

	client := &AuthClient{
		serverURL:         config.ServerURL,
		softwareName:      config.SoftwareName,
		softwareVersion:   config.SoftwareVersion,
		clientSecret:      config.ClientSecret,
		enableCache:       config.EnableCache,
		cacheValidityDays: config.CacheValidityDays,
		checkIntervalDays: config.CheckIntervalDays,
		debug:             config.Debug,
	}

	if client.cacheValidityDays == 0 {
		client.cacheValidityDays = 7
	}
	if client.checkIntervalDays == 0 {
		client.checkIntervalDays = 2
	}

	// 收集设备信息
	facts := CollectDeviceFacts()

	// 构建设备ID
	var err error
	client.deviceID, err = BuildDeviceID(
		config.ServerURL,
		config.DeviceID,
		facts,
		config.SoftwareName,
	)
	if err != nil {
		return nil, fmt.Errorf("构建设备ID失败: %w", err)
	}

	// 构建设备信息
	client.deviceInfo = BuildDeviceInfo(facts, config.DeviceInfo)
	client.deviceInfo.SoftwareVersion = client.softwareVersion

	// 初始化缓存
	if client.enableCache {
		client.cache = NewAuthCache(
			config.CacheDir,
			client.deviceID,
			client.serverURL,
			client.softwareName,
			client.cacheValidityDays,
			client.checkIntervalDays,
		)
	}

	return client, nil
}

// errorResult 创建错误结果辅助函数
func (c *AuthClient) errorResult(msg string) *AuthResult {
	return &AuthResult{
		Authorized: false,
		Message:    msg,
		Success:    false,
		FromCache:  false,
	}
}

// checkOnline 在线检查授权状态
func (c *AuthClient) checkOnline() *AuthResult {
	c.logDebug("开始在线订阅请求...")

	// 准备请求数据
	requestData := map[string]interface{}{
		"device_id":     c.deviceID,
		"software_name": c.softwareName,
		"device_info":   c.deviceInfo,
	}

	jsonData, err := json.Marshal(requestData)
	if err != nil {
		return c.errorResult(fmt.Sprintf("序列化请求失败: %v", err))
	}

	encrypted, err := EncryptData(jsonData, c.clientSecret)
	if err != nil {
		return c.errorResult(fmt.Sprintf("加密请求失败: %v", err))
	}

	// 使用resty发送HTTP请求
	client := resty.New().SetTimeout(10 * time.Second)
	resp, err := client.R().
		SetHeader("Content-Type", "application/json").
		SetBody(map[string]string{"encrypted_data": encrypted}).
		SetResult(map[string]interface{}{}).
		Post(fmt.Sprintf("%s/api/auth/heartbeat", c.serverURL))

	if err != nil {
		c.logDebug(fmt.Sprintf("在线订阅请求异常: %v", err))
		return c.errorResult(fmt.Sprintf("连接失败: %v", err))
	}

	if resp.StatusCode() != http.StatusOK {
		var errorResp map[string]interface{}
		errorMsg := fmt.Sprintf("服务器错误: %d", resp.StatusCode())
		if err := json.Unmarshal(resp.Body(), &errorResp); err == nil {
			if detail, ok := errorResp["detail"].(string); ok {
				errorMsg = detail
			}
		}
		c.logDebug(fmt.Sprintf("在线订阅失败，status=%d, message=%s", resp.StatusCode(), errorMsg))
		return c.errorResult(errorMsg)
	}

	var response map[string]interface{}
	if err := json.Unmarshal(resp.Body(), &response); err != nil {
		return c.errorResult("解析响应失败")
	}

	encryptedData, ok := response["encrypted_data"].(string)
	if !ok {
		return c.errorResult("响应格式错误")
	}

	decrypted, err := DecryptData(encryptedData, c.clientSecret)
	if err != nil {
		c.logDebug("在线订阅响应解密失败")
		return c.errorResult("解密响应失败")
	}

	var result map[string]interface{}
	if err := json.Unmarshal(decrypted, &result); err != nil {
		return c.errorResult("解析解密数据失败")
	}

	authorized, _ := result["authorized"].(bool)
	message, _ := result["message"].(string)

	c.logDebug(fmt.Sprintf("在线订阅成功，authorized=%v", authorized))
	return &AuthResult{
		Authorized: authorized,
		Message:    message,
		Success:    true,
		FromCache:  false,
	}
}

// CheckAuthorization 检查授权状态
func (c *AuthClient) CheckAuthorization() *AuthResult {
	if !c.enableCache || c.cache == nil {
		return c.checkOnline()
	}

	// 尝试读取缓存
	cacheData, err := c.cache.GetCache()
	cacheValid := false
	if err == nil && cacheData != nil {
		elapsed := time.Now().Unix() - int64(cacheData.CachedAt)
		if elapsed < c.cache.cacheValiditySeconds {
			cacheValid = true
			c.logDebug("命中有效缓存，直接授权通过")
		}
	}

	if cacheValid {
		c.logDebug("缓存有效，继续尝试在线订阅来更新订阅")
	} else {
		if cacheData != nil {
			c.logDebug("缓存存在但已过期，准备发起在线订阅请求")
		} else {
			c.logDebug("未找到缓存，准备发起在线订阅请求")
		}
	}

	// 始终尝试在线检查
	onlineResult := c.checkOnline()

	if onlineResult.Success {
		c.logDebug("在线订阅成功，更新缓存")
		c.cache.SaveCache(onlineResult.Authorized, onlineResult.Message)
		return onlineResult
	}

	// 在线检查失败，如果缓存有效则使用缓存
	if cacheValid {
		remaining := c.formatRemainingTime(cacheData.CachedAt)
		c.logDebug(fmt.Sprintf("在线订阅失败，但缓存有效，使用缓存结果，订阅剩余时间: %s", remaining))
		return &AuthResult{
			Authorized: cacheData.Authorized,
			Message:    cacheData.Message,
			Success:    true,
			FromCache:  true,
		}
	}

	// 返回失败结果
	if cacheData != nil {
		remaining := c.formatRemainingTime(cacheData.CachedAt)
		c.logDebug(fmt.Sprintf("在线订阅失败，缓存已过期，返回失败结果，订阅剩余时间: %s", remaining))
	} else {
		c.logDebug(fmt.Sprintf("在线订阅失败，返回失败结果: %s", onlineResult.Message))
	}
	return onlineResult
}

// RequireAuthorization 要求授权，如果未授权则返回错误
func (c *AuthClient) RequireAuthorization() error {
	result := c.CheckAuthorization()

	if !result.Success {
		return &AuthorizationError{
			Message:   result.Message,
			Result:    result,
			DeviceID:  c.deviceID,
			ServerURL: c.serverURL,
		}
	}

	if !result.Authorized {
		return &AuthorizationError{
			Message:   result.Message,
			Result:    result,
			DeviceID:  c.deviceID,
			ServerURL: c.serverURL,
		}
	}

	return nil
}

// ClearCache 清除本地缓存
func (c *AuthClient) ClearCache() error {
	if c.cache != nil {
		return c.cache.ClearCache()
	}
	return nil
}

// GetAuthorizationInfo 获取授权信息
func (c *AuthClient) GetAuthorizationInfo() *AuthorizationInfo {
	result := c.CheckAuthorization()

	info := &AuthorizationInfo{
		Authorized: result.Authorized,
		Success:    result.Success,
		FromCache:  result.FromCache,
		Message:    result.Message,
		DeviceID:   c.deviceID,
		ServerURL:  c.serverURL,
	}

	if c.cache != nil {
		cache, err := c.cache.GetCache()
		if err == nil && cache != nil {
			info.CachedAt = cache.CachedAt
			info.RemainingTime = c.formatRemainingTime(cache.CachedAt)
			info.CacheValid = c.cache.IsCacheValid()
			if cache.CachedAt > 0 {
				info.CachedAtReadable = time.Unix(int64(cache.CachedAt), 0).Format("2006-01-02 15:04:05")
			}
		} else {
			info.RemainingTime = "无缓存"
			info.CacheValid = false
		}
	}

	return info
}

// 辅助函数
func (c *AuthClient) logDebug(msg string) {
	if c.debug {
		fmt.Printf("[go-auth-client][DEBUG] %s\n", msg)
	}
}

func (c *AuthClient) formatRemainingTime(cachedAt float64) string {
	if cachedAt <= 0 || c.cache == nil {
		return "未知"
	}

	now := float64(time.Now().Unix())
	elapsed := now - cachedAt
	remaining := float64(c.cache.cacheValiditySeconds) - elapsed

	if remaining <= 0 {
		return "已过期"
	}

	days := int(remaining / 86400)
	hours := int((remaining - float64(days*86400)) / 3600)
	minutes := int((remaining - float64(days*86400) - float64(hours*3600)) / 60)

	var parts []string
	if days > 0 {
		parts = append(parts, fmt.Sprintf("%d天", days))
	}
	if hours > 0 {
		parts = append(parts, fmt.Sprintf("%d小时", hours))
	}
	if minutes > 0 || len(parts) == 0 {
		parts = append(parts, fmt.Sprintf("%d分钟", minutes))
	}

	if len(parts) == 0 {
		return "0分钟"
	}

	result := ""
	for _, part := range parts {
		result += part
	}
	return result
}
