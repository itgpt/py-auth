import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import fs from "node:fs";
import { machineIdSync } from "node-machine-id";
import type { DeviceInfo } from "./types";

function deviceIdStorePath(serverUrl: string, softwareName: string): string {
  const home = os.homedir();
  const base = path.join(home, ".py_auth_device");
  try {
    fs.mkdirSync(base, { recursive: true });
  } catch {
    // ignore
  }

  const serverHash = crypto.createHash("sha256").update(serverUrl, "utf8").digest("hex").slice(0, 12);
  const softwareHash = softwareName
    ? crypto.createHash("sha256").update(softwareName, "utf8").digest("hex").slice(0, 8)
    : "default";

  return path.join(base, `device_${serverHash}_${softwareHash}.txt`);
}

export function loadPersistedDeviceId(serverUrl: string, softwareName: string): string | null {
  try {
    const p = deviceIdStorePath(serverUrl, softwareName);
    if (!fs.existsSync(p)) return null;
    const content = fs.readFileSync(p, "utf8").trim();
    return content || null;
  } catch {
    return null;
  }
}

export function persistDeviceId(serverUrl: string, softwareName: string, deviceId: string): void {
  try {
    const p = deviceIdStorePath(serverUrl, softwareName);
    fs.writeFileSync(p, deviceId, "utf8");
  } catch {
    // ignore
  }
}

export function buildDeviceId(serverUrl: string, providedDeviceId: string | undefined, softwareName: string): string {
  if (providedDeviceId) {
    persistDeviceId(serverUrl, softwareName, providedDeviceId);
    return providedDeviceId;
  }

  const persisted = loadPersistedDeviceId(serverUrl, softwareName);
  if (persisted) return persisted;

  // Node 环境下用机器 ID 做稳定输入；再混入 softwareName 保证同机不同软件不同 device_id
  let base = "";
  try {
    base = machineIdSync();
  } catch {
    base = crypto.randomUUID();
  }

  const deviceId = crypto.createHash("sha256").update(`${base}-${softwareName}`, "utf8").digest("hex").slice(0, 32);
  persistDeviceId(serverUrl, softwareName, deviceId);
  return deviceId;
}

export function collectDeviceInfo(): DeviceInfo {
  const info: DeviceInfo = {
    hostname: os.hostname(),
    system: os.platform(),
    release: os.release(),
    machine: os.arch(),
  };

  try {
    info.username = os.userInfo().username;
  } catch {
    // ignore
  }

  // 收集CPU信息
  try {
    const cpus = os.cpus();
    info.cpu_count = cpus.length;
    if (cpus.length > 0) {
      info.cpu_model = cpus[0].model;
    }
  } catch {
    // ignore
  }

  // 收集内存信息
  try {
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    info.memory_total_gb = Math.round((totalMem / (1024 ** 3)) * 100) / 100;
    info.memory_free_gb = Math.round((freeMem / (1024 ** 3)) * 100) / 100;
  } catch {
    // ignore
  }

  // 收集网络接口信息
  try {
    const interfaces = os.networkInterfaces();
    const ips: string[] = [];
    const macs: string[] = [];
    
    for (const [, addrs] of Object.entries(interfaces)) {
      if (!addrs) continue;
      for (const addr of addrs) {
        if (addr.family === 'IPv4' && !addr.address.startsWith('127.') && !addr.address.startsWith('169.254.')) {
          ips.push(addr.address);
        }
        if (addr.mac && addr.mac !== '00:00:00:00:00:00') {
          macs.push(addr.mac);
        }
      }
    }
    
    if (ips.length > 0) {
      info.ip_address = ips[0];
    }
    if (macs.length > 0) {
      info.mac_address = macs[0];
    }
  } catch {
    // ignore
  }

  // 收集平台特定信息
  try {
    const platform = os.platform();
    if (platform === 'win32') {
      info.platform_version = os.release();
    } else if (platform === 'darwin') {
      info.platform_version = os.release();
    } else if (platform === 'linux') {
      info.platform_version = os.release();
    }
  } catch {
    // ignore
  }

  // 收集Node.js版本
  try {
    info.node_version = process.version;
  } catch {
    // ignore
  }

  // 收集运行时信息
  try {
    const uptime = os.uptime();
    info.system_uptime_seconds = Math.round(uptime);
  } catch {
    // ignore
  }

  return info;
}
