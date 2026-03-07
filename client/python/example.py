"""
授权客户端使用示例

缓存策略：
- 始终向服务端发送请求并更新本地缓存
- 缓存有效期7天
- 网络失败时，在有效期内使用缓存作为后备
"""
from py_auth_client import AuthClient, AuthorizationError

# 初始化客户端
client = AuthClient(
    server_url="http://localhost:8000",
    software_name="我的软件",
    client_secret="aB3cD5eF7gH9iJ1kL3mN5oP7qR9sT1uV3wX5yZ7aB9cD1eF3gH5iJ7kL9mN1oP3qR5sT7uV9wX1yZ3",
    # debug=True  # 开启调试日志，便于排查网络/缓存状态
)

# 检查授权
try:
    client.require_authorization()
    print("✅ 设备已授权")
except AuthorizationError as e:
    print(f"❌ 授权失败: {e}")
    exit(1)

print(client.get_authorization_info())
# 你的软件代码...
