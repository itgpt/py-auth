import fs from "node:fs";
import path from "node:path";

import { AuthClient, AuthorizationError } from "./src";

function readRepoEnv(): string {
  let dir = __dirname;
  for (let i = 0; i < 8; i++) {
    const p = path.join(dir, ".env");
    if (fs.existsSync(p)) {
      return fs.readFileSync(p, "utf-8");
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      break;
    }
    dir = parent;
  }
  throw new Error("未找到仓库根目录下的 .env（已从 __dirname 向上查找）");
}

async function main() {
  const debug = true;
  let clientSecret = "";
  const text = readRepoEnv();
  for (const line of text.split("\n")) {
    const s = line.trim();
    if (!s || s.startsWith("#")) continue;
    const i = s.indexOf("=");
    if (i < 0) continue;
    if (s.slice(0, i).trim() !== "CLIENT_SECRET") continue;
    const raw = s.slice(i + 1).trim();
    clientSecret = raw.replace(/^["']|["']$/g, "");
    break;
  }

  const client = new AuthClient({
    serverUrl: "http://localhost:8000",
    softwareName: "软件ts示例",
    softwareVersion: "0.0.1",
    clientSecret,
    debug,
  });

  try {
    await client.requireAuthorization();
    
    console.log("✅ 设备已授权");
  } catch (e) {
    if (e instanceof AuthorizationError) {
      
      console.error(`❌ 授权失败: ${e.message}`);
      process.exit(1);
    }
    throw e;
  }

  const info = await client.getAuthorizationInfo();
  if (!debug) {
    
    console.log(info);
  }
}

main().catch((e) => {
  
  console.error(e);
  process.exit(1);
});
