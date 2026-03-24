//go:build windows

package authclient

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
)

var (
	modkernel32                = windows.NewLazySystemDLL("kernel32.dll")
	procGlobalMemoryStatusEx   = modkernel32.NewProc("GlobalMemoryStatusEx")
)

type memoryStatusEx struct {
	Length               uint32
	MemoryLoad           uint32
	TotalPhys            uint64
	AvailPhys            uint64
	TotalPageFile        uint64
	AvailPageFile        uint64
	TotalVirtual         uint64
	AvailVirtual         uint64
	AvailExtendedVirtual uint64
}

func getWindowsReleaseAndVersion() (release, version string) {
	k, err := registry.OpenKey(registry.LOCAL_MACHINE, `SOFTWARE\Microsoft\Windows NT\CurrentVersion`, registry.READ)
	if err != nil {
		return "", ""
	}
	defer k.Close()

	currentBuild, _, err := k.GetStringValue("CurrentBuild")
	if err != nil || strings.TrimSpace(currentBuild) == "" {
		return "", ""
	}
	ubr, _, err := k.GetIntegerValue("UBR")
	if err != nil {
		ubr = 0
	}

	version = fmt.Sprintf("10.0.%s.%d", strings.TrimSpace(currentBuild), ubr)

	buildNum, _ := strconv.Atoi(strings.TrimSpace(currentBuild))
	if buildNum >= 22000 {
		release = "11"
	} else {
		release = "10"
	}
	return release, version
}

func getWindowsDisplayAndProduct() (display, product string) {
	k, err := registry.OpenKey(registry.LOCAL_MACHINE, `SOFTWARE\Microsoft\Windows NT\CurrentVersion`, registry.READ)
	if err != nil {
		return "", ""
	}
	defer k.Close()
	if s, _, err := k.GetStringValue("DisplayVersion"); err == nil {
		display = strings.TrimSpace(s)
	}
	if s, _, err := k.GetStringValue("ProductName"); err == nil {
		product = strings.TrimSpace(s)
	}
	return display, product
}

func getMemoryInfoWindows() (map[string]float64, error) {
	var msx memoryStatusEx
	msx.Length = uint32(unsafe.Sizeof(msx))
	r1, _, _ := procGlobalMemoryStatusEx.Call(uintptr(unsafe.Pointer(&msx)))
	if r1 == 0 {
		return nil, fmt.Errorf("GlobalMemoryStatusEx failed")
	}
	avail := round2(float64(msx.AvailPhys) / (1024 * 1024 * 1024))
	out := make(map[string]float64)
	out["total"] = round2(float64(msx.TotalPhys) / (1024 * 1024 * 1024))
	out["free"] = avail
	out["available"] = avail 
	return out, nil
}

func getDiskInfoWindows() (map[string]float64, error) {
	root := os.Getenv("SystemDrive")
	if root == "" {
		root = "C:"
	}
	if !strings.HasSuffix(root, `\`) {
		root += `\`
	}
	p, err := syscall.UTF16PtrFromString(root)
	if err != nil {
		return nil, err
	}
	var free, total, totfree uint64
	if err := windows.GetDiskFreeSpaceEx(p, &free, &total, &totfree); err != nil {
		return nil, err
	}
	out := make(map[string]float64)
	out["total"] = round2(float64(total) / (1024 * 1024 * 1024))
	out["free"] = round2(float64(totfree) / (1024 * 1024 * 1024))
	return out, nil
}

type psDiskRow struct {
	Mount     string  `json:"Mount"`
	Size      float64 `json:"Size"`
	FreeSpace float64 `json:"FreeSpace"`
	Model     string  `json:"Model"`
}

func parsePowerShellDiskJSON(data []byte) ([]psDiskRow, error) {
	data = bytes.TrimSpace(bytes.TrimPrefix(data, []byte{0xef, 0xbb, 0xbf}))
	var arr []psDiskRow
	if err := json.Unmarshal(data, &arr); err == nil && len(arr) > 0 {
		return arr, nil
	}
	var single psDiskRow
	if err := json.Unmarshal(data, &single); err != nil {
		return nil, err
	}
	if single.Mount == "" {
		return nil, fmt.Errorf("empty disk row")
	}
	return []psDiskRow{single}, nil
}

func listDiskVolumesWindows() (map[string]DeviceDiskModelGroup, error) {
	psScript := `$rows = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
  $id = $_.DeviceID
  if (-not $id.EndsWith('\')) { $id = $id + '\' }
  $letter = $_.DeviceID.TrimEnd('\')[0]
  $model = ''
  try {
    $part = Get-Partition -DriveLetter $letter -ErrorAction Stop
    $dsk = $part | Get-Disk
    if ($dsk) { $model = [string]$dsk.FriendlyName }
  } catch {}
  [PSCustomObject]@{ Mount = $id; Size = $_.Size; FreeSpace = $_.FreeSpace; Model = $model }
}
$rows | ConvertTo-Json -Compress -Depth 4`
	cmd := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command", psScript)
	out, err := cmd.Output()
	if err == nil {
		if rows, jerr := parsePowerShellDiskJSON(out); jerr == nil && len(rows) > 0 {
			var entries []diskVolEnt
			for _, r := range rows {
				mount := r.Mount
				if !strings.HasSuffix(mount, `\`) {
					mount += `\`
				}
				entries = append(entries, diskVolEnt{
					model:   r.Model,
					mount:   mount,
					device:  "",
					totalGB: round2(r.Size / (1024 * 1024 * 1024)),
					freeGB:  round2(r.FreeSpace / (1024 * 1024 * 1024)),
				})
			}
			return foldDiskVolumesByModel(entries), nil
		}
	}
	var entries []diskVolEnt
	for i := byte('A'); i <= 'Z'; i++ {
		root := string([]byte{i}) + `:\`
		p, err := syscall.UTF16PtrFromString(root)
		if err != nil {
			continue
		}
		if windows.GetDriveType(p) != windows.DRIVE_FIXED {
			continue
		}
		var free, total, totfree uint64
		if err := windows.GetDiskFreeSpaceEx(p, &free, &total, &totfree); err != nil {
			continue
		}
		entries = append(entries, diskVolEnt{
			mount:   root,
			totalGB: round2(float64(total) / (1024 * 1024 * 1024)),
			freeGB:  round2(float64(totfree) / (1024 * 1024 * 1024)),
		})
	}
	if len(entries) == 0 {
		return nil, fmt.Errorf("no fixed volumes")
	}
	sys := os.Getenv("SystemDrive")
	if sys == "" {
		sys = "C:"
	}
	if !strings.HasSuffix(sys, `\`) {
		sys += `\`
	}
	sort.Slice(entries, func(i, j int) bool {
		si := strings.EqualFold(entries[i].mount, sys)
		sj := strings.EqualFold(entries[j].mount, sys)
		if si != sj {
			return si
		}
		return entries[i].mount < entries[j].mount
	})
	return foldDiskVolumesByModel(entries), nil
}

func getSystemUptimeWindows() (int64, error) {
	return int64(windows.DurationSinceBoot().Seconds()), nil
}

func getCPUInfoWindows() (string, error) {
	m, _, _, err := getCPUWindowsExtended()
	if err != nil {
		return "", err
	}
	m = strings.TrimSpace(m)
	if m == "" {
		return "", fmt.Errorf("empty cpu name")
	}
	return m, nil
}

func getCPUWindowsExtended() (model string, physical int, maxMHz float64, err error) {
	const script = `$p = @(Get-CimInstance Win32_Processor -ErrorAction Stop)
if ($null -eq $p -or $p.Count -eq 0) { '{}' } else {
  $cores = ($p | Measure-Object -Property NumberOfCores -Sum).Sum
  $log = ($p | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
  $mhzGroup = $p | Where-Object { $_.MaxClockSpeed -gt 0 }
  $mhz = 0.0
  if ($mhzGroup) { $mhz = ($mhzGroup | Measure-Object -Property MaxClockSpeed -Maximum).Maximum }
  [PSCustomObject]@{ name = [string]$p[0].Name; physical = [int]$cores; logical = [int]$log; max_mhz = [double]$mhz } | ConvertTo-Json -Compress
}`
	ps := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command", script)
	ps.Stderr = nil
	out, e := ps.Output()
	if e != nil {
		return "", 0, 0, e
	}
	raw := strings.TrimSpace(string(out))
	raw = strings.TrimPrefix(raw, "\uFEFF")
	if raw == "" || raw == "{}" {
		return "", 0, 0, fmt.Errorf("empty wmi cpu")
	}
	var w struct {
		Name     string  `json:"name"`
		Physical int     `json:"physical"`
		MaxMHz   float64 `json:"max_mhz"`
	}
	if e := json.Unmarshal([]byte(raw), &w); e != nil {
		return "", 0, 0, e
	}
	model = strings.TrimSpace(w.Name)
	physical = w.Physical
	maxMHz = w.MaxMHz
	if model == "" && physical == 0 && maxMHz == 0 {
		return "", 0, 0, fmt.Errorf("empty wmi cpu fields")
	}
	return model, physical, maxMHz, nil
}
