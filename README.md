# trial-eligibility-omop

Parse clinical trial eligibility criteria into a **logic tree**, anchor each
criterion to an **OMOP standard concept**, and execute the result as a **cohort**
against an OMOP CDM.

```
ClinicalTrials.gov ──▶  tree  ──▶  omop  ──▶  cohort
   protocol text      AND / OR      standard      SQL on a CDM
                      n-of-m        concept +     patient counts
                      thresholds    predicate     + attrition
```

Everything on the critical path is Python standard library. No database server,
no R, no API key, no patient data.

## Quick start

```bash
make test        # 29 tests, no network, no model, no data
make tree        # parse one trial and print its logic tree
make cohort      # download a reference CDM and execute a cohort on it
```

`make cohort` downloads OHDSI's Eunomia GiBleed dataset (about 15 MB), loads it
into SQLite and prints an attrition table. It takes roughly two minutes from a
clean clone and needs nothing configured.

## What the logic tree is for

ClinicalTrials.gov criteria are indented plain text, and the indentation is the
**only** thing encoding structure. Consider:

```
- At least 2 of the following risk factors:
  - Age over 70
  - Current smoker
  - Parental history of fracture
```

Read flat, that is three mandatory requirements and a patient with one risk
factor is rejected. Read as a tree, it is one requirement satisfied by any two of
three. The first version of this parser called `line.strip()` on every line, and
so produced confidently wrong exclusions. `tests/test_tree.py` is that bug and
its siblings, written down.

Evaluation is **three-valued** (true / false / unknown) and unknown never
excludes. A record that is silent about a criterion has not failed it. This is
the difference between a screening aid a coordinator will use and one that
quietly discards eligible patients.

The tree also survives into the output, so a result says *which criterion*
failed, not just a score.

## How criteria reach OMOP

**Retrieve, then decide.** The OHDSI vocabulary supplies real candidate concepts;
a classifier only picks among them. It cannot invent a `concept_id`, because it
never generates one. That is a structural guarantee, not an instruction in a
prompt.

Candidate quality is the ceiling on the whole pipeline. A worked example: a
lexical search over all concept names maps "Pregnancy or planning to become
pregnant" to *13 weeks gestation of pregnancy*. Filtered to **valid standard
concepts in the expected domain** and ranked by name similarity, the same model
and the same criterion give *Pregnancy* (concept 4299535). The model was never
the failing component. Check the candidate list before blaming the classifier.

The phrase table in `src/trialcriteria/omop.py` covers 16 curated clinical
phrases and a generic fallback. **It does not generalise**; extending it is
ordinary, tractable work and the obvious first contribution.

## The classifier

`map` and `strictness` need a local, non-generative classifier: one that answers
a typed question by choosing from a supplied option set and returns a
probability, generating no text. Any module matching the contract in
`src/trialcriteria/classifier.py` works. Set `TC_CLASSIFIER_MODULE` and
`TC_CLASSIFIER_MODEL`.

Running locally is not an optimisation. Under the European Health Data Space,
secondary use of health data happens inside a secure processing environment and
the data does not leave it, so a hosted API is structurally excluded. On-device
is the only form of this that could ever touch a hospital record.

Hardware: the reference implementation is MLX and needs Apple Silicon with a
native arm64 Python. A Python running under Rosetta reports `x86_64` and cannot
install mlx. Check with:

```bash
python3 -c "import platform; print(platform.machine())"   # must print arm64
```

`make test` and `make cohort` do not need the classifier at all.

## Commands

| command | what it does | needs |
|---|---|---|
| `trialcriteria show NCT…` | parse one trial, print the tree | network |
| `trialcriteria map --nct NCT…` | anchor criteria to OMOP concepts | network, classifier |
| `trialcriteria cohort [--build]` | execute a cohort on a CDM | a CDM (`make cdm`) |
| `trialcriteria fetch-corpus` | build the 2008-2024 corpus (~90 MB) | network, patience |
| `trialcriteria strictness` | three-way exclusion classification | corpus, classifier |
| `trialcriteria validate --n 90` | stratified hand-validation sample | classifier output |
| `trialcriteria config` | print every resolved setting | nothing |

## Configuration

Every path and endpoint resolves through `src/trialcriteria/config.py`, in the
order environment variable, then `.env`, then a working default. Copy
`.env.example` to `.env` and set only what differs. `trialcriteria config` prints
what is actually in use and where each value came from.

The vocabulary default is the **public OHDSI demo WebAPI**. It is rate limited
and it is someone else's server. Anything bulk should run against a local Athena
vocabulary load with `TC_WEBAPI` pointed at your own instance.

## Layout

```
src/trialcriteria/
  tree.py         the parser and Kleene evaluation   <- the core artifact
  ctgov.py        ClinicalTrials.gov API v2, cached
  corpus.py       bulk year-stratified fetch
  omop.py         criterion -> OMOP standard concept
  cohort.py       an anchored tree executed as SQL
  classifier.py   the local model, behind one contract
  strictness.py   three-way exclusion classification over a corpus
  validate.py     stratified hand-validation sampler
tests/            29 tests: the parser, Kleene logic, threshold predicates
data/validation/  a drawn sample awaiting human marking  <- see its README
attic/            analyses that did not survive, kept so they are not redone
```

## Status, honestly

The pipeline runs end to end and reproduces. One finding on top of it, a shift in
oncology exclusion criteria from outright to conditional, is **preliminary and
unvalidated**: `data/validation/` holds the drawn sample and nobody has marked it
yet. Direction agrees with a published study of HIV exclusions; magnitude is
roughly half, and that discrepancy is unexplained.

Prior art: OHDSI's **Criteria2Query** already converts free-text criteria into an
OMOP cohort query. The difference here is that the logic tree survives, so a
single patient can be evaluated criterion by criterion with a stated reason. Say
this up front in any write-up. A systematic prior-art search has not been done
and must precede any novelty claim.

## Licence

MIT, see `LICENSE`. Trial records come from ClinicalTrials.gov (public domain);
OMOP vocabularies carry their own licence terms from OHDSI/Athena, which this
repository does not redistribute.
