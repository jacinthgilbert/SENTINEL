# The Sentinel — task runner.
#
# Prefer this over ./prep/*.sh: macOS 15 tags files written by sandboxed
# processes with com.apple.provenance, which makes direct ./script execution
# fail with "Operation not permitted". Invoking `bash <file>` reads the script
# instead of exec()ing it, so it always works.

SHELL := /bin/bash
PY    ?= python3
VENV  := .venv
BIN   := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help setup prep prep-synthetic train test api web db load fresh-terrain clean stop demo check sms-test wa-test tg-list tg-test

help:  ## show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk -F':.*?## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## create .venv and install the geo-prep stack (run once)
	@command -v $(PY) >/dev/null || { echo "no $(PY) on PATH"; exit 1; }
	@[ -d $(VENV) ] || $(PY) -m venv $(VENV)
	@$(BIN)/pip install --quiet --upgrade pip
	@$(BIN)/pip install --timeout 120 --retries 5 -r prep/requirements.txt
	@$(BIN)/pip install --quiet --timeout 120 --retries 5 -r api/requirements.txt
	@echo "ready — next: make prep"

prep: ## fetch DEM + population, build HAND, roads, zones
	@[ -f .env ] || { echo "no .env — cp .env.example .env and add your key"; exit 1; }
	@[ -x $(BIN)/python ] || { echo "run: make setup"; exit 1; }
	@set -a; source .env; set +a; $(BIN)/python prep/run.py

prep-synthetic: ## build everything on stand-in terrain (no API key needed)
	@[ -x $(BIN)/python ] || { echo "run: make setup"; exit 1; }
	@cd prep && ../$(BIN)/python make_synthetic_dem.py \
	  && ../$(BIN)/python make_hand.py \
	  && ../$(BIN)/python fetch_osm.py \
	  && ../$(BIN)/python make_zones.py

fresh-terrain: ## drop synthetic terrain so `make prep` rebuilds from the real DEM
	@rm -f data/dem.tif data/hand.tif data/zones.geojson data/dem.SYNTHETIC
	@echo "terrain cleared — now: make prep"

train: ## train the nowcast models (writes data/nowcast/, ~2 min)
	@$(BIN)/python prep/train_nowcast.py

test: ## verify the D8/HAND implementation against known-answer terrain
	@$(BIN)/python prep/tests/test_hydrology.py

api: ## run the API on :8000
	@cd api && DATA_DIR=../data ../$(BIN)/uvicorn main:app --port 8000 --reload

web: ## run the web app on :3000
	@cd web && npm install --no-audit --no-fund && npm run dev

demo: ## reset to a known-good demo state (calm, scenario, 10x)
	@bash scripts/demo.sh

sms-test: ## does SMS reach a handset?  make sms-test TO=+91XXXXXXXXXX [FREE=1]
	@FREE=$(FREE) bash scripts/sms-test.sh $(TO)

wa-test: ## does WhatsApp reach a handset?  make wa-test TO=+91XXXXXXXXXX
	@bash scripts/wa-test.sh $(TO)

tg-list: ## who has opted in to the Telegram bot
	@bash scripts/tg-test.sh

tg-test: ## send a Telegram test to everyone opted in
	@bash scripts/tg-test.sh send

check: ## pre-demo smoke test: every endpoint the script touches
	@bash scripts/check.sh

stop: ## free :8000 and :3000 (kills stray dev servers)
	@-pkill -f "uvicorn main:app" 2>/dev/null || true
	@-pkill -f "next-server" 2>/dev/null || true
	@-lsof -ti:8000 -ti:3000 2>/dev/null | xargs -r kill 2>/dev/null || true
	@echo "ports freed"

db: ## start postgres+postgis only
	@docker compose up -d db

load: ## load the precomputed layers into postgis
	@set -a; source .env; set +a; $(BIN)/python prep/load.py

clean: ## remove caches and build artifacts (keeps data/)
	@rm -rf prep/cache prep/__pycache__ prep/tests/__pycache__ api/__pycache__ \
	        web/.next web/tsconfig.tsbuildinfo
	@echo cleaned
