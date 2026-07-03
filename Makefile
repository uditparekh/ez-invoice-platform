PYTHON ?= python3
API_PORT ?= 8000
WEB_PORT ?= 3000
STREAMLIT_PORT ?= 8506

NODE_PATH := $(HOME)/.nvm/versions/node/v26.4.0/bin:$(HOME)/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$(PATH)
PNPM := PATH="$(NODE_PATH)" pnpm

DEMO_EMAIL ?= udit@example.com
DEMO_PASSWORD ?= local-demo-password-123
DEMO_ORG ?= SiftEntry Demo Workspace

.PHONY: help install-python install-web api web streamlit bootstrap worker test-postgres test build-web check status clean-cache

help:
	@echo "SiftEntry local commands"
	@echo ""
	@echo "  make install-python   Install Python dependencies"
	@echo "  make install-web      Install Next.js dependencies"
	@echo "  make api              Run FastAPI on http://127.0.0.1:$(API_PORT)"
	@echo "  make web              Run Next.js on http://127.0.0.1:$(WEB_PORT)"
	@echo "  make streamlit        Run Streamlit demo on http://127.0.0.1:$(STREAMLIT_PORT)"
	@echo "  make bootstrap        Create local owner if the database is empty"
	@echo "  make test             Run Python tests"
	@echo "  make build-web        Build Next.js app"
	@echo "  make check            Run Python tests and Next.js build"
	@echo "  make status           Show git and project file status"

install-python:
	$(PYTHON) -m pip install -r siftentry_app/requirements.txt

install-web:
	cd apps/web && $(PNPM) install

api:
	EZ_API_ENVIRONMENT=development \
	EZ_API_ALLOW_DEV_BOOTSTRAP=true \
	EZ_API_JWT_SECRET="local-development-secret-change-before-hosting" \
	PYTHONDONTWRITEBYTECODE=1 \
	$(PYTHON) -m uvicorn siftentry_app.backend.main:app --reload --host 127.0.0.1 --port $(API_PORT)

web:
	cd apps/web && PATH="$(NODE_PATH)" EZ_WEB_API_BASE_URL=http://127.0.0.1:$(API_PORT) NEXT_PUBLIC_APP_NAME=SiftEntry $(PNPM) dev --hostname 127.0.0.1 --port $(WEB_PORT)

streamlit:
	SIFTENTRY_BACKEND=api \
	EZ_API_BASE_URL=http://127.0.0.1:$(API_PORT) \
	EZ_API_EMAIL="$(DEMO_EMAIL)" \
	EZ_API_PASSWORD="$(DEMO_PASSWORD)" \
	$(PYTHON) -m streamlit run siftentry_app/app.py --server.port $(STREAMLIT_PORT)

bootstrap:
	@curl -sS -X POST http://127.0.0.1:$(API_PORT)/api/v1/auth/bootstrap \
		-H "Content-Type: application/json" \
		-d '{"email":"$(DEMO_EMAIL)","password":"$(DEMO_PASSWORD)","full_name":"Demo Owner","organization_name":"$(DEMO_ORG)","legal_names":["$(DEMO_ORG)"],"default_currency":"USD"}' \
		| $(PYTHON) -m json.tool

worker:
	$(PYTHON) -m siftentry_app.backend.worker

test-postgres:
	SIFTENTRY_TEST_DATABASE_URL=postgresql://root@/postgres $(PYTHON) -m pytest tests/ -q

test:
	$(PYTHON) -m pytest -q

build-web:
	cd apps/web && $(PNPM) run build

check: test build-web

status:
	@git status --short
	@echo ""
	@echo "Python files:"
	@find . -path './.git' -prune -o -path './apps/web/node_modules' -prune -o -path './siftentry_app/.venv' -prune -o -name '*.py' -print | wc -l
	@echo "Next.js TypeScript files:"
	@find apps/web/src -type f \( -name '*.ts' -o -name '*.tsx' \) | wc -l

clean-cache:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	rm -rf .pytest_cache
