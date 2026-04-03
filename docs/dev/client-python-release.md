# Python 客户端构建与发布

本文面向维护 `client/python` 包的开发者。

## 本地构建

```bash
pip install build
cd client/python
python -m build
```

构建产物输出到 `client/python/dist/`。

## 发布说明

- 包名：`py-auth-client`
- 版本号以 `client/python/pyproject.toml` 为准
- 如上传到私有 PyPI 静态源，应按 PEP 503 布局放置 wheel 和 sdist

安装指定版本示例：

```bash
pip install py-auth-client==<版本> --extra-index-url https://www.geekery.cn/pip/simple/
```
