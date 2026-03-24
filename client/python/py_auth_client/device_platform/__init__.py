"""按进程平台加载实现（思路对齐 Go client：`disk_windows` / `disk` / `disk_nounix`）。"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from .windows import (
        apply_os_version_facts,
        cpu_model_platform_specific,
        disk_model_for_partition,
        root_disk_mount_and_id,
    )
elif sys.platform in ("linux", "darwin"):
    from .posix import (
        apply_os_version_facts,
        cpu_model_platform_specific,
        disk_model_for_partition,
        root_disk_mount_and_id,
    )
else:
    from .fallback import (
        apply_os_version_facts,
        cpu_model_platform_specific,
        disk_model_for_partition,
        root_disk_mount_and_id,
    )

__all__ = [
    "apply_os_version_facts",
    "cpu_model_platform_specific",
    "disk_model_for_partition",
    "root_disk_mount_and_id",
]
