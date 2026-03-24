import fs from "node:fs";
import os from "node:os";
import { execFileSync } from "node:child_process";
import type { DeviceCpuInfo, DeviceDiskModelGroupInfo } from "./types";
import { groupDiskEntriesToModels, round2, skipUnixFstype, statfsGb } from "./devicePlatformShared";

export function rootDiskId(): string {
  const p = os.platform();
  if (p === "linux") {
    try {
      const line = (fs.readFileSync("/proc/mounts", "utf8").split("\n")[0] ?? "").trim();
      const dev = line.split(/\s+/)[0];
      if (dev) return dev;
    } catch {
      
    }
  }
  if (p === "darwin") {
    try {
      const out = execFileSync("df", ["/"], { encoding: "utf8" });
      const lines = out.trim().split("\n");
      if (lines.length >= 2) {
        const c0 = lines[1]!.trim().split(/\s+/)[0];
        if (c0) return c0;
      }
    } catch {
      
    }
  }
  return "/";
}

export function rootDiskTotalGB(): number {
  const f = fs as typeof fs & { statfsSync?: (path: string) => { blocks: number; bsize: number } };
  if (typeof f.statfsSync !== "function") return 0;
  try {
    const s = f.statfsSync("/");
    return Math.round(((Number(s.blocks) * Number(s.bsize)) / 1024 ** 3) * 100) / 100;
  } catch {
    return 0;
  }
}

export function rootDiskUsageGB(): { total: number; free: number } | null {
  return statfsGb("/");
}

function linuxDiskModel(dev: string): string {
  const d = (dev || "").trim();
  if (!d.startsWith("/dev/")) return "";
  try {
    return execFileSync("lsblk", ["-no", "MODEL", d], { encoding: "utf8", timeout: 5000 }).trim();
  } catch {
    return "";
  }
}

function darwinDiskModel(mount: string): string {
  try {
    const o = execFileSync("diskutil", ["info", mount], { encoding: "utf8", timeout: 10_000 });
    for (const line of o.split("\n")) {
      const t = line.trim();
      if (t.startsWith("Device / Media Name:"))
        return t.slice("Device / Media Name:".length).trim();
      if (t.startsWith("Media Name:")) return t.slice("Media Name:".length).trim();
    }
  } catch {
    
  }
  return "";
}

export function listLocalDiskVolumesGB(): Record<string, DeviceDiskModelGroupInfo> {
  const p = os.platform();
  if (p === "linux") {
    try {
      const data = fs.readFileSync("/proc/mounts", "utf8");
      const seen = new Set<string>();
      const modelCache = new Map<string, string>();
      const entries: { model: string; mount: string; device?: string; total_gb: number; free_gb: number }[] = [];
      for (const line of data.split("\n")) {
        const fields = line.trim().split(/\s+/);
        if (fields.length < 3) continue;
        const [dev, mp, fst] = fields;
        if (!mp || skipUnixFstype(fst)) continue;
        if (mp.startsWith("/proc") || mp.startsWith("/sys")) continue;
        if (mp === "/dev" || mp.startsWith("/dev/")) continue;
        if (dev.startsWith("/dev/loop")) continue;
        if (seen.has(mp)) continue;
        const usage = statfsGb(mp);
        if (!usage) continue;
        seen.add(mp);
        let model = "";
        if (dev.startsWith("/dev/")) {
          const mc = modelCache.get(dev);
          if (mc !== undefined) model = mc;
          else {
            model = linuxDiskModel(dev);
            modelCache.set(dev, model);
          }
        }
        const e: (typeof entries)[0] = {
          model,
          mount: mp,
          total_gb: usage.total,
          free_gb: usage.free,
        };
        if (dev.startsWith("/dev/")) e.device = dev;
        entries.push(e);
      }
      if (entries.length > 0) return groupDiskEntriesToModels(entries);
    } catch {
      
    }
    return {};
  }
  if (p === "darwin") {
    try {
      const out = execFileSync("df", ["-l", "-P", "-k"], { encoding: "utf8" });
      const lines = out.trim().split("\n");
      const entries: { model: string; mount: string; device?: string; total_gb: number; free_gb: number }[] = [];
      for (let i = 1; i < lines.length; i++) {
        const fields = lines[i]!.trim().split(/\s+/);
        if (fields.length < 6) continue;
        const n = fields.length;
        const mount = fields[n - 1]!;
        const availKB = parseInt(fields[n - 3]!, 10);
        const blocks = parseInt(fields[n - 5]!, 10);
        if (!Number.isFinite(availKB) || !Number.isFinite(blocks)) continue;
        const dev = fields.slice(0, n - 5).join(" ");
        entries.push({
          model: darwinDiskModel(mount),
          mount,
          device: dev || undefined,
          total_gb: round2(blocks / 1024 ** 2),
          free_gb: round2(availKB / 1024 ** 2),
        });
      }
      if (entries.length > 0) return groupDiskEntriesToModels(entries);
    } catch {
      
    }
    return {};
  }
  return {};
}

function parseLinuxProcCpuInfo(): Partial<DeviceCpuInfo> {
  const out: Partial<DeviceCpuInfo> = {};
  try {
    const text = fs.readFileSync("/proc/cpuinfo", "utf8").replace(/\r\n/g, "\n");
    const lines = text.split("\n");
    const seen = new Set<string>();
    let physId = "";
    let coreId = "";
    let blockStarted = false;
    const flush = () => {
      if (!blockStarted) return;
      seen.add(`${physId}/${coreId}`);
    };
    for (const rawLine of lines) {
      const line = rawLine.trim();
      const low = line.toLowerCase();
      if (low.startsWith("processor") && line.includes(":")) {
        flush();
        blockStarted = true;
        physId = "";
        coreId = "";
        continue;
      }
      const idx = line.indexOf(":");
      if (idx < 0) continue;
      const key = line.slice(0, idx).trim().toLowerCase();
      const val = line.slice(idx + 1).trim();
      switch (key) {
        case "model name":
          if (!out.model) out.model = val;
          break;
        case "model":
          if (!out.model) out.model = val;
          break;
        case "hardware":
          if (!out.model) out.model = val;
          break;
        case "physical id":
          physId = val;
          break;
        case "core id":
          coreId = val;
          break;
        case "cpu mhz":
          if (out.freq_max_mhz === undefined) {
            const f = parseFloat(val);
            if (Number.isFinite(f) && f > 0) out.freq_max_mhz = round2(f);
          }
          break;
        default:
          break;
      }
    }
    flush();
    if (seen.size > 0) out.physical_count = seen.size;
  } catch {
  }
  return out;
}

function collectDarwinCpuHardware(): Partial<DeviceCpuInfo> {
  const out: Partial<DeviceCpuInfo> = {};
  try {
    const brand = execFileSync("sysctl", ["-n", "machdep.cpu.brand_string"], {
      encoding: "utf8",
      timeout: 5000,
    }).trim();
    if (brand) out.model = brand;
  } catch {
  }
  try {
    const s = execFileSync("sysctl", ["-n", "hw.physicalcpu"], { encoding: "utf8", timeout: 5000 }).trim();
    const n = parseInt(s, 10);
    if (n > 0) out.physical_count = n;
  } catch {
  }
  try {
    let s = execFileSync("sysctl", ["-n", "hw.cpufrequency_max"], { encoding: "utf8", timeout: 5000 }).trim();
    if (!s || s === "0") {
      s = execFileSync("sysctl", ["-n", "hw.cpufrequency"], { encoding: "utf8", timeout: 5000 }).trim();
    }
    const hz = parseInt(s, 10);
    if (hz > 0) out.freq_max_mhz = round2(hz / 1e6);
  } catch {
  }
  return out;
}

export function collectCpuHardwarePosix(): Partial<DeviceCpuInfo> {
  const p = os.platform();
  if (p === "linux") return parseLinuxProcCpuInfo();
  if (p === "darwin") return collectDarwinCpuHardware();
  return {};
}
