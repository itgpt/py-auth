//go:build unix

package authclient

import (
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"syscall"
)

func rootDiskTotalBytes() (uint64, error) {
	if runtime.GOOS != "linux" && runtime.GOOS != "darwin" {
		return 0, os.ErrNotExist
	}
	var st syscall.Statfs_t
	if err := syscall.Statfs("/", &st); err != nil {
		return 0, err
	}
	return uint64(st.Blocks) * uint64(st.Bsize), nil
}

func rootDiskID() string {
	switch runtime.GOOS {
	case "linux":
		data, err := os.ReadFile("/proc/mounts")
		if err != nil {
			return "/"
		}
		line := strings.TrimSpace(strings.Split(string(data), "\n")[0])
		if line == "" {
			return "/"
		}
		fields := strings.Fields(line)
		if len(fields) > 0 && fields[0] != "" {
			return fields[0]
		}
		return "/"
	case "darwin":
		out, err := exec.Command("df", "/").Output()
		if err != nil {
			return "/"
		}
		lines := strings.Split(strings.TrimSpace(string(out)), "\n")
		if len(lines) < 2 {
			return "/"
		}
		fields := strings.Fields(lines[1])
		if len(fields) > 0 && fields[0] != "" {
			return fields[0]
		}
		return "/"
	default:
		return "/"
	}
}

func skipUnixDiskFstype(fstype string) bool {
	switch fstype {
	case "tmpfs", "devtmpfs", "proc", "sysfs", "devpts", "cgroup2", "cgroup", "pstore",
		"bpf", "tracefs", "fusectl", "mqueue", "hugetlbfs", "squashfs", "rpc_pipefs",
		"autofs", "configfs", "securityfs", "debugfs", "binfmt_misc", "overlay", "nsfs",
		"fuse.portal":
		return true
	case "nfs", "nfs4", "cifs", "smb3", "9p", "ceph", "glusterfs":
		return true
	}
	if strings.HasPrefix(fstype, "fuse.") && fstype != "fuseblk" {
		return true
	}
	return false
}

func linuxDiskModel(dev string) string {
	dev = strings.TrimSpace(dev)
	if dev == "" || !strings.HasPrefix(dev, "/dev/") {
		return ""
	}
	out, err := exec.Command("lsblk", "-no", "MODEL", dev).Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

func darwinDiskModel(mount string) string {
	out, err := exec.Command("diskutil", "info", mount).Output()
	if err != nil {
		return ""
	}
	for _, line := range strings.Split(string(out), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "Device / Media Name:") {
			return strings.TrimSpace(strings.TrimPrefix(line, "Device / Media Name:"))
		}
		if strings.HasPrefix(line, "Media Name:") {
			return strings.TrimSpace(strings.TrimPrefix(line, "Media Name:"))
		}
	}
	return ""
}

func listDiskVolumesLinux() (map[string]DeviceDiskModelGroup, error) {
	data, err := os.ReadFile("/proc/mounts")
	if err != nil {
		return nil, err
	}
	seen := make(map[string]bool)
	modelCache := make(map[string]string)
	var entries []diskVolEnt
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 3 {
			continue
		}
		dev, mp, fst := fields[0], fields[1], fields[2]
		if skipUnixDiskFstype(fst) {
			continue
		}
		if strings.HasPrefix(mp, "/proc") || strings.HasPrefix(mp, "/sys") {
			continue
		}
		if mp == "/dev" || strings.HasPrefix(mp, "/dev/") {
			continue
		}
		if strings.HasPrefix(dev, "/dev/loop") {
			continue
		}
		if seen[mp] {
			continue
		}
		var st syscall.Statfs_t
		if err := syscall.Statfs(mp, &st); err != nil {
			continue
		}
		seen[mp] = true
		bs := float64(st.Bsize)
		t := round2(float64(st.Blocks) * bs / (1024 * 1024 * 1024))
		f := round2(float64(st.Bavail) * bs / (1024 * 1024 * 1024))
		var model string
		if strings.HasPrefix(dev, "/dev/") {
			if m, ok := modelCache[dev]; ok {
				model = m
			} else {
				model = linuxDiskModel(dev)
				modelCache[dev] = model
			}
		}
		entries = append(entries, diskVolEnt{
			model:   model,
			mount:   mp,
			device:  dev,
			totalGB: t,
			freeGB:  f,
		})
	}
	if len(entries) == 0 {
		return nil, fmt.Errorf("no volumes from /proc/mounts")
	}
	return foldDiskVolumesByModel(entries), nil
}

func listDiskVolumesDarwin() (map[string]DeviceDiskModelGroup, error) {
	out, err := exec.Command("df", "-l", "-P", "-k").Output()
	if err != nil {
		return nil, err
	}
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	if len(lines) < 2 {
		return nil, fmt.Errorf("df empty")
	}
	var entries []diskVolEnt
	for _, line := range lines[1:] {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 6 {
			continue
		}
		n := len(fields)
		mount := fields[n-1]
		availKB, err1 := strconv.ParseInt(fields[n-3], 10, 64)
		blocks, err2 := strconv.ParseInt(fields[n-5], 10, 64)
		if err1 != nil || err2 != nil {
			continue
		}
		dev := strings.Join(fields[:n-5], " ")
		totalGB := round2(float64(blocks) / (1024 * 1024))
		freeGB := round2(float64(availKB) / (1024 * 1024))
		entries = append(entries, diskVolEnt{
			model:   darwinDiskModel(mount),
			mount:   mount,
			device:  dev,
			totalGB: totalGB,
			freeGB:  freeGB,
		})
	}
	if len(entries) == 0 {
		return nil, fmt.Errorf("df parse: no rows")
	}
	return foldDiskVolumesByModel(entries), nil
}

func listDiskVolumesUnix() (map[string]DeviceDiskModelGroup, error) {
	switch runtime.GOOS {
	case "linux":
		return listDiskVolumesLinux()
	case "darwin":
		return listDiskVolumesDarwin()
	default:
		return nil, os.ErrNotExist
	}
}

func getDiskInfoUnix() (map[string]float64, error) {
	if runtime.GOOS != "linux" && runtime.GOOS != "darwin" {
		return nil, os.ErrNotExist
	}
	var st syscall.Statfs_t
	if err := syscall.Statfs("/", &st); err != nil {
		return nil, err
	}
	bs := float64(st.Bsize)
	total := round2(float64(st.Blocks) * bs / (1024 * 1024 * 1024))
	free := round2(float64(st.Bavail) * bs / (1024 * 1024 * 1024))
	return map[string]float64{"total": total, "free": free}, nil
}

func physicalMemoryBytes() (uint64, error) {
	switch runtime.GOOS {
	case "linux":
		data, err := os.ReadFile("/proc/meminfo")
		if err != nil {
			return 0, err
		}
		for _, line := range strings.Split(string(data), "\n") {
			if strings.HasPrefix(line, "MemTotal:") {
				fields := strings.Fields(line)
				if len(fields) >= 2 {
					kb, err := strconv.ParseUint(fields[1], 10, 64)
					if err != nil {
						return 0, err
					}
					return kb * 1024, nil
				}
			}
		}
		return 0, os.ErrNotExist
	case "darwin":
		out, err := exec.Command("sysctl", "-n", "hw.memsize").Output()
		if err != nil {
			return 0, err
		}
		s := strings.TrimSpace(string(out))
		return strconv.ParseUint(s, 10, 64)
	default:
		return 0, os.ErrNotExist
	}
}

func getDiskInfo() (map[string]float64, error) {
	if runtime.GOOS == "linux" || runtime.GOOS == "darwin" {
		if m, err := getDiskInfoUnix(); err == nil {
			return m, nil
		}
	}
	return nil, fmt.Errorf("disk info not available")
}

func listDiskVolumes() (map[string]DeviceDiskModelGroup, error) {
	switch runtime.GOOS {
	case "linux", "darwin":
		return listDiskVolumesUnix()
	default:
		return nil, fmt.Errorf("disk volumes not available")
	}
}
