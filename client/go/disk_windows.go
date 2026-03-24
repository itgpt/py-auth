//go:build windows

package authclient

import (
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
)

func getDiskInfo() (map[string]float64, error) {
	return getDiskInfoWindows()
}

func listDiskVolumes() (map[string]DeviceDiskModelGroup, error) {
	return listDiskVolumesWindows()
}

func rootDiskID() string {
	d := os.Getenv("SystemDrive")
	if d == "" {
		d = "C:"
	}
	if !strings.HasSuffix(d, "\\") {
		d += "\\"
	}
	return d
}

func rootDiskTotalBytes() (uint64, error) {
	drive := strings.TrimSuffix(rootDiskID(), "\\")
	if drive == "" {
		drive = "C:"
	}
	ps := fmt.Sprintf("[uint64](Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='%s'\").Size", drive)
	out, err := exec.Command("powershell", "-NoProfile", "-Command", ps).Output()
	if err != nil {
		return 0, err
	}
	s := strings.TrimSpace(string(out))
	return strconv.ParseUint(s, 10, 64)
}

func physicalMemoryBytes() (uint64, error) {
	out, err := exec.Command("powershell", "-NoProfile", "-Command",
		"[uint64](Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory").Output()
	if err != nil {
		return 0, err
	}
	s := strings.TrimSpace(string(out))
	return strconv.ParseUint(s, 10, 64)
}
