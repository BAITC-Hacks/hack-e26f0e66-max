.PHONY: run offline existing setup pipeline app profile test clean

# The one command. Installs, runs the pipeline, verifies the exports, reports
# time/tokens/spend, then opens the viewer with a public share link.
run:
	./agent_run.sh

offline:                  ## same, with no model calls at all
	./agent_run.sh --offline

existing:                 ## skip the pipeline, open the viewer on the last run
	./agent_run.sh --use-existing

PY ?= .venv/bin/python

setup:
	$(PY) -m pip install -r requirements.txt
	@test -f .env || cp .env.example .env

pipeline:                 ## pipeline only: data/ -> output_files/
	$(PY) run.py

recalibrate:              ## re-run the calibrator agent
	$(PY) run.py --recalibrate

profile:                  ## data profile report only
	$(PY) run.py --only-profile

app:                      ## viewer only; reads output_files/
	$(PY) app/app.py --share

test:
	$(PY) -m pytest -q

clean:
	rm -rf output_files/*.csv output_files/*.parquet output_files/*.json \
	       output_files/*.md .pytest_cache .run_logs
