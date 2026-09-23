.PHONY: setup run app test profile clean

PY ?= python

setup:
	$(PY) -m pip install -r requirements.txt

run:
	$(PY) run.py

profile:
	$(PY) -m moneygraph.profile --data data --out outputs

app:
	streamlit run app/app.py

test:
	$(PY) -m pytest -q

clean:
	rm -rf outputs/*.csv outputs/*.parquet .pytest_cache
