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
}
