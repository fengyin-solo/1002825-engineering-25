.PHONY: install backend frontend prepare preflight recompute status

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

# 联调准备固定动作：端口/数据库预检 → 导入固定示例工单 → 自动核对工单数量
prepare:
	cd backend && .venv/bin/python -m app.cli prepare

# 只做起服务前预检（端口占用、数据库连通），不改动数据
preflight:
	cd backend && .venv/bin/python -m app.cli preflight

# 工单数量核对口径变更后，对存量数据重算一遍
recompute:
	cd backend && .venv/bin/python -m app.cli recompute

# 查看当前联调准备状态（工单数量是否与示例数据一致）
status:
	cd backend && .venv/bin/python -m app.cli status

backend:
	cd backend && ./run.sh

frontend:
	cd frontend && npm run dev
