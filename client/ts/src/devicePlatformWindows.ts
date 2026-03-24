import fs from "node:fs";
import { execFileSync } from "node:child_process";
import type { DeviceCpuInfo, DeviceDiskModelGroupInfo, DeviceSystemInfo } from "./types";
import { groupDiskEntriesToModels, round2, type StatFsLike } from "./devicePlatformShared";

export function rootDiskId(): string {
  const d = process.env.SystemDrive || "C:";
  return d.endsWith("\\") ? d : `${d}\\`;
}

export function rootDiskTotalGB(): number {
  const root = rootDiskId();
  const f = fs as typeof fs & { statfsSync?: (path: string) => { blocks: number; bsize: number } };
  if (typeof f.statfsSync !== "function") return 0;
  try {
    const s = f.statfsSync(root);
    return Math.round(((Number(s.blocks) * Number(s.bsize)) / 1024 ** 3) * 100) / 100;
  } catch {
    return 0;
  }
}

export function rootDiskUsageGB(): { total: number; free: number } | null {
  const root = rootDiskId();
  const f = fs as typeof fs & {
    statfsSync?: (path: string) => { bsize: number; blocks: number; bavail: number };
  };
  if (typeof f.statfsSync !== "function") return null;
  try {
    const s = f.statfsSync(root);
    const bs = Number(s.bsize);
    const total = (Number(s.blocks) * bs) / 1024 ** 3;
    const free = (Number(s.bavail) * bs) / 1024 ** 3;
    return { total: round2(total), free: round2(free) };
  } catch {
    return null;
  }
}

type PsDiskRow = { Mount?: string; Size?: number; FreeSpace?: number; Model?: string };

function parsePsDiskJson(raw: string): PsDiskRow[] {
  const s = raw.trim().replace(/^\uFEFF/, "");
  try {
    const arr = JSON.parse(s) as unknown;
    if (Array.isArray(arr)) return arr as PsDiskRow[];
    if (arr && typeof arr === "object") return [arr as PsDiskRow];
  } catch {}
  return [];
}

export function listLocalDiskVolumesGB(): Record<string, DeviceDiskModelGroupInfo> {
  const psScript = `$rows = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
  $id = $_.DeviceID
  if (-not $id.EndsWith('\\')) { $id = $id + '\\' }
  $letter = $_.DeviceID.TrimEnd('\\')[0]
  $model = ''
  try {
    $part = Get-Partition -DriveLetter $letter -ErrorAction Stop
    $dsk = $part | Get-Disk
    if ($dsk) { $model = [string]$dsk.FriendlyName }
  } catch {}
  [PSCustomObject]@{ Mount = $id; Size = $_.Size; FreeSpace = $_.FreeSpace; Model = $model }
}
$rows | ConvertTo-Json -Compress -Depth 4`;
  try {
    const raw = execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", psScript], {
      encoding: "utf-8",
      timeout: 25_000,
      windowsHide: true,
      maxBuffer: 512 * 1024,
    });
    const rows = parsePsDiskJson(raw);
    if (rows.length > 0) {
      const entries = rows
        .map((row) => {
          let mount = String(row.Mount ?? "").trim();
          if (!mount) return null;
          if (!mount.endsWith("\\")) mount += "\\";
          const sz = Number(row.Size);
          const fr = Number(row.FreeSpace);
          if (!Number.isFinite(sz) || sz <= 0) return null;
          return {
            model: String(row.Model ?? "").trim(),
            mount,
            total_gb: round2(sz / 1024 ** 3),
            free_gb: round2(Number.isFinite(fr) ? fr / 1024 ** 3 : 0),
          };
        })
        .filter((x): x is NonNullable<typeof x> => x != null);
      if (entries.length > 0) return groupDiskEntriesToModels(entries);
    }
  } catch {}
  const sys = (process.env.SystemDrive || "C:").toLowerCase();
  const sysMount = (sys.endsWith("\\") ? sys : `${sys}\\`).toLowerCase();
  const fallback: { model: string; mount: string; total_gb: number; free_gb: number }[] = [];
  for (let i = 0; i < 26; i++) {
    const letter = String.fromCharCode(65 + i);
    const mount = `${letter}:\\`;
    try {
      const st = (fs as typeof fs & { statfsSync?: (path: string) => StatFsLike }).statfsSync?.(mount);
      if (!st) continue;
      const bs = Number(st.bsize);
      const total = round2((Number(st.blocks) * bs) / 1024 ** 3);
      const free = round2((Number(st.bavail) * bs) / 1024 ** 3);
      fallback.push({ model: "", mount, total_gb: total, free_gb: free });
    } catch {}
  }
  fallback.sort((a, b) => {
    const ai = a.mount.toLowerCase() === sysMount ? 0 : 1;
    const bi = b.mount.toLowerCase() === sysMount ? 0 : 1;
    if (ai !== bi) return ai - bi;
    return a.mount.localeCompare(b.mount);
  });
  return groupDiskEntriesToModels(fallback);
}

export function readWindowsNtRegistryExtra(): Partial<
  Pick<DeviceSystemInfo, "release" | "version" | "windows_display_version" | "windows_product_name">
> {
  try {
    const script = `$p='HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion'
$o=Get-ItemProperty -LiteralPath $p -ErrorAction Stop
[PSCustomObject]@{CurrentBuild=[string]$o.CurrentBuild;UBR=[int]$o.UBR;DisplayVersion=[string]$o.DisplayVersion;ProductName=[string]$o.ProductName}|ConvertTo-Json -Compress`;
    const raw = execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], {
      encoding: "utf-8",
      timeout: 12_000,
      windowsHide: true,
      maxBuffer: 256 * 1024,
    });
    const j = JSON.parse(raw.trim().replace(/^\uFEFF/, "")) as Record<string, unknown>;
    const build = String(j.CurrentBuild ?? "").trim();
    const ubr = Number(j.UBR ?? 0);
    const out: Partial<
      Pick<DeviceSystemInfo, "release" | "version" | "windows_display_version" | "windows_product_name">
    > = {};
    if (build) {
      out.version = `10.0.${build}.${Number.isFinite(ubr) ? ubr : 0}`;
      const bn = parseInt(build, 10);
      if (!Number.isNaN(bn)) out.release = bn >= 22000 ? "11" : "10";
    }
    const dv = String(j.DisplayVersion ?? "").trim();
    const pn = String(j.ProductName ?? "").trim();
    if (dv) out.windows_display_version = dv;
    if (pn) out.windows_product_name = pn;
    return out;
  } catch {
    return {};
  }
}

export function collectCpuHardwareWindows(): Partial<DeviceCpuInfo> {
  const script = `$p = @(Get-CimInstance Win32_Processor -ErrorAction Stop)
if ($null -eq $p -or $p.Count -eq 0) { '{}' } else {
  $cores = ($p | Measure-Object -Property NumberOfCores -Sum).Sum
  $mhzGroup = $p | Where-Object { $_.MaxClockSpeed -gt 0 }
  $mhz = 0.0
  if ($mhzGroup) { $mhz = ($mhzGroup | Measure-Object -Property MaxClockSpeed -Maximum).Maximum }
  [PSCustomObject]@{ name = [string]$p[0].Name; physical = [int]$cores; max_mhz = [double]$mhz } | ConvertTo-Json -Compress
}`;
  try {
    const raw = execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], {
      encoding: "utf-8",
      timeout: 20_000,
      windowsHide: true,
      maxBuffer: 256 * 1024,
    });
    const j = JSON.parse(raw.trim().replace(/^\uFEFF/, "")) as {
      name?: string;
      physical?: number;
      max_mhz?: number;
    };
    const out: Partial<DeviceCpuInfo> = {};
    const name = typeof j.name === "string" ? j.name.trim() : "";
    if (name) out.model = name;
    if (typeof j.physical === "number" && j.physical > 0) out.physical_count = j.physical;
    if (typeof j.max_mhz === "number" && j.max_mhz > 0) out.freq_max_mhz = round2(j.max_mhz);
    return out;
  } catch {
    return {};
  }
}

export function refineCpuModelWindows(model: string | undefined): string | undefined {
  const m = (model ?? "").trim();
  if (!m) return undefined;
  if (
    /\bFamily\s+\d+\s+Model\s+\d+/i.test(m) &&
    !/\b(Ryzen|Core|Xeon|EPYC|Pentium|Celeron|Athlon|Threadripper|Snapdragon)\b/i.test(m)
  ) {
    try {
      const o = execFileSync(
        "powershell.exe",
        [
          "-NoProfile",
          "-NonInteractive",
          "-Command",
          "(Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1).Name",
        ],
        { encoding: "utf-8", timeout: 15_000, windowsHide: true, maxBuffer: 64 * 1024 },
      );
      const s = o.trim().replace(/^\uFEFF/, "");
      if (s) return s;
    } catch {}
  }
  return m;
}
