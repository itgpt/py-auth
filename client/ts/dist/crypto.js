"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.encryptData = encryptData;
exports.decryptData = decryptData;
const node_crypto_1 = require("node:crypto");
function b64UrlEncode(buf) {
    return buf.toString("base64").replace(/\+/g, "-").replace(/\//g, "_");
}
function b64UrlDecode(s) {
    const normalized = s.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "===".slice((normalized.length + 3) % 4);
    return Buffer.from(padded, "base64");
}
function timingSafeEqual(a, b) {
    if (a.length !== b.length)
        return false;
    let diff = 0;
    for (let i = 0; i < a.length; i++)
        diff |= a[i] ^ b[i];
    return diff === 0;
}
function deriveFernetKey(clientSecret) {
    const digest = (0, node_crypto_1.createHash)("sha256").update(Buffer.from(clientSecret, "utf8")).digest();
    return digest.subarray(0, 32);
}
function pkcs7Pad(data, blockSize = 16) {
    const rem = data.length % blockSize;
    const padLen = rem === 0 ? blockSize : blockSize - rem;
    return Buffer.concat([data, Buffer.alloc(padLen, padLen)]);
}
function pkcs7Unpad(data, blockSize = 16) {
    if (data.length === 0 || data.length % blockSize !== 0)
        return null;
    const padLen = data[data.length - 1];
    if (padLen <= 0 || padLen > blockSize)
        return null;
    for (let i = 0; i < padLen; i++) {
        if (data[data.length - 1 - i] !== padLen)
            return null;
    }
    return data.subarray(0, data.length - padLen);
}
function aesCbcEncrypt(key, iv, plaintext) {
    const cipher = require("node:crypto").createCipheriv("aes-128-cbc", key, iv);
    cipher.setAutoPadding(false);
    const padded = pkcs7Pad(plaintext, 16);
    return Buffer.concat([cipher.update(padded), cipher.final()]);
}
function aesCbcDecrypt(key, iv, ciphertext) {
    const decipher = require("node:crypto").createDecipheriv("aes-128-cbc", key, iv);
    decipher.setAutoPadding(false);
    const padded = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
    return pkcs7Unpad(padded, 16);
}
function encryptData(plaintextUtf8Json, clientSecret) {
    if (!clientSecret)
        throw new Error("client_secret不能为空");
    const key = deriveFernetKey(clientSecret);
    const signingKey = key.subarray(0, 16);
    const encryptionKey = key.subarray(16, 32);
    const version = Buffer.from([0x80]);
    const timestamp = Buffer.alloc(8);
    const ts = BigInt(Math.floor(Date.now() / 1000));
    timestamp.writeBigUInt64BE(ts, 0);
    const iv = (0, node_crypto_1.randomBytes)(16);
    const ciphertext = aesCbcEncrypt(encryptionKey, iv, Buffer.from(plaintextUtf8Json, "utf8"));
    const payload = Buffer.concat([version, timestamp, iv, ciphertext]);
    const hmac = (0, node_crypto_1.createHmac)("sha256", signingKey).update(payload).digest();
    return b64UrlEncode(Buffer.concat([payload, hmac]));
}
function decryptData(token, clientSecret) {
    if (!clientSecret)
        throw new Error("client_secret不能为空");
    const raw = b64UrlDecode(token);
    if (raw.length < 1 + 8 + 16 + 32)
        return null;
    const key = deriveFernetKey(clientSecret);
    const signingKey = key.subarray(0, 16);
    const encryptionKey = key.subarray(16, 32);
    const payload = raw.subarray(0, raw.length - 32);
    const mac = raw.subarray(raw.length - 32);
    const expected = (0, node_crypto_1.createHmac)("sha256", signingKey).update(payload).digest();
    if (!timingSafeEqual(mac, expected))
        return null;
    if (payload[0] !== 0x80)
        return null;
    const iv = payload.subarray(1 + 8, 1 + 8 + 16);
    const ciphertext = payload.subarray(1 + 8 + 16);
    const plaintext = aesCbcDecrypt(encryptionKey, iv, ciphertext);
    if (!plaintext)
        return null;
    return plaintext.toString("utf8");
}
