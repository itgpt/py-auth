package authclient

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"math"
	"os"
	"os/exec"
	"os/user"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"

	"github.com/google/uuid"
)

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
	MemoryTotalGB float64
	DiskTotalGB   float64
}

type SDKInfo struct {
	Language   string `json:"language"`
	SDKName    string `json:"sdk_name"`
	SDKVersion string `json:"sdk_version"`
	Runtime    string `json:"runtime,omitempty"`
}

type DeviceNetworkEndpoint struct {
	MACAddress string `json:"mac_address,omitempty"`
	IPAddress  string `json:"ip_address,omitempty"`
}

type DeviceNetwork struct {
	MACAddress string                   `json:"mac_address,omitempty"`
	IPAddress  string                   `json:"ip_address,omitempty"`
	Interfaces []DeviceNetworkEndpoint   `json:"interfaces,omitempty"`
	PublicIP   string                   `json:"public_ip,omitempty"`
}

type DeviceMemory struct {
	TotalGB     float64 `json:"total_gb,omitempty"`
	FreeGB      float64 `json:"free_gb,omitempty"`
	AvailableGB float64 `json:"available_gb,omitempty"`
}

type DeviceCPU struct {
	Model          string  `json:"model,omitempty"`
	Count          int     `json:"count,omitempty"`
	PhysicalCount  int     `json:"physical_count,omitempty"`
	FreqMHz        float64 `json:"freq_mhz,omitempty"`
	FreqMinMHz     float64 `json:"freq_min_mhz,omitempty"`
	FreqMaxMHz     float64 `json:"freq_max_mhz,omitempty"`
}

type DeviceDiskVolume struct {
	Mount   string  `json:"mount,omitempty"`
	Device  string  `json:"device,omitempty"`
	TotalGB float64 `json:"total_gb,omitempty"`
	FreeGB  float64 `json:"free_gb,omitempty"`
}

type DeviceDiskModelGroup struct {
	Volumes []DeviceDiskVolume `json:"volumes"`
}

type DeviceDisk struct {
	TotalGB float64                         `json:"total_gb,omitempty"`
	FreeGB  float64                         `json:"free_gb,omitempty"`
	Models  map[string]DeviceDiskModelGroup `json:"models,omitempty"`
}

type DeviceSystem struct {
	Hostname              string `json:"hostname,omitempty"`
	OS                    string `json:"os,omitempty"`
	Release               string `json:"release,omitempty"`
	Version               string `json:"version,omitempty"`
	Machine               string `json:"machine,omitempty"`
	Processor             string `json:"processor,omitempty"`
	PlatformVersion       string `json:"platform_version,omitempty"`
	GoVersion             string `json:"go_version,omitempty"`
	SystemUptimeSecond    int64  `json:"system_uptime_seconds,omitempty"`
	Username              string `json:"username,omitempty"`
	WindowsDisplayVersion string `json:"windows_display_version,omitempty"`
	WindowsProductName    string `json:"windows_product_name,omitempty"`
}

type DeviceInfo struct {
	Sys             *DeviceSystem  `json:"system,omitempty"`
	Network         *DeviceNetwork `json:"network,omitempty"`
	Memory          *DeviceMemory  `json:"memory,omitempty"`
	Disk            *DeviceDisk    `json:"disk,omitempty"`
	CPU             *DeviceCPU     `json:"cpu,omitempty"`
	SoftwareVersion string         `json:"software_version,omitempty"`
	SDK             *SDKInfo       `json:"sdk,omitempty"`
}

func LoadPersistedDeviceID(serverURL, softwareName, baseDir string) (string, error) {
	if baseDir == "" {
		baseDir = DefaultClientStorageRoot()
	}
	m, err := ReadStateDict(serverURL, baseDir)
	if err != nil {
		return "", err
	}
	if m == nil {
		return "", nil
	}
	row := loadAppsMap(m)[softwareName]
	if row == nil {
		return "", nil
	}
	if id := rowDeviceIDString(row); id != "" {
		return id, nil
	}
	return "", nil
}

func PersistDeviceID(serverURL, deviceID, softwareName, baseDir string) error {
	if baseDir == "" {
		baseDir = DefaultClientStorageRoot()
	}
	_ = os.MkdirAll(baseDir, 0o755)
	m, _ := ReadStateDict(serverURL, baseDir)
	if m == nil {
		m = make(map[string]interface{})
	}
	apps := loadAppsMap(m)
	sub := cloneStringMap(apps[softwareName])
	delete(sub, "software_name")
	sub["device_id"] = deviceID
	apps[softwareName] = sub
	commitAppsMap(m, apps)
	delete(m, "device_id")
	path := BundlePath(serverURL, baseDir)
	if err := WriteStateDict(serverURL, baseDir, m); err != nil {
		if runtime.GOOS == "windows" {
			if _, statErr := os.Stat(path); statErr == nil {
				_ = exec.Command("attrib", "-H", path).Run()
				_ = os.Remove(path)
				return WriteStateDict(serverURL, baseDir, m)
			}
		}
		return err
	}
	return nil
}

func getMACAddressLegacy() string {
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

func CollectDeviceFacts() DeviceFacts {
	hn, err := os.Hostname()
	if err != nil {
		hn = "Unknown"
	}
	facts := DeviceFacts{
		System:   pythonStyleSystem(),
		Machine:  pythonStyleMachine(),
		Hostname: hn,
	}

	facts.Release, facts.Version, facts.Processor = getSystemInfo()

	mac, ip := preferredNetworkEndpoint()
	if mac == "" {
		mac = strings.ToLower(strings.TrimSpace(getMACAddressLegacy()))
	}
	if ip == "" {
		ip = getOutboundIPv4Hint()
	}
	facts.MAC = strings.ToLower(strings.TrimSpace(mac))
	facts.IPAddress = ip

	facts.CPUCount = runtime.NumCPU()

	facts.DiskID = rootDiskID()
	if b, err := physicalMemoryBytes(); err == nil && b > 0 {
		facts.MemoryTotalGB = round2(float64(b) / (1024 * 1024 * 1024))
	}
	if b, err := rootDiskTotalBytes(); err == nil && b > 0 {
		facts.DiskTotalGB = round2(float64(b) / (1024 * 1024 * 1024))
	}

	return facts
}

func pythonStyleSystem() string {
	s := runtime.GOOS
	if s == "" {
		return s
	}
	return strings.ToUpper(s[:1]) + strings.ToLower(s[1:])
}

func pythonStyleMachine() string {
	switch runtime.GOOS {
	case "windows":
		if runtime.GOARCH == "amd64" {
			return "AMD64"
		}
	case "linux":
		if runtime.GOARCH == "amd64" {
			return "x86_64"
		}
	case "darwin":
		if runtime.GOARCH == "amd64" {
			return "x86_64"
		}
	}
	return runtime.GOARCH
}

type diskVolEnt struct {
	model   string
	mount   string
	device  string
	totalGB float64
	freeGB  float64
}

func diskVolumeMapKey(model, mount, device string, used map[string]struct{}) string {
	base := strings.TrimSpace(model)
	if base == "" {
		base = strings.TrimSpace(device)
	}
	if base == "" {
		base = strings.TrimSpace(mount)
	}
	if base == "" {
		base = "unknown"
	}
	k := base
	suffix := 0
	for {
		if _, dup := used[k]; !dup {
			used[k] = struct{}{}
			return k
		}
		suffix++
		if suffix == 1 {
			k = base + " @ " + mount
		} else {
			k = fmt.Sprintf("%s @ %s (%d)", base, mount, suffix)
		}
	}
}

func foldDiskVolumesByModel(entries []diskVolEnt) map[string]DeviceDiskModelGroup {
	if len(entries) == 0 {
		return nil
	}
	used := make(map[string]struct{})
	by := make(map[string][]diskVolEnt)
	for _, e := range entries {
		m := strings.TrimSpace(e.model)
		var key string
		if m != "" {
			key = m
		} else {
			key = diskVolumeMapKey("", e.mount, e.device, used)
		}
		by[key] = append(by[key], e)
	}
	out := make(map[string]DeviceDiskModelGroup, len(by))
	for key, sl := range by {
		sort.Slice(sl, func(i, j int) bool { return sl[i].mount < sl[j].mount })
		vols := make([]DeviceDiskVolume, 0, len(sl))
		for _, e := range sl {
			vols = append(vols, DeviceDiskVolume{
				Mount:   e.mount,
				Device:  e.device,
				TotalGB: e.totalGB,
				FreeGB:  e.freeGB,
			})
		}
		out[key] = DeviceDiskModelGroup{Volumes: vols}
	}
	return out
}

func volumeFromMap(m map[string]interface{}) (DeviceDiskVolume, string) {
	var v DeviceDiskVolume
	var model string
	if s, ok := m["model"].(string); ok {
		model = s
	}
	if s, ok := m["mount"].(string); ok {
		v.Mount = s
	}
	if s, ok := m["device"].(string); ok {
		v.Device = s
	}
	if f, ok := m["total_gb"].(float64); ok {
		v.TotalGB = f
	}
	if f, ok := m["free_gb"].(float64); ok {
		v.FreeGB = f
	}
	return v, model
}

func diskVolumesToIface(vols []DeviceDiskVolume) []interface{} {
	out := make([]interface{}, 0, len(vols))
	for _, v := range vols {
		m := map[string]interface{}{
			"mount": v.Mount, "total_gb": v.TotalGB, "free_gb": v.FreeGB,
		}
		if v.Device != "" {
			m["device"] = v.Device
		}
		out = append(out, m)
	}
	return out
}

func parseVolumesListFromInterface(vraw interface{}) []DeviceDiskVolume {
	var vlist []interface{}
	switch vv := vraw.(type) {
	case []interface{}:
		vlist = vv
	case []map[string]interface{}:
		for _, vm := range vv {
			vlist = append(vlist, vm)
		}
	default:
		return nil
	}
	var out []DeviceDiskVolume
	for _, vi := range vlist {
		vm, ok := vi.(map[string]interface{})
		if !ok {
			continue
		}
		v, _ := volumeFromMap(vm)
		if v.Mount == "" && v.TotalGB == 0 && v.FreeGB == 0 {
			continue
		}
		out = append(out, v)
	}
	return out
}

func unmarshalDiskModelsMap(raw interface{}) map[string]DeviceDiskModelGroup {
	m, ok := raw.(map[string]interface{})
	if !ok || len(m) == 0 {
		return nil
	}
	out := make(map[string]DeviceDiskModelGroup)
	for key, val := range m {
		vm, ok := val.(map[string]interface{})
		if !ok {
			continue
		}
		vols := parseVolumesListFromInterface(vm["volumes"])
		if len(vols) == 0 {
			continue
		}
		out[key] = DeviceDiskModelGroup{Volumes: vols}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

func mergeDiskDisksSliceIntoModels(raw interface{}) map[string]DeviceDiskModelGroup {
	var arr []interface{}
	switch x := raw.(type) {
	case []interface{}:
		arr = x
	case []map[string]interface{}:
		for _, m := range x {
			arr = append(arr, m)
		}
	default:
		return nil
	}
	tmp := make(map[string][]DeviceDiskVolume)
	for _, e := range arr {
		em, ok := e.(map[string]interface{})
		if !ok {
			continue
		}
		mkey := strings.TrimSpace(strFromIface(em["model"]))
		if mkey == "" {
			mkey = "unknown"
		}
		vols := parseVolumesListFromInterface(em["volumes"])
		if len(vols) == 0 {
			continue
		}
		tmp[mkey] = append(tmp[mkey], vols...)
	}
	if len(tmp) == 0 {
		return nil
	}
	out := make(map[string]DeviceDiskModelGroup, len(tmp))
	for k, sl := range tmp {
		sort.Slice(sl, func(i, j int) bool { return sl[i].Mount < sl[j].Mount })
		out[k] = DeviceDiskModelGroup{Volumes: sl}
	}
	return out
}

func strFromIface(v interface{}) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func migrateLegacyDiskVolumesToModels(raw interface{}) map[string]DeviceDiskModelGroup {
	switch x := raw.(type) {
	case map[string]interface{}:
		out := make(map[string]DeviceDiskModelGroup)
		for k, val := range x {
			vm, ok := val.(map[string]interface{})
			if !ok {
				continue
			}
			v, _ := volumeFromMap(vm)
			if v.Mount == "" && v.TotalGB == 0 && v.FreeGB == 0 {
				continue
			}
			out[k] = DeviceDiskModelGroup{Volumes: []DeviceDiskVolume{v}}
		}
		if len(out) == 0 {
			return nil
		}
		return out
	case map[string]DeviceDiskVolume:
		iface := make(map[string]interface{}, len(x))
		for k, v := range x {
			m := map[string]interface{}{
				"mount": v.Mount, "total_gb": v.TotalGB, "free_gb": v.FreeGB,
			}
			if v.Device != "" {
				m["device"] = v.Device
			}
			iface[k] = m
		}
		return migrateLegacyDiskVolumesToModels(iface)
	case []interface{}:
		used := make(map[string]struct{})
		folded := make(map[string]DeviceDiskVolume)
		for _, e := range x {
			em, ok := e.(map[string]interface{})
			if !ok {
				continue
			}
			v, model := volumeFromMap(em)
			if v.Mount == "" && v.TotalGB == 0 && v.FreeGB == 0 {
				continue
			}
			key := diskVolumeMapKey(model, v.Mount, v.Device, used)
			folded[key] = v
		}
		return migrateLegacyDiskVolumesToModels(folded)
	case []map[string]interface{}:
		used := make(map[string]struct{})
		folded := make(map[string]DeviceDiskVolume)
		for _, em := range x {
			v, model := volumeFromMap(em)
			if v.Mount == "" && v.TotalGB == 0 && v.FreeGB == 0 {
				continue
			}
			key := diskVolumeMapKey(model, v.Mount, v.Device, used)
			folded[key] = v
		}
		return migrateLegacyDiskVolumesToModels(folded)
	default:
		return nil
	}
}

func parseDiskModelsFromExtended(extended map[string]interface{}) map[string]DeviceDiskModelGroup {
	if raw, ok := extended["disk_models"]; ok && raw != nil {
		if out := unmarshalDiskModelsMap(raw); len(out) > 0 {
			return out
		}
	}
	if raw, ok := extended["disk_disks"]; ok && raw != nil {
		if out := mergeDiskDisksSliceIntoModels(raw); len(out) > 0 {
			return out
		}
	}
	if raw, ok := extended["disk_volumes"]; ok && raw != nil {
		if out := migrateLegacyDiskVolumesToModels(raw); len(out) > 0 {
			return out
		}
	}
	return nil
}

func round2(v float64) float64 {
	return math.Round(v*100) / 100
}

func intFromExtended(v interface{}) (int, bool) {
	switch x := v.(type) {
	case int:
		return x, true
	case int32:
		return int(x), true
	case int64:
		return int(x), true
	case float64:
		return int(x), true
	default:
		return 0, false
	}
}

func floatFromExtended(v interface{}) (float64, bool) {
	switch x := v.(type) {
	case float64:
		return x, true
	case int:
		return float64(x), true
	case int64:
		return float64(x), true
	default:
		return 0, false
	}
}

func parseLinuxProcCPUInfo() (model string, physical int, mhz float64) {
	data, err := os.ReadFile("/proc/cpuinfo")
	if err != nil {
		return "", 0, 0
	}
	text := strings.ReplaceAll(string(data), "\r\n", "\n")
	lines := strings.Split(text, "\n")
	seen := make(map[string]struct{})
	var physID, coreID string
	blockStarted := false
	flush := func() {
		if !blockStarted {
			return
		}
		seen[physID+"/"+coreID] = struct{}{}
	}
	for _, line := range lines {
		line = strings.TrimSpace(line)
		low := strings.ToLower(line)
		if strings.HasPrefix(low, "processor") && strings.Contains(line, ":") {
			flush()
			blockStarted = true
			physID, coreID = "", ""
			continue
		}
		idx := strings.Index(line, ":")
		if idx < 0 {
			continue
		}
		key := strings.TrimSpace(line[:idx])
		val := strings.TrimSpace(line[idx+1:])
		switch strings.ToLower(key) {
		case "model name":
			if model == "" {
				model = val
			}
		case "model":
			if model == "" {
				model = val
			}
		case "hardware":
			if model == "" {
				model = val
			}
		case "physical id":
			physID = val
		case "core id":
			coreID = val
		case "cpu mhz":
			if mhz == 0 {
				var f float64
				fmt.Sscanf(val, "%f", &f)
				if f > 0 {
					mhz = f
				}
			}
		}
	}
	flush()
	if len(seen) > 0 {
		physical = len(seen)
	}
	return model, physical, mhz
}

func fillCPUExtendedInfo(info map[string]interface{}) {
	switch runtime.GOOS {
	case "windows":
		model, phys, maxMHz, err := getCPUWindowsExtended()
		if err != nil {
			return
		}
		if model != "" {
			info["cpu_model"] = model
		}
		if phys > 0 {
			info["cpu_physical_count"] = phys
		}
		if maxMHz > 0 {
			info["cpu_freq_max_mhz"] = round2(maxMHz)
		}
	case "darwin":
		if out, err := exec.Command("sysctl", "-n", "machdep.cpu.brand_string").Output(); err == nil {
			if s := strings.TrimSpace(string(out)); s != "" {
				info["cpu_model"] = s
			}
		}
		if out, err := exec.Command("sysctl", "-n", "hw.physicalcpu").Output(); err == nil {
			var p int
			if _, e := fmt.Sscanf(strings.TrimSpace(string(out)), "%d", &p); e == nil && p > 0 {
				info["cpu_physical_count"] = p
			}
		}
		var hz int64
		if out, err := exec.Command("sysctl", "-n", "hw.cpufrequency_max").Output(); err == nil {
			_, _ = fmt.Sscanf(strings.TrimSpace(string(out)), "%d", &hz)
		}
		if hz <= 0 {
			if out, err := exec.Command("sysctl", "-n", "hw.cpufrequency").Output(); err == nil {
				_, _ = fmt.Sscanf(strings.TrimSpace(string(out)), "%d", &hz)
			}
		}
		if hz > 0 {
			info["cpu_freq_max_mhz"] = round2(float64(hz) / 1e6)
		}
	case "linux":
		model, phys, mhz := parseLinuxProcCPUInfo()
		if model != "" {
			info["cpu_model"] = model
		}
		if phys > 0 {
			info["cpu_physical_count"] = phys
		}
		if mhz > 0 {
			info["cpu_freq_max_mhz"] = round2(mhz)
		}
	default:
		if s, err := getCPUInfo(); err == nil {
			if t := strings.TrimSpace(s); t != "" {
				info["cpu_model"] = t
			}
		}
	}
}

func pyStyleFloatStr(v float64) string {
	s := strconv.FormatFloat(v, 'f', -1, 64)
	if !strings.Contains(s, ".") && !strings.ContainsAny(strings.ToLower(s), "e") {
		s += ".0"
	}
	return s
}

func buildPythonStyleDeviceComponents(facts DeviceFacts, softwareName string) []string {
	var parts []string
	if facts.MAC != "" {
		parts = append(parts, facts.MAC)
	}
	if facts.DiskID != "" {
		parts = append(parts, facts.DiskID)
	}
	if facts.CPUCount != 0 {
		parts = append(parts, fmt.Sprintf("%d", facts.CPUCount))
	}
	if facts.MemoryTotalGB != 0 {
		parts = append(parts, pyStyleFloatStr(round2(facts.MemoryTotalGB)))
	}
	if facts.DiskTotalGB != 0 {
		parts = append(parts, pyStyleFloatStr(round2(facts.DiskTotalGB)))
	}
	if facts.System != "" {
		parts = append(parts, facts.System)
	}
	if facts.Machine != "" {
		parts = append(parts, facts.Machine)
	}
	if softwareName != "" {
		parts = append(parts, softwareName)
	}
	return parts
}

func CollectExtendedDeviceInfo() map[string]interface{} {
	info := make(map[string]interface{})

	fillCPUExtendedInfo(info)

	if mem, err := getMemoryInfo(); err == nil {
		info["memory_total_gb"] = mem["total"]
		info["memory_free_gb"] = mem["free"]
		if a, ok := mem["available"]; ok && a > 0 {
			info["memory_available_gb"] = a
		}
	}

	if disk, err := getDiskInfo(); err == nil {
		info["disk_total_gb"] = disk["total"]
		info["disk_free_gb"] = disk["free"]
	}
	if models, err := listDiskVolumes(); err == nil && len(models) > 0 {
		raw := make(map[string]interface{}, len(models))
		for k, g := range models {
			raw[k] = map[string]interface{}{"volumes": diskVolumesToIface(g.Volumes)}
		}
		info["disk_models"] = raw
	}

	info["go_version"] = runtime.Version()

	if uptime, err := getSystemUptime(); err == nil {
		info["system_uptime_seconds"] = uptime
	}

	if runtime.GOOS == "windows" {
		d, p := getWindowsDisplayAndProduct()
		if d != "" {
			info["windows_display_version"] = d
		}
		if p != "" {
			info["windows_product_name"] = p
		}
	}

	return info
}

func BuildDeviceID(serverURL string, providedDeviceID string, facts DeviceFacts, softwareName string, baseDir string, persistedIfKnown string) (string, error) {
	if baseDir == "" {
		baseDir = DefaultClientStorageRoot()
	}
	_ = os.MkdirAll(baseDir, 0o755)

	su := NormalizeServerURL(serverURL)

	if providedDeviceID != "" {
		if err := PersistDeviceID(su, providedDeviceID, softwareName, baseDir); err != nil {
			return "", err
		}
		return providedDeviceID, nil
	}

	if persistedIfKnown != "" {
		return persistedIfKnown, nil
	}

	if persisted, err := LoadPersistedDeviceID(su, softwareName, baseDir); err == nil && persisted != "" {
		return persisted, nil
	}

	parts := buildPythonStyleDeviceComponents(facts, softwareName)

	var deviceID string
	if len(parts) > 0 {
		combined := strings.Join(parts, "-")
		hash := sha256.Sum256([]byte(combined))
		deviceID = hex.EncodeToString(hash[:])[:32]
	} else {
		deviceID = uuid.New().String()
	}

	if err := PersistDeviceID(su, deviceID, softwareName, baseDir); err != nil {
		return "", err
	}
	return deviceID, nil
}

func BuildDeviceInfo(facts DeviceFacts, override *DeviceInfo) DeviceInfo {
	if override != nil {
		return *override
	}

	sys := &DeviceSystem{
		Hostname:  facts.Hostname,
		OS:        facts.System,
		Release:   facts.Release,
		Version:   facts.Version,
		Machine:   facts.Machine,
		Processor: facts.Processor,
	}
	info := DeviceInfo{Sys: sys}

	var endpoints []DeviceNetworkEndpoint
	var extended map[string]interface{}
	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		endpoints = CollectDeviceNetworkEndpoints()
	}()
	go func() {
		defer wg.Done()
		extended = CollectExtendedDeviceInfo()
	}()
	wg.Wait()

	if len(endpoints) > 0 || facts.MAC != "" || facts.IPAddress != "" {
		info.Network = &DeviceNetwork{}
		if facts.MAC != "" {
			info.Network.MACAddress = facts.MAC
		}
		if facts.IPAddress != "" {
			info.Network.IPAddress = facts.IPAddress
		}
		if len(endpoints) > 0 {
			info.Network.Interfaces = endpoints
		}
	}
	if u, err := user.Current(); err == nil {
		sys.Username = u.Username
	}

	var cpu DeviceCPU
	var cpuAny bool
	if facts.CPUCount > 0 {
		cpu.Count = facts.CPUCount
		cpuAny = true
	}
	if cpuModel, ok := extended["cpu_model"].(string); ok && strings.TrimSpace(cpuModel) != "" {
		cpu.Model = cpuModel
		cpuAny = true
	}
	if v, ok := intFromExtended(extended["cpu_physical_count"]); ok && v > 0 {
		cpu.PhysicalCount = v
		cpuAny = true
	}
	if v, ok := floatFromExtended(extended["cpu_freq_min_mhz"]); ok && v > 0 {
		cpu.FreqMinMHz = round2(v)
		cpuAny = true
	}
	if v, ok := floatFromExtended(extended["cpu_freq_max_mhz"]); ok && v > 0 {
		cpu.FreqMaxMHz = round2(v)
		cpuAny = true
	}
	if cpuAny {
		info.CPU = &cpu
	}
	var mem DeviceMemory
	var memAny bool
	if v, ok := extended["memory_total_gb"].(float64); ok {
		mem.TotalGB = v
		memAny = true
	}
	if v, ok := extended["memory_free_gb"].(float64); ok {
		mem.FreeGB = v
		memAny = true
	}
	if v, ok := extended["memory_available_gb"].(float64); ok {
		mem.AvailableGB = v
		memAny = true
	}
	if memAny {
		info.Memory = &mem
	}
	var dsk DeviceDisk
	var dskAny bool
	if models := parseDiskModelsFromExtended(extended); len(models) > 0 {
		dsk.Models = models
		dskAny = true
	} else {
		if v, ok := extended["disk_total_gb"].(float64); ok {
			dsk.TotalGB = v
			dskAny = true
		}
		if v, ok := extended["disk_free_gb"].(float64); ok {
			dsk.FreeGB = v
			dskAny = true
		}
	}
	if dskAny {
		info.Disk = &dsk
	}
	if goVer, ok := extended["go_version"].(string); ok {
		sys.GoVersion = goVer
	}
	if uptime, ok := extended["system_uptime_seconds"].(int64); ok {
		sys.SystemUptimeSecond = uptime
	}
	if v, ok := extended["windows_display_version"].(string); ok && v != "" {
		sys.WindowsDisplayVersion = v
	}
	if v, ok := extended["windows_product_name"].(string); ok && v != "" {
		sys.WindowsProductName = v
	}

	return info
}

func getSystemInfo() (release, version, processor string) {
	switch runtime.GOOS {
	case "windows":
		if wr, wv := getWindowsReleaseAndVersion(); wv != "" {
			release = wr
			version = wv
		} else {
			release = "Windows"
			cmd := exec.Command("cmd", "/c", "ver")
			if output, err := cmd.Output(); err == nil {
				version = strings.TrimSpace(string(output))
			}
		}
		processor = normalizeProcessorGOARCH()
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
		processor = normalizeProcessorGOARCH()
	}
	return
}

func normalizeProcessorGOARCH() string {
	a := runtime.GOARCH
	switch a {
	case "386":
		return "386"
	case "amd64":
		return "amd64"
	case "arm", "arm64":
		if a == "arm64" {
			return "arm64"
		}
		return "arm"
	default:
		return a
	}
}

func getCPUInfo() (string, error) {
	if runtime.GOOS == "windows" {
		if s, err := getCPUInfoWindows(); err == nil && s != "" {
			return s, nil
		}
	}
	if runtime.GOOS == "darwin" {
		cmd := exec.Command("sysctl", "-n", "machdep.cpu.brand_string")
		if output, err := cmd.Output(); err == nil {
			s := strings.TrimSpace(string(output))
			if s != "" {
				return s, nil
			}
		}
	}
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
	if runtime.GOOS == "windows" {
		return getMemoryInfoWindows()
	}

	result := make(map[string]float64)

	if runtime.GOOS == "linux" {
		if data, err := os.ReadFile("/proc/meminfo"); err == nil {
			lines := strings.Split(string(data), "\n")
			var memTotal, memFree, memAvailable float64
			var hasAvail bool
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
				} else if strings.HasPrefix(line, "MemAvailable:") {
					parts := strings.Fields(line)
					if len(parts) > 1 {
						fmt.Sscanf(parts[1], "%f", &memAvailable)
						hasAvail = true
					}
				}
			}
			if memTotal > 0 {
				result["total"] = memTotal / (1024 * 1024)
				result["free"] = memFree / (1024 * 1024)
				if hasAvail {
					result["available"] = memAvailable / (1024 * 1024)
				}
				return result, nil
			}
		}
	}
	
	return result, fmt.Errorf("memory info not available")
}

func getSystemUptime() (int64, error) {
	if runtime.GOOS == "windows" {
		return getSystemUptimeWindows()
	}

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
