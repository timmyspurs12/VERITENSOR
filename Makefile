.PHONY: help install dev-backend dev-frontend seed test lint docker clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install:            ## install python + node dependencies (incl. bittensor SDK)
	pip install -r requirements-dev.txt
	cd frontend && npm install

dev-backend:        ## run the FastAPI backend with autoreload
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:       ## run the Next.js dev server
	cd frontend && npm run dev

seed:               ## run a standalone simulation and print the leaderboard
	python -m scripts.run_simulation --miners 25 --validators 3 --tasks 100

test:               ## run the python test suite
	pytest -q

test-verbose:       ## run tests with names
	pytest -v

preflight:          ## read-only bittensor prerequisite check
	python -m scripts.preflight

neurons-setup:      ## create UNFUNDED local dev wallets (10 miners, 3 validators)
	./scripts/setup_testnet.sh

neurons-up:         ## start 10 miner neurons + 3 validator neurons locally
	./scripts/start_miners.sh && ./scripts/start_validators.sh

neurons-down:       ## stop every neuron started by the scripts
	./scripts/stop_all.sh

docker:             ## build and start the whole stack
	docker compose up --build

docker-neurons:     ## build and start the standalone neuron profile
	docker compose --profile neurons up --build

clean:
	rm -f veritensor.db veritensor_test.db
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
