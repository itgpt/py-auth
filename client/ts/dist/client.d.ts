import type { AuthClientConfig, AuthResult, AuthorizationInfo } from "./types";
export declare class AuthClient {
    private readonly serverUrl;
    private readonly softwareName;
    private readonly softwareVersion;
    private readonly deviceId;
    private readonly deviceInfo;
    private readonly clientSecret;
    private readonly debug;
    private readonly cache?;
    constructor(config: AuthClientConfig);
    private logDebug;
    private formatRemainingTime;
    private checkOnline;
    checkAuthorization(): Promise<AuthResult>;
    requireAuthorization(): Promise<boolean>;
    clearCache(): boolean;
    getAuthorizationInfo(): Promise<AuthorizationInfo>;
}
