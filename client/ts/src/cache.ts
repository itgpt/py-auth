import fs from "node:fs";
import type { CacheRecord, DeviceInfo } from "./types";
import {
  BUNDLE_PRODUCT_DEVICE_INFO_SNAPSHOT_KEY,
  BUNDLE_PRODUCT_REVOKE_KEYS,
  BUNDLE_ROOT_STRAY_KEYS,
  bundlePath,
  commitAppsMap,
  loadAppsMap,
  normalizeServerUrl,
  readStateDict,
  rowDeviceId,
  rowLastSuccessTs,
  writeStateDictWithRetry,
} from "./stateBundle";

export class AuthCache {
  readonly cacheValiditySeconds: number;
  readonly checkIntervalSeconds: number;
  readonly cacheFile: string;

  private readonly deviceId: string;
  private readonly serverUrl: string;
  private readonly softwareName: string;
  private readonly cacheDir: string;
  constructor(args: {
    storageRoot: string;
    deviceId: string;
    serverUrl: string;
    softwareName: string;
    cacheValidityDays: number;
    checkIntervalDays: number;
  }) {
    this.deviceId = args.deviceId;
    this.serverUrl = normalizeServerUrl(args.serverUrl);
    this.softwareName = args.softwareName;

    const cacheValidityDays = args.cacheValidityDays > 0 ? args.cacheValidityDays : 7;
    this.cacheValiditySeconds = cacheValidityDays * 24 * 60 * 60;
    this.checkIntervalSeconds = (args.checkIntervalDays > 0 ? args.checkIntervalDays : 2) * 24 * 60 * 60;

    this.cacheDir = args.storageRoot;
    this.cacheFile = bundlePath(this.serverUrl, this.cacheDir);
  }

  private readRow(): Record<string, unknown> | null {
    const d = readStateDict(this.serverUrl, this.cacheDir);
    if (!d) return null;
    const row = loadAppsMap(d)[this.softwareName];
    return row && typeof row === "object" && !Array.isArray(row) ? row : null;
  }

  private cacheRecordFromRow(row: Record<string, unknown> | null): CacheRecord | null {
    if (!row) return null;
    const ts = rowLastSuccessTs(row);
    if (ts === null) return null;
    return {
      authorized: true,
      message: "设备已授权",
      cachedAt: ts,
    };
  }

  snapshotForAuthorizationCheck(): { cacheData: CacheRecord | null; storedHeartbeatTimes: number } {
    try {
      const row = this.readRow();
      if (!row || rowLastSuccessTs(row) === null) return { cacheData: null, storedHeartbeatTimes: 0 };
      const raw = row.heartbeat_times;
      const n = typeof raw === "number" && Number.isFinite(raw) ? Math.floor(raw) : Number(raw);
      if (!Number.isFinite(n) || n < 1) {
        this.clearCache();
        return { cacheData: null, storedHeartbeatTimes: 0 };
      }
      return { cacheData: this.cacheRecordFromRow(row), storedHeartbeatTimes: n };
    } catch {
      return { cacheData: null, storedHeartbeatTimes: 0 };
    }
  }

  isCacheTTLValid(cache: CacheRecord | null): boolean {
    if (!cache?.cachedAt) return false;
    const elapsed = Date.now() / 1000 - cache.cachedAt;
    return elapsed < this.cacheValiditySeconds;
  }

  needsCheck(): boolean {
    const cache = this.getCache();
    if (!cache?.cachedAt) return true;
    const elapsed = Date.now() / 1000 - cache.cachedAt;
    return elapsed >= this.checkIntervalSeconds;
  }

  getCache(): CacheRecord | null {
    try {
      return this.cacheRecordFromRow(this.readRow());
    } catch {
      return null;
    }
  }

  loadDeviceInfoSnapshot(): DeviceInfo | null {
    try {
      const row = this.readRow();
      if (!row) return null;
      const raw = row[BUNDLE_PRODUCT_DEVICE_INFO_SNAPSHOT_KEY];
      if (raw == null) return null;
      if (typeof raw === "string") {
        if (!raw.trim()) return null;
        try {
          const p = JSON.parse(raw) as unknown;
          if (!p || typeof p !== "object" || Array.isArray(p)) return null;
          return JSON.parse(JSON.stringify(p)) as DeviceInfo;
        } catch {
          return null;
        }
      }
      if (typeof raw === "object" && !Array.isArray(raw)) {
        return JSON.parse(JSON.stringify(raw)) as DeviceInfo;
      }
      return null;
    } catch {
      return null;
    }
  }

  saveCache(authorized: boolean, _message: string, nextHeartbeat?: number, deviceInfoSnapshot?: DeviceInfo): boolean {
    try {
      const now = Date.now() / 1000;

      const cur = readStateDict(this.serverUrl, this.cacheDir) ?? {};
      const payload: Record<string, unknown> = { ...cur };
      for (const k of BUNDLE_ROOT_STRAY_KEYS) delete payload[k];
      const apps = loadAppsMap(payload);
      const sub: Record<string, unknown> = { ...(apps[this.softwareName] ?? {}) };
      delete sub.software_name;
      if (!authorized) {
        for (const k of BUNDLE_PRODUCT_REVOKE_KEYS) delete sub[k];
        sub.device_id = this.deviceId;
      } else {
        sub.device_id = this.deviceId;
        sub.last_success_at = now;
        if (nextHeartbeat !== undefined) sub.heartbeat_times = nextHeartbeat;
        if (deviceInfoSnapshot !== undefined) {
          sub[BUNDLE_PRODUCT_DEVICE_INFO_SNAPSHOT_KEY] = JSON.parse(JSON.stringify(deviceInfoSnapshot)) as Record<
            string,
            unknown
          >;
        }
      }
      apps[this.softwareName] = sub;
      commitAppsMap(payload, apps);

      return writeStateDictWithRetry(this.serverUrl, payload, this.cacheDir);
    } catch {
      return false;
    }
  }

  clearCache(): boolean {
    try {
      const d = readStateDict(this.serverUrl, this.cacheDir);
      if (!d) return true;
      const next: Record<string, unknown> = { ...d };
      for (const k of BUNDLE_ROOT_STRAY_KEYS) delete next[k];
      const apps = loadAppsMap(next);
      const sub: Record<string, unknown> = { ...(apps[this.softwareName] ?? {}) };
      for (const k of BUNDLE_PRODUCT_REVOKE_KEYS) delete sub[k];
      delete sub.software_name;
      sub.device_id = this.deviceId;
      apps[this.softwareName] = sub;
      commitAppsMap(next, apps);
      const anyAppHasDevice = Object.values(apps).some((r) => {
        if (!r || typeof r !== "object" || Array.isArray(r)) return false;
        return rowDeviceId(r as Record<string, unknown>) != null;
      });
      if (!anyAppHasDevice) {
        try {
          if (fs.existsSync(this.cacheFile)) fs.unlinkSync(this.cacheFile);
        } catch {}
        return true;
      }
      return writeStateDictWithRetry(this.serverUrl, next, this.cacheDir);
    } catch {
      return false;
    }
  }
}
