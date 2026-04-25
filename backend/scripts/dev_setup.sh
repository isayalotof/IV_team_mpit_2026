#!/bin/bash
# Quick dev setup for AskData backend
set -e

echo "=== AskData Dev Setup ==="

# Create venv if not exists
if [ ! -d ".venv" ]; then
    uv venv .venv
fi

# Install dependencies
echo "Installing dependencies..."
uv pip install -p .venv -e ".[dev]"

# Copy .env if not exists
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example — please edit GIGACHAT_CREDENTIALS"
fi

echo ""
echo "=== Ready! Run with: ==="
echo "  source .venv/bin/activate && PYTHONPATH=src uvicorn askdata.main:app --reload --port 8000"
echo ""
echo "Or set LLM_PROVIDER=local to use local Qwen model"
