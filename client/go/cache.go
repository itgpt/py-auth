package authclient

import (
	"encoding/json"
	"os"
	"os/exec"
	"runtime"
	"time"
)

type CacheData struct {
	Message         string
	LastSuccessAt   float64
	HeartbeatTimes  int
}

type AuthCache struct {
	cacheDir             string
	cacheFile            string
	deviceID             string
	serverURL            string
	softwareName         string
	cacheValidityDays    int
	cacheValiditySeconds int64
	checkIntervalDays    int
	checkIntervalSeconds int64
}

func NewAuthCache(cacheDir, deviceID, serverURL, softwareName string, cacheValidityDays, checkIntervalDays int) *AuthCache {
	c := &AuthCache{
		deviceID:          deviceID,
		serverURL:         NormalizeServerURL(serverURL),
		softwareName:      softwareName,
		cacheValidityDays: cacheValidityDays,
		checkIntervalDays: checkIntervalDays,
	}
	if c.cacheValidityDays <= 0 {
		c.cacheValidityDays = 7
	}
	if c.checkIntervalDays <= 0 {
		c.checkIntervalDays = 2
	}

	c.cacheValiditySeconds = int64(c.cacheValidityDays * 24 * 60 * 60)
	c.checkIntervalSeconds = int64(c.checkIntervalDays * 24 * 60 * 60)

	if cacheDir == "" {
		cacheDir = DefaultClientStorageRoot()
	}
	c.cacheDir = cacheDir
	_ = os.MkdirAll(c.cacheDir, 0o755)
	c.cacheFile = BundlePath(c.serverURL, c.cacheDir)
	return c
}

func intFromJSON(v interface{}) (int, bool) {
	switch x := v.(type) {
	case float64:
		if x >= 0 {
			return int(x), true
		}
		return 0, false
	case int:
		return x, true
	case int64:
		return int(x), true
	default:
		return 0, false
	}
}

func (c *AuthCache) snapshotAuthRow() (*CacheData, int) {
	m, _ := ReadStateDict(c.serverURL, c.cacheDir)
	if m == nil {
		return nil, 0
	}
	row := loadAppsMap(m)[c.softwareName]
	if row == nil {
		return nil, 0
	}
	if _, ok := rowLastSuccessUnix(row); !ok {
		return nil, 0
	}
	n, ok := intFromJSON(row["heartbeat_times"])
	if !ok || n < 1 {
		_ = c.ClearCache()
		return nil, 0
	}
	cd := stateMapToCacheData(row)
	if cd == nil {
		return nil, 0
	}
	return cd, n
}

func (c *AuthCache) StoredHeartbeatTimes() int {
	_, n := c.snapshotAuthRow()
	return n
}

func (c *AuthCache) IsCacheTTLValid(cache *CacheData) bool {
	if cache == nil || cache.LastSuccessAt <= 0 {
		return false
	}
	now := float64(time.Now().UnixNano()) / 1e9
	return (now-cache.LastSuccessAt) < float64(c.cacheValiditySeconds)
}

func stateMapToCacheData(m map[string]interface{}) *CacheData {
	if m == nil {
		return nil
	}
	ts, ok := rowLastSuccessUnix(m)
	if !ok {
		return nil
	}
	cd := &CacheData{
		Message:       "设备已授权",
		LastSuccessAt: ts,
	}
	if n, ok := intFromJSON(m["heartbeat_times"]); ok && n > 0 {
		cd.HeartbeatTimes = n
	}
	return cd
}

func (c *AuthCache) GetCache() (*CacheData, error) {
	m, err := ReadStateDict(c.serverURL, c.cacheDir)
	if err != nil {
		return nil, err
	}
	if m == nil {
		return nil, nil
	}
	row := loadAppsMap(m)[c.softwareName]
	if row == nil {
		return nil, nil
	}
	return stateMapToCacheData(row), nil
}

func (c *AuthCache) writeBundleWithRetry(data map[string]interface{}) error {
	err := WriteStateDict(c.serverURL, c.cacheDir, data)
	if err == nil {
		if runtime.GOOS == "windows" {
			_ = exec.Command("attrib", "+H", c.cacheFile).Run()
		}
		return nil
	}
	if runtime.GOOS == "windows" {
		if _, statErr := os.Stat(c.cacheFile); statErr == nil {
			_ = exec.Command("attrib", "-H", c.cacheFile).Run()
			_ = os.Remove(c.cacheFile)
			err = WriteStateDict(c.serverURL, c.cacheDir, data)
			if err == nil {
				_ = exec.Command("attrib", "+H", c.cacheFile).Run()
			}
		}
	}
	return err
}

func (c *AuthCache) LoadDeviceInfoSnapshot() (*DeviceInfo, error) {
	m, err := ReadStateDict(c.serverURL, c.cacheDir)
	if err != nil || m == nil {
		return nil, err
	}
	row := loadAppsMap(m)[c.softwareName]
	if row == nil {
		return nil, nil
	}
	var di DeviceInfo
	switch v := row[BundleProductDeviceInfoSnapshotKey].(type) {
	case string:
		if v == "" {
			return nil, nil
		}
		if err := json.Unmarshal([]byte(v), &di); err != nil {
			return nil, err
		}
		return &di, nil
	case map[string]interface{}:
		b, err := json.Marshal(v)
		if err != nil {
			return nil, err
		}
		if err := json.Unmarshal(b, &di); err != nil {
			return nil, err
		}
		return &di, nil
	default:
		return nil, nil
	}
}

func (c *AuthCache) SaveCache(authorized bool, _ string, nextHeartbeat *int, snapshot *DeviceInfo) error {
	m, _ := ReadStateDict(c.serverURL, c.cacheDir)
	if m == nil {
		m = make(map[string]interface{})
	}
	for _, k := range bundleRootStrayKeys {
		delete(m, k)
	}
	now := float64(time.Now().UnixNano()) / 1e9

	apps := loadAppsMap(m)
	sub := cloneStringMap(apps[c.softwareName])
	delete(sub, "software_name")
	if !authorized {
		for _, k := range bundleProductRevokeKeys {
			delete(sub, k)
		}
		sub["device_id"] = c.deviceID
	} else {
		for _, k := range bundleProductAuthorizeStripKeys {
			delete(sub, k)
		}
		sub["device_id"] = c.deviceID
		sub["last_success_at"] = now
		if nextHeartbeat != nil {
			sub["heartbeat_times"] = *nextHeartbeat
		}
		if snapshot != nil {
			if b, err := json.Marshal(snapshot); err == nil && len(b) > 0 {
				var obj map[string]interface{}
				if err := json.Unmarshal(b, &obj); err == nil && len(obj) > 0 {
					sub[BundleProductDeviceInfoSnapshotKey] = obj
				}
			}
		}
	}
	apps[c.softwareName] = sub
	commitAppsMap(m, apps)

	return c.writeBundleWithRetry(m)
}

func (c *AuthCache) IsCacheValid() bool {
	cache, err := c.GetCache()
	if err != nil || cache == nil {
		return false
	}
	return c.IsCacheTTLValid(cache)
}

func (c *AuthCache) NeedsCheck() bool {
	cache, err := c.GetCache()
	if err != nil || cache == nil {
		return true
	}
	now := float64(time.Now().UnixNano()) / 1e9
	return (now - cache.LastSuccessAt) >= float64(c.checkIntervalSeconds)
}

func (c *AuthCache) ClearCache() error {
	m, err := ReadStateDict(c.serverURL, c.cacheDir)
	if err != nil {
		return err
	}
	if m == nil {
		return nil
	}
	for _, k := range bundleRootStrayKeys {
		delete(m, k)
	}
	apps := loadAppsMap(m)
	sub := cloneStringMap(apps[c.softwareName])
	delete(sub, "software_name")
	for _, k := range bundleProductClearRowKeys {
		delete(sub, k)
	}
	sub["device_id"] = c.deviceID
	apps[c.softwareName] = sub
	commitAppsMap(m, apps)
	if !anyAppMapHasDeviceID(apps) {
		if _, statErr := os.Stat(c.cacheFile); statErr == nil {
			_ = os.Remove(c.cacheFile)
		}
		return nil
	}
	return c.writeBundleWithRetry(m)
}

func anyAppMapHasDeviceID(apps map[string]map[string]interface{}) bool {
	for _, row := range apps {
		if rowDeviceIDString(row) != "" {
			return true
		}
	}
	return false
}
