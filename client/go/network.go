package authclient

import (
	"context"
	"io"
	"net"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
)

type NetworkInterface struct {
	MAC string
	IP  string
}

func isProbablyVirtualMAC(mac string) bool {
	m := strings.ToLower(strings.ReplaceAll(mac, ":", ""))
	if len(m) < 6 {
		return false
	}
	prefixes := []string{
		"005056", "000c29", "000569", "001c14", 
		"080027", 
		"00155d", 
		"525400", 
	}
	for _, p := range prefixes {
		if strings.HasPrefix(m, p) {
			return true
		}
	}
	return false
}

func isCommonHyperVNatHostIP(ip string) bool {
	return strings.HasPrefix(ip, "192.168.117.")
}

func networkIfaceScore(n NetworkInterface) int {
	score := 0
	if n.IP != "" {
		score += 40
		if strings.HasPrefix(n.IP, "169.254.") {
			score -= 25
		}
		if isCommonHyperVNatHostIP(n.IP) {
			score -= 50
		}
	}
	if n.MAC != "" {
		score += 10
	}
	if !isProbablyVirtualMAC(n.MAC) {
		score += 100
	}
	return score
}

func getNetworkInterfaces() ([]NetworkInterface, error) {
	var result []NetworkInterface

	interfaces, err := net.Interfaces()
	if err != nil {
		return result, err
	}

	for _, iface := range interfaces {
		if iface.Flags&net.FlagUp == 0 {
			continue
		}
		if iface.Flags&net.FlagLoopback != 0 {
			continue
		}

		mac := iface.HardwareAddr.String()
		if mac == "" {
			continue
		}

		addrs, err := iface.Addrs()
		if err != nil {
			continue
		}

		var ip string
		for _, addr := range addrs {
			ipNet, ok := addr.(*net.IPNet)
			if !ok {
				continue
			}
			ipv4 := ipNet.IP.To4()
			if ipv4 != nil {
				ip = ipv4.String()
				break
			}
		}

		result = append(result, NetworkInterface{
			MAC: mac,
			IP:  ip,
		})
	}

	return result, nil
}

func sortedNetworkInterfaces() ([]NetworkInterface, error) {
	list, err := getNetworkInterfaces()
	if err != nil {
		return nil, err
	}
	sort.SliceStable(list, func(i, j int) bool {
		return networkIfaceScore(list[i]) > networkIfaceScore(list[j])
	})
	return list, nil
}

func preferredNetworkEndpoint() (mac, ip string) {
	list, err := sortedNetworkInterfaces()
	if err != nil || len(list) == 0 {
		return "", ""
	}

	for _, n := range list {
		if n.MAC != "" && n.IP != "" && !strings.HasPrefix(n.IP, "127.") {
			return strings.ToLower(strings.TrimSpace(n.MAC)), n.IP
		}
	}
	for _, n := range list {
		if n.MAC != "" && n.IP != "" {
			return strings.ToLower(strings.TrimSpace(n.MAC)), n.IP
		}
	}
	for _, n := range list {
		if n.IP != "" && !strings.HasPrefix(n.IP, "127.") && !strings.HasPrefix(n.IP, "169.254.") {
			ip = n.IP
			break
		}
	}
	for _, n := range list {
		if n.MAC == "" {
			continue
		}
		if !isProbablyVirtualMAC(n.MAC) {
			mac = strings.ToLower(strings.TrimSpace(n.MAC))
			break
		}
	}
	if mac == "" {
		for _, n := range list {
			if n.MAC != "" {
				mac = strings.ToLower(strings.TrimSpace(n.MAC))
				break
			}
		}
	}
	return mac, ip
}

func CollectDeviceNetworkEndpoints() []DeviceNetworkEndpoint {
	list, err := sortedNetworkInterfaces()
	if err != nil {
		return nil
	}
	seen := make(map[string]bool)
	var out []DeviceNetworkEndpoint
	for _, n := range list {
		mac := strings.ToLower(strings.TrimSpace(n.MAC))
		ip := strings.TrimSpace(n.IP)
		if mac == "" && ip == "" {
			continue
		}
		key := mac + "|" + ip
		if seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, DeviceNetworkEndpoint{MACAddress: mac, IPAddress: ip})
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

func getOutboundIPv4Hint() string {
	c, err := net.Dial("udp4", "8.8.8.8:80")
	if err != nil {
		return ""
	}
	defer c.Close()
	addr, ok := c.LocalAddr().(*net.UDPAddr)
	if !ok || addr == nil || addr.IP == nil {
		return ""
	}
	if v4 := addr.IP.To4(); v4 != nil {
		s := v4.String()
		if s != "" && !strings.HasPrefix(s, "127.") {
			return s
		}
	}
	return ""
}

const publicIPFetchURL = "https://ifconfig.icu/ip"

func publicIPFetchTimeout() time.Duration {
	const defaultD = 8 * time.Second
	s := strings.TrimSpace(os.Getenv("AUTH_PUBLIC_IP_TIMEOUT_MS"))
	if s == "" {
		return defaultD
	}
	ms, err := strconv.Atoi(s)
	if err != nil || ms < 500 || ms > 60000 {
		return defaultD
	}
	return time.Duration(ms) * time.Millisecond
}


func fetchPublicIP() string {
	d := publicIPFetchTimeout()
	ctx, cancel := context.WithTimeout(context.Background(), d)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, publicIPFetchURL, nil)
	if err != nil {
		return ""
	}
	req.Header.Set("User-Agent", "py-auth-client-go/1")
	client := &http.Client{Timeout: d}
	resp, err := client.Do(req)
	if err != nil || resp == nil {
		return ""
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return ""
	}
	b, err := io.ReadAll(io.LimitReader(resp.Body, 128))
	if err != nil {
		return ""
	}
	s := strings.TrimSpace(string(b))
	if s == "" {
		return ""
	}
	if i := strings.IndexAny(s, " \t\r\n"); i >= 0 {
		s = strings.TrimSpace(s[:i])
	}
	parsed := net.ParseIP(s)
	if parsed == nil {
		return ""
	}
	return parsed.String()
}
