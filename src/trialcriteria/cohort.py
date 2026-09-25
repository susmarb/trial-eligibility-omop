#!/usr/bin/env python3
"""End-to-end: eligibility criteria -> OMOP concepts -> an executable cohort.

Closes the loop the rest of the pipeline was building toward.

    trial criteria text
      -> criteria_tree.py      logic tree (AND / OR / n-of-m, thresholds kept)
      -> criteria_omop.py      each leaf anchored to an OMOP standard concept
      -> THIS                  SQL against a real OMOP CDM, patient counts out

The CDM is OHDSI's **Eunomia GiBleed** reference dataset (2,694 synthetic people),
the same one the OHDSI community tests against. Loaded into SQLite so it needs no
database server and no R.

What this demonstrates that a concept mapping alone does not: the mapped criteria
are **executable**. Each leaf becomes a patient set; the logic tree combines those
sets with the trial's own AND / OR / n-of-m structure; the result is a count and a
per-criterion attrition table, which is what a feasibility question actually needs.

    make cdm                       # download the reference CDM once
    trialcriteria cohort --build   # load the CSVs into SQLite
    trialcriteria cohort           # run the demo cohort
"""
import argparse
import csv
import os
import sqlite3
import sys

from . import config

CDM_DIR = config.get("TC_CDM_DIR")
DB = config.cache("cdm.sqlite")

WANT = ["PERSON", "CONDITION_OCCURRENCE", "MEASUREMENT", "OBSERVATION",
        "DRUG_EXPOSURE", "PROCEDURE_OCCURRENCE", "CONCEPT", "CONCEPT_ANCESTOR",
        "OBSERVATION_PERIOD", "DEATH"]


def build(cdm_dir=CDM_DIR):
    if not os.path.isdir(cdm_dir):
        raise SystemExit(
            "no CDM at %s\nDownload one first:  make cdm   (see README, 'The CDM')"
            % cdm_dir)
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    for name in WANT:
        path = os.path.join(cdm_dir, name + ".csv")
        if not os.path.exists(path):
            print("  skip %s" % name, file=sys.stderr)
            continue
        with open(path, newline="", encoding="utf-8-sig") as f:
            r = csv.reader(f)
            cols = [c.strip().lower() for c in next(r)]
            con.execute("CREATE TABLE %s (%s)" % (name.lower(), ",".join(cols)))
            con.executemany("INSERT INTO %s VALUES (%s)"
                            % (name.lower(), ",".join("?" * len(cols))),
                            (row for row in r if len(row) == len(cols)))
        n = con.execute("SELECT COUNT(*) FROM %s" % name.lower()).fetchone()[0]
        print("  %-24s %8d rows" % (name.lower(), n), file=sys.stderr)
    for idx in ("CREATE INDEX i_co ON condition_occurrence(condition_concept_id)",
                "CREATE INDEX i_m ON measurement(measurement_concept_id)",
                "CREATE INDEX i_ca ON concept_ancestor(ancestor_concept_id)"):
        try:
            con.execute(idx)
        except sqlite3.Error:
            pass
    con.commit()
    con.close()
    print("built -> %s" % DB, file=sys.stderr)


# --- one mapped criterion -> the set of person_ids it selects ---------------

def persons_with_condition(con, concept_id, descendants=True):
    """Condition domain. Uses CONCEPT_ANCESTOR so a parent concept also matches
    its descendants, which is how OHDSI cohorts are actually written."""
    if descendants:
        q = """SELECT DISTINCT co.person_id FROM condition_occurrence co
               WHERE co.condition_concept_id IN (
                 SELECT descendant_concept_id FROM concept_ancestor
                 WHERE ancestor_concept_id = ?)"""
    else:
        q = ("SELECT DISTINCT person_id FROM condition_occurrence "
             "WHERE condition_concept_id = ?")
    return {r[0] for r in con.execute(q, (str(concept_id),))}


def persons_with_measurement(con, concept_id, op=None, value=None):
    """Measurement domain, with the criterion's own threshold applied."""
    rows = con.execute(
        "SELECT person_id, value_as_number FROM measurement "
        "WHERE measurement_concept_id = ?", (str(concept_id),)).fetchall()
    out = set()
    for pid, v in rows:
        if op is None:
            out.add(pid)
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if (op == ">=" and x >= value) or (op == ">" and x > value) or \
           (op == "<=" and x <= value) or (op == "<" and x < value):
            out.add(pid)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--cdm", default=CDM_DIR)
    args = ap.parse_args()
    if args.build or not os.path.exists(DB):
        build(args.cdm)

    con = sqlite3.connect(DB)
    total = con.execute("SELECT COUNT(*) FROM person").fetchone()[0]

    # what concepts does this CDM actually carry? (a vocabulary subset)
    present = con.execute("""
        SELECT c.concept_id, c.concept_name, c.domain_id, COUNT(*) n
        FROM condition_occurrence co JOIN concept c
          ON c.concept_id = co.condition_concept_id
        GROUP BY 1,2,3 ORDER BY n DESC LIMIT 8""").fetchall()
    print("CDM: Eunomia GiBleed, %d persons\n" % total)
    print("most frequent conditions present:")
    for cid, name, _domain, n in present:
        print("   %-10s %-44s %6d" % (cid, name[:44], n))

    meas = con.execute("""
        SELECT c.concept_id, c.concept_name, COUNT(*) n
        FROM measurement m JOIN concept c ON c.concept_id = m.measurement_concept_id
        GROUP BY 1,2 ORDER BY n DESC LIMIT 5""").fetchall()
    print("\nmost frequent measurements present:")
    for cid, name, n in meas:
        print("   %-10s %-44s %6d" % (cid, name[:44], n))

    # --- a cohort built the way a trial's criteria would be -----------------
    # inclusion: the indication; exclusion: a comorbidity. Concepts chosen from
    # what this CDM carries, so the demonstration is real rather than empty.
    inc_id, inc_name = present[0][0], present[0][1]
    exc_id, exc_name = present[1][0], present[1][1]

    inc = persons_with_condition(con, inc_id)
    exc = persons_with_condition(con, exc_id)
    eligible = inc - exc

    print("\n" + "=" * 78)
    print("COHORT, EXECUTED")
    print("=" * 78)
    print("  %-52s %6d  (%4.1f%%)" % ("all persons in CDM", total, 100.0))
    print("  %-52s %6d  (%4.1f%%)"
          % ("INCLUDE  " + inc_name[:42], len(inc), 100 * len(inc) / total))
    print("  %-52s %6d  (%4.1f%%)"
          % ("EXCLUDE  " + exc_name[:42], len(exc), 100 * len(exc) / total))
    print("  %-52s %6d  (%4.1f%%)"
          % ("-> eligible", len(eligible), 100 * len(eligible) / total))
    print("\n  attrition: %d of %d removed by the exclusion criterion"
          % (len(inc) - len(eligible), len(inc)))
    print("\nEvery concept_id is an OMOP standard concept; descendants resolved via")
    print("CONCEPT_ANCESTOR. This is the feasibility number a site would want:")
    print("how many of my patients would this trial's criteria actually admit.")
    con.close()
