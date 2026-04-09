#!/bin/bash

# 代码质量检查脚本
# 用法: ./scripts/check-code-quality.sh [--fix]

set -e

FIX=false

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --fix)
            FIX=true
            shift
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

echo "🔍 开始代码质量检查..."

# 检查 Python 版本
echo "📦 检查 Python 版本..."
python --version

# 检查依赖是否安装
echo "📦 检查依赖..."
pip list | grep -E "(black|ruff|mypy|isort)" || {
    echo "❌ 缺少代码质量工具，请运行: pip install black ruff mypy isort"
    exit 1
}

# 运行代码格式化
echo "🎨 运行代码格式化..."
if [ "$FIX" = true ]; then
    echo "  运行 black..."
    black .
    echo "  运行 isort..."
    isort .
    echo "  运行 ruff --fix..."
    ruff check --fix .
else
    echo "  检查 black 格式..."
    black --check .
    echo "  检查 isort 排序..."
    isort --check-only .
    echo "  检查 ruff..."
    ruff check .
fi

# 运行类型检查
echo "📝 运行类型检查..."
mypy app client

# 检查导入顺序
echo "📚 检查导入顺序..."
python -c "
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 检查所有 Python 文件
for root, dirs, files in os.walk('.'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                in_import = False
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith(('import ', 'from ')):
                        in_import = True
                    elif in_import and stripped and not stripped.startswith(('#', 'import ', 'from ')):
                        print(f'⚠️  文件 {filepath}:{i+1} 导入语句后有空行')
                        in_import = False
"

# 检查文件编码
echo "🔤 检查文件编码..."
find . -name "*.py" -type f -exec file {} \; | grep -v "UTF-8" && {
    echo "❌ 发现非 UTF-8 编码文件"
    exit 1
}

# 检查行尾
echo "↩️  检查行尾..."
if [[ "$OSTYPE" == "darwin"* ]] || [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if grep -r $'\r' --include="*.py" .; then
        echo "❌ 发现 Windows 行尾 (CRLF)"
        if [ "$FIX" = true ]; then
            echo "  转换为 Unix 行尾..."
            find . -name "*.py" -type f -exec dos2unix {} \;
        else
            exit 1
        fi
    fi
fi

# 检查 shebang
echo "🐍 检查 shebang..."
for file in $(find . -name "*.py" -type f); do
    if [[ $(head -c 2 "$file") == "#!" ]]; then
        if ! head -n 1 "$file" | grep -q "python"; then
            echo "⚠️  文件 $file 有非 Python shebang"
        fi
    fi
done

echo "✅ 代码质量检查完成！"

if [ "$FIX" = false ]; then
    echo ""
    echo "💡 提示: 使用 --fix 参数自动修复问题:"
    echo "  ./scripts/check-code-quality.sh --fix"
fi