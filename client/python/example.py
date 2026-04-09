import json
from pathlib import Path
from typing import Optional

from py_auth_client import AuthClient, AuthorizationError


def _client_secret() -> Optional[str]:
    text = (Path(__file__).resolve().parent.parent.parent / ".env").read_text(
        encoding="utf-8"
    )
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        if key.strip() == "CLIENT_SECRET":
            return val.strip().strip('"').strip("'") or None
    return None


def main() -> None:
    client = AuthClient(
        server_url="http://localhost:8000",
        software_name="软件python示例",
        software_version="0.0.1",
        client_secret=_client_secret(),
        debug=True,
    )
    try:
        client.require_authorization()
    except AuthorizationError as e:
        print(f"授权失败: {e}")
    info = client.get_authorization_info()
    if not client.debug:
        print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
