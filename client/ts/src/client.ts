import fs from "node:fs";
import os from "node:os";
import type { AuthClientConfig, AuthResult, AuthorizationInfo, DeviceInfo } from "./types";
import { AuthorizationError } from "./errors";
import { encryptData, decryptData } from "./crypto";
import { AuthCache } from "./cache";
import { buildDeviceId, collectDeviceInfo, fetchPublicIp, loadPersistedDeviceId } from "./device";
import { postJson } from "./http";
import { getClientStorageRoot } from "./storage";
import { bundlePath } from "./stateBundle";
import { baseSdk } from "./sdkMeta";

const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3600;
const SECONDS_PER_DAY = 86400;
const HEARTBEAT_TIMEOUT_MS = 2_000;
const HEARTBEAT_LIGHT_TIMEOUT_MS = 4_000;

type HeartbeatRequest = {
  device_id: string;
  software_name: string;
  device_info: DeviceInfo;
};

type EncryptedEnvelope = {
  encrypted_data: string;
};

type HeartbeatResponseDecrypted = {
  authorized?: boolean;
  message?: string;
};

export class AuthClient {
  private readonly serverUrl: string;
  private readonly softwareName: string;
  private readonly softwareVersion: string;
  private readonly deviceId: string;
  private deviceInfo: DeviceInfo;
  private deviceInfoDeferred: boolean;
  private readonly clientSecret: string;
  private readonly debug: boolean;
  private readonly cache: AuthCache;
  private readonly stateBundleExistedBeforeInit: boolean;

  constructor(config: AuthClientConfig) {
    if (!config.serverUrl) throw new Error("serverUrl不能为空");
    if (!config.softwareName) throw new Error("softwareName不能为空");

    const secret = config.clientSecret ?? process.env.CLIENT_SECRET ?? "";
    if (!secret) {
      throw new Error(
        "CLIENT_SECRET未配置！请在初始化时传入clientSecret参数，或设置环境变量CLIENT_SECRET。这是安全要求，必须配置。",
      );
    }

    this.serverUrl = config.serverUrl.replace(/\/+$/, "");
    this.softwareName = config.softwareName;
    this.softwareVersion = config.softwareVersion ?? "0.0.0";
    this.clientSecret = secret;
    this.debug = !!config.debug;

    const cacheValidityDays = config.cacheValidityDays ?? 7;
    const checkIntervalDays = config.checkIntervalDays ?? 2;

    const storageBase = getClientStorageRoot();

    const stateBundleExistedBeforeInit = fs.existsSync(bundlePath(this.serverUrl, storageBase));
    const hasStableDeviceId =
      !!config.deviceId || !!loadPersistedDeviceId(this.serverUrl, this.softwareName, storageBase);

    this.deviceId = buildDeviceId(this.serverUrl, config.deviceId, this.softwareName, storageBase);

    if (config.deviceInfo) {
      this.deviceInfoDeferred = false;
      this.deviceInfo = {
        ...config.deviceInfo,
        software_version: this.softwareVersion,
        sdk: baseSdk(process.version),
      };
    } else if (hasStableDeviceId) {
      this.deviceInfoDeferred = true;
      this.deviceInfo = {
        software_version: this.softwareVersion,
        sdk: baseSdk(process.version),
      };
    } else {
      this.deviceInfoDeferred = false;
      this.deviceInfo = {
        ...collectDeviceInfo(),
        software_version: this.softwareVersion,
        sdk: baseSdk(process.version),
      };
    }

    this.cache = new AuthCache({
      storageRoot: storageBase,
      deviceId: this.deviceId,
      serverUrl: this.serverUrl,
      softwareName: this.softwareName,
      cacheValidityDays,
      checkIntervalDays,
    });

    if (this.deviceInfoDeferred) {
      const snap = this.cache.loadDeviceInfoSnapshot();
      if (snap && typeof snap === "object") {
        this.deviceInfo = {
          ...snap,
          software_version: this.softwareVersion,
          sdk: baseSdk(process.version),
        };
        this.deviceInfoDeferred = false;
      }
    }

    this.stateBundleExistedBeforeInit = stateBundleExistedBeforeInit;
  }

  private logDebug(msg: string): void {
    if (this.debug) {
      
      console.debug(`[ts][DEBUG] ${msg}`);
    }
  }

  private ensureFullDeviceInfo(): void {
    if (!this.deviceInfoDeferred) return;
    this.deviceInfo = {
      ...collectDeviceInfo(),
      software_version: this.softwareVersion,
      sdk: baseSdk(process.version),
    };
    this.deviceInfoDeferred = false;
  }

  private formatRemainingTime(cachedAtSeconds: number): string {
    if (!cachedAtSeconds || cachedAtSeconds <= 0) return "未知";

    const now = Date.now() / 1000;
    const elapsed = now - cachedAtSeconds;
    const remaining = this.cache.cacheValiditySeconds - elapsed;
    if (remaining <= 0) return "已过期";

    const days = Math.floor(remaining / SECONDS_PER_DAY);
    const hours = Math.floor((remaining % SECONDS_PER_DAY) / SECONDS_PER_HOUR);
    const minutes = Math.floor((remaining % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);

    const parts: string[] = [];
    if (days > 0) parts.push(`${days}天`);
    if (hours > 0) parts.push(`${hours}小时`);
    if (minutes > 0 || parts.length === 0) parts.push(`${minutes}分钟`);
    return parts.join("");
  }

  private async postHeartbeatDeviceInfo(
    deviceInfoPayload: DeviceInfo,
    heartbeatTimes: number,
    timeoutMs: number,
  ): Promise<AuthResult> {
    const device_info: DeviceInfo = {
      ...deviceInfoPayload,
      sdk: {
        ...(deviceInfoPayload.sdk ?? baseSdk(process.version)),
        heartbeat_times: heartbeatTimes,
      },
    };
    const requestData: HeartbeatRequest = {
      device_id: this.deviceId,
      software_name: this.softwareName,
      device_info,
    };
    const encrypted = encryptData(JSON.stringify(requestData), this.clientSecret);
    const { status, json, text } = await postJson<EncryptedEnvelope>(
      `${this.serverUrl}/api/auth/heartbeat`,
      { encrypted_data: encrypted },
      timeoutMs,
    );
    if (status === 200) {
      const token = json?.encrypted_data ?? "";
      const decryptedText = token ? decryptData(token, this.clientSecret) : null;
      if (!decryptedText) {
        this.logDebug("在线订阅响应解密失败");
        return { authorized: false, message: "解密响应失败", success: false, from_cache: false };
      }
      const decrypted = JSON.parse(decryptedText) as HeartbeatResponseDecrypted;
      this.logDebug(`在线订阅成功，authorized=${!!decrypted.authorized}`);
      return {
        authorized: !!decrypted.authorized,
        message: decrypted.message ?? "",
        success: true,
        from_cache: false,
      };
    }
    const detail = (json as any)?.detail;
    const msg = status === 403 && typeof detail === "string" ? detail : `服务器错误: ${status}`;
    this.logDebug(`在线订阅失败，status=${status}, message=${msg}; raw=${text}`);
    return { authorized: false, message: msg, success: false, from_cache: false, is_auth_error: status === 403 };
  }

  private async checkOnlineLight(heartbeatTimes: number): Promise<AuthResult> {
    try {
      this.logDebug("轻量在线订阅请求（不等待全量 device_info / 公网 IP）...");
      const light: DeviceInfo = {
        ...this.deviceInfo,
        software_version: this.softwareVersion,
        system: {
          ...(this.deviceInfo.system ?? {}),
          hostname: this.deviceInfo.system?.hostname?.trim() || os.hostname(),
          os: this.deviceInfo.system?.os || process.platform,
        },
      };
      return await this.postHeartbeatDeviceInfo(light, heartbeatTimes, HEARTBEAT_LIGHT_TIMEOUT_MS);
    } catch (e: any) {
      const msg = e?.name === "AbortError" ? "连接失败: timeout" : `连接失败: ${String(e?.message ?? e)}`;
      this.logDebug(`在线订阅请求异常: ${msg}`);
      return { authorized: false, message: msg, success: false, from_cache: false };
    }
  }

  private async checkOnline(heartbeatTimes: number): Promise<AuthResult> {
    try {
      const hasPublicIp =
        typeof this.deviceInfo.network?.public_ip === "string" &&
        this.deviceInfo.network.public_ip.trim() !== "";
      const needPublicIp = this.deviceInfoDeferred || !hasPublicIp;
      
      const pubPromise = needPublicIp ? fetchPublicIp() : Promise.resolve("");
      this.ensureFullDeviceInfo();
      this.logDebug("开始在线订阅请求...");

      const pub = await pubPromise;
      const nw = { ...(this.deviceInfo.network ?? {}) };
      if (pub) nw.public_ip = pub;
      if (pub) {
        this.deviceInfo = { ...this.deviceInfo, network: nw };
      }
      const device_info: DeviceInfo = {
        ...this.deviceInfo,
        ...(Object.keys(nw).length > 0 ? { network: nw } : {}),
      };
      return await this.postHeartbeatDeviceInfo(device_info, heartbeatTimes, HEARTBEAT_TIMEOUT_MS);
    } catch (e: any) {
      const msg = e?.name === "AbortError" ? "连接失败: timeout" : `连接失败: ${String(e?.message ?? e)}`;
      this.logDebug(`在线订阅请求异常: ${msg}`);
      return { authorized: false, message: msg, success: false, from_cache: false };
    }
  }

  private persistOnlineResult(result: AuthResult, heartbeatIfAuthorized: number | undefined): void {
    const snap = result.authorized
      ? (JSON.parse(JSON.stringify(this.deviceInfo)) as DeviceInfo)
      : undefined;
    this.cache.saveCache(
      result.authorized,
      result.message,
      result.authorized ? heartbeatIfAuthorized : undefined,
      snap,
    );
  }

  async checkAuthorization(_forceOnline = false): Promise<AuthResult> {
    if (this.debug) {
      const cf = this.cache.cacheFile;
      const fileNow = fs.existsSync(cf);
      const pre = this.stateBundleExistedBeforeInit;
      let desc = "不存在（持久化可能失败）";
      if (fileNow && pre) desc = "启动前已存在";
      else if (fileNow && !pre) desc = "启动前不存在，构造客户端时已新建（device_id 持久化）";
      else if (!fileNow && pre) desc = "启动前曾有，当前缺失（异常）";
      this.logDebug(`状态包: ${cf} | ${desc}`);
    }

    const snap = this.cache.snapshotForAuthorizationCheck();
    const cacheData = snap.cacheData;
    const cacheValid = this.cache.isCacheTTLValid(cacheData);

    if (cacheValid) {
      this.logDebug("本地缓存仍在有效期内（在线失败时可作后备）");
      this.logDebug("缓存有效，继续尝试在线订阅来更新订阅");
    } else {
      this.logDebug(cacheData ? "缓存存在但已过期，准备发起在线订阅请求" : "未找到缓存，准备发起在线订阅请求");
    }

    const nextHb = snap.storedHeartbeatTimes + 1;
    const onlineResult = await this.checkOnline(nextHb);

    if (onlineResult.success) {
      this.logDebug("在线订阅成功，更新缓存");
      this.persistOnlineResult(onlineResult, nextHb);
      return onlineResult;
    }

    if (cacheValid && cacheData) {
      const remaining = this.formatRemainingTime(cacheData.cachedAt);
      this.logDebug(`在线订阅失败，但缓存有效，使用缓存结果，订阅剩余时间: ${remaining}`);
      return {
        authorized: cacheData.authorized,
        message: cacheData.message,
        success: true,
        from_cache: true,
      };
    }

    return onlineResult;
  }

  async checkAuthorizationProgressive(_forceOnline = false): Promise<AuthResult> {
    if (this.debug) {
      const cf = this.cache.cacheFile;
      const fileNow = fs.existsSync(cf);
      const pre = this.stateBundleExistedBeforeInit;
      let desc = "不存在（持久化可能失败）";
      if (fileNow && pre) desc = "启动前已存在";
      else if (fileNow && !pre) desc = "启动前不存在，构造客户端时已新建（device_id 持久化）";
      else if (!fileNow && pre) desc = "启动前曾有，当前缺失（异常）";
      this.logDebug(`状态包: ${cf} | ${desc}`);
    }

    const snap = this.cache.snapshotForAuthorizationCheck();
    const cacheData = snap.cacheData;
    const cacheValid = this.cache.isCacheTTLValid(cacheData);

    if (cacheValid) {
      this.logDebug("本地缓存仍在有效期内（在线失败时可作后备）");
      this.logDebug("缓存有效，继续尝试在线订阅来更新订阅");
    } else {
      this.logDebug(cacheData ? "缓存存在但已过期，准备发起在线订阅请求" : "未找到缓存，准备发起在线订阅请求");
    }

    const nextHb = snap.storedHeartbeatTimes + 1;

    const rFast = await this.checkOnlineLight(nextHb);
    if (rFast.success) {
      if (rFast.authorized) {
        this.logDebug("在线订阅成功，更新缓存");
        this.persistOnlineResult(rFast, nextHb);
        this.logDebug("轻量心跳已落盘，发起全量 device_info 补全心跳...");
        const rFull = await this.checkOnline(nextHb + 1);
        if (rFull.success) {
          this.logDebug("在线订阅成功，更新缓存");
          this.persistOnlineResult(rFull, rFull.authorized ? nextHb + 1 : undefined);
          return rFull;
        }
        const gc = this.cache.getCache();
        if (gc && this.cache.isCacheTTLValid(gc)) {
          const remaining = this.formatRemainingTime(gc.cachedAt);
          this.logDebug(`补全心跳失败，沿用轻量结果，订阅剩余时间: ${remaining}`);
          return {
            authorized: gc.authorized,
            message: gc.message,
            success: true,
            from_cache: true,
          };
        }
        return rFull;
      }
      this.persistOnlineResult(rFast, undefined);
      return rFast;
    }

    const onlineResult = await this.checkOnline(nextHb);
    if (onlineResult.success) {
      this.logDebug("在线订阅成功，更新缓存");
      this.persistOnlineResult(onlineResult, onlineResult.authorized ? nextHb : undefined);
      return onlineResult;
    }

    if (cacheValid && cacheData) {
      const remaining = this.formatRemainingTime(cacheData.cachedAt);
      this.logDebug(`在线订阅失败，但缓存有效，使用缓存结果，订阅剩余时间: ${remaining}`);
      return {
        authorized: cacheData.authorized,
        message: cacheData.message,
        success: true,
        from_cache: true,
      };
    }

    return onlineResult;
  }

  async requireAuthorization(forceOnline = false): Promise<boolean> {
    const result = await this.checkAuthorization(forceOnline);

    if (!result.success || !result.authorized) {
      throw new AuthorizationError({
        message: result.message,
        result,
        deviceId: this.deviceId,
        serverUrl: this.serverUrl,
      });
    }

    return true;
  }

  clearCache(): boolean {
    return this.cache.clearCache();
  }

  canSoftLaunch(): boolean {
    const c = this.cache.getCache();
    return !!(c?.authorized && this.cache.isCacheTTLValid(c));
  }

  startBackgroundRefresh(options?: {
    forceOnline?: boolean;
    onDone?: (result: AuthResult) => void;
  }): boolean {
    const soft = this.canSoftLaunch();
    const fo = options?.forceOnline ?? false;
    void this.checkAuthorizationProgressive(fo).then(
      (r) => {
        options?.onDone?.(r);
      },
      (err: unknown) => {
        options?.onDone?.({
          authorized: false,
          success: false,
          from_cache: false,
          message: err instanceof Error ? err.message : String(err),
        });
      },
    );
    return soft;
  }

  async getAuthorizationInfo(): Promise<AuthorizationInfo> {
    const cache = this.cache.getCache();

    const info: AuthorizationInfo = cache
      ? {
          authorized: cache.authorized,
          success: true,
          from_cache: true,
          message: cache.message,
          device_id: this.deviceId,
          server_url: this.serverUrl,
          remaining_time: this.formatRemainingTime(cache.cachedAt),
          cache_valid: this.cache.isCacheTTLValid(cache),
          cached_at: cache.cachedAt,
          cached_at_readable:
            cache.cachedAt > 0
              ? new Date(cache.cachedAt * 1000).toISOString().replace("T", " ").slice(0, 19)
              : undefined,
        }
      : {
          authorized: false,
          success: false,
          from_cache: false,
          message: "无本地授权缓存",
          device_id: this.deviceId,
          server_url: this.serverUrl,
          remaining_time: "无缓存",
          cache_valid: false,
        };

    if (this.debug) {
      try {
        this.logDebug(`授权信息摘要:\n${JSON.stringify(info, null, 2)}`);
      } catch {}
    }

    return info;
  }
}
