import { AuthClient, AuthorizationError } from "./src";

async function main() {
  const client = new AuthClient({
    serverUrl: "https://auth.certauth.cn/",
    softwareName: "我的软件",
    clientSecret: "your-client-secret-key-change-in-production",
    // debug: true,
  });

  try {
    await client.requireAuthorization();
    // eslint-disable-next-line no-console
    console.log("✅ 设备已授权");
  } catch (e) {
    if (e instanceof AuthorizationError) {
      // eslint-disable-next-line no-console
      console.error(`❌ 授权失败: ${e.message}`);
      process.exit(1);
    }
    throw e;
  }

  // eslint-disable-next-line no-console
  console.log(await client.getAuthorizationInfo());
}

main().catch((e) => {
  // eslint-disable-next-line no-console
  console.error(e);
  process.exit(1);
});
