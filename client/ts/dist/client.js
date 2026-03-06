"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.AuthClient = void 0;
const errors_1 = require("./errors");
const crypto_1 = require("./crypto");
const cache_1 = require("./cache");
const device_1 = require("./device");
const http_1 = require("./http");
class AuthClient {
    serverUrl;
    softwareName;
    deviceId;
    deviceInfo;
    clientSecret;
    debug;
    cache;
    constructor(config) {
        if (!config.serverUrl)
            throw new Error("serverUrl不能为空");
        if (!config.softwareName)
            throw new Error("softwareName不能为空");
        const secret = config.clientSecret ?? process.env.CLIENT_SECRET ?? "";
        if (!secret) {
            throw new Error("CLIENT_SECRET未配置！请在初始化时传入clientSecret参数，或设置环境变量CLIENT_SECRET。这是安全要求，必须配置。");
        }
        this.serverUrl = config.serverUrl.replace(/\/+$/, "");
        this.softwareName = config.softwareName;
        this.clientSecret = secret;
        this.debug = !!config.debug;
        this.deviceId = (0, device_1.buildDeviceId)(this.serverUrl, config.deviceId, this.softwareName);
        this.deviceInfo = config.deviceInfo ?? (0, device_1.collectDeviceInfo)();
        const enableCache = config.enableCache ?? true;
        const cacheValidityDays = config.cacheValidityDays ?? 7;
        const checkIntervalDays = config.checkIntervalDays ?? 2;
        if (enableCache) {
            this.cache = new cache_1.AuthCache({
                cacheDir: config.cacheDir,
                deviceId: this.deviceId,
                serverUrl: this.serverUrl,
                softwareName: this.softwareName,
                cacheValidityDays,
                checkIntervalDays,
            });
        }
    }
    logDebug(msg) {
        if (this.debug) {
            // 不加额外依赖，直接输出
            // eslint-disable-next-line no-console
            console.debug(`[ts-auth-client][DEBUG] ${msg}`);
        }
    }
    formatRemainingTime(cachedAtSeconds) {
        if (!cachedAtSeconds || cachedAtSeconds <= 0 || !this.cache)
            return "未知";
        const now = Date.now() / 1000;
        const elapsed = now - cachedAtSeconds;
        const remaining = this.cache.cacheValiditySeconds - elapsed;
        if (remaining <= 0)
            return "已过期";
        const days = Math.floor(remaining / 86400);
        const hours = Math.floor((remaining % 86400) / 3600);
        const minutes = Math.floor((remaining % 3600) / 60);
        const parts = [];
        if (days > 0)
            parts.push(`${days}天`);
        if (hours > 0)
            parts.push(`${hours}小时`);
        if (minutes > 0 || parts.length === 0)
            parts.push(`${minutes}分钟`);
        return parts.join("");
    }
    async checkOnline() {
        try {
            this.logDebug("开始在线订阅请求...");
            const requestData = {
                device_id: this.deviceId,
                software_name: this.softwareName,
                device_info: this.deviceInfo,
            };
            const encrypted = (0, crypto_1.encryptData)(JSON.stringify(requestData), this.clientSecret);
            const { status, json, text } = await (0, http_1.postJson)(`${this.serverUrl}/api/auth/heartbeat`, { encrypted_data: encrypted }, 10_000);
            if (status === 200) {
                const token = json?.encrypted_data ?? "";
                const decryptedText = token ? (0, crypto_1.decryptData)(token, this.clientSecret) : null;
                if (!decryptedText) {
                    this.logDebug("在线订阅响应解密失败");
                    return { authorized: false, message: "解密响应失败", success: false, from_cache: false };
                }
                const decrypted = JSON.parse(decryptedText);
                this.logDebug(`在线订阅成功，authorized=${!!decrypted.authorized}`);
                return {
                    authorized: !!decrypted.authorized,
                    message: decrypted.message ?? "",
                    success: true,
                    from_cache: false,
                };
            }
            // Python 逻辑：403 取 detail，其它返回 “服务器错误: status”
            const detail = json?.detail;
            const msg = status === 403 && typeof detail === "string" ? detail : `服务器错误: ${status}`;
            this.logDebug(`在线订阅失败，status=${status}, message=${msg}; raw=${text}`);
            return { authorized: false, message: msg, success: false, from_cache: false, is_auth_error: status === 403 };
        }
        catch (e) {
            const msg = e?.name === "AbortError" ? "连接失败: timeout" : `连接失败: ${String(e?.message ?? e)}`;
            this.logDebug(`在线订阅请求异常: ${msg}`);
            return { authorized: false, message: msg, success: false, from_cache: false };
        }
    }
    async checkAuthorization() {
        if (!this.cache) {
            return this.checkOnline();
        }
        let cacheData = this.cache.getCache();
        let cacheValid = false;
        if (cacheData?.cachedAt) {
            const elapsed = Date.now() / 1000 - cacheData.cachedAt;
            if (elapsed < this.cache.cacheValiditySeconds) {
                cacheValid = true;
                this.logDebug("命中有效缓存，直接授权通过");
            }
        }
        if (cacheValid) {
            this.logDebug("缓存有效，继续尝试在线订阅来更新订阅");
        }
        else {
            this.logDebug(cacheData ? "缓存存在但已过期，准备发起在线订阅请求" : "未找到缓存，准备发起在线订阅请求");
        }
        const onlineResult = await this.checkOnline();
        if (onlineResult.success) {
            this.logDebug("在线订阅成功，更新缓存");
            this.cache.saveCache(onlineResult.authorized, onlineResult.message);
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
    async requireAuthorization() {
        const result = await this.checkAuthorization();
        if (!result.success) {
            throw new errors_1.AuthorizationError({
                message: result.message,
                result,
                deviceId: this.deviceId,
                serverUrl: this.serverUrl,
            });
        }
        if (!result.authorized) {
            throw new errors_1.AuthorizationError({
                message: result.message,
                result,
                deviceId: this.deviceId,
                serverUrl: this.serverUrl,
            });
        }
        return true;
    }
    clearCache() {
        if (!this.cache)
            return true;
        return this.cache.clearCache();
    }
    async getAuthorizationInfo() {
        const result = await this.checkAuthorization();
        const info = {
            authorized: result.authorized,
            success: result.success,
            from_cache: result.from_cache,
            message: result.message,
            device_id: this.deviceId,
            server_url: this.serverUrl,
        };
        if (this.cache) {
            const cache = this.cache.getCache();
            if (cache) {
                const remaining = this.formatRemainingTime(cache.cachedAt);
                info.remaining_time = remaining;
                info.cache_valid = this.cache.isCacheValid();
                info.cached_at = cache.cachedAt;
                if (cache.cachedAt > 0) {
                    info.cached_at_readable = new Date(cache.cachedAt * 1000).toISOString().replace("T", " ").slice(0, 19);
                }
            }
            else {
                info.remaining_time = "无缓存";
                info.cache_valid = false;
            }
        }
        return info;
    }
}
exports.AuthClient = AuthClient;
