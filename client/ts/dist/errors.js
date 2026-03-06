"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.AuthorizationError = void 0;
class AuthorizationError extends Error {
    result;
    deviceId;
    serverUrl;
    constructor(args) {
        super(args.message);
        this.name = "AuthorizationError";
        this.result = args.result;
        this.deviceId = args.deviceId;
        this.serverUrl = args.serverUrl;
    }
    get isNetworkError() {
        const message = (this.result?.message ?? this.message).toLowerCase();
        const keywords = ["连接失败", "连接", "network", "timeout", "connection"];
        return keywords.some((k) => message.includes(k.toLowerCase()));
    }
    get isUnauthorized() {
        if (this.result) {
            return !this.result.authorized && this.result.success;
        }
        return this.message.includes("未授权") || this.message.includes("禁用");
    }
    get isValidationError() {
        if (this.result) {
            return !this.result.success;
        }
        return this.message.includes("无法验证授权") || this.message.includes("验证失败");
    }
}
exports.AuthorizationError = AuthorizationError;
