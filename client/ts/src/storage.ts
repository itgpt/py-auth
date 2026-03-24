import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export function getClientStorageRoot(): string {
  if (process.platform === "win32") {
    const pd = process.env.ProgramData || "C:\\ProgramData";
    const p = path.join(pd, ".RuntimeRepository");
    fs.mkdirSync(p, { recursive: true });
    return p;
  }
  const p = path.join(os.tmpdir(), ".runtime-repository");
  fs.mkdirSync(p, { recursive: true });
  return p;
}
