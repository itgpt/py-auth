//go:build !windows

package authclient

import "errors"

var errNotWindows = errors.New("not windows")

func getWindowsReleaseAndVersion() (release, version string) {
	return "", ""
}

func getMemoryInfoWindows() (map[string]float64, error) {
	return nil, errNotWindows
}

func getDiskInfoWindows() (map[string]float64, error) {
	return nil, errNotWindows
}

func listDiskVolumesWindows() (map[string]DeviceDiskModelGroup, error) {
	return nil, errNotWindows
}

func getSystemUptimeWindows() (int64, error) {
	return 0, errNotWindows
}

func getCPUInfoWindows() (string, error) {
	return "", errNotWindows
}

func getCPUWindowsExtended() (model string, physical int, maxMHz float64, err error) {
	return "", 0, 0, errNotWindows
}

func getWindowsDisplayAndProduct() (display, product string) {
	return "", ""
}
