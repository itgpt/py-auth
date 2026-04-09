"""
健康检查端点测试
"""

from datetime import datetime

import pytest


def test_health_endpoint(client):
    """测试健康检查端点"""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == "py-auth"
    assert data["version"] == "1.0.0"

    # 检查时间戳格式
    try:
        datetime.fromisoformat(data["timestamp"])
    except ValueError:
        pytest.fail("时间戳格式不正确")


def test_root_endpoint_no_frontend(client):
    """测试根端点（无前端构建）"""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()

    assert "message" in data
    assert "docs" in data
    assert "api_endpoints" in data

    # 检查 API 端点列表
    endpoints = data["api_endpoints"]
    assert "/api/auth" in endpoints
    assert "/api/admin" in endpoints
    assert "/api/user" in endpoints
    assert "/ws" in endpoints


def test_docs_endpoints(client):
    """测试文档端点"""
    # 测试 OpenAPI 文档
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    # 测试 ReDoc 文档
    response = client.get("/redoc")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    # 测试 OpenAPI JSON
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data
    assert "paths" in data
