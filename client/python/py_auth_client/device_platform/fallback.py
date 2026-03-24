"""非 Windows、非 Linux、非 Darwin：桩实现（与 Go `disk_nounix` 一致）。"""

from __future__ import annotations

from typing import Any, Dict, Optional


def root_disk_mount_and_id() -> tuple[str, str]:
    return "/", "/"


def apply_os_version_facts(_facts: Dict[str, Any]) -> None:
    return None


def cpu_model_platform_specific() -> Optional[str]:
    return None


def disk_model_for_partition(_mountpoint: str, _device: str) -> str:
    return ""
