import type { DeviceDiskModelGroupInfo } from "./types";

export function rootDiskId(): string {
  return "/";
}

export function rootDiskTotalGB(): number {
  return 0;
}

export function rootDiskUsageGB(): { total: number; free: number } | null {
  return null;
}

export function listLocalDiskVolumesGB(): Record<string, DeviceDiskModelGroupInfo> {
  return {};
}

export function readWindowsNtRegistryExtra(): Record<string, never> {
  return {};
}

export function refineCpuModelWindows(model: string | undefined): string | undefined {
  const m = (model ?? "").trim();
  return m || undefined;
}
