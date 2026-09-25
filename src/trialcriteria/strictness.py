#!/usr/bin/env python3
"""Three-way strictness of oncology eligibility criteria, 2008-2024.

The presence/absence measurement in `eligibility_trend.py` cannot distinguish

    "Patients with HIV are excluded."                      (wholly excluded)
    "HIV-positive patients with CD4 > 350 are eligible."   (conditional)

and the published work on HIV shows that distinction IS the finding: after the
2017 ASCO-Friends recommendations, exclusions moved from wholly to conditional
rather than disappearing. Counting mentions therefore reads a field getting more
inclusive as one getting stricter, which is what our first pass did.

So classify each matching criterion three ways with a local model. Only criteria
whose text mentions a targeted topic are sent, which is about 30k decisions
rather than 500k.

Runs entirely on-device (laya-mlx, Apple Silicon). No API, no rate limit, no data
leaving the machine, which is also the architecture this would need in a hospital.

    trialcriteria strictness --limit 2000      # pilot
    trialcriteria strictness                   # full corpus (~9 min on an M3)
"""
import argparse
import collections
import json
import os
import re
import statistics
import sys
import time

from . import classifier, config
from . import tree as CT

CACHE = config.get("TC_CACHE")
CORPUS = os.path.join(CACHE, "onc-2008-2024-2000.json")

TOPICS = {
    "brain metastases": r"(?i)\b(brain|cns|cerebral|leptomening)\w*\s+(metasta|involv|"
                        r"lesion|disease)|\bmetasta\w*\s+to\s+the\s+(brain|cns)",
    "HIV": r"(?i)\b(hiv|human immunodeficiency|aids)\b",
    "hepatitis B/C": r"(?i)\b(hepatitis\s*[bc]\b|hbv|hcv)\b",
    "prior malignancy": r"(?i)\b(prior|previous|second|other|concurrent|history of)\s+"
                        r"(\w+\s+){0,2}(malignan|cancer|neoplasm|carcinoma)",
}
COMPILED = {k: re.compile(v) for k, v in TOPICS.items()}

QUESTION = {
    "strictness": {
        "type": "choice",
        "instructions": ("This sentence is an eligibility criterion from a cancer "
                         "clinical trial protocol, taken from the exclusion section. "
                         "Decide how it treats patients with the named condition."),
        "criteria": [
            "wholly excluded",      # any patient with the condition is barred
            "conditional",          # allowed if further conditions are met
            "not an exclusion",     # the sentence does not exclude for it
        ],
    }
}


def load_agent():
    """The configured local classifier (see trialcriteria/classifier.py)."""
    return classifier.load()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0, help="trials to process (0 = all)")
    ap.add_argument("--json", metavar="FILE", default=os.path.join(CACHE, "strictness.json"))
    args = ap.parse_args()

    if not os.path.exists(CORPUS):
        raise SystemExit(
            "corpus not found: %s\nBuild it first:  trialcriteria fetch-corpus" % CORPUS)
    rows = json.load(open(CORPUS))
    if args.limit:
        # keep the year balance when piloting
        byy = collections.defaultdict(list)
        for r in rows:
            byy[r["year"]].append(r)
        per = max(1, args.limit // max(len(byy), 1))
        rows = [r for y in sorted(byy) for r in byy[y][:per]]
    print("%d trials" % len(rows), file=sys.stderr)

    # collect the criteria worth asking about
    jobs = []
    for r in rows:
        y = r["year"]
        if not y or not (2008 <= y <= 2024):
            continue
        try:
            tree = CT.parse(r["criteria"])
        except Exception:
            continue
        for lf in tree["exclusion"].leaves():
            for topic, rx in COMPILED.items():
                if rx.search(lf.text):
                    jobs.append((y, topic, lf.text[:400], r["nct"]))
                    break
    print("%d criteria to classify" % len(jobs), file=sys.stderr)

    agent = load_agent()
    out, t0 = [], time.time()
    for i, (y, topic, text, nct) in enumerate(jobs, 1):
        try:
            res = agent.predict(text, QUESTION)["answers"]["strictness"]
        except Exception as e:
            print("  ! %s" % e, file=sys.stderr)
            continue
        out.append({"year": y, "topic": topic, "nct": nct,
                    "label": res["choice"], "conf": res.get("confidence"),
                    "text": text[:160]})
        if i % 2000 == 0:
            el = time.time() - t0
            print("  %d/%d  %.0f/s  eta %.0f min"
                  % (i, len(jobs), i / el, (len(jobs) - i) / (i / el) / 60),
                  file=sys.stderr)
    json.dump(out, open(args.json, "w"))
    print("%d classified in %.1f min -> %s"
          % (len(out), (time.time() - t0) / 60, args.json), file=sys.stderr)

    # ---- report: share of trials wholly excluding, by topic and year
    trials_per_year = collections.Counter(
        r["year"] for r in rows if r["year"] and 2008 <= r["year"] <= 2024)
    years = sorted(trials_per_year)
    wholly = collections.defaultdict(lambda: collections.defaultdict(set))
    cond = collections.defaultdict(lambda: collections.defaultdict(set))
    for o in out:
        if o["label"] == "wholly excluded":
            wholly[o["topic"]][o["year"]].add(o["nct"])
        elif o["label"] == "conditional":
            cond[o["topic"]][o["year"]].add(o["nct"])

    print("\n" + "=" * 96)
    print("SHARE OF TRIALS **WHOLLY** EXCLUDING, BY TOPIC AND YEAR (%)")
    print("=" * 96)
    print("%-20s%s" % ("", "".join("%5d" % (y % 100) for y in years)))
    for topic in TOPICS:
        print("  %-18s%s" % (topic, "".join(
            "%5.0f" % (100 * len(wholly[topic][y]) / max(trials_per_year[y], 1))
            for y in years)))
    print("\nSHARE **CONDITIONAL** (the inclusive form) (%)")
    for topic in TOPICS:
        print("  %-18s%s" % (topic, "".join(
            "%5.0f" % (100 * len(cond[topic][y]) / max(trials_per_year[y], 1))
            for y in years)))

    print("\n" + "-" * 96)
    print("PRE-2017 (<=2016) vs POST (>=2019)")
    print("%-20s %10s %10s %9s   %10s %10s %9s"
          % ("topic", "wholly pre", "post", "change", "cond pre", "post", "change"))
    for topic in TOPICS:
        def mean(d, lo, hi, topic=topic):
            v = [100 * len(d[topic][y]) / max(trials_per_year[y], 1)
                 for y in years if lo <= y <= hi]
            return statistics.mean(v) if v else 0.0
        wp, wq = mean(wholly, 2008, 2016), mean(wholly, 2019, 2024)
        cp, cq = mean(cond, 2008, 2016), mean(cond, 2019, 2024)
        print("  %-18s %9.1f%% %9.1f%% %+8.1f   %9.1f%% %9.1f%% %+8.1f"
              % (topic, wp, wq, wq - wp, cp, cq, cq - cp))
    print("\nPublished HIV result to check against: wholly 62.8%% -> 42.0%%,")
    print("conditional 13.1%% -> 29.1%% (of trials that address HIV at all).")
