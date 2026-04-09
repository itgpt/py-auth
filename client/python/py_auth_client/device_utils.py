from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import sys
import uuid
from pathlib import Path
from typing import Any

from .device_platform import (
    apply_os_version_facts,
    cpu_model_platform_specific,
    disk_model_for_partition,
    root_disk_mount_and_id,
)


def _processor_arch_normalized() -> str:
    m = (platform.machine() or "").lower()
    if m in ("amd64", "x86_64"):
        return "amd64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("i386", "i686"):
        return "386"
    return m or "unknown"


def _cpu_model_best() -> str | None:
    if s := cpu_model_platform_specific():
        return s
    raw = platform.processor()
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def load_persisted_device_id(
    server_url: str,
    software_name: str,
    base_dir: Path | None = None,
) -> str | None:
    try:
        from .state_bundle import load_apps_map, read_state_dict, row_device_id_str

        d = read_state_dict(
            server_url,
            base_dir=base_dir,
        )
        if not d:
            return None
        row = load_apps_map(d).get(software_name)
        if isinstance(row, dict):
            rid = row_device_id_str(row)
            if rid:
                return rid
    except Exception:
        pass
    return None


def persist_device_id(
    server_url: str,
    device_id: str,
    software_name: str,
    base_dir: Path | None = None,
) -> None:
    try:
        from .state_bundle import (
            commit_apps_map,
            load_apps_map,
            read_state_dict,
            write_state_dict,
        )

        cur = (
            read_state_dict(
                server_url,
                base_dir=base_dir,
            )
            or {}
        )
        apps_m = load_apps_map(cur)
        sub = dict(apps_m.get(software_name, {}))
        sub.pop("software_name", None)
        sub["device_id"] = device_id
        apps_m[software_name] = sub
        commit_apps_map(cur, apps_m)
        cur.pop("device_id", None)
        write_state_dict(
            server_url,
            cur,
            base_dir=base_dir,
        )
    except Exception:
        pass


def _normalize_mac_colon_lower(addr: str) -> str | None:
    if not addr or not isinstance(addr, str):
        return None
    s = addr.strip().lower().replace("-", ":")
    parts = [p for p in s.split(":") if p]
    if len(parts) != 6:
        return None
    try:
        out = ":".join(f"{int(p, 16):02x}" for p in parts)
    except ValueError:
        return None
    if out == "00:00:00:00:00:00":
        return None
    return out


def _is_probably_virtual_mac(mac: str) -> bool:
    m = mac.lower().replace(":", "").replace("-", "")
    if len(m) < 6:
        return False
    prefixes = (
        "005056",
        "000c29",
        "000569",
        "001c14",
        "080027",
        "00155d",
        "525400",
    )
    return any(m.startswith(p) for p in prefixes)


def _is_common_hyperv_nat_host_ip(ip: str) -> bool:
    return ip.startswith("192.168.117.")


def _network_endpoint_score(mac: str | None, ip: str | None) -> int:
    score = 0
    if ip:
        score += 40
        if ip.startswith("169.254."):
            score -= 25
        if _is_common_hyperv_nat_host_ip(ip):
            score -= 50
    if mac:
        score += 10
    if mac and not _is_probably_virtual_mac(mac):
        score += 100
    return score


def _outbound_ipv4_hint() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return None


def _iface_loopback_name(name: str) -> bool:
    n = (name or "").lower()
    return n == "lo" or "loopback" in n


def _sorted_scored_iface_endpoints() -> list[tuple[int, str | None, str | None]]:
    import psutil

    out: list[tuple[int, str | None, str | None]] = []
    try:
        stats = psutil.net_if_stats()
        addrs_map = psutil.net_if_addrs()
        af_link = getattr(psutil, "AF_LINK", -1)
        af_packet = getattr(socket, "AF_PACKET", None)
        for name, addrs in addrs_map.items():
            if _iface_loopback_name(name):
                continue
            st = stats.get(name)
            if st is not None and not st.isup:
                continue
            mac: str | None = None
            ip: str | None = None
            for a in addrs:
                fam = a.family
                if fam == socket.AF_INET:
                    addr = getattr(a, "address", "") or ""
                    if addr.startswith("127.") or addr.startswith("169.254."):
                        continue
                    ip = addr
                elif fam == af_link or (af_packet is not None and fam == af_packet):
                    mac = _normalize_mac_colon_lower(getattr(a, "address", "") or "")
            if mac or ip:
                out.append((_network_endpoint_score(mac, ip), mac, ip))
    except Exception:
        return []
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def _preferred_mac_and_ipv4() -> tuple[str | None, str | None]:
    candidates = _sorted_scored_iface_endpoints()
    if not candidates:
        return None, _outbound_ipv4_hint()

    for _, mac, ip in candidates:
        if mac and ip and not ip.startswith("127."):
            return mac, ip
    for _, mac, ip in candidates:
        if mac and ip:
            return mac, ip

    best_ip: str | None = None
    for _, _, ip in candidates:
        if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
            best_ip = ip
            break

    best_mac: str | None = None
    for _, mac, _ in candidates:
        if not mac:
            continue
        if not _is_probably_virtual_mac(mac):
            best_mac = mac
            break
    if best_mac is None:
        for _, mac, _ in candidates:
            if mac:
                best_mac = mac
                break

    if best_ip is None:
        best_ip = _outbound_ipv4_hint()
    return best_mac, best_ip


def _collect_network_interface_rows() -> list[dict[str, str]]:
    seen_keys: set[str] = set()
    out: list[dict[str, str]] = []
    for _, mac, ip in _sorted_scored_iface_endpoints():
        row: dict[str, str] = {}
        if mac:
            row["mac_address"] = mac
        if ip:
            row["ip_address"] = ip
        key = f"{mac or ''}|{ip or ''}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(row)
    return out


def _mac_from_uuid_node() -> str | None:
    try:
        mac_int = uuid.getnode()
        if (mac_int >> 40) & 1:
            return None
        octets = [
            f"{(mac_int >> elements) & 0xFF:02x}" for elements in range(0, 2 * 6, 2)
        ][::-1]
        return _normalize_mac_colon_lower(":".join(octets))
    except Exception:
        return None


def get_mac_address() -> str | None:
    mac, _ = _preferred_mac_and_ipv4()
    return mac or _mac_from_uuid_node()


def _disk_volume_map_key(model: str, mount: str, device: str, used: set[str]) -> str:
    base = (
        (model or "").strip()
        or (device or "").strip()
        or (mount or "").strip()
        or "unknown"
    )
    k = base
    suffix = 0
    while k in used:
        suffix += 1
        if suffix == 1:
            k = f"{base} @ {mount}"
        else:
            k = f"{base} @ {mount} ({suffix})"
    used.add(k)
    return k


def _windows_disks_powershell() -> list[dict[str, Any]] | None:
    if sys.platform != "win32":
        return None
    script = r"""$rows = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
  $id = $_.DeviceID
  if (-not $id.EndsWith('\')) { $id = $id + '\' }
  $letter = $_.DeviceID.TrimEnd('\')[0]
  $model = ''
  try {
    $part = Get-Partition -DriveLetter $letter -ErrorAction Stop
    $dsk = $part | Get-Disk
    if ($dsk) { $model = [string]$dsk.FriendlyName }
  } catch {}
  [PSCustomObject]@{ Mount = $id; Size = [double]$_.Size; FreeSpace = [double]$_.FreeSpace; Model = $model }
}
$rows | ConvertTo-Json -Compress -Depth 4"""
    try:
        import subprocess

        kw: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "timeout": 25,
            "check": False,
        }
        cnw = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if cnw:
            kw["creationflags"] = cnw
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            **kw,
        )
        if r.returncode != 0:
            return None
        raw = (r.stdout or "").strip().strip("\ufeff")
        if not raw:
            return None
        data = json.loads(raw)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except Exception:
        return None
    return None


def _entries_to_models_map(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    used: set[str] = set()
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        m = str(e.get("model") or "").strip()
        k = (
            m
            if m
            else _disk_volume_map_key(
                "", str(e.get("mount") or ""), str(e.get("device") or ""), used
            )
        )
        groups.setdefault(k, []).append(e)
    out: dict[str, dict[str, Any]] = {}
    for k, sl in groups.items():
        sl.sort(key=lambda x: str(x.get("mount") or ""))
        vols: list[dict[str, Any]] = []
        for row in sl:
            v: dict[str, Any] = {
                "mount": row["mount"],
                "total_gb": row["total_gb"],
                "free_gb": row["free_gb"],
            }
            if row.get("device"):
                v["device"] = row["device"]
            vols.append(v)
        out[k] = {"volumes": vols}
    return out


def _legacy_disk_volumes_to_models(vols: Any) -> dict[str, dict[str, Any]]:
    if isinstance(vols, dict) and vols:
        out: dict[str, dict[str, Any]] = {}
        for key in sorted(vols.keys()):
            item = vols[key]
            if not isinstance(item, dict):
                continue
            row = {
                x: item[x]
                for x in ("mount", "total_gb", "free_gb", "device")
                if x in item
            }
            out[key] = {"volumes": [row]}
        return out
    if isinstance(vols, list) and vols:
        used: set[str] = set()
        folded: dict[str, dict[str, Any]] = {}
        for item in vols:
            if not isinstance(item, dict):
                continue
            model = str(item.get("model") or "")
            mount = str(item.get("mount") or "")
            device = str(item.get("device") or "")
            key = _disk_volume_map_key(model, mount, device, used)
            folded[key] = {kk: vv for kk, vv in item.items() if kk != "model"}
        return _legacy_disk_volumes_to_models(folded)
    return {}


def _legacy_disk_disks_to_models(disks: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(disks, list) or not disks:
        return {}
    merged: dict[str, list[dict[str, Any]]] = {}
    for item in disks:
        if not isinstance(item, dict):
            continue
        m = str(item.get("model") or "").strip() or "unknown"
        vols = item.get("volumes")
        if not isinstance(vols, list):
            continue
        for v in vols:
            if isinstance(v, dict):
                merged.setdefault(m, []).append(v)
    return {k: {"volumes": v} for k, v in merged.items() if v}


_PUBLIC_IP_URL = "https://ifconfig.icu/ip"

_PUBLIC_IP_DEADLINE_SEC = 8.0


def _fetch_public_ip_blocking(timeout_sec: float) -> str:
    try:
        import ipaddress
        import urllib.request

        req = urllib.request.Request(
            _PUBLIC_IP_URL,
            headers={"User-Agent": "py-auth-client-python/1"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read(128).decode("utf-8", errors="replace").strip()
        if not raw:
            return ""
        line = raw.split()[0].strip()
        ipaddress.ip_address(line)
        return line
    except Exception:
        return ""


def fetch_public_ip() -> str:
    deadline = _PUBLIC_IP_DEADLINE_SEC
    raw = os.environ.get("PY_AUTH_PUBLIC_IP_DEADLINE_SEC", "").strip()
    if raw:
        try:
            v = float(raw)
            if 0.5 <= v <= 30.0:
                deadline = v
        except ValueError:
            pass

    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as _FuturesTimeout

    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_fetch_public_ip_blocking, deadline)
        try:
            return future.result(timeout=deadline)
        except _FuturesTimeout:
            return ""
    finally:
        executor.shutdown(wait=False)


def _facts_psutil_cpu(*, extended: bool) -> dict[str, Any]:
    import psutil

    out: dict[str, Any] = {}
    try:
        out["cpu_count"] = psutil.cpu_count(logical=True)
        if not extended:
            return out
        phys = psutil.cpu_count(logical=False)
        if phys is not None and phys > 0:
            out["cpu_count_physical"] = int(phys)
        if cpu_freq := psutil.cpu_freq():
            cur = cpu_freq.current
            if cur is None or cur <= 0:
                cur = cpu_freq.max
            if cur is not None and cur > 0:
                out["cpu_freq_mhz"] = round(float(cur), 2)
            if cpu_freq.min is not None and cpu_freq.min > 0:
                out["cpu_freq_min_mhz"] = round(float(cpu_freq.min), 2)
            if cpu_freq.max is not None and cpu_freq.max > 0:
                out["cpu_freq_max_mhz"] = round(float(cpu_freq.max), 2)
    except Exception:
        pass
    return out


def _facts_psutil_memory(*, extended: bool) -> dict[str, Any]:
    import psutil

    out: dict[str, Any] = {}
    try:
        mem = psutil.virtual_memory()
        out["memory_total_gb"] = round(mem.total / (1024**3), 2)
        if extended:
            out["memory_available_gb"] = round(mem.available / (1024**3), 2)
            out["memory_free_gb"] = round(mem.free / (1024**3), 2)
    except Exception:
        pass
    return out


def _facts_psutil_root_disk_usage(disk_mount: str) -> dict[str, Any]:
    import psutil

    out: dict[str, Any] = {}
    try:
        disk_usage = psutil.disk_usage(disk_mount)
        out["disk_total_gb"] = round(disk_usage.total / (1024**3), 2)
        out["disk_free_gb"] = round(disk_usage.free / (1024**3), 2)
    except Exception:
        pass
    return out


def collect_device_facts(*, for_device_id: bool = False) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor

    import psutil

    system = platform.system()
    try:
        hn = socket.gethostname()
    except Exception:
        hn = platform.node()
    facts: dict[str, Any] = {
        "system": system,
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": _processor_arch_normalized(),
        "hostname_value": hn,
    }

    apply_os_version_facts(facts)

    ext = not for_device_id
    win_disk_fut = None
    n_io_workers = 3
    if ext and sys.platform == "win32":
        n_io_workers = 4

    with ThreadPoolExecutor(max_workers=max(2, n_io_workers)) as ex:
        f_net = ex.submit(_preferred_mac_and_ipv4)
        f_rd = ex.submit(root_disk_mount_and_id)
        f_cm = ex.submit(_cpu_model_best) if ext else None
        if ext and sys.platform == "win32":
            win_disk_fut = ex.submit(_windows_disks_powershell)
        mac, ip_address = f_net.result()
        disk_mount, disk_id = f_rd.result()
        if f_cm is not None:
            if cm := f_cm.result():
                facts["cpu_model"] = cm
        win_ps_rows: list[dict[str, Any]] | None = None
        if win_disk_fut is not None:
            try:
                win_ps_rows = win_disk_fut.result()
            except Exception:
                win_ps_rows = None

    facts["ip_address"] = ip_address
    facts["disk_id"] = disk_id

    with ThreadPoolExecutor(max_workers=3) as ex:
        f_cpu = ex.submit(_facts_psutil_cpu, extended=ext)
        f_mem = ex.submit(_facts_psutil_memory, extended=ext)
        f_du = ex.submit(_facts_psutil_root_disk_usage, disk_mount)
        for part in (f_cpu, f_mem, f_du):
            facts.update(part.result())

    if for_device_id:
        facts["mac"] = mac or _mac_from_uuid_node()
        return facts

    try:
        entries: list[dict[str, Any]] = []
        if sys.platform == "win32":
            for row in (win_ps_rows or []) or []:
                mount = str(row.get("Mount") or row.get("mount") or "").strip()
                if not mount:
                    continue
                if not mount.endswith("\\"):
                    mount += "\\"
                sz = float(row.get("Size") or 0)
                fr = row.get("FreeSpace")
                if fr is None:
                    fr = row.get("free_space")
                fr_f = float(fr or 0)
                if sz <= 0:
                    continue
                model = str(row.get("Model") or row.get("model") or "").strip()
                entries.append(
                    {
                        "model": model,
                        "mount": mount,
                        "device": "",
                        "total_gb": round(sz / (1024**3), 2),
                        "free_gb": round(fr_f / (1024**3), 2),
                    }
                )
        if not entries:
            seen_mp: set[str] = set()
            pending: list[tuple[str, str, float, float]] = []
            for p in psutil.disk_partitions(all=False):
                mp = p.mountpoint
                if not mp or mp in seen_mp:
                    continue
                seen_mp.add(mp)
                try:
                    u = psutil.disk_usage(mp)
                except (OSError, PermissionError):
                    continue
                dev = (p.device or "").strip()
                if dev.startswith("//"):
                    dev = ""
                tg = round(u.total / (1024**3), 2)
                fg = round(u.free / (1024**3), 2)
                pending.append((mp, dev, tg, fg))
            if pending:
                nw = min(16, max(4, (os.cpu_count() or 2) * 2))
                with ThreadPoolExecutor(max_workers=nw) as pex:
                    futs = [
                        (mp, dev, tg, fg, pex.submit(disk_model_for_partition, mp, dev))
                        for mp, dev, tg, fg in pending
                    ]
                    for mp, dev, tg, fg, fut in futs:
                        try:
                            model = fut.result()
                        except Exception:
                            model = ""
                        ent: dict[str, Any] = {
                            "model": model,
                            "mount": mp,
                            "total_gb": tg,
                            "free_gb": fg,
                        }
                        if dev:
                            ent["device"] = dev
                        entries.append(ent)
        if entries:
            facts["disk_models"] = _entries_to_models_map(entries)
    except Exception:
        pass

    facts["mac"] = mac or _mac_from_uuid_node()

    return facts


_PERSISTED_DEVICE_ID_NOT_PREFETCHED = object()


def build_device_id(
    server_url: str,
    provided_device_id: str | None,
    facts: dict[str, Any],
    software_name: str = "",
    base_dir: Path | None = None,
    *,
    persisted_device_id: Any = _PERSISTED_DEVICE_ID_NOT_PREFETCHED,
) -> str:
    if provided_device_id:
        persist_device_id(
            server_url,
            provided_device_id,
            software_name,
            base_dir=base_dir,
        )
        return provided_device_id

    if persisted_device_id is not _PERSISTED_DEVICE_ID_NOT_PREFETCHED:
        if persisted_device_id:
            return str(persisted_device_id).strip()
    elif persisted := load_persisted_device_id(
        server_url,
        software_name,
        base_dir=base_dir,
    ):
        return persisted

    components = [
        facts.get("mac"),
        facts.get("disk_id"),
        str(facts.get("cpu_count") or ""),
        str(facts.get("memory_total_gb") or ""),
        str(facts.get("disk_total_gb") or ""),
        facts.get("system"),
        facts.get("machine"),
        software_name,
    ]
    filtered = [c for c in components if c]
    device_id = (
        hashlib.sha256("-".join(filtered).encode()).hexdigest()[:32]
        if filtered
        else str(uuid.uuid4())
    )
    persist_device_id(
        server_url,
        device_id,
        software_name,
        base_dir=base_dir,
    )
    return device_id


def build_device_info(
    facts: dict[str, Any], device_info_override: dict[str, Any] | None
) -> dict[str, Any]:
    if device_info_override is not None:
        return device_info_override

    from concurrent.futures import ThreadPoolExecutor

    info: dict[str, Any] = {}

    system_block: dict[str, Any] = {}
    if hv := facts.get("hostname_value"):
        system_block["hostname"] = hv
    if os_name := facts.get("system"):
        system_block["os"] = os_name
    if rv := facts.get("release"):
        system_block["release"] = rv
    if vv := facts.get("version"):
        system_block["version"] = vv
    if mv := facts.get("machine"):
        system_block["machine"] = mv
    if pv := facts.get("processor"):
        system_block["processor"] = pv
    if wd := facts.get("windows_display_version"):
        system_block["windows_display_version"] = wd
    if wp := facts.get("windows_product_name"):
        system_block["windows_product_name"] = wp

    cpu_block: dict[str, Any] = {}
    if cm := facts.get("cpu_model"):
        cpu_block["model"] = cm

    memory: dict[str, Any] = {}
    if mem := facts.get("memory_total_gb"):
        memory["total_gb"] = mem
    if mem_avail := facts.get("memory_available_gb"):
        memory["available_gb"] = mem_avail
    if mem_free := facts.get("memory_free_gb"):
        memory["free_gb"] = mem_free

    disk_block: dict[str, Any] = {}
    models_map: dict[str, Any] | None = None
    if models := facts.get("disk_models"):
        if isinstance(models, dict) and models:
            models_map = models
    elif disks := facts.get("disk_disks"):
        models_map = _legacy_disk_disks_to_models(disks) or None
    elif vols := facts.get("disk_volumes"):
        models_map = _legacy_disk_volumes_to_models(vols) or None
    if models_map:
        disk_block["models"] = models_map
    else:
        if disk := facts.get("disk_total_gb"):
            disk_block["total_gb"] = disk
        if disk_free := facts.get("disk_free_gb"):
            disk_block["free_gb"] = disk_free

    _iface_ex = ThreadPoolExecutor(max_workers=1)
    _iface_fut = _iface_ex.submit(_collect_network_interface_rows)
    try:
        if cpu_n := facts.get("cpu_count"):
            cpu_block["count"] = cpu_n
        if cpu_phys := facts.get("cpu_count_physical"):
            cpu_block["physical_count"] = cpu_phys
        if freq := facts.get("cpu_freq_mhz"):
            cpu_block["freq_mhz"] = freq
        if fmin := facts.get("cpu_freq_min_mhz"):
            cpu_block["freq_min_mhz"] = fmin
        if fmax := facts.get("cpu_freq_max_mhz"):
            cpu_block["freq_max_mhz"] = fmax

        try:
            import getpass

            system_block["username"] = getpass.getuser()
        except Exception:
            pass

        try:
            import sys as _sys

            system_block["python_version"] = _sys.version
        except Exception:
            pass

        try:
            import time

            import psutil as _psutil_boot

            uptime = _psutil_boot.boot_time()
            system_block["system_uptime_seconds"] = int(time.time() - uptime)
        except Exception:
            pass

        iface_rows: list[dict[str, str]] = []
        try:
            iface_rows = _iface_fut.result()
        except Exception:
            pass
        if not iface_rows:
            iface_rows = []

        network: dict[str, Any] = {}
        if mac := facts.get("mac"):
            network["mac_address"] = mac
        if ip := facts.get("ip_address"):
            network["ip_address"] = ip
        if iface_rows:
            network["interfaces"] = iface_rows

        if network:
            info["network"] = network
        if cpu_block:
            info["cpu"] = cpu_block
        if memory:
            info["memory"] = memory
        if disk_block:
            info["disk"] = disk_block
        if system_block:
            info["system"] = system_block
    finally:
        try:
            _iface_ex.shutdown(wait=False)
        except Exception:
            pass

    return info
