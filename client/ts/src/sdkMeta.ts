import type { SdkInfo } from "./types";

export const CLIENT_SDK_LANGUAGE = "typescript";
export const CLIENT_SDK_NAME = "py-auth-client";
export const CLIENT_SDK_VERSION = "0.1.4";

export function baseSdk(runtime: string): SdkInfo {
  return {
    language: CLIENT_SDK_LANGUAGE,
    sdk_name: CLIENT_SDK_NAME,
    sdk_version: CLIENT_SDK_VERSION,
    runtime,
  };
}