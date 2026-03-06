import type { CacheRecord } from "./types";
export declare class AuthCache {
    readonly cacheValiditySeconds: number;
    readonly checkIntervalSeconds: number;
    readonly cacheFile: string;
    private readonly encryptKey;
    private readonly deviceId;
    private readonly softwareName;
    private readonly cacheValidityDays;
    constructor(args: {
        cacheDir?: string;
        deviceId: string;
        serverUrl: string;
        softwareName: string;
        cacheValidityDays: number;
        checkIntervalDays: number;
    });
    getCache(): CacheRecord | null;
    saveCache(authorized: boolean, message: string): boolean;
    isCacheValid(): boolean;
    clearCache(): boolean;
    private obfuscate;
    private deobfuscate;
}
