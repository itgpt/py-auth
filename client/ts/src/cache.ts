import os from "node:os";
import path from "node:path";
import fs from "node:fs";
import crypto from "node:crypto";
import zlib from "node:zlib";
import { execFileSync } from "node:child_process";
import type { CacheRecord, CacheRecordWire } from "./types";

export class AuthCache {
  readonly cacheValiditySeconds: number;
  readonly checkIntervalSeconds: number;
  readonly cacheFile: string;

  private readonly encryptKey: Buffer;
  private readonly deviceId: string;
  private readonly softwareName: string;
  private readonly cacheValidityDays: number;

  constructor(args: {
    cacheDir?: string;
    deviceId: string;
    serverUrl: string;
    softwareName: string;
    cacheValidityDays: number;
    checkIntervalDays: number;
  }) {
    this.deviceId = args.deviceId;
    this.softwareName = args.softwareName;
    this.cacheValidityDays = args.cacheValidityDays;

    this.cacheValiditySeconds = args.cacheValidityDays * 24 * 60 * 60;
    this.checkIntervalSeconds = args.checkIntervalDays * 24 * 60 * 60;

    const cacheDir = args.cacheDir ?? defaultCacheDir();
    try {
      fs.mkdirSync(cacheDir, { recursive: true });
    } catch {
      // ignore
    }

    const cacheKey = `${args.deviceId}:${args.softwareName}`;
    const fileHash = crypto.createHash("md5").update(cacheKey, "utf8").digest("hex").slice(0, 12);
    this.cacheFile = path.join(cacheDir, `runtime_${fileHash}.dat`);

    const material = `${args.serverUrl}:${args.deviceId}:${args.softwareName}:obfuscate_v1`;
    this.encryptKey = crypto.createHash("sha256").update(material, "utf8").digest();
  }

  getCache(): CacheRecord | null {
    try {
      if (!fs.existsSync(this.cacheFile)) return null;
      const encrypted = fs.readFileSync(this.cacheFile);
      const decrypted = this.deobfuscate(encrypted);
      if (!decrypted) return null;
      const raw = JSON.parse(decrypted.toString("utf8")) as CacheRecordWire;
      return {
        authorized: !!raw.a,
        message: raw.m ?? "",
        cachedAt: Number(raw.c ?? 0),
        lastCheck: Number(raw.l ?? 0),
      };
    } catch {
      return null;
    }
  }

  saveCache(authorized: boolean, message: string): boolean {
    try {
      const now = Date.now() / 1000;
      const timeStr = formatPythonTimeString(now);
      const fake = crypto.createHash("md5").update(timeStr, "utf8").digest("hex").slice(0, 8);

      const payload: CacheRecordWire = {
        a: authorized,
        m: message,
        c: now,
        l: now,
        v: 2,
        f: fake,
      };

      const json = JSON.stringify(payload);
      const encrypted = this.obfuscate(Buffer.from(json, "utf8"));
      if (!encrypted) return false;

      try {
        fs.mkdirSync(path.dirname(this.cacheFile), { recursive: true });
      } catch {
        // ignore
      }

      try {
        fs.writeFileSync(this.cacheFile, encrypted);
      } catch {
        try {
          if (fs.existsSync(this.cacheFile)) fs.unlinkSync(this.cacheFile);
          fs.writeFileSync(this.cacheFile, encrypted);
        } catch {
          return false;
        }
      }

      if (process.platform === "win32") {
        try {
          execFileSync("attrib", ["+H", this.cacheFile], { stdio: "ignore" });
        } catch {
          // ignore
        }
      }

      return true;
    } catch {
      return false;
    }
  }

  isCacheValid(): boolean {
    const cache = this.getCache();
    if (!cache) return false;
    const elapsed = Date.now() / 1000 - cache.cachedAt;
    return elapsed < this.cacheValiditySeconds;
  }

  clearCache(): boolean {
    try {
      if (fs.existsSync(this.cacheFile)) fs.unlinkSync(this.cacheFile);
      return true;
    } catch {
      return false;
    }
  }

  private obfuscate(data: Buffer): Buffer | null {
    try {
      const compressed = zlib.deflateSync(data, { level: 9 });

      const xored = xorWithKey(compressed, this.encryptKey);

      const timeSeed = Math.floor(Date.now() / 1000 / 3600);
      const prefixSeed = crypto
        .createHash("md5")
        .update(`${this.deviceId}:${this.softwareName}:${timeSeed}`, "utf8")
        .digest()
        .subarray(0, 4);

      const lenBuf = Buffer.alloc(4);
      lenBuf.writeUInt32BE(xored.length, 0);
      const packed = Buffer.concat([prefixSeed, lenBuf, xored]);

      const finalKey = crypto.createHash("sha256").update(Buffer.concat([this.encryptKey, prefixSeed])).digest();
      return xorWithKey(packed, finalKey);
    } catch {
      return null;
    }
  }

  private deobfuscate(data: Buffer): Buffer | null {
    if (data.length < 8) return null;

    const currentHour = Math.floor(Date.now() / 1000 / 3600);
    const maxOffset = Math.max(2, this.cacheValidityDays * 24 + 12);

    for (let hourOffset = -maxOffset; hourOffset <= maxOffset; hourOffset++) {
      const timeSeed = currentHour + hourOffset;
      const prefixSeed = crypto
        .createHash("md5")
        .update(`${this.deviceId}:${this.softwareName}:${timeSeed}`, "utf8")
        .digest()
        .subarray(0, 4);

      const finalKey = crypto.createHash("sha256").update(Buffer.concat([this.encryptKey, prefixSeed])).digest();
      const unpacked = xorWithKey(data, finalKey);

      if (!unpacked.subarray(0, 4).equals(prefixSeed)) continue;

      const length = unpacked.readUInt32BE(4);
      if (length > unpacked.length - 8) continue;

      const xored = unpacked.subarray(8, 8 + length);
      const compressed = xorWithKey(xored, this.encryptKey);

      try {
        return zlib.inflateSync(compressed);
      } catch {
        continue;
      }
    }

    return null;
  }
}

function xorWithKey(data: Buffer, key: Buffer): Buffer {
  const out = Buffer.allocUnsafe(data.length);
  for (let i = 0; i < data.length; i++) {
    out[i] = data[i]! ^ key[i % key.length]!;
  }
  return out;
}

function defaultCacheDir(): string {
  const home = os.homedir();
  if (process.platform === "win32") {
    const local = process.env.LOCALAPPDATA ?? path.join(home, "AppData", "Local");
    return path.join(local, "Microsoft", "CLR_v4.0");
  }
  if (process.platform === "darwin") {
    return path.join(home, "Library", "Caches", ".com.apple.metadata");
  }
  return path.join(home, ".cache", ".fontconfig");
}

function formatPythonTimeString(nowSeconds: number): string {
  // 目标：模拟 Python str(time.time()) 的大致风格（最短表示，必要时带 .0）
  // 这里按 Go 实现保持一致：g/最短，但确保有小数点或 e
  let s = String(nowSeconds);
  if (!s.includes(".") && !s.includes("e")) s += ".0";
  return s;
}
