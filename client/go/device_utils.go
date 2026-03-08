package authclient

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"github.com/google/uuid"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"runtime"
	"strings"
)

// DeviceFacts 设备硬件信息
type DeviceFacts struct {
	System    string
	Release   string
	Version   string
	Machine   string
	Processor string
	Hostname  string
	MAC       string
	IPAddress string
	CPUCount  int
	DiskID    string
}

// DeviceInfo 设备信息（发送给服务器）
type DeviceInfo struct {
	Hostname           string  `json:"hostname,omitempty"`
	System             string  `json:"system,omitempty"`
	Release            string  `json:"release,omitempty"`
	Version            string  `json:"version,omitempty"`
	Machine            string  `json:"machine,omitempty"`
	Processor          string  `json:"processor,omitempty"`
	MACAddress         string  `json:"mac_address,omitempty"`
	IPAddress          string  `json:"ip_address,omitempty"`
	CPUCount           int     `json:"cpu_count,omitempty"`
	CPUModel           string  `json:"cpu_model,omitempty"`
	MemoryTotalGB      float64 `json:"memory_total_gb,omitempty"`
	MemoryFreeGB       float64 `json:"memory_free_gb,omitempty"`
	DiskTotalGB        float64 `json:"disk_total_gb,omitempty"`
	DiskFreeGB         float64 `json:"disk_free_gb,omitempty"`
	PlatformVersion    string  `json:"platform_version,omitempty"`
	GoVersion          string  `json:"go_version,omitempty"`
	SystemUptimeSecond int64   `json:"system_uptime_seconds,omitempty"`
	Username           string  `json:"username,omitempty"`
	SoftwareVersion    string  `json:"software_version,omitempty"`
}

// deviceIDStorePath 设备ID持久化路径
func deviceIDStorePath(serverURL, softwareName string) string {
	home, _ := os.UserHomeDir()
	base := filepath.Join(home, ".py_auth_device")
	os.MkdirAll(base, 0755)

	hash := sha256.Sum256([]byte(serverURL))
	serverHash := hex.EncodeToString(hash[:])[:12]

	var softHash string
	if softwareName != "" {
		hash2 := sha256.Sum256([]byte(softwareName))
		softHash = hex.EncodeToString(hash2[:])[:8]
	} else {
		softHash = "default"
	}

	return filepath.Join(base, fmt.Sprintf("device_%s_%s.txt", serverHash, softHash))
}

// LoadPersistedDeviceID 加载持久化的设备ID
func LoadPersistedDeviceID(serverURL, softwareName string) (string, error) {
	path := deviceIDStorePath(serverURL, softwareName)
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(data)), nil
}

// PersistDeviceID 持久化设备ID
func PersistDeviceID(serverURL, deviceID, softwareName string) error {
	path := deviceIDStorePath(serverURL, softwareName)
	return os.WriteFile(path, []byte(deviceID), 0644)
}

// GetMACAddress 获取主网卡MAC地址
func GetMACAddress() string {
	// 尝试使用net包获取
	interfaces, err := getNetworkInterfaces()
	if err == nil {
		for _, iface := range interfaces {
			if iface.MAC != "" && !strings.HasPrefix(iface.MAC, "00:00:00:00:00:00") {
				return iface.MAC
			}
		}
	}

	// 备用方案：使用系统命令
	if runtime.GOOS == "windows" {
		cmd := exec.Command("getmac", "/fo", "csv", "/nh")
		output, err := cmd.Output()
		if err == nil {
			lines := strings.Split(string(output), "\n")
			for _, line := range lines {
				parts := strings.Split(line, ",")
				if len(parts) >= 1 {
					mac := strings.TrimSpace(strings.Trim(parts[0], "\""))
					if mac != "" && !strings.HasPrefix(mac, "00-00-00-00-00-00") {
						mac = strings.ReplaceAll(mac, "-", ":")
						return mac
					}
				}
			}
		}
	} else if runtime.GOOS == "darwin" || runtime.GOOS == "linux" {
		cmd := exec.Command("ifconfig")
		output, err := cmd.Output()
		if err == nil {
			// 简单解析MAC地址
			lines := strings.Split(string(output), "\n")
			for _, line := range lines {
				if strings.Contains(line, "ether") || strings.Contains(line, "HWaddr") {
					parts := strings.Fields(line)
					for _, part := range parts {
						if len(part) == 17 && strings.Count(part, ":") == 5 {
							return part
						}
					}
				}
			}
		}
	}

	return ""
}

// CollectDeviceFacts 采集设备信息
func CollectDeviceFacts() DeviceFacts {
	facts := DeviceFacts{
		System:   runtime.GOOS,
		Machine:  runtime.GOARCH,
		Hostname: getHostname(),
	}

	// 获取系统信息
	facts.Release, facts.Version, facts.Processor = getSystemInfo()

	// 网络信息
	facts.MAC = GetMACAddress()
	facts.IPAddress = getIPAddress()

	// 硬件信息
	facts.CPUCount = runtime.NumCPU()

	// 磁盘ID（简化：仅使用基本路径）
	if runtime.GOOS == "windows" {
		facts.DiskID = "C:"
	} else {
		facts.DiskID = "/"
	}

	return facts
}

// CollectExtendedDeviceInfo 采集扩展设备信息（包括内存、磁盘等）
func CollectExtendedDeviceInfo() map[string]interface{} {
	info := make(map[string]interface{})

	// CPU信息
	if cpus, err := getCPUInfo(); err == nil {
		info["cpu_model"] = cpus
	}

	// 内存信息
	if mem, err := getMemoryInfo(); err == nil {
		info["memory_total_gb"] = mem["total"]
		info["memory_free_gb"] = mem["free"]
	}

	// 磁盘信息
	if disk, err := getDiskInfo(); err == nil {
		info["disk_total_gb"] = disk["total"]
		info["disk_free_gb"] = disk["free"]
	}

	// Go版本
	info["go_version"] = runtime.Version()

	// 系统运行时间
	if uptime, err := getSystemUptime(); err == nil {
		info["system_uptime_seconds"] = uptime
	}

	return info
}

// BuildDeviceID 构建设备ID
func BuildDeviceID(serverURL string, providedDeviceID string, facts DeviceFacts, softwareName string) (string, error) {
	if providedDeviceID != "" {
		PersistDeviceID(serverURL, providedDeviceID, softwareName)
		return providedDeviceID, nil
	}

	// 尝试加载持久化的设备ID
	if persisted, err := LoadPersistedDeviceID(serverURL, softwareName); err == nil && persisted != "" {
		return persisted, nil
	}

	// 生成新的设备ID
	components := []string{
		facts.MAC,
		facts.DiskID,
		fmt.Sprintf("%d", facts.CPUCount),
		facts.System,
		facts.Machine,
		softwareName,
	}

	var filtered []string
	for _, c := range components {
		if c != "" && c != "0" {
			filtered = append(filtered, c)
		}
	}

	var deviceID string
	if len(filtered) > 0 {
		combined := strings.Join(filtered, "-")
		hash := sha256.Sum256([]byte(combined))
		deviceID = hex.EncodeToString(hash[:])[:32]
	} else {
		deviceID = uuid.New().String()
	}

	PersistDeviceID(serverURL, deviceID, softwareName)
	return deviceID, nil
}

// BuildDeviceInfo 构建设备信息
func BuildDeviceInfo(facts DeviceFacts, override *DeviceInfo) DeviceInfo {
	if override != nil {
		return *override
	}

	info := DeviceInfo{
		Hostname:  facts.Hostname,
		System:    facts.System,
		Release:   facts.Release,
		Version:   facts.Version,
		Machine:   facts.Machine,
		Processor: facts.Processor,
	}

	if facts.MAC != "" {
		info.MACAddress = facts.MAC
	}
	if facts.IPAddress != "" {
		info.IPAddress = facts.IPAddress
	}
	if facts.CPUCount > 0 {
		info.CPUCount = facts.CPUCount
	}

	// 获取用户名
	if u, err := user.Current(); err == nil {
		info.Username = u.Username
	}

	// 收集扩展信息
	extended := CollectExtendedDeviceInfo()
	if cpuModel, ok := extended["cpu_model"].(string); ok {
		info.CPUModel = cpuModel
	}
	if memTotal, ok := extended["memory_total_gb"].(float64); ok {
		info.MemoryTotalGB = memTotal
	}
	if memFree, ok := extended["memory_free_gb"].(float64); ok {
		info.MemoryFreeGB = memFree
	}
	if diskTotal, ok := extended["disk_total_gb"].(float64); ok {
		info.DiskTotalGB = diskTotal
	}
	if diskFree, ok := extended["disk_free_gb"].(float64); ok {
		info.DiskFreeGB = diskFree
	}
	if goVer, ok := extended["go_version"].(string); ok {
		info.GoVersion = goVer
	}
	if uptime, ok := extended["system_uptime_seconds"].(int64); ok {
		info.SystemUptimeSecond = uptime
	}

	return info
}

// 辅助函数
func getHostname() string {
	hostname, err := os.Hostname()
	if err != nil {
		return "Unknown"
	}
	return hostname
}

func getSystemInfo() (release, version, processor string) {
	switch runtime.GOOS {
	case "windows":
		release = "Windows"
		// 尝试获取详细版本信息
		cmd := exec.Command("cmd", "/c", "ver")
		if output, err := cmd.Output(); err == nil {
			version = strings.TrimSpace(string(output))
		}
		processor = runtime.GOARCH
	case "darwin":
		release = "macOS"
		cmd := exec.Command("sw_vers", "-productVersion")
		if output, err := cmd.Output(); err == nil {
			release = "macOS " + strings.TrimSpace(string(output))
		}
		cmd = exec.Command("uname", "-m")
		if output, err := cmd.Output(); err == nil {
			processor = strings.TrimSpace(string(output))
		}
	case "linux":
		release = "Linux"
		// 尝试读取 /etc/os-release
		if data, err := os.ReadFile("/etc/os-release"); err == nil {
			lines := strings.Split(string(data), "\n")
			for _, line := range lines {
				if strings.HasPrefix(line, "PRETTY_NAME=") {
					release = strings.Trim(strings.TrimPrefix(line, "PRETTY_NAME="), "\"")
					break
				}
			}
		}
		cmd := exec.Command("uname", "-m")
		if output, err := cmd.Output(); err == nil {
			processor = strings.TrimSpace(string(output))
		}
	default:
		release = runtime.GOOS
		processor = runtime.GOARCH
	}
	return
}

func getIPAddress() string {
	interfaces, err := getNetworkInterfaces()
	if err == nil {
		for _, iface := range interfaces {
			if iface.IP != "" && !strings.HasPrefix(iface.IP, "127.") && !strings.HasPrefix(iface.IP, "169.254.") {
				return iface.IP
			}
		}
	}
	return ""
}

func getCPUInfo() (string, error) {
	// 尝试从 /proc/cpuinfo 读取 CPU 型号（Linux）
	if runtime.GOOS == "linux" {
		if data, err := os.ReadFile("/proc/cpuinfo"); err == nil {
			lines := strings.Split(string(data), "\n")
			for _, line := range lines {
				if strings.HasPrefix(line, "model name") {
					parts := strings.Split(line, ":")
					if len(parts) > 1 {
						return strings.TrimSpace(parts[1]), nil
					}
				}
			}
		}
	}
	return "", fmt.Errorf("cpu info not available")
}

func getMemoryInfo() (map[string]float64, error) {
	result := make(map[string]float64)
	
	// 尝试从 /proc/meminfo 读取内存信息（Linux）
	if runtime.GOOS == "linux" {
		if data, err := os.ReadFile("/proc/meminfo"); err == nil {
			lines := strings.Split(string(data), "\n")
			var memTotal, memFree float64
			for _, line := range lines {
				if strings.HasPrefix(line, "MemTotal:") {
					parts := strings.Fields(line)
					if len(parts) > 1 {
						fmt.Sscanf(parts[1], "%f", &memTotal)
					}
				} else if strings.HasPrefix(line, "MemFree:") {
					parts := strings.Fields(line)
					if len(parts) > 1 {
						fmt.Sscanf(parts[1], "%f", &memFree)
					}
				}
			}
			if memTotal > 0 {
				result["total"] = memTotal / (1024 * 1024)
				result["free"] = memFree / (1024 * 1024)
				return result, nil
			}
		}
	}
	
	return result, fmt.Errorf("memory info not available")
}

func getDiskInfo() (map[string]float64, error) {
	result := make(map[string]float64)
	
	// 简化实现：仅返回空值
	// 完整实现需要调用系统命令或使用 syscall
	return result, fmt.Errorf("disk info not available")
}

func getSystemUptime() (int64, error) {
	// 尝试从 /proc/uptime 读取系统运行时间（Linux）
	if runtime.GOOS == "linux" {
		if data, err := os.ReadFile("/proc/uptime"); err == nil {
			parts := strings.Fields(string(data))
			if len(parts) > 0 {
				var uptime float64
				fmt.Sscanf(parts[0], "%f", &uptime)
				return int64(uptime), nil
			}
		}
	}
	
	return 0, fmt.Errorf("uptime not available")
}
