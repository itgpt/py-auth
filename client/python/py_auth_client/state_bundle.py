from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_NONCE_LEN = 12


def _aesgcm(key: bytes):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(key)


logger = logging.getLogger("py_auth_client")

_RESERVED_ROOT_KEYS = frozenset(
    {
        "apps",
        "heartbeat_times",
        "device_id",
        "last_success_at",
    }
)

BUNDLE_ROOT_STRAY_KEYS = (
    "heartbeat_times",
    "device_id",
    "last_success_at",
)

BUNDLE_PRODUCT_DEVICE_INFO_SNAPSHOT_KEY = "device_info_snapshot"

BUNDLE_PRODUCT_REVOKE_KEYS = (
    "heartbeat_times",
    "last_success_at",
    BUNDLE_PRODUCT_DEVICE_INFO_SNAPSHOT_KEY,
)


def get_client_storage_root() -> Path:
    if os.name == "nt" or sys.platform == "win32":
        pd = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        p = Path(pd) / ".RuntimeRepository"
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = Path(tempfile.gettempdir()) / ".runtime-repository"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _unlink_state_file_quietly(path: Path) -> None:
    try:
        if os.name == "nt":
            try:
                import ctypes

                ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x80)
            except Exception:
                pass
        path.unlink()
    except OSError:
        pass


def load_apps_map(root: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for k, v in root.items():
        if k in _RESERVED_ROOT_KEYS:
            continue
        if not isinstance(v, dict):
            continue
        name = str(k).strip()
        if not name:
            continue
        sub = dict(v)
        sub.pop("software_name", None)
        out[name] = sub
    return out


def commit_apps_map(root: dict[str, Any], apps_map: dict[str, dict[str, Any]]) -> None:
    root.pop("apps", None)
    for k in list(root.keys()):
        if k in _RESERVED_ROOT_KEYS:
            continue
        if isinstance(root.get(k), dict) and k not in apps_map:
            del root[k]
    for sn, row in apps_map.items():
        root[sn] = dict(row)


def row_last_success_ts(row: dict[str, Any] | None) -> float | None:
    if not isinstance(row, dict):
        return None
    v = row.get("last_success_at")
    if v is None:
        return None
    try:
        f = float(v)
        if f > 0:
            return f
    except (TypeError, ValueError):
        pass
    return None


def row_device_id_str(row: dict[str, Any] | None) -> str | None:
    if not isinstance(row, dict):
        return None
    v = row.get("device_id")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def _normalize_server_url(server_url: str) -> str:
    return (server_url or "").strip().rstrip("/")


def bundle_path(server_url: str, base_dir: Path | None = None) -> Path:
    root = base_dir if base_dir is not None else get_client_storage_root()
    su = _normalize_server_url(server_url)
    sh = hashlib.sha256(su.encode("utf-8")).hexdigest()[:12]
    return root / f"state_{sh}_default.dat"


def _derive_key(server_url: str) -> bytes:
    su = _normalize_server_url(server_url)
    return hashlib.sha256(su.encode("utf-8")).digest()


def read_state_dict(
    server_url: str,
    *,
    base_dir: Path | None = None,
) -> dict[str, Any] | None:
    path = bundle_path(server_url, base_dir)
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
    except Exception:
        return None
    if len(raw) < _NONCE_LEN + 16 + 1:
        return None
    key = _derive_key(server_url)
    nonce = raw[:_NONCE_LEN]
    ct = raw[_NONCE_LEN:]
    aes = _aesgcm(key)
    try:
        plain = aes.decrypt(nonce, ct, None)
    except Exception:
        return None
    try:
        data = json.loads(plain.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        _unlink_state_file_quietly(path)
        return None
    data.pop("device_id", None)
    return data


def write_state_dict(
    server_url: str,
    data: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> bool:
    path = bundle_path(server_url, base_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        key = _derive_key(server_url)
        nonce = os.urandom(_NONCE_LEN)
        aes = _aesgcm(key)
        enc = aes.encrypt(nonce, body, None)
        path.write_bytes(nonce + enc)
        return True
    except Exception as e:
        errno = getattr(e, "errno", None)
        is_perm = isinstance(e, PermissionError) or errno in (1, 13)
        if not is_perm:
            try:
                logger.debug(f"写入状态文件失败: {e}")
            except Exception:
                pass
        return False
