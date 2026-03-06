import type { AuthResult } from "./types";
export declare class AuthorizationError extends Error {
    readonly result?: AuthResult;
    readonly deviceId?: string;
    readonly serverUrl?: string;
    constructor(args: {
        message: string;
        result?: AuthResult;
        deviceId?: string;
        serverUrl?: string;
    });
    get isNetworkError(): boolean;
    get isUnauthorized(): boolean;
    get isValidationError(): boolean;
}
