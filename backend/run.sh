#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

# 起服务前的固定动作：
# 1) 端口占用检查（被占用直接打印缺哪一步并退出）
# 2) 数据库连通检查（自动补齐数据库目录，其余问题给出处理办法）
# 3) 幂等导入固定示例工单（问题类型、转办部门、工单均取自同一份示例数据）
# 4) 自动核对工单数量，核对不通过不算准备好，拒绝带着空表起服务
.venv/bin/python -m app.cli prepare

exec .venv/bin/uvicorn app.main:app --host "${APP_HOST:-127.0.0.1}" --port "${APP_PORT:-8000}"
