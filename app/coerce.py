"""将配置/API 中的值规范为 bool（与历史行为一致）。"""

from typing import Any

_TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})


def coerce_boolish(value: Any, *, if_none: bool = False) -> bool:
    if value is None:
        return if_none
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_STRINGS
    return bool(value)
