import json
import sys
from pathlib import Path
from typing import List, Optional

from py_auth_client import (
    AuthClient,
    AuthorizationError,
    shutdown_auth_background_executor,
)


def _client_secret() -> Optional[str]:
    text = Path(f"{Path(__file__).resolve().parent.parent.parent}/.env").read_text(encoding="utf-8")
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        if key.strip() == "CLIENT_SECRET":
            return val.strip().strip('"').strip("'") or None
    return None


def main() -> None:
    secret = _client_secret()
    if not secret:
        print("缺少 CLIENT_SECRET", file=sys.stderr)
        sys.exit(1)

    clients: List[AuthClient] = [
        AuthClient(
            server_url="http://localhost:8000",
            software_name="软件python示例",
            software_version="0.0.1",
            client_secret=secret,
            debug=True,
        ),
    ]

    print("（模拟）界面/初始化已继续，后台刷新授权…")

    def on_refresh(r: dict) -> None:
        if r.get("success") and r.get("authorized"):
            print("后台刷新：仍授权")
        else:
            print(f"后台刷新：{r.get('message', '失败')}（可在此禁用功能）", file=sys.stderr)

    futures = []
    for c in clients:
        soft, fut = c.start_background_refresh(on_done=on_refresh)
        futures.append((c, soft, fut))
        if soft:
            print(f"产品 {c.software_name}: 可先依据本地快照启动")
        else:
            print(f"产品 {c.software_name}: 无有效本地快照，需等待本次检查结果")

    for _c, soft, fut in futures:
        try:
            r = fut.result(timeout=120)
        except Exception as e:
            print(f"检查异常: {e}", file=sys.stderr)
            sys.exit(1)
        if not soft and (not r.get("success") or not r.get("authorized")):
            print(f"未授权: {r.get('message')}", file=sys.stderr)
            sys.exit(1)
        if soft and (not r.get("success") or not r.get("authorized")):
            print(f"警告：本地曾放行但刷新失败: {r.get('message')}", file=sys.stderr)

    print("✅ 全部产品授权有效（含后台刷新结果）")
    c0 = clients[0]
    info = c0.get_authorization_info()
    if not c0.debug:
        print(json.dumps(info, ensure_ascii=False, indent=2))

    shutdown_auth_background_executor(wait=True)


if __name__ == "__main__":
    try:
        main()
    except AuthorizationError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
