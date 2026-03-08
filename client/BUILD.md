# 构建和发布 py-auth-client

## 构建

```bash
# 安装构建工具
pip install build

# 进入 client/python 目录并构建
cd client/python
python -m build
```

构建完成后，会在 `client/python/dist/` 目录下生成分发包文件。

## 部署到私有仓库

构建完成后，将 `client/python/dist/` 目录下的文件上传到 `www.geekery.cn/pip/` 目录。

### 目录结构

需要创建以下目录结构：

```text
www.geekery.cn/pip/
├── py_auth_client-0.1.3-py3-none-any.whl
├── py_auth_client-0.1.3.tar.gz
└── simple/
    └── py-auth-client/
        └── index.html
```

`simple/py-auth-client/index.html` 内容示例：

```html
<!DOCTYPE html>
<html>
<head><title>Links for py-auth-client</title></head>
<body>
<h1>Links for py-auth-client</h1>
<a href="../../py_auth_client-0.1.3-py3-none-any.whl">py_auth_client-0.1.3-py3-none-any.whl</a><br/>
<a href="../../py_auth_client-0.1.3.tar.gz">py_auth_client-0.1.3.tar.gz</a><br/>
</body>
</html>
```

### 注意事项

1. 版本管理：保留历史版本文件，便于回滚
2. 索引：静态目录即可，pip 可通过 `simple/` 路径安装

## 从私有仓库安装

```bash
# 安装最新
pip install py-auth-client --extra-index-url https://www.geekery.cn/pip/simple/

# 安装指定版本
pip install py-auth-client==0.1.3 --extra-index-url https://www.geekery.cn/pip/simple/
```
