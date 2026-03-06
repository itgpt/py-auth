# py-auth-client

TypeScript/Node.js client for **py-auth**. Compatible with the Python and Go clients in this repository.

## Install

```bash
npm i py-auth-client
```

## Usage

```ts
import { AuthClient, AuthorizationError } from "py-auth-client";

const client = new AuthClient({
  serverUrl: "http://localhost:8000",
  softwareName: "我的软件",
  clientSecret: process.env.CLIENT_SECRET!,
  // debug: true,
});

try {
  await client.requireAuthorization();
  console.log("authorized");
} catch (e) {
  if (e instanceof AuthorizationError) {
    console.error(e.message);
    process.exit(1);
  }
  throw e;
}
```

## API

- `new AuthClient(config)`
- `client.checkAuthorization()`
- `client.requireAuthorization()`
- `client.getAuthorizationInfo()`
- `client.clearCache()`

## Notes

- Requires `clientSecret` or environment variable `CLIENT_SECRET`.
- Uses Fernet-compatible encryption derived from `CLIENT_SECRET`.
- Uses an obfuscated local cache file with a 7-day validity window.
