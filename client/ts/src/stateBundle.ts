import path from "node:path";
import fs from "node:fs";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";
import { getClientStorageRoot } from "./storage";

const NONCE_LEN = 12;
const TAG_LEN = 16;

const RESERVED_BUNDLE_ROOT = new Set([
  "apps",
  "heartbeat_times",
  "device_id",
  "last_success_at",
]);

export const BUNDLE_ROOT_STRAY_KEYS = [
  "heartbeat_times",
  "device_id",
  "last_success_at",
] as const;

export const BUNDLE_PRODUCT_DEVICE_INFO_SNAPSHOT_KEY = "device_info_snapshot";

export const BUNDLE_PRODUCT_REVOKE_KEYS = [
  "heartbeat_times",
  "last_success_at",
  BUNDLE_PRODUCT_DEVICE_INFO_SNAPSHOT_KEY,
] as const;

export function rowLastSuccessTs(row: Record<string, unknown>): number | null {
  const v = row.last_success_at;
  if (typeof v === "number" && Number.isFinite(v) && v > 0) return v;
  if (typeof v === "string" && v.trim()) {
    const n = Number(v);
    if (Number.isFinite(n) && n > 0) return n;
  }
  return null;
}

export function rowDeviceId(row: Record<string, unknown>): string | null {
  const d = row.device_id;
  if (typeof d === "string" && d.trim()) return d.trim();
  return null;
}

function unlinkStateFileQuietly(file: string): void {
  try {
    if (process.platform === "win32") {
      try {
        execFileSync("attrib", ["-H", file], { stdio: "ignore" });
      } catch {}
    }
    fs.unlinkSync(file);
  } catch {}
}

export function loadAppsMap(root: Record<string, unknown>): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {};
  for (const [k, v] of Object.entries(root)) {
    if (RESERVED_BUNDLE_ROOT.has(k)) continue;
    if (!v || typeof v !== "object" || Array.isArray(v)) continue;
    const name = String(k).trim();
    if (!name) continue;
    const sub = { ...(v as Record<string, unknown>) };
    delete sub.software_name;
    out[name] = sub;
  }
  return out;
}

export function commitAppsMap(root: Record<string, unknown>, apps: Record<string, Record<string, unknown>>): void {
  delete root.apps;
  for (const k of Object.keys(root)) {
    if (RESERVED_BUNDLE_ROOT.has(k)) continue;
    const v = root[k];
    if (v && typeof v === "object" && !Array.isArray(v) && !(k in apps)) {
      delete root[k];
    }
  }
  for (const [sn, row] of Object.entries(apps)) {
    root[sn] = { ...row };
  }
}

export function normalizeServerUrl(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

export function bundlePath(serverUrl: string, baseDir?: string): string {
  const root = baseDir ?? getClientStorageRoot();
  const su = normalizeServerUrl(serverUrl);
  const sh = crypto.createHash("sha256").update(su, "utf8").digest("hex").slice(0, 12);
  return path.join(root, `state_${sh}_default.dat`);
}

function deriveBundleKey(serverUrl: string): Buffer {
  const su = normalizeServerUrl(serverUrl);
  return crypto.createHash("sha256").update(su, "utf8").digest();
}

function encryptState(plain: Buffer, key: Buffer): Buffer {
  const nonce = crypto.randomBytes(NONCE_LEN);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, nonce);
  const enc = Buffer.concat([cipher.update(plain), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([nonce, enc, tag]);
}

function decryptState(data: Buffer, key: Buffer): Buffer | null {
  if (data.length < NONCE_LEN + TAG_LEN + 1) return null;
  const nonce = data.subarray(0, NONCE_LEN);
  const rest = data.subarray(NONCE_LEN);
  const tag = rest.subarray(-TAG_LEN);
  const enc = rest.subarray(0, -TAG_LEN);
  try {
    const decipher = crypto.createDecipheriv("aes-256-gcm", key, nonce);
    decipher.setAuthTag(tag);
    return Buffer.concat([decipher.update(enc), decipher.final()]);
  } catch {
    return null;
  }
}

export function readStateDict(serverUrl: string, baseDir?: string): Record<string, unknown> | null {
  const file = bundlePath(serverUrl, baseDir);
  if (!fs.existsSync(file)) return null;
  let raw: Buffer;
  try {
    raw = fs.readFileSync(file);
  } catch {
    return null;
  }
  const key = deriveBundleKey(serverUrl);
  const dec = decryptState(raw, key);
  if (!dec) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(dec.toString("utf8"));
  } catch {
    return null;
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    unlinkStateFileQuietly(file);
    return null;
  }
  const root = parsed as Record<string, unknown>;
  delete root.device_id;
  return root;
}

function writeStateDict(serverUrl: string, data: Record<string, unknown>, baseDir?: string): boolean {
  const file = bundlePath(serverUrl, baseDir);
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const body = Buffer.from(JSON.stringify(data), "utf8");
    const key = deriveBundleKey(serverUrl);
    const out = encryptState(body, key);
    fs.writeFileSync(file, out);
    return true;
  } catch {
    return false;
  }
}

export function writeStateDictWithRetry(
  serverUrl: string,
  data: Record<string, unknown>,
  baseDir?: string,
): boolean {
  if (writeStateDict(serverUrl, data, baseDir)) {
    if (process.platform === "win32") {
      const file = bundlePath(serverUrl, baseDir);
      try {
        execFileSync("attrib", ["+H", file], { stdio: "ignore" });
      } catch {}
    }
    return true;
  }
  if (process.platform === "win32") {
    const file = bundlePath(serverUrl, baseDir);
    try {
      if (fs.existsSync(file)) {
        try {
          execFileSync("attrib", ["-H", file], { stdio: "ignore" });
        } catch {
        }
        fs.unlinkSync(file);
      }
    } catch {}
    if (writeStateDict(serverUrl, data, baseDir)) {
      try {
        execFileSync("attrib", ["+H", file], { stdio: "ignore" });
      } catch {}
      return true;
    }
  }
  return false;
}
