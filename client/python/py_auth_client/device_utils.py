from __future__ import annotations

import hashlib
import os
import socket
import uuid
from pathlib import Path
from typing import Dict, Optional

import platform
import psutil


def _device_id_store_path(server_url: str, software_name: str = "") -> Path:
    """设备ID持久化路径（按server_url和software_name隔离）"""
    base = Path.home() / '.py_auth_device'
    base.mkdir(parents=True, exist_ok=True)
    server_hash = hashlib.sha256(server_url.encode('utf-8')).hexdigest()[:12]
    software_hash = hashlib.sha256(software_name.encode('utf-8')).hexdigest()[:8] if software_name else "default"
    return base / f'device_{server_hash}_{software_hash}.txt'


def load_persisted_device_id(server_url: str, software_name: str = "") -> Optional[str]:
    try:
        path = _device_id_store_path(server_url, software_name)
        if path.exists():
            content = path.read_text(encoding='utf-8').strip()
            if content:
                return content
    except Exception:
        pass
    return None


def persist_device_id(server_url: str, device_id: str, software_name: str = "") -> None:
    try:
        path = _device_id_store_path(server_url, software_name)
        path.write_text(device_id, encoding='utf-8')
    except Exception:
        pass


def get_mac_address() -> Optional[str]:
    try:
        mac_int = uuid.getnode()
        if (mac_int >> 40) & 1:
            return None
        mac = ':'.join(['{:02x}'.format((mac_int >> elements) & 0xff)
                       for elements in range(0, 2*6, 2)][::-1])
        return mac
    except Exception:
        return None


def collect_device_facts() -> Dict[str, Optional[str]]:
    """采集设备信息（尽量稳定的字段）"""
    system = platform.system()
    facts: Dict[str, Optional[str]] = {
        "system": system,
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname_value": platform.node(),
    }

    # 网络/IP
    ip_address = None
    try:
        net_addrs = psutil.net_if_addrs()
        for _, addrs in net_addrs.items():
            for addr in addrs:
                if getattr(addr, "family", None) == socket.AF_INET:
                    if addr.address.startswith("127.") or addr.address.startswith("169.254."):
                        continue
                    ip_address = addr.address
                    break
            if ip_address:
                break
        if not ip_address:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip_address = s.getsockname()[0]
                s.close()
            except Exception:
                pass
    except Exception:
        pass
    facts["ip_address"] = ip_address

    # 硬件信息
    try:
        facts["cpu_count"] = psutil.cpu_count(logical=True)
        if cpu_freq := psutil.cpu_freq():
            facts["cpu_freq_mhz"] = round(cpu_freq.current, 2)
    except Exception:
        pass

    try:
        mem = psutil.virtual_memory()
        facts["memory_total_gb"] = round(mem.total / (1024**3), 2)
        facts["memory_free_gb"] = round(mem.available / (1024**3), 2)
    except Exception:
        pass

    disk_id = None
    try:
        partitions = psutil.disk_partitions()
        if partitions:
            disk_id = partitions[0].device or partitions[0].mountpoint
            disk_usage = psutil.disk_usage(partitions[0].mountpoint)
            facts["disk_total_gb"] = round(disk_usage.total / (1024**3), 2)
            facts["disk_free_gb"] = round(disk_usage.free / (1024**3), 2)
    except Exception:
        pass
    facts["disk_id"] = disk_id

    # MAC
    facts["mac"] = get_mac_address()

    return facts


def build_device_id(server_url: str, provided_device_id: Optional[str], facts: Dict[str, Optional[str]], software_name: str = "") -> str:
    """
    构建设备ID
    
    设备ID基于硬件信息和软件名称生成，确保同一台电脑上的不同软件有不同的设备ID
    
    Args:
        server_url: 服务器URL
        provided_device_id: 用户提供的设备ID（可选）
        facts: 设备硬件信息
        software_name: 软件名称（必填），用于区分同一设备上的不同软件
        
    Returns:
        设备ID字符串
    """
    if provided_device_id:
        persist_device_id(server_url, provided_device_id, software_name)
        return provided_device_id

    if persisted := load_persisted_device_id(server_url, software_name):
        return persisted

    # 将 software_name 包含在 device_id 的生成组件中
    components = [
        facts.get("mac"),
        facts.get("disk_id"),
        str(facts.get("cpu_count") or ""),
        str(facts.get("memory_total_gb") or ""),
        str(facts.get("disk_total_gb") or ""),
        facts.get("system"),
        facts.get("machine"),
        software_name,  # 包含软件名称，确保不同软件有不同的 device_id
    ]
    filtered = [c for c in components if c]
    device_id = hashlib.sha256("-".join(filtered).encode()).hexdigest()[:32] if filtered else str(uuid.uuid4())
    persist_device_id(server_url, device_id, software_name)
    return device_id


def build_device_info(facts: Dict[str, Optional[str]], device_info_override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if device_info_override is not None:
        return device_info_override

    info: Dict[str, Any] = {
        "hostname": facts.get("hostname_value"),
        "system": facts.get("system"),
        "release": facts.get("release"),
        "version": facts.get("version"),
        "machine": facts.get("machine"),
        "processor": facts.get("processor"),
    }

    if mac := facts.get("mac"):
        info["mac_address"] = mac
    if ip := facts.get("ip_address"):
        info["ip_address"] = ip
    if cpu := facts.get("cpu_count"):
        info["cpu_count"] = cpu
    if freq := facts.get("cpu_freq_mhz"):
        info["cpu_freq_mhz"] = freq
    if mem := facts.get("memory_total_gb"):
        info["memory_total_gb"] = mem
    if mem_free := facts.get("memory_free_gb"):
        info["memory_free_gb"] = mem_free
    if disk := facts.get("disk_total_gb"):
        info["disk_total_gb"] = disk
    if disk_free := facts.get("disk_free_gb"):
        info["disk_free_gb"] = disk_free

    try:
        import getpass
        info["username"] = getpass.getuser()
    except Exception:
        pass

    # 收集Python版本
    try:
        import sys
        info["python_version"] = sys.version
    except Exception:
        pass

    # 收集系统运行时间
    try:
        uptime = psutil.boot_time()
        import time
        info["system_uptime_seconds"] = int(time.time() - uptime)
    except Exception:
        pass

    return info

