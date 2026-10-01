#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  if [ -d .venv ]; then
    echo "检测到 .venv 已损坏（比如从别的机器拷贝过来的），重新创建……"
    rm -rf .venv
  fi
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
# 起服务前先过联调准备检查：端口、数据层连通、示例数据核对，缺哪一步会打印出来。
.venv/bin/python -m app.preflight
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
