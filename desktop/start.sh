#!/bin/bash
# ============================================================
# 🐼 情绪出口 · 团团 — 一键启动脚本
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DESKTOP_DIR="$SCRIPT_DIR"

echo "🐼 情绪出口 · 团团 v2.0"
echo "========================"
echo ""

# ---------- 检查依赖 ----------
echo "📦 检查环境..."

# Python
if command -v python3 &> /dev/null; then
    echo "  ✅ Python $(python3 --version | cut -d' ' -f2)"
else
    echo "  ❌ 需要 Python 3.8+"
    exit 1
fi

# Node.js
if command -v node &> /dev/null; then
    echo "  ✅ Node.js $(node --version | cut -d'v' -f2)"
else
    echo "  ❌ 需要 Node.js 18+"
    exit 1
fi

# ---------- 安装依赖 ----------
echo ""
echo "📦 安装依赖..."

# Python 依赖
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "  创建 Python 虚拟环境..."
    cd "$PROJECT_DIR" && python3 -m venv .venv
fi

source "$PROJECT_DIR/.venv/bin/activate" 2>/dev/null || true

# 安装必要 Python 包
echo "  安装 Python 依赖..."
pip install -q fastapi uvicorn langchain-openai langgraph langchain-coze coze-calling 2>/dev/null || true

# Electron 依赖
echo "  安装 Electron..."
cd "$DESKTOP_DIR"
if [ ! -d "node_modules" ]; then
    npm install --loglevel=error 2>&1 | tail -1
fi

echo ""
echo "🎉 一切就绪！正在启动..."
echo ""

# ---------- 启动 ----------
cd "$DESKTOP_DIR"
npm start