#!/usr/bin/env python3

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

_NONCE_LEN = 12
_TAG_LEN = 16


def _normalize_server_url(server_url: str) -> str:
    """与 Go NormalizeServerURL、TS normalizeServerUrl、py_auth_client 一致（文件名与 AES 密钥共用）。"""
    return (server_url or "").strip().rstrip("/")


def _derive_bundle_key(server_url: str) -> bytes:
    su = _normalize_server_url(server_url)
    return hashlib.sha256(su.encode("utf-8")).digest()


def _default_storage_root() -> Path:
    """与 py_auth_client.state_bundle.get_client_storage_root 一致（默认存储根）。"""
    if os.name == "nt" or sys.platform == "win32":
        pd = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        p = Path(pd) / ".RuntimeRepository"
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = Path(tempfile.gettempdir()) / ".runtime-repository"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _bundle_path(server_url: str, *, base_dir: Path) -> Path:
    su = _normalize_server_url(server_url)
    sh = hashlib.sha256(su.encode("utf-8")).hexdigest()[:12]
    return base_dir / f"state_{sh}_default.dat"


def _parse_dotenv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def _merged_dotenv() -> dict[str, str]:
    merged = _parse_dotenv_file(_REPO_ROOT / ".env")
    merged.update(_parse_dotenv_file(Path.cwd() / ".env"))
    return merged


def _resolve_server_url() -> str:
    for key in ("SERVER_URL", "AUTH_SERVER_URL", "PY_AUTH_SERVER_URL"):
        v = os.environ.get(key, "").strip()
        if v:
            return _normalize_server_url(v)
    env_file = _merged_dotenv()
    v = env_file.get("SERVER_URL", "").strip()
    if v:
        return _normalize_server_url(v)
    port = env_file.get("SERVICE_PORT", os.environ.get("SERVICE_PORT", "")).strip()
    if port.isdigit():
        return _normalize_server_url(f"http://localhost:{port}")
    return _normalize_server_url("http://localhost:8000")


def _format_local_time(value: object) -> str:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return "?"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return "?"


_TS_COMMENT_LINE = re.compile(
    r'^(\s*)"last_success_at":\s*(-?(?:\d+(?:\.\d*)?)(?:[eE][+-]?\d+)?)(,?)\s*$',
    re.MULTILINE,
)


def _inject_timestamp_line_comments(json_text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        indent, num, comma = m.group(1), m.group(2), m.group(3)
        hum = _format_local_time(float(num))
        return f'{indent}"last_success_at": {num}{comma}  // {hum}'

    return _TS_COMMENT_LINE.sub(repl, json_text)


_BUNDLE_DEVICE_INFO_SNAPSHOT_KEY = "device_info_snapshot"


def _redact_device_info_snapshots_for_display(obj: object) -> object:
    """默认隐藏各处的 device_info_snapshot 内容，仅保留占位字符串 HIDE。"""
    if isinstance(obj, dict):
        return {
            k: "HIDE"
            if k == _BUNDLE_DEVICE_INFO_SNAPSHOT_KEY
            else _redact_device_info_snapshots_for_display(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_device_info_snapshots_for_display(x) for x in obj]
    return obj


class _BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO(ctypes.Structure):
    """与 bcrypt.h 一致；cbData 为 ULONGLONG（见 Microsoft 文档）。"""

    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("dwInfoVersion", ctypes.c_uint32),
        ("pbNonce", ctypes.c_void_p),
        ("cbNonce", ctypes.c_uint32),
        ("pbAuthData", ctypes.c_void_p),
        ("cbAuthData", ctypes.c_uint32),
        ("pbTag", ctypes.c_void_p),
        ("cbTag", ctypes.c_uint32),
        ("pbMacContext", ctypes.c_void_p),
        ("cbMacContext", ctypes.c_uint32),
        ("cbAAD", ctypes.c_uint32),
        ("cbData", ctypes.c_uint64),
        ("dwFlags", ctypes.c_uint32),
    ]


_BCRYPT_AUTH_MODE_INFO_VERSION = 1


def _decrypt_aes_gcm_windows_cng(raw: bytes, key: bytes) -> bytes | None:
    """用 Windows CNG（bcrypt.dll）解密，与 cryptography AESGCM 格式一致；失败返回 None。"""
    if os.name != "nt" and sys.platform != "win32":
        return None
    if len(key) != 32 or len(raw) < _NONCE_LEN + _TAG_LEN + 1:
        return None
    body = raw[_NONCE_LEN:]
    if len(body) < _TAG_LEN + 1:
        return None
    nonce = raw[:_NONCE_LEN]
    ciphertext = body[:-_TAG_LEN]
    tag = body[-_TAG_LEN:]

    try:
        bcrypt = ctypes.WinDLL("bcrypt.dll")
    except OSError:
        return None

    NTSTATUS = ctypes.c_int32
    BCryptOpenAlgorithmProvider = bcrypt.BCryptOpenAlgorithmProvider
    BCryptOpenAlgorithmProvider.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
    ]
    BCryptOpenAlgorithmProvider.restype = NTSTATUS

    BCryptSetProperty = bcrypt.BCryptSetProperty
    BCryptSetProperty.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    BCryptSetProperty.restype = NTSTATUS

    BCryptGetProperty = bcrypt.BCryptGetProperty
    BCryptGetProperty.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_uint32,
    ]
    BCryptGetProperty.restype = NTSTATUS

    BCryptGenerateSymmetricKey = bcrypt.BCryptGenerateSymmetricKey
    BCryptGenerateSymmetricKey.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    BCryptGenerateSymmetricKey.restype = NTSTATUS

    BCryptDecrypt = bcrypt.BCryptDecrypt
    BCryptDecrypt.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_uint32,
    ]
    BCryptDecrypt.restype = NTSTATUS

    BCryptDestroyKey = bcrypt.BCryptDestroyKey
    BCryptDestroyKey.argtypes = [ctypes.c_void_p]
    BCryptDestroyKey.restype = NTSTATUS

    BCryptCloseAlgorithmProvider = bcrypt.BCryptCloseAlgorithmProvider
    BCryptCloseAlgorithmProvider.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    BCryptCloseAlgorithmProvider.restype = NTSTATUS

    h_alg = ctypes.c_void_p()
    st = BCryptOpenAlgorithmProvider(ctypes.byref(h_alg), "AES", None, 0)
    if st != 0:
        return None

    gcm_utf16 = ("ChainingModeGCM" + "\0").encode("utf-16-le")
    st = BCryptSetProperty(
        h_alg,
        "ChainingMode",
        ctypes.cast(gcm_utf16, ctypes.c_void_p),
        len(gcm_utf16),
        0,
    )
    if st != 0:
        BCryptCloseAlgorithmProvider(h_alg, 0)
        return None

    cb_key_obj = ctypes.c_uint32()
    pcb = ctypes.c_uint32()
    st = BCryptGetProperty(
        h_alg,
        "ObjectLength",
        ctypes.cast(ctypes.byref(cb_key_obj), ctypes.c_void_p),
        ctypes.sizeof(cb_key_obj),
        ctypes.byref(pcb),
        0,
    )
    if st != 0:
        BCryptCloseAlgorithmProvider(h_alg, 0)
        return None

    key_obj = (ctypes.c_ubyte * cb_key_obj.value)()
    h_key = ctypes.c_void_p()
    key_buf = (ctypes.c_ubyte * len(key))(*key)
    st = BCryptGenerateSymmetricKey(
        h_alg,
        ctypes.byref(h_key),
        ctypes.cast(key_obj, ctypes.c_void_p),
        cb_key_obj.value,
        ctypes.cast(key_buf, ctypes.c_void_p),
        len(key),
        0,
    )
    if st != 0:
        BCryptCloseAlgorithmProvider(h_alg, 0)
        return None

    nonce_buf = (ctypes.c_ubyte * len(nonce))(*nonce)
    tag_buf = (ctypes.c_ubyte * len(tag))(*tag)
    ct_buf = (ctypes.c_ubyte * len(ciphertext))(*ciphertext)
    out_buf = (ctypes.c_ubyte * len(ciphertext))()

    auth = _BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO()
    auth.cbSize = ctypes.sizeof(_BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO)
    auth.dwInfoVersion = _BCRYPT_AUTH_MODE_INFO_VERSION
    auth.pbNonce = ctypes.addressof(nonce_buf)
    auth.cbNonce = len(nonce)
    auth.pbAuthData = 0
    auth.cbAuthData = 0
    auth.pbTag = ctypes.addressof(tag_buf)
    auth.cbTag = len(tag)
    auth.pbMacContext = 0
    auth.cbMacContext = 0
    auth.cbAAD = 0
    auth.cbData = 0
    auth.dwFlags = 0

    cb_plain = ctypes.c_uint32()
    st = BCryptDecrypt(
        h_key,
        ct_buf,
        len(ciphertext),
        ctypes.byref(auth),
        None,
        0,
        out_buf,
        len(out_buf),
        ctypes.byref(cb_plain),
        0,
    )
    BCryptDestroyKey(h_key)
    BCryptCloseAlgorithmProvider(h_alg, 0)
    if st != 0:
        return None
    return bytes(memoryview(out_buf)[: cb_plain.value])


def _decrypt_raw(raw: bytes, server_url: str) -> dict:
    if len(raw) < _NONCE_LEN + _TAG_LEN + 1:
        raise ValueError(f"密文过短或已损坏（{len(raw)} 字节）")

    key = _derive_bundle_key(server_url)
    plain = _decrypt_aes_gcm_windows_cng(raw, key)
    if plain is None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aes = AESGCM(key)
        plain = aes.decrypt(raw[:_NONCE_LEN], raw[_NONCE_LEN:], None)
    return json.loads(plain.decode("utf-8"))


def _print_decrypt_inputs(
    *,
    encrypted_file: Path,
    server_url: str,
    path_tag: str,
) -> None:
    abs_dir = encrypted_file.resolve().parent
    su = _normalize_server_url(server_url)
    key = _derive_bundle_key(server_url)

    lines = [
        f"path: {abs_dir} ({path_tag})",
        f"server_url: {su}",
        f"AES-256 密钥: {key.hex()}",
    ]
    print("\n".join(lines), file=sys.stderr)


def _resolve_encrypted_path(
    server_url: str,
    base_dir: Path,
    positional_file: str | None,
) -> tuple[Path, str]:
    if positional_file:
        return Path(positional_file), "cli"
    expected = _bundle_path(server_url, base_dir=base_dir)
    if expected.exists():
        return expected, "hash"
    candidates = sorted(base_dir.glob("state_*_default.dat"))
    if len(candidates) == 1:
        return candidates[0], "single"
    if not candidates:
        raise FileNotFoundError(
            f"未找到状态包：{expected}；目录 {base_dir} 下也无 state_*_default.dat。"
            "请传入密文路径，或设置正确的 SERVER_URL（与客户端一致）。"
        )
    raise FileNotFoundError(
        f"目录 {base_dir} 下有多份 state_*_default.dat，无法自动选择。"
        f"请传入密文路径，或调整 SERVER_URL 以匹配其中一份。"
        f" 候选: {[p.name for p in candidates]}"
    )


def _usage() -> str:
    return (
        "用法: python tools/decrypt_state_bundle.py [--detail] [密文路径]\n"
        "  --detail    输出中包含完整的 device_info_snapshot（默认该字段为字符串 HIDE）\n"
        "  无路径参数：在默认存储根自动查找 state_*_default.dat（需环境变量或 .env 中的 SERVER_URL / SERVICE_PORT 与客户端一致）\n"
        "  密文路径：直接解密指定 .dat 文件\n"
        "其他以 - 开头的参数无效。服务地址：环境变量 SERVER_URL，或仓库/当前目录 .env 中的 SERVER_URL、SERVICE_PORT。"
    )


def main() -> None:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass

    argv = sys.argv[1:]
    detail = False
    positionals: list[str] = []
    for a in argv:
        if a == "--detail":
            detail = True
        elif a.startswith("-"):
            raise SystemExit(f"错误：未知选项 {a!r}。\n" + _usage())
        else:
            positionals.append(a)
    if len(positionals) > 1:
        raise SystemExit("错误：至多传入一个密文路径。\n" + _usage())

    state_file: str | None = positionals[0] if positionals else None

    server_url = _resolve_server_url()
    base_dir = _default_storage_root()

    encrypted_file, path_tag = _resolve_encrypted_path(server_url, base_dir, state_file)

    if not encrypted_file.exists():
        raise FileNotFoundError(f"未找到状态包文件: {encrypted_file}")

    raw = encrypted_file.read_bytes()
    _print_decrypt_inputs(
        encrypted_file=encrypted_file,
        server_url=server_url,
        path_tag=path_tag,
    )

    try:
        payload = _decrypt_raw(raw, server_url)
    except Exception as e:
        raise SystemExit(
            f"解密失败（{encrypted_file}）：{e}\n"
            "请确认环境变量 SERVER_URL（或 .env 中的 SERVER_URL / SERVICE_PORT）与客户端 server_url 完全一致（含协议与端口）。"
        ) from e

    enc = (getattr(sys.stdout, "encoding", None) or "").upper()
    ensure_ascii = enc not in ("UTF-8", "UTF8")
    to_dump = payload if detail else _redact_device_info_snapshots_for_display(payload)
    body = json.dumps(to_dump, ensure_ascii=ensure_ascii, indent=2)
    print(_inject_timestamp_line_comments(body))


if __name__ == "__main__":
    main()
