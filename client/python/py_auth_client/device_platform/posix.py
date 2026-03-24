"""Linux 与 Darwin：根盘、卷型号、CPU 型号（本模块仅在 linux/darwin 上被加载）。"""

from __future__ import annotations

import sys
from typing import Any, Dict, Optional


def apply_os_version_facts(_facts: Dict[str, Any]) -> None:
    return None


def cpu_model_platform_specific() -> Optional[str]:
    if sys.platform == "linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line_l = line.lower()
                    if line_l.startswith("model name") or line_l.startswith(
                        "cpu model\t"
                    ) or line_l.startswith("processor model"):
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            v = parts[1].strip()
                            if v:
                                return v
        except Exception:
            pass
        return None
    if sys.platform == "darwin":
        try:
            import subprocess

            r = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            s = (r.stdout or "").strip()
            return s or None
        except Exception:
            return None
    return None


def root_disk_mount_and_id() -> tuple[str, str]:
    if sys.platform == "linux":
        disk_id = "/"
        try:
            with open("/proc/mounts", encoding="utf-8") as f:
                line = (f.readline() or "").strip()
            fields = line.split()
            if fields and fields[0]:
                disk_id = fields[0]
        except Exception:
            pass
        return "/", disk_id
    if sys.platform == "darwin":
        try:
            import subprocess

            out = subprocess.run(
                ["df", "/"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            lines = (out.stdout or "").strip().split("\n")
            if len(lines) >= 2:
                c0 = lines[1].split()[0]
                if c0:
                    return "/", c0
        except Exception:
            pass
        return "/", "/"
    return "/", "/"


def disk_model_for_partition(mountpoint: str, device: str) -> str:
    dev = (device or "").strip()
    mp = (mountpoint or "").strip()
    if sys.platform == "linux" and dev.startswith("/dev/"):
        try:
            import subprocess

            r = subprocess.run(
                ["lsblk", "-no", "MODEL", dev],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return (r.stdout or "").strip()
        except Exception:
            return ""
    if sys.platform == "darwin":
        try:
            import subprocess

            r = subprocess.run(
                ["diskutil", "info", mp],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            for line in (r.stdout or "").splitlines():
                line = line.strip()
                if line.startswith("Device / Media Name:"):
                    return line.split(":", 1)[-1].strip()
                if line.startswith("Media Name:"):
                    return line.split(":", 1)[-1].strip()
        except Exception:
            pass
    return ""
