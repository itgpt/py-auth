export interface SdkInfo {
  language: string;
  sdk_name: string;
  sdk_version: string;
  runtime?: string;
  heartbeat_times?: number;
}

export interface DeviceNetworkInterfaceRow {
  mac_address?: string;
  ip_address?: string;
}

export interface DeviceNetworkInfo {
  mac_address?: string;
  ip_address?: string;
  public_ip?: string;
  interfaces?: DeviceNetworkInterfaceRow[];
}

export interface DeviceMemoryInfo {
  total_gb?: number;
  free_gb?: number;
  available_gb?: number;
}

export interface DeviceDiskVolumeInfo {
  mount?: string;
  device?: string;
  total_gb?: number;
  free_gb?: number;
}

export interface DeviceDiskModelGroupInfo {
  volumes: DeviceDiskVolumeInfo[];
}

export interface DeviceDiskInfo {
  total_gb?: number;
  free_gb?: number;
  models?: Record<string, DeviceDiskModelGroupInfo>;
}

export interface DeviceCpuInfo {
  model?: string;
  count?: number;
  physical_count?: number;
  freq_mhz?: number;
  freq_min_mhz?: number;
  freq_max_mhz?: number;
}

export interface DeviceSystemInfo {
  hostname?: string;
  os?: string;
  release?: string;
  version?: string;
  machine?: string;
  processor?: string;
  platform_version?: string;
  windows_display_version?: string;
  windows_product_name?: string;
  node_version?: string;
  python_version?: string;
  go_version?: string;
  system_uptime_seconds?: number;
  username?: string;
}

export interface DeviceInfo {
  sdk?: SdkInfo;
  system?: DeviceSystemInfo;
  network?: DeviceNetworkInfo;
  memory?: DeviceMemoryInfo;
  disk?: DeviceDiskInfo;
  cpu?: DeviceCpuInfo;
  software_version?: string;
}

export interface AuthResult {
  authorized: boolean;
  message: string;
  success: boolean;
  from_cache: boolean;
  is_auth_error?: boolean;
}

export interface AuthorizationInfo {
  authorized: boolean;
  success: boolean;
  from_cache: boolean;
  message: string;
  device_id: string;
  server_url: string;
  remaining_time?: string;
  cache_valid?: boolean;
  cached_at?: number;
  cached_at_readable?: string;
}

export interface CacheRecordWire {
  device_id: string;
  last_success_at: number;
  heartbeat_times: number;
}

export interface CacheRecord {
  authorized: boolean;
  message: string;
  cachedAt: number;
}

export interface AuthClientConfig {
  serverUrl: string;
  softwareName: string;
  softwareVersion?: string;
  deviceId?: string;
  deviceInfo?: DeviceInfo;
  clientSecret?: string;
  cacheValidityDays?: number;
  checkIntervalDays?: number;
  debug?: boolean;
}
