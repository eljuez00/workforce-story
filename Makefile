.PHONY: data build test evals evals-live serve all

data:        ## generate the fictional company (data/hr.db, data/csv/)
	python -m generator.generate

build:       ## rebuild the dashboard data from the shared metric layer
	python -m metrics.build

test:        ## data invariants, guardrails, agent loop
	python -m pytest -q

evals:       ## tools vs independent SQL ground truth (no API key)
	python -m evals.run_evals

evals-live:  ## agent answers end to end (needs ANTHROPIC_API_KEY)
	python -m evals.run_evals --live

serve:       ## open http://localhost:8000
	python -m http.server 8000 -d app

all: data test evals build
