import os from "node:os";
import { isIPv4, isIPv6 } from "node:net";
import crypto from "node:crypto";
import dgram from "node:dgram";
import type { DeviceInfo, DeviceNetworkInterfaceRow, DeviceSystemInfo } from "./types";
import {
  collectCpuHardwareDetails,
  listLocalDiskVolumesGB,
  readWindowsNtRegistryExtra,
  refineCpuModelWindows,
  rootDiskId,
  rootDiskTotalGB,
  rootDiskUsageGB,
} from "./devicePlatform";
import { round2 } from "./devicePlatformShared";
import {
  BUNDLE_ROOT_STRAY_KEYS,
  commitAppsMap,
  loadAppsMap,
  readStateDict,
  rowDeviceId,
  writeStateDictWithRetry,
} from "./stateBundle";

export function loadPersistedDeviceId(serverUrl: string, softwareName: string, baseDir: string): string | null {
  try {
    const root = readStateDict(serverUrl, baseDir);
    if (!root) return null;
    const row = loadAppsMap(root)[softwareName];
    if (row && typeof row === "object" && !Array.isArray(row)) {
      return rowDeviceId(row as Record<string, unknown>);
    }
  } catch {
    
  }
  return null;
}

function persistDeviceId(serverUrl: string, softwareName: string, deviceId: string, baseDir: string): void {
  try {
    const cur = readStateDict(serverUrl, baseDir) ?? {};
    const payload: Record<string, unknown> = { ...cur };
    for (const k of BUNDLE_ROOT_STRAY_KEYS) delete payload[k];
    const apps = loadAppsMap(payload);
    const sub: Record<string, unknown> = { ...(apps[softwareName] ?? {}) };
    delete sub.software_name;
    sub.device_id = deviceId;
    apps[softwareName] = sub;
    commitAppsMap(payload, apps);
    writeStateDictWithRetry(serverUrl, payload, baseDir);
  } catch {
    
  }
}

function pythonStyleSystem(): string {
  const p = os.platform();
  if (p === "win32") return "Windows";
  if (p === "linux") return "Linux";
  if (p === "darwin") return "Darwin";
  if (!p) return p;
  return p[0]!.toUpperCase() + p.slice(1).toLowerCase();
}

function pythonStyleMachine(): string {
  try {
    const m = os.machine();
    if (m) return m;
  } catch {
    
  }
  const a = os.arch();
  if (a === "x64") {
    const pl = os.platform();
    if (pl === "linux" || pl === "darwin") return "x86_64";
    if (pl === "win32") return "AMD64";
  }
  return a;
}

function normalizeProcessorArch(): string {
  let m = "";
  try {
    m = (os.machine() || "").toLowerCase();
  } catch {
    
  }
  if (m === "amd64" || m === "x86_64") return "amd64";
  if (m === "arm64" || m === "aarch64") return "arm64";
  if (m === "i386" || m === "i686") return "386";
  const a = os.arch();
  if (a === "x64") return "amd64";
  if (a === "arm64") return "arm64";
  if (a === "ia32") return "386";
  return a || "unknown";
}

function pyStyleFloatStr(v: number): string {
  const r = Math.round(v * 100) / 100;
  let s = String(r);
  if (!s.includes(".") && !s.toLowerCase().includes("e")) s += ".0";
  return s;
}

const VIRTUAL_MAC_PREFIXES = ["005056", "000c29", "000569", "001c14", "080027", "00155d", "525400"];

function macHexNoSep(mac: string): string {
  return mac.toLowerCase().replace(/[:-]/g, "");
}

function isProbablyVirtualMac(mac: string): boolean {
  const m = macHexNoSep(mac);
  if (m.length < 6) return false;
  return VIRTUAL_MAC_PREFIXES.some((p) => m.startsWith(p));
}

function isHyperVNatHostIp(ip: string): boolean {
  return ip.startsWith("192.168.117.");
}

function networkEndpointScore(mac: string, ip: string): number {
  let s = 0;
  if (ip) {
    s += 40;
    if (ip.startsWith("169.254.")) s -= 25;
    if (isHyperVNatHostIp(ip)) s -= 50;
  }
  if (mac) s += 10;
  if (mac && !isProbablyVirtualMac(mac)) s += 100;
  return s;
}

function getOutboundIpv4Hint(): string | undefined {
  try {
    const sock = dgram.createSocket("udp4");
    sock.connect(80, "8.8.8.8");
    const a = sock.address() as { address?: string };
    sock.close();
    const ip = typeof a?.address === "string" ? a.address : "";
    if (ip && !ip.startsWith("127.")) return ip;
  } catch {
    
  }
  return undefined;
}

type NetworkCand = { score: number; mac: string; ip: string };

function sortedNetworkCandidates(): NetworkCand[] {
  const cands: NetworkCand[] = [];
  try {
    const nif = os.networkInterfaces();
    for (const [name, addrs] of Object.entries(nif)) {
      if (!addrs) continue;
      const nl = name.toLowerCase();
      if (nl.includes("loopback") || nl === "lo") continue;
      let mac = "";
      let ip = "";
      for (const a of addrs) {
        if (a.internal) continue;
        const fam = a.family as string | number;
        if (fam === "IPv4" || fam === 4) {
          const addr = a.address;
          if (!addr.startsWith("127.") && !addr.startsWith("169.254.")) ip = addr;
        }
        if (a.mac && a.mac !== "00:00:00:00:00:00") mac = a.mac.toLowerCase();
      }
      if (mac || ip) cands.push({ score: networkEndpointScore(mac, ip), mac, ip });
    }
    cands.sort((a, b) => b.score - a.score);
    return cands;
  } catch {
    return [];
  }
}

function collectNetworkInterfaceRows(): DeviceNetworkInterfaceRow[] {
  const cands = sortedNetworkCandidates();
  const seen = new Set<string>();
  const out: DeviceNetworkInterfaceRow[] = [];
  for (const c of cands) {
    if (!c.mac && !c.ip) continue;
    const key = `${c.mac}|${c.ip}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const row: DeviceNetworkInterfaceRow = {};
    if (c.mac) row.mac_address = c.mac;
    if (c.ip) row.ip_address = c.ip;
    out.push(row);
  }
  return out;
}

function preferredMacAndIpv4(): { mac: string; ip: string } {
  try {
    const cands = sortedNetworkCandidates();
    for (const c of cands) {
      if (c.mac && c.ip && !c.ip.startsWith("127.")) return { mac: c.mac, ip: c.ip };
    }
    for (const c of cands) {
      if (c.mac && c.ip) return { mac: c.mac, ip: c.ip };
    }
    let bestIp = "";
    for (const c of cands) {
      if (c.ip && !c.ip.startsWith("127.") && !c.ip.startsWith("169.254.")) {
        bestIp = c.ip;
        break;
      }
    }
    let bestMac = "";
    for (const c of cands) {
      if (c.mac && !isProbablyVirtualMac(c.mac)) {
        bestMac = c.mac;
        break;
      }
    }
    if (!bestMac) {
      for (const c of cands) {
        if (c.mac) {
          bestMac = c.mac;
          break;
        }
      }
    }
    if (!bestIp) bestIp = getOutboundIpv4Hint() ?? "";
    return { mac: bestMac, ip: bestIp };
  } catch {
    return { mac: "", ip: getOutboundIpv4Hint() ?? "" };
  }
}

function physicalMemoryTotalGB(): number {
  try {
    return Math.round((os.totalmem() / 1024 ** 3) * 100) / 100;
  } catch {
    return 0;
  }
}

type DeviceIdFacts = {
  mac: string;
  disk_id: string;
  cpu_count: number;
  memory_total_gb: number;
  disk_total_gb: number;
  system: string;
  machine: string;
};

function collectFactsForDeviceId(): DeviceIdFacts {
  let cpu = 0;
  try {
    cpu = os.cpus().length;
  } catch {
  }
  let mac = "";
  {
    const pm = preferredMacAndIpv4();
    if (pm.mac) mac = pm.mac;
    else {
      try {
        const interfaces = os.networkInterfaces();
        for (const addrs of Object.values(interfaces)) {
          if (!addrs) continue;
          for (const addr of addrs) {
            if (addr.internal) continue;
            if (addr.mac && addr.mac !== "00:00:00:00:00:00") {
              mac = addr.mac.toLowerCase();
              break;
            }
          }
          if (mac) break;
        }
      } catch {
      }
    }
  }
  return {
    mac,
    disk_id: rootDiskId(),
    cpu_count: cpu,
    memory_total_gb: physicalMemoryTotalGB(),
    disk_total_gb: rootDiskTotalGB(),
    system: pythonStyleSystem(),
    machine: pythonStyleMachine(),
  };
}

function buildPythonStyleDeviceComponents(f: DeviceIdFacts): string[] {
  const parts: string[] = [];
  if (f.mac) parts.push(f.mac);
  if (f.disk_id) parts.push(f.disk_id);
  if (f.cpu_count) parts.push(String(f.cpu_count));
  if (f.memory_total_gb) parts.push(pyStyleFloatStr(Math.round(f.memory_total_gb * 100) / 100));
  if (f.disk_total_gb) parts.push(pyStyleFloatStr(Math.round(f.disk_total_gb * 100) / 100));
  if (f.system) parts.push(f.system);
  if (f.machine) parts.push(f.machine);
  return parts;
}

export function buildDeviceId(
  serverUrl: string,
  providedDeviceId: string | undefined,
  softwareName: string,
  baseDir: string,
): string {
  if (providedDeviceId) {
    persistDeviceId(serverUrl, softwareName, providedDeviceId, baseDir);
    return providedDeviceId;
  }

  const persisted = loadPersistedDeviceId(serverUrl, softwareName, baseDir);
  if (persisted) return persisted;

  const facts = collectFactsForDeviceId();
  const parts = buildPythonStyleDeviceComponents(facts);
  if (softwareName) parts.push(softwareName);
  if (parts.length === 0) {
    const id = crypto.randomUUID();
    persistDeviceId(serverUrl, softwareName, id, baseDir);
    return id;
  }

  const combined = parts.join("-");
  const deviceId = crypto.createHash("sha256").update(combined, "utf8").digest("hex").slice(0, 32);
  persistDeviceId(serverUrl, softwareName, deviceId, baseDir);
  return deviceId;
}

export function collectDeviceInfo(): DeviceInfo {
  const system: DeviceSystemInfo = {
    hostname: os.hostname(),
    os: pythonStyleSystem(),
    release: os.release(),
    machine: pythonStyleMachine(),
    processor: normalizeProcessorArch(),
  };

  if (process.platform === "win32") {
    Object.assign(system, readWindowsNtRegistryExtra());
  }

  try {
    system.username = os.userInfo().username;
  } catch {
  }

  const info: DeviceInfo = { system };

  try {
    const hw = collectCpuHardwareDetails();
    const cpus = os.cpus();
    const cpu: NonNullable<DeviceInfo["cpu"]> = { ...hw };
    if (cpus.length > 0) {
      cpu.count = cpus.length;
      const raw = cpus[0]!.model?.trim();
      const refined = refineCpuModelWindows(raw);
      if (!cpu.model && refined) cpu.model = refined;
    }
    if (Object.keys(cpu).length > 0) info.cpu = cpu;
  } catch {
  }

  try {
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    const freeGb = round2(freeMem / 1024 ** 3);
    info.memory = {
      total_gb: round2(totalMem / 1024 ** 3),
      free_gb: freeGb,
      available_gb: freeGb,
    };
  } catch {
  }

  const du = rootDiskUsageGB();
  const models = listLocalDiskVolumesGB();
  const hasModels = Object.keys(models).length > 0;
  if (hasModels || du) {
    const disk: NonNullable<DeviceInfo["disk"]> = {};
    if (hasModels) {
      disk.models = models;
    } else if (du) {
      disk.total_gb = du.total;
      disk.free_gb = du.free;
    }
    info.disk = disk;
  }

  try {
    const { mac, ip } = preferredMacAndIpv4();
    const rows = collectNetworkInterfaceRows();
    const network: NonNullable<DeviceInfo["network"]> = {};
    if (ip) network.ip_address = ip;
    if (mac) network.mac_address = mac;
    if (rows.length > 0) network.interfaces = rows;
    if (Object.keys(network).length > 0) info.network = network;
  } catch {
  }

  try {
    const platform = os.platform();
    if (platform === "win32" || platform === "darwin" || platform === "linux") {
      system.platform_version = os.release();
    }
  } catch {
  }

  try {
    system.node_version = process.version;
  } catch {
  }

  try {
    system.system_uptime_seconds = Math.round(os.uptime());
  } catch {
  }

  return info;
}

const PUBLIC_IP_URL = "https://ifconfig.icu/ip";

function publicIpFetchTimeoutMs(): number {
  const raw = process.env.AUTH_PUBLIC_IP_TIMEOUT_MS?.trim();
  if (raw) {
    const n = Number.parseInt(raw, 10);
    if (Number.isFinite(n) && n >= 500 && n <= 60_000) {
      return n;
    }
  }
  return 8000;
}


export async function fetchPublicIp(): Promise<string> {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), publicIpFetchTimeoutMs());
  try {
    const r = await fetch(PUBLIC_IP_URL, {
      signal: ac.signal,
      headers: { "User-Agent": "py-auth-client-ts/1" },
    });
    if (!r.ok) return "";
    const text = (await r.text()).trim();
    const token = text.split(/\s|\n|\r/)[0] ?? "";
    if (!token) return "";
    if (isIPv4(token) || isIPv6(token)) return token;
    return "";
  } catch {
    return "";
  } finally {
    clearTimeout(t);
  }
}
