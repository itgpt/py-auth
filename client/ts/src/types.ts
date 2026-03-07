export interface DeviceInfo {
  hostname?: string;
  system?: string;
  release?: string;
  version?: string;
  machine?: string;
  processor?: string;
  mac_address?: string;
  ip_address?: string;
  cpu_count?: number;
  cpu_model?: string;
  cpu_freq_mhz?: number;
  memory_total_gb?: number;
  memory_free_gb?: number;
  disk_total_gb?: number;
  platform_version?: string;
  node_version?: string;
  system_uptime_seconds?: number;
  username?: string;
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
  a: boolean;
  m: string;
  c: number;
  l: number;
  v: number;
  f: string;
}

export interface CacheRecord {
  authorized: boolean;
  message: string;
  cachedAt: number;
  lastCheck: number;
}

export interface AuthClientConfig {
  serverUrl: string;
  softwareName: string;
  deviceId?: string;
  deviceInfo?: DeviceInfo;
  clientSecret?: string;
  cacheDir?: string;
  enableCache?: boolean;
  cacheValidityDays?: number;
  checkIntervalDays?: number;
  debug?: boolean;
}
