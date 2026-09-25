#!/usr/bin/env python3
"""Which specific eligibility criteria are associated with recruitment failure?

`criteria_burden.py` established that trials terminated for poor accrual carry
more criteria than completed trials, and more than trials terminated for other
reasons (the control). That says *how many*. This asks **which ones**.

Method: bucket each parsed criterion into an interpretable type (ECOG, life
expectancy, prior therapy, washout, lab thresholds, …), then compare how often
each type appears in accrual-terminated versus completed trials, matched on
phase. Enrichment is reported as a rate ratio with the counts, so a big ratio on
tiny numbers is visible as such rather than hidden.

    python3 criteria_killers.py                 # uses the cached corpus
    python3 criteria_killers.py --phase PHASE2  # restrict

This is registry data. No patients, no privacy regime, no data agreements.
"""
import argparse
import collections
import glob
import json
import math
import os
import re
import statistics
import sys

import criteria_burden as CB
import criteria_tree as CT

# Interpretable criterion types. Order matters: first match wins.
TYPES = [
    ("performance status", r"(?i)\b(ecog|karnofsky|kps|performance status|lansky)\b"),
    ("life expectancy", r"(?i)life expectancy"),
    ("prior therapy limit", r"(?i)\b(no more than|at most|maximum of|up to)\b.{0,40}"
                            r"(prior|previous)\b|\b(prior|previous)\s+(lines?|regimens?|"
                            r"therap|treatment|chemo)"),
    ("treatment-naive", r"(?i)\b(treatment|chemotherapy|therapy)[- ]na[iï]ve|"
                        r"\bno prior\b"),
    ("washout period", r"(?i)\bwash[- ]?out\b|\bwithin \d+\s*(days?|weeks?|months?)\b.{0,40}"
                       r"(prior|before|preceding)"),
    ("renal function", r"(?i)\b(creatinine|egfr|gfr|creatinine clearance|renal)\b"),
    ("hepatic function", r"(?i)\b(bilirubin|alt\b|ast\b|alat|asat|transaminase|hepatic)\b"),
    ("haematology", r"(?i)\b(platelet|neutrophil|anc\b|haemoglobin|hemoglobin|"
                    r"leukocyte|wbc\b)\b"),
    ("cardiac function", r"(?i)\b(ejection fraction|lvef|qtc?\b|nyha|cardiac)\b"),
    ("brain metastases", r"(?i)\b(brain|cns)\s+(metasta|involvement)"),
    ("other malignancy", r"(?i)\b(second|other|prior)\s+(primary\s+)?malignan|"
                         r"history of cancer"),
    ("infection status", r"(?i)\b(hiv|hepatitis [bc]|hbv|hcv|active infection|"
                         r"tuberculosis)\b"),
    ("pregnancy/contraception", r"(?i)\b(pregnan|breast[- ]?feed|lactat|contracept|"
                                r"childbearing)\b"),
    ("consent/compliance", r"(?i)\b(informed consent|willing|able to comply|adherence|"
                           r"cooperat)\b"),
    ("biopsy/tissue required", r"(?i)\b(biops|tissue sample|archival tissue|tumor tissue)\b"),
    ("imaging/measurable disease", r"(?i)\b(recist|measurable disease|evaluable disease|"
                                   r"imaging)\b"),
    ("biomarker/mutation", r"(?i)\b(mutation|biomarker|expression|positive for|her2|"
                           r"egfr\b|pd-l1|genotype)\b"),
    ("age threshold", r"(?i)\b(years? of age|aged?\b)\b"),
    ("psychiatric/substance", r"(?i)\b(psychiatric|substance abuse|alcohol|drug abuse)\b"),
    ("language/literacy", r"(?i)\b(language|english|literate|read and write|"
                          r"comprehen)\b"),
    ("device/implant", r"(?i)\b(pacemaker|implant|prosthes|defibrillator|shunt)\b"),
]
COMPILED = [(n, re.compile(p)) for n, p in TYPES]


def bucket(text):
    for name, rx in COMPILED:
        if rx.search(text):
            return name
    return None


def load():
    files = sorted(glob.glob(os.path.join(CB.CACHE, "burden-*.json")),
                   key=lambda p: os.path.getsize(p))
    if not files:
        raise SystemExit("no corpus — run criteria_burden.py --fetch first")
    return json.load(open(files[-1])), files[-1]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", default="", help="e.g. PHASE2; default: any declared phase")
    ap.add_argument("--min-count", type=int, default=15,
                    help="ignore criterion types rarer than this (default %(default)s)")
    args = ap.parse_args()

    d, path = load()
    print("corpus: %s  (%d terminated, %d completed)"
          % (os.path.basename(path), len(d["terminated"]), len(d["completed"])),
          file=sys.stderr)

    groups = collections.defaultdict(list)
    for t in d["terminated"]:
        if not t["criteria"]:
            continue
        if CB.ACCRUAL.search(t["why"]):
            groups["accrual"].append(t)
        elif CB.OTHER.search(t["why"]):
            groups["other"].append(t)
    for t in d["completed"]:
        if t["criteria"]:
            groups["completed"].append(t)

    def keep(t):
        p = t.get("phase") or ""
        return p.startswith(args.phase) if args.phase else p.startswith("PHASE")
    for k in groups:
        groups[k] = [t for t in groups[k] if keep(t)]

    print("phase filter %-8s accrual=%d  other=%d  completed=%d"
          % (args.phase or "PHASE*", len(groups["accrual"]),
             len(groups["other"]), len(groups["completed"])), file=sys.stderr)
    if len(groups["accrual"]) < 20:
        raise SystemExit("too few accrual failures to analyse")

    # per-trial presence of each criterion type + burden
    pres, burden = {}, {}
    for g, rows in groups.items():
        pres[g] = collections.Counter()
        burden[g] = []
        for t in rows:
            tree = CT.parse(t["criteria"])
            seen = set()
            for sec in ("inclusion", "exclusion"):
                for lf in tree[sec].leaves():
                    b = bucket(lf.text)
                    if b:
                        seen.add(b)
            pres[g].update(seen)
            burden[g].append(CB.burden(t)["n_total"])

    na, nc, no = (len(groups["accrual"]), len(groups["completed"]), len(groups["other"]))
    print("\n" + "=" * 86)
    print("WHICH CRITERIA TYPES ARE ENRICHED IN ACCRUAL FAILURES")
    print("=" * 86)
    print("%-28s %>9s %>9s %>9s %>8s"
          .replace("%>", "%") % ("criterion type", "accrual", "completed", "other",
                                 "ratio"))
    print("-" * 86)

    rows = []
    for name, _ in TYPES:
        ca, cc, co = pres["accrual"][name], pres["completed"][name], pres["other"][name]
        if ca + cc < args.min_count:
            continue
        ra, rc, ro = ca / na, cc / nc, (co / no if no else 0)
        ratio = ra / rc if rc else float("inf")
        rows.append((ratio, name, ra, rc, ro, ca, cc))
    for ratio, name, ra, rc, ro, ca, cc in sorted(rows, reverse=True):
        flag = "  <<<" if ratio >= 1.4 and ca >= 10 else ""
        print("%-28s %8.0f%% %8.0f%% %8.0f%% %7.2fx%s"
              % (name, 100 * ra, 100 * rc, 100 * ro, ratio, flag))

    print("\naccrual   = terminated for poor accrual/enrolment")
    print("completed = ran to completion")
    print("other     = terminated for other reasons (safety, funding, sponsor) — CONTROL")
    print("ratio     = accrual rate / completed rate;  <<< marks >=1.4x on >=10 trials")

    print("\nBURDEN (median criteria per trial)")
    for g in ("accrual", "other", "completed"):
        if burden[g]:
            print("   %-10s %5.1f   (n=%d)" % (g, statistics.median(burden[g]),
                                               len(burden[g])))


if __name__ == "__main__":
    main()
