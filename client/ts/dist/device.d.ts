import type { DeviceInfo } from "./types";
export declare function loadPersistedDeviceId(serverUrl: string, softwareName: string): string | null;
export declare function persistDeviceId(serverUrl: string, softwareName: string, deviceId: string): void;
export declare function buildDeviceId(serverUrl: string, providedDeviceId: string | undefined, softwareName: string): string;
export declare function collectDeviceInfo(): DeviceInfo;
