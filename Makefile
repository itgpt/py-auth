.PHONY: help install dev-install test lint format check pre-commit run docker-build docker-run clean

# 默认目标
help:
	@echo "可用命令:"
	@echo "  make install        - 安装生产依赖"
	@echo "  make dev-install    - 安装开发依赖"
	@echo "  make test           - 运行测试"
	@echo "  make lint           - 运行代码检查"
	@echo "  make format         - 格式化代码"
	@echo "  make check          - 运行所有检查（格式化 + 代码检查）"
	@echo "  make pre-commit     - 安装 pre-commit 钩子"
	@echo "  make run            - 启动开发服务器"
	@echo "  make docker-build   - 构建 Docker 镜像"
	@echo "  make docker-run     - 运行 Docker 容器"
	@echo "  make clean          - 清理临时文件"

# 安装生产依赖
install:
	pip install -e .

# 安装开发依赖
dev-install:
	pip install -e ".[dev]"
	pre-commit install

# 运行测试
test:
	pytest -v --cov=app --cov=client --cov-report=term-missing --cov-report=html

# 代码检查
lint:
	ruff check .
	mypy app client

# 格式化代码
format:
	black .
	ruff check --fix .
	isort .

# 运行所有检查
check: format lint

# 安装 pre-commit 钩子
pre-commit:
	pre-commit install
	pre-commit run --all-files

# 启动开发服务器
run:
	uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 构建 Docker 镜像
docker-build:
	docker build -t py-auth:latest .

# 运行 Docker 容器
docker-run:
	docker run -p 8000:8000 --env-file .env --name py-auth py-auth:latest

# 清理临时文件
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf .mypy_cache/
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/