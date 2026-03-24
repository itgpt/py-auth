package authclient

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

const nonceLen = 12

const BundleProductDeviceInfoSnapshotKey = "device_info_snapshot"

var bundleRootStrayKeys = []string{"heartbeat_times", "device_id", "last_success_at"}

var bundleProductRevokeKeys = []string{"heartbeat_times", "last_success_at", BundleProductDeviceInfoSnapshotKey}

var bundleProductAuthorizeStripKeys = []string{}

var bundleProductClearRowKeys = []string{"heartbeat_times", "last_success_at", BundleProductDeviceInfoSnapshotKey}

func NormalizeServerURL(serverURL string) string {
	return strings.TrimRight(strings.TrimSpace(serverURL), "/")
}

func BundlePath(serverURL, baseDir string) string {
	if baseDir == "" {
		baseDir = DefaultClientStorageRoot()
	}
	su := NormalizeServerURL(serverURL)
	suSum := sha256.Sum256([]byte(su))
	sh := hex.EncodeToString(suSum[:])[:12]
	return filepath.Join(baseDir, fmt.Sprintf("state_%s_default.dat", sh))
}

func deriveBundleKey(serverURL string) []byte {
	su := NormalizeServerURL(serverURL)
	sum := sha256.Sum256([]byte(su))
	return sum[:]
}

func ReadStateDict(serverURL, baseDir string) (map[string]interface{}, error) {
	path := BundlePath(serverURL, baseDir)
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return nil, nil
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	key := deriveBundleKey(serverURL)
	if len(raw) < nonceLen+16+1 {
		return nil, nil
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, nil
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, nil
	}
	nonce := raw[:nonceLen]
	sealed := raw[nonceLen:]
	plain, err := gcm.Open(nil, nonce, sealed, nil)
	if err != nil {
		return nil, nil
	}
	var root interface{}
	if err := json.Unmarshal(plain, &root); err != nil {
		return nil, nil
	}
	m, ok := root.(map[string]interface{})
	if !ok {
		if runtime.GOOS == "windows" {
			_ = exec.Command("attrib", "-H", path).Run()
		}
		_ = os.Remove(path)
		return nil, nil
	}
	delete(m, "device_id")
	return m, nil
}

func isReservedBundleRootKey(k string) bool {
	switch k {
	case "apps", "heartbeat_times", "device_id", "last_success_at":
		return true
	default:
		return false
	}
}

func WriteStateDict(serverURL, baseDir string, data map[string]interface{}) error {
	path := BundlePath(serverURL, baseDir)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	plain, err := json.Marshal(data)
	if err != nil {
		return err
	}
	key := deriveBundleKey(serverURL)
	block, err := aes.NewCipher(key)
	if err != nil {
		return err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return err
	}
	nonce := make([]byte, nonceLen)
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return err
	}
	sealed := gcm.Seal(nil, nonce, plain, nil)
	return os.WriteFile(path, append(nonce, sealed...), 0o644)
}

func cloneStringMap(sub map[string]interface{}) map[string]interface{} {
	if sub == nil {
		return map[string]interface{}{}
	}
	cp := make(map[string]interface{}, len(sub))
	for k, v := range sub {
		cp[k] = v
	}
	return cp
}

func rowLastSuccessUnix(row map[string]interface{}) (float64, bool) {
	if row == nil {
		return 0, false
	}
	jsonFloat := func(v interface{}) (float64, bool) {
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
	if f, ok := jsonFloat(row["last_success_at"]); ok && f > 0 {
		return f, true
	}
	return 0, false
}

func rowDeviceIDString(row map[string]interface{}) string {
	if row == nil {
		return ""
	}
	if s, ok := row["device_id"].(string); ok && strings.TrimSpace(s) != "" {
		return strings.TrimSpace(s)
	}
	return ""
}

func loadAppsMap(m map[string]interface{}) map[string]map[string]interface{} {
	out := make(map[string]map[string]interface{})
	if m == nil {
		return out
	}
	for k, v := range m {
		if isReservedBundleRootKey(k) {
			continue
		}
		sub, ok := v.(map[string]interface{})
		if !ok {
			continue
		}
		name := strings.TrimSpace(k)
		if name == "" {
			continue
		}
		cp := cloneStringMap(sub)
		delete(cp, "software_name")
		out[name] = cp
	}
	return out
}

func commitAppsMap(m map[string]interface{}, apps map[string]map[string]interface{}) {
	delete(m, "apps")
	var stale []string
	for k := range m {
		if isReservedBundleRootKey(k) {
			continue
		}
		v, ok := m[k]
		if !ok {
			continue
		}
		if _, isMap := v.(map[string]interface{}); !isMap {
			continue
		}
		if _, still := apps[k]; !still {
			stale = append(stale, k)
		}
	}
	for _, k := range stale {
		delete(m, k)
	}
	for k, v := range apps {
		m[k] = cloneStringMap(v)
	}
}
