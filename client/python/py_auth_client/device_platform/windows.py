"""Windows 专用：注册表版本号、根盘、卷型号、CPU 名称（本模块仅在 win32 上被加载）。"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def _windows_nt_current_version_reg() -> Dict[str, Any]:
    """读注册表 CurrentVersion，与 Go device_windows 语义对齐（ASCII 友好、含 UBR）。"""
    out: Dict[str, Any] = {}
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        ) as key:
            for name in (
                "CurrentBuild",
                "UBR",
                "DisplayVersion",
                "ProductName",
                "CurrentMajorVersionNumber",
                "CurrentMinorVersionNumber",
            ):
                try:
                    val, _ = winreg.QueryValueEx(key, name)
                    out[name] = val
                except OSError:
                    pass
    except Exception:
        pass
    return out


def apply_os_version_facts(facts: Dict[str, Any]) -> None:
    """用 CurrentBuild + UBR 覆盖 version，避免 platform.version() 缺修订号；release 与 Go 一致（build≥22000 → 11）。"""
    reg = _windows_nt_current_version_reg()
    cb = reg.get("CurrentBuild")
    if cb is None:
        return
    build_str = str(cb).strip()
    if not build_str:
        return
    try:
        ubr_raw = reg.get("UBR", 0)
        ubr = int(ubr_raw) if ubr_raw is not None else 0
    except (TypeError, ValueError):
        ubr = 0
    facts["version"] = f"10.0.{build_str}.{ubr}"
    try:
        bn = int(build_str)
        facts["release"] = "11" if bn >= 22000 else "10"
    except ValueError:
        pass
    if reg.get("DisplayVersion") is not None:
        facts["windows_display_version"] = str(reg["DisplayVersion"]).strip()
    if reg.get("ProductName") is not None:
        facts["windows_product_name"] = str(reg["ProductName"]).strip()


def cpu_model_platform_specific() -> Optional[str]:
    """与 Go getCPUInfoWindows 一致，读 Win32_Processor.Name。"""
    try:
        import subprocess

        cmd = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "(Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1).Name",
        ]
        kw: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "timeout": 15,
            "check": False,
        }
        cnw = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if cnw:
            kw["creationflags"] = cnw
        r = subprocess.run(cmd, **kw)
        if r.returncode != 0:
            return None
        s = (r.stdout or "").strip().strip("\ufeff")
        return s or None
    except Exception:
        return None


def root_disk_mount_and_id() -> tuple[str, str]:
    """与 Go rootDiskID 对齐；勿用 disk_partitions()[0]（常为非系统盘）。"""
    d = (os.environ.get("SystemDrive", "C:").rstrip("\\") + "\\")
    return d, d


def disk_model_for_partition(mountpoint: str, _device: str) -> str:
    m = (mountpoint or "").strip()
    if len(m) >= 2 and m[1] == ":":
        letter = m[0].upper()
    else:
        return ""
    try:
        import subprocess

        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"(Get-Partition -DriveLetter '{letter}' -ErrorAction SilentlyContinue | "
                "Get-Disk -ErrorAction SilentlyContinue).FriendlyName",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return (r.stdout or "").strip()
    except Exception:
        return ""
