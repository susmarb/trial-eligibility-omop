# Everything a new clone needs, in dependency order.
PY ?= python3
CDM_URL = https://github.com/OHDSI/EunomiaDatasets/raw/main/datasets/GiBleed/GiBleed_5.3.zip
CACHE ?= .cache

.PHONY: help install test lint tree cdm cohort corpus strictness validate config clean

help:            ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:         ## install the package in editable mode
	$(PY) -m pip install -e ".[dev]"

test:            ## run the test suite (no network, no model, no data)
	PYTHONPATH=src $(PY) -m unittest discover -s tests -v

lint:            ## static checks
	$(PY) -m ruff check src tests

config:          ## print every resolved setting
	PYTHONPATH=src $(PY) -m trialcriteria.cli config

tree:            ## parse one trial and print its logic tree (network, 1 request)
	PYTHONPATH=src $(PY) -m trialcriteria.cli show NCT03432533

cdm:             ## download the OHDSI Eunomia GiBleed reference CDM (~15 MB)
	@mkdir -p $(CACHE)/cdm
	@test -d $(CACHE)/cdm/GiBleed_5.3 || ( \
	  curl -fsSL $(CDM_URL) -o $(CACHE)/cdm/GiBleed_5.3.zip && \
	  unzip -q -o $(CACHE)/cdm/GiBleed_5.3.zip -d $(CACHE)/cdm && \
	  rm -f $(CACHE)/cdm/GiBleed_5.3.zip )
	@ls $(CACHE)/cdm/GiBleed_5.3 | head -5

cohort: cdm      ## load the CDM into SQLite and execute the demo cohort
	PYTHONPATH=src $(PY) -m trialcriteria.cli cohort --build

corpus:          ## fetch the 2008-2024 oncology corpus (slow, ~90 MB)
	PYTHONPATH=src $(PY) -m trialcriteria.cli fetch-corpus --per-year 2000

strictness:      ## classify the corpus (needs the local classifier)
	PYTHONPATH=src $(PY) -m trialcriteria.cli strictness

validate:        ## draw a fresh hand-validation sample
	PYTHONPATH=src $(PY) -m trialcriteria.cli validate --n 90

clean:           ## remove build artefacts, keep the cache
	rm -rf build dist src/*.egg-info .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
