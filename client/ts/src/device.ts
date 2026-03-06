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

  return info;
}
