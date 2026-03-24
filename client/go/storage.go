package authclient

import (
	"os"
	"path/filepath"
	"runtime"
)

func DefaultClientStorageRoot() string {
	if runtime.GOOS == "windows" {
		pd := os.Getenv("ProgramData")
		if pd == "" {
			pd = `C:\ProgramData`
		}
		return filepath.Join(pd, ".RuntimeRepository")
	}
	return filepath.Join(os.TempDir(), ".runtime-repository")
}
