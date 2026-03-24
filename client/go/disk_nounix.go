//go:build !unix && !windows

package authclient

import (
	"fmt"
	"os"
)


func rootDiskTotalBytes() (uint64, error) {
	return 0, os.ErrNotExist
}

func rootDiskID() string {
	return "/"
}

func physicalMemoryBytes() (uint64, error) {
	return 0, os.ErrNotExist
}

func getDiskInfo() (map[string]float64, error) {
	return nil, fmt.Errorf("disk info not available")
}

func listDiskVolumes() (map[string]DeviceDiskModelGroup, error) {
	return nil, fmt.Errorf("disk volumes not available")
}
