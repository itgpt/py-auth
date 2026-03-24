import fs from "node:fs";
import type { DeviceDiskVolumeInfo, DeviceDiskModelGroupInfo } from "./types";

export function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

const SKIP_UNIX_FSTYPE = new Set([
  "tmpfs",
  "devtmpfs",
  "proc",
  "sysfs",
  "devpts",
  "cgroup2",
  "cgroup",
  "pstore",
  "bpf",
  "tracefs",
  "fusectl",
  "mqueue",
  "hugetlbfs",
  "squashfs",
  "rpc_pipefs",
  "autofs",
  "configfs",
  "securityfs",
  "debugfs",
  "binfmt_misc",
  "overlay",
  "nsfs",
  "fuse.portal",
  "nfs",
  "nfs4",
  "cifs",
  "smb3",
  "9p",
  "ceph",
  "glusterfs",
]);

export function skipUnixFstype(fstype: string): boolean {
  if (SKIP_UNIX_FSTYPE.has(fstype)) return true;
  return fstype.startsWith("fuse.") && fstype !== "fuseblk";
}

export type StatFsLike = { bsize: number; blocks: number; bavail: number };

export function statfsGb(mp: string): { total: number; free: number } | null {
  const f = fs as typeof fs & { statfsSync?: (path: string) => StatFsLike };
  if (typeof f.statfsSync !== "function") return null;
  try {
    const s = f.statfsSync(mp);
    const bs = Number(s.bsize);
    const total = round2((Number(s.blocks) * bs) / 1024 ** 3);
    const free = round2((Number(s.bavail) * bs) / 1024 ** 3);
    return { total, free };
  } catch {
    return null;
  }
}

export function diskVolumeMapKey(model: string, mount: string, device: string, used: Set<string>): string {
  const base =
    (model || "").trim() || (device || "").trim() || (mount || "").trim() || "unknown";
  let k = base;
  let suffix = 0;
  for (;;) {
    if (!used.has(k)) {
      used.add(k);
      return k;
    }
    suffix++;
    if (suffix === 1) k = `${base} @ ${mount}`;
    else k = `${base} @ ${mount} (${suffix})`;
  }
}

export type DiskVolEnt = {
  model: string;
  mount: string;
  device?: string;
  total_gb: number;
  free_gb: number;
};

export function groupDiskEntriesToModels(entries: DiskVolEnt[]): Record<string, DeviceDiskModelGroupInfo> {
  if (entries.length === 0) return {};
  const used = new Set<string>();
  const by = new Map<string, DiskVolEnt[]>();
  for (const e of entries) {
    const m = (e.model || "").trim();
    const k = m || diskVolumeMapKey("", e.mount, e.device || "", used);
    const arr = by.get(k);
    if (arr) arr.push(e);
    else by.set(k, [e]);
  }
  const out: Record<string, DeviceDiskModelGroupInfo> = {};
  for (const [k, sl] of by) {
    const sorted = sl.slice().sort((a, b) => a.mount.localeCompare(b.mount));
    out[k] = {
      volumes: sorted.map((row) => {
        const v: DeviceDiskVolumeInfo = { mount: row.mount, total_gb: row.total_gb, free_gb: row.free_gb };
        if (row.device) v.device = row.device;
        return v;
      }),
    };
  }
  return out;
}
