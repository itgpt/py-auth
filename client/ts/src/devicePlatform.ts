import os from "node:os";
import type { DeviceCpuInfo, DeviceDiskModelGroupInfo, DeviceSystemInfo } from "./types";
import * as win from "./devicePlatformWindows";
import * as posix from "./devicePlatformPosix";
import * as fb from "./devicePlatformFallback";

function impl(): typeof win | typeof posix | typeof fb {
  const p = os.platform();
  if (p === "win32") return win;
  if (p === "linux" || p === "darwin") return posix;
  return fb;
}

export function rootDiskId(): string {
  return impl().rootDiskId();
}

export function rootDiskTotalGB(): number {
  return impl().rootDiskTotalGB();
}

export function rootDiskUsageGB(): { total: number; free: number } | null {
  return impl().rootDiskUsageGB();
}

export function listLocalDiskVolumesGB(): Record<string, DeviceDiskModelGroupInfo> {
  return impl().listLocalDiskVolumesGB();
}

export function readWindowsNtRegistryExtra(): Partial<
  Pick<DeviceSystemInfo, "release" | "version" | "windows_display_version" | "windows_product_name">
> {
  if (os.platform() !== "win32") return {};
  return win.readWindowsNtRegistryExtra();
}

export function refineCpuModelWindows(model: string | undefined): string | undefined {
  if (os.platform() !== "win32") return fb.refineCpuModelWindows(model);
  return win.refineCpuModelWindows(model);
}

export function collectCpuHardwareDetails(): Partial<DeviceCpuInfo> {
  const p = os.platform();
  if (p === "win32") return win.collectCpuHardwareWindows();
  if (p === "linux" || p === "darwin") return posix.collectCpuHardwarePosix();
  return {};
}
