import type { AuthResult } from "./types";

export class AuthorizationError extends Error {
  readonly result?: AuthResult;
  readonly deviceId?: string;
  readonly serverUrl?: string;

  constructor(args: {
    message: string;
    result?: AuthResult;
    deviceId?: string;
    serverUrl?: string;
  }) {
    super(args.message);
    this.name = "AuthorizationError";
    this.result = args.result;
    this.deviceId = args.deviceId;
    this.serverUrl = args.serverUrl;
  }

  get isNetworkError(): boolean {
    const message = (this.result?.message ?? this.message).toLowerCase();
    const keywords = ["连接失败", "连接", "network", "timeout", "connection"];
    return keywords.some((k) => message.includes(k.toLowerCase()));
  }

  get isUnauthorized(): boolean {
    if (this.result) {
      return !this.result.authorized && this.result.success;
    }
    return this.message.includes("未授权") || this.message.includes("禁用");
  }

  get isValidationError(): boolean {
    if (this.result) {
      return !this.result.success;
    }
    return this.message.includes("无法验证授权") || this.message.includes("验证失败");
  }
}
