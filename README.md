# Trial eligibility criteria and OMOP

This repository contains scripts and related explanations for parsing clinical
trial eligibility criteria, mapping clinical terms to OMOP concepts, and
exploring how these criteria can be evaluated against a healthcare database.
It also contains an analysis of exclusion wording in oncology trials.

The different parts of the workflow are described below, with links to the
scripts used in each part. The parsing and mapping commands can be run on trial
records from ClinicalTrials.gov. The cohort demonstration runs separately on a
synthetic reference dataset; it does not yet execute the parsed criteria of an
arbitrary trial.

## Getting started

Python 3.9 or newer is required for the core scripts. Parsing, database loading,
cohort execution and the test suite use the Python standard library. The local
classifier is an optional component with additional requirements described below.

From the repository directory, create an environment and install the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

The development installation includes Ruff, which checks the code for common
errors and formatting issues. You can then run the tests and demonstrations:

```bash
make test        # run the 34 tests
make lint        # run Ruff
make tree        # download one trial record and display its criteria tree
make cohort      # download the reference dataset and run the cohort example
```

The tests need no network connection, classifier or downloaded data. The first
runs of `make tree` and `make cohort` need internet access. The cohort example
uses synthetic records and does not require a database server or an API key.

## Part 1: [Retrieval of clinical trial records](src/trialcriteria/ctgov.py)

Trial records are retrieved from the ClinicalTrials.gov API and cached locally.
An individual trial can be selected by its NCT identifier. For the oncology
analysis, records are collected by year to form a corpus covering 2008–2024.
The full corpus is about 90 MB and is not included in the repository.

* [ctgov.py](src/trialcriteria/ctgov.py) retrieves individual trial records.
* [corpus.py](src/trialcriteria/corpus.py) builds the year-stratified corpus.

```bash
trialcriteria show NCT03432533
trialcriteria fetch-corpus
```

## Part 2: [Parsing of eligibility criteria into a logic tree](src/trialcriteria/tree.py)

In this step, inclusion and exclusion criteria are separated and nested groups
are retained. The parser uses indentation and phrases such as “any of the
following” and “at least two of the following” to identify these groups.
For example:

```text
- At least 2 of the following risk factors:
  - Age over 70
  - Current smoker
  - Parental history of fracture
```

This is one requirement satisfied by any two of the three factors. Treating the
three lines as independent mandatory requirements would exclude someone who
satisfies two of them.

The tree evaluator combines supplied values using true, false and unknown.
Missing information remains unknown where it could change the result. The
explanation function reports the value of each rule and group. These functions
are tested separately from the database demonstration in Part 4.

* [tree.py](src/trialcriteria/tree.py) contains the parser and evaluator.
* [test_tree.py](tests/test_tree.py) tests parsing and nested groups.
* [test_kleene.py](tests/test_kleene.py) tests three-valued evaluation.

## Part 3: [Mapping clinical terms to OMOP concepts](src/trialcriteria/omop.py)

OMOP provides a common structure and standard vocabularies for observational
healthcare data. Here, candidate concepts are retrieved from an OHDSI vocabulary
service, filtered to valid standard concepts in the expected domain, and ranked
by name similarity. A local classifier selects from the candidate list, with an
option to select none of them.

Restricting the choice to retrieved candidates prevents the classifier from
inventing a concept identifier. It does not guarantee that the selected concept
matches the criterion. The current phrase table contains 16 curated clinical
phrases and a generic fallback; coverage beyond these examples has not been
measured. Numeric comparisons, such as a measurement above a threshold, are
also extracted where recognised.

* [omop.py](src/trialcriteria/omop.py) retrieves concepts and extracts predicates.
* [classifier.py](src/trialcriteria/classifier.py) defines the classifier interface.
* [test_predicates.py](tests/test_predicates.py) tests selected numeric expressions
  and phrase handling.

```bash
trialcriteria map --nct NCT03432533
```

This command needs a vocabulary service and the optional classifier.

## Part 4: [Execution of a cohort example](src/trialcriteria/cohort.py)

The cohort example downloads OHDSI's Eunomia GiBleed dataset, loads the CSV tables
into SQLite, and selects people using recorded conditions and their vocabulary
descendants. The initial download is about 15 MB and setup takes roughly two
minutes, depending on the connection and machine.

The demonstration chooses two frequent conditions from the dataset. With the
reference data, it includes people with recorded viral sinusitis and excludes
those with recorded acute viral pharyngitis:

| Step | People |
|---|---:|
| All people in the synthetic database | 2,694 |
| People with the inclusion condition | 2,686 |
| People in the inclusion group also meeting the exclusion rule | 2,598 |
| Remaining people | 88 (3.3% of the full database) |

The output also lists 2,606 people with the exclusion condition across the whole
database. Only 2,598 of them belong to the inclusion group, so those are the
people removed from it.

This example checks database loading and condition-set operations. It does not
consume the parsed tree or mapping output, apply trial-specific time windows,
or use the tree evaluator's unknown state. The result is a reproducible example
on synthetic data, not a recruitment estimate for a real trial.

* [cohort.py](src/trialcriteria/cohort.py) loads the data and runs the example.

```bash
make cohort
trialcriteria cohort    # repeat the example using the existing database
```

## Part 5: [Analysis of exclusion wording](src/trialcriteria/strictness.py)

This analysis examines how oncology trial criteria describe exclusions relating
to HIV, hepatitis B/C, brain metastases and prior malignancy. The classifier
assigns one of three labels: wholly excluded, conditional, or not an exclusion.
This distinguishes an outright exclusion from a statement that allows
participation under specified conditions.

The reported shift from outright to conditional exclusion remains preliminary.
The classifier has not been validated, discrepancies with published HIV trend
estimates remain unexplained, and statistical uncertainty in the trend has not
been assessed. These findings should not be presented as established results.

* [strictness.py](src/trialcriteria/strictness.py) classifies criteria from the corpus.

```bash
trialcriteria strictness
```

This command requires the corpus and the local classifier.

## Part 6: [Human validation of the classifications](data/validation/README.md)

The validation directory contains a blinded sheet of 74 items awaiting human
annotation. Each item includes the recovered criterion text and marks the end of
the classifier's 400-character input window. The annotator assigns W, C, N or ?
without seeing the model's answer. A model must not provide the human labels.

An earlier sheet exposed the predictions and shortened criteria to 160
characters. That version is unsuitable for measuring accuracy and has been
removed. Use the current sheet and the instructions in the validation directory.

Scoring requires the exact answer key created with the sheet. The key is kept
separately and is not bundled with the supplied sheet. A key from a newly drawn
sample must not be used to score a different sheet.

* [validate.py](src/trialcriteria/validate.py) draws a sheet and writes its answer key.
* [score.py](src/trialcriteria/score.py) reports agreement, a Wilson confidence
  interval, per-label results and a confusion matrix.
* [test_score.py](tests/test_score.py) tests reading human marks.

```bash
# Draw a new sheet and matching key when the corpus and model output are available.
trialcriteria validate --n 74 --key .cache/new-key.json > new-sheet.txt

# After a human has marked that sheet, score it against the matching key.
trialcriteria score new-sheet.txt --key .cache/new-key.json
```

Keep the key out of the annotator's view. Review disagreements on criteria longer
than 400 characters separately: the length flags a possible input-window problem,
but does not establish its cause. The reported sample accuracy is not
automatically an estimate of accuracy across the full corpus, because the sample
is stratified by model label and confidence band.

## Local classifier and configuration

The `map` and `strictness` commands use a local classifier that chooses from
supplied options and returns a confidence score. A compatible module must expose
the interface in [classifier.py](src/trialcriteria/classifier.py). Configure it
with `TC_CLASSIFIER_MODULE` and `TC_CLASSIFIER_MODEL`.

The reference classifier uses MLX on Apple Silicon with native arm64 Python.
The supplied configuration example describes a separate Python 3.12 environment
for it. The core installation above does not install this classifier. If using
the MLX implementation, check the interpreter architecture:

```bash
python -c "import platform; print(platform.machine())"
```

It should report `arm64`. Local inference avoids sending classification inputs
to a hosted model, but the record retrieval and vocabulary commands still use
network services. Tests and the cohort example do not use the classifier.

Copy [.env.example](.env.example) to `.env` and set values that differ from the
defaults. Settings are resolved through [config.py](src/trialcriteria/config.py)
in the order environment variable, `.env`, then default.

```bash
cp .env.example .env
trialcriteria config
```

The default vocabulary endpoint is the public OHDSI demo WebAPI. For bulk mapping,
use a local vocabulary service and point `TC_WEBAPI` to it. Cached data, the
SQLite database, `.env` and the virtual environment are excluded from Git.

## Further work

The next research step is human validation. Further development includes
connecting parsed and mapped criteria to cohort execution, extending mapping
coverage, testing on a broader CDM, and supporting local vocabulary lookups.

OHDSI's Criteria2Query addresses related work on converting free-text criteria
to OMOP cohort queries. This project retains a logic tree and provides functions
for evaluating and explaining its individual rules. A systematic comparison with
prior work has not been completed, so no novelty claim is made here.

Earlier analyses that did not support their initial conclusions are retained in
[attic/](attic/README.md), with explanations of why they were set aside.

## Licence and citation

The code is available under the MIT licence; see [LICENSE](LICENSE).
[CITATION.cff](CITATION.cff) contains the software citation details. The repository
does not redistribute the OMOP vocabularies; their respective licence terms apply.
