import { createHash, createHmac, randomBytes } from "node:crypto";

function b64UrlEncode(buf: Buffer): string {
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function b64UrlDecode(s: string): Buffer {
  const padded = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
  return Buffer.from(padded, "base64");
}

function timingSafeEqual(a: Buffer, b: Buffer): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i]! ^ b[i]!;
  return diff === 0;
}

function deriveFernetKey(clientSecret: string): Buffer {
  const digest = createHash("sha256").update(Buffer.from(clientSecret, "utf8")).digest();
  return digest.subarray(0, 32);
}

function pkcs7Pad(data: Buffer, blockSize = 16): Buffer {
  const padLen = blockSize - (data.length % blockSize || blockSize);
  return Buffer.concat([data, Buffer.alloc(padLen, padLen)]);
}

function pkcs7Unpad(data: Buffer, blockSize = 16): Buffer | null {
  if (data.length === 0 || data.length % blockSize !== 0) return null;
  const padLen = data[data.length - 1]!;
  if (padLen <= 0 || padLen > blockSize) return null;
  for (let i = 0; i < padLen; i++) {
    if (data[data.length - 1 - i] !== padLen) return null;
  }
  return data.subarray(0, data.length - padLen);
}

function aesCbcEncrypt(key: Buffer, iv: Buffer, plaintext: Buffer): Buffer {
  const cipher = require("node:crypto").createCipheriv("aes-128-cbc", key, iv);
  cipher.setAutoPadding(false);
  const padded = pkcs7Pad(plaintext, 16);
  return Buffer.concat([cipher.update(padded), cipher.final()]);
}

function aesCbcDecrypt(key: Buffer, iv: Buffer, ciphertext: Buffer): Buffer | null {
  const decipher = require("node:crypto").createDecipheriv("aes-128-cbc", key, iv);
  decipher.setAutoPadding(false);
  const padded = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
  return pkcs7Unpad(padded, 16);
}

export function encryptData(plaintextUtf8Json: string, clientSecret: string): string {
  if (!clientSecret) throw new Error("client_secret不能为空");

  const key = deriveFernetKey(clientSecret);
  const signingKey = key.subarray(0, 16);
  const encryptionKey = key.subarray(16, 32);

  const version = Buffer.from([0x80]);
  const timestamp = Buffer.alloc(8);
  const ts = BigInt(Math.floor(Date.now() / 1000));
  timestamp.writeBigUInt64BE(ts, 0);

  const iv = randomBytes(16);
  const ciphertext = aesCbcEncrypt(encryptionKey, iv, Buffer.from(plaintextUtf8Json, "utf8"));

  const payload = Buffer.concat([version, timestamp, iv, ciphertext]);
  const hmac = createHmac("sha256", signingKey).update(payload).digest();

  return b64UrlEncode(Buffer.concat([payload, hmac]));
}

export function decryptData(token: string, clientSecret: string): string | null {
  if (!clientSecret) throw new Error("client_secret不能为空");

  const raw = b64UrlDecode(token);
  if (raw.length < 1 + 8 + 16 + 32) return null;

  const key = deriveFernetKey(clientSecret);
  const signingKey = key.subarray(0, 16);
  const encryptionKey = key.subarray(16, 32);

  const payload = raw.subarray(0, raw.length - 32);
  const mac = raw.subarray(raw.length - 32);

  const expected = createHmac("sha256", signingKey).update(payload).digest();
  if (!timingSafeEqual(mac, expected)) return null;

  if (payload[0] !== 0x80) return null;

  const iv = payload.subarray(1 + 8, 1 + 8 + 16);
  const ciphertext = payload.subarray(1 + 8 + 16);

  const plaintext = aesCbcDecrypt(encryptionKey, iv, ciphertext);
  if (!plaintext) return null;

  return plaintext.toString("utf8");
}
