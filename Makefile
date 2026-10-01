.PHONY: install preflight seed backend frontend

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

preflight:
	cd backend && .venv/bin/python -m app.preflight

seed:
	cd backend && .venv/bin/python -m app.seed_import

backend:
	cd backend && ./run.sh

frontend:
	cd frontend && npm run dev
