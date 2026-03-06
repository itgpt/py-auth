"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.AuthCache = void 0;
const node_os_1 = __importDefault(require("node:os"));
const node_path_1 = __importDefault(require("node:path"));
const node_fs_1 = __importDefault(require("node:fs"));
const node_crypto_1 = __importDefault(require("node:crypto"));
const node_zlib_1 = __importDefault(require("node:zlib"));
const node_child_process_1 = require("node:child_process");
class AuthCache {
    cacheValiditySeconds;
    checkIntervalSeconds;
    cacheFile;
    encryptKey;
    deviceId;
    softwareName;
    cacheValidityDays;
    constructor(args) {
        this.deviceId = args.deviceId;
        this.softwareName = args.softwareName;
        this.cacheValidityDays = args.cacheValidityDays;
        this.cacheValiditySeconds = args.cacheValidityDays * 24 * 60 * 60;
        this.checkIntervalSeconds = args.checkIntervalDays * 24 * 60 * 60;
        const cacheDir = args.cacheDir ?? defaultCacheDir();
        try {
            node_fs_1.default.mkdirSync(cacheDir, { recursive: true });
        }
        catch {
            // ignore
        }
        const cacheKey = `${args.deviceId}:${args.softwareName}`;
        const fileHash = node_crypto_1.default.createHash("md5").update(cacheKey, "utf8").digest("hex").slice(0, 12);
        this.cacheFile = node_path_1.default.join(cacheDir, `runtime_${fileHash}.dat`);
        const material = `${args.serverUrl}:${args.deviceId}:${args.softwareName}:obfuscate_v1`;
        this.encryptKey = node_crypto_1.default.createHash("sha256").update(material, "utf8").digest();
    }
    getCache() {
        try {
            if (!node_fs_1.default.existsSync(this.cacheFile))
                return null;
            const encrypted = node_fs_1.default.readFileSync(this.cacheFile);
            const decrypted = this.deobfuscate(encrypted);
            if (!decrypted)
                return null;
            const raw = JSON.parse(decrypted.toString("utf8"));
            return {
                authorized: !!raw.a,
                message: raw.m ?? "",
                cachedAt: Number(raw.c ?? 0),
                lastCheck: Number(raw.l ?? 0),
            };
        }
        catch {
            return null;
        }
    }
    saveCache(authorized, message) {
        try {
            const now = Date.now() / 1000;
            const timeStr = formatPythonTimeString(now);
            const fake = node_crypto_1.default.createHash("md5").update(timeStr, "utf8").digest("hex").slice(0, 8);
            const payload = {
                a: authorized,
                m: message,
                c: now,
                l: now,
                v: 2,
                f: fake,
            };
            const json = JSON.stringify(payload);
            const encrypted = this.obfuscate(Buffer.from(json, "utf8"));
            if (!encrypted)
                return false;
            try {
                node_fs_1.default.mkdirSync(node_path_1.default.dirname(this.cacheFile), { recursive: true });
            }
            catch {
                // ignore
            }
            try {
                node_fs_1.default.writeFileSync(this.cacheFile, encrypted);
            }
            catch {
                try {
                    if (node_fs_1.default.existsSync(this.cacheFile))
                        node_fs_1.default.unlinkSync(this.cacheFile);
                    node_fs_1.default.writeFileSync(this.cacheFile, encrypted);
                }
                catch {
                    return false;
                }
            }
            if (process.platform === "win32") {
                try {
                    (0, node_child_process_1.execFileSync)("attrib", ["+H", this.cacheFile], { stdio: "ignore" });
                }
                catch {
                    // ignore
                }
            }
            return true;
        }
        catch {
            return false;
        }
    }
    isCacheValid() {
        const cache = this.getCache();
        if (!cache)
            return false;
        const elapsed = Date.now() / 1000 - cache.cachedAt;
        return elapsed < this.cacheValiditySeconds;
    }
    clearCache() {
        try {
            if (node_fs_1.default.existsSync(this.cacheFile))
                node_fs_1.default.unlinkSync(this.cacheFile);
            return true;
        }
        catch {
            return false;
        }
    }
    obfuscate(data) {
        try {
            const compressed = node_zlib_1.default.deflateSync(data, { level: 9 });
            const xored = xorWithKey(compressed, this.encryptKey);
            const timeSeed = Math.floor(Date.now() / 1000 / 3600);
            const prefixSeed = node_crypto_1.default
                .createHash("md5")
                .update(`${this.deviceId}:${this.softwareName}:${timeSeed}`, "utf8")
                .digest()
                .subarray(0, 4);
            const lenBuf = Buffer.alloc(4);
            lenBuf.writeUInt32BE(xored.length, 0);
            const packed = Buffer.concat([prefixSeed, lenBuf, xored]);
            const finalKey = node_crypto_1.default.createHash("sha256").update(Buffer.concat([this.encryptKey, prefixSeed])).digest();
            return xorWithKey(packed, finalKey);
        }
        catch {
            return null;
        }
    }
    deobfuscate(data) {
        if (data.length < 8)
            return null;
        const currentHour = Math.floor(Date.now() / 1000 / 3600);
        const maxOffset = Math.max(2, this.cacheValidityDays * 24 + 12);
        for (let hourOffset = -maxOffset; hourOffset <= maxOffset; hourOffset++) {
            const timeSeed = currentHour + hourOffset;
            const prefixSeed = node_crypto_1.default
                .createHash("md5")
                .update(`${this.deviceId}:${this.softwareName}:${timeSeed}`, "utf8")
                .digest()
                .subarray(0, 4);
            const finalKey = node_crypto_1.default.createHash("sha256").update(Buffer.concat([this.encryptKey, prefixSeed])).digest();
            const unpacked = xorWithKey(data, finalKey);
            if (!unpacked.subarray(0, 4).equals(prefixSeed))
                continue;
            const length = unpacked.readUInt32BE(4);
            if (length > unpacked.length - 8)
                continue;
            const xored = unpacked.subarray(8, 8 + length);
            const compressed = xorWithKey(xored, this.encryptKey);
            try {
                return node_zlib_1.default.inflateSync(compressed);
            }
            catch {
                continue;
            }
        }
        return null;
    }
}
exports.AuthCache = AuthCache;
function xorWithKey(data, key) {
    const out = Buffer.allocUnsafe(data.length);
    for (let i = 0; i < data.length; i++) {
        out[i] = data[i] ^ key[i % key.length];
    }
    return out;
}
function defaultCacheDir() {
    const home = node_os_1.default.homedir();
    if (process.platform === "win32") {
        const local = process.env.LOCALAPPDATA ?? node_path_1.default.join(home, "AppData", "Local");
        return node_path_1.default.join(local, "Microsoft", "CLR_v4.0");
    }
    if (process.platform === "darwin") {
        return node_path_1.default.join(home, "Library", "Caches", ".com.apple.metadata");
    }
    return node_path_1.default.join(home, ".cache", ".fontconfig");
}
function formatPythonTimeString(nowSeconds) {
    // 目标：模拟 Python str(time.time()) 的大致风格（最短表示，必要时带 .0）
    // 这里按 Go 实现保持一致：g/最短，但确保有小数点或 e
    let s = String(nowSeconds);
    if (!s.includes(".") && !s.includes("e"))
        s += ".0";
    return s;
}
