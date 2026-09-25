#!/usr/bin/env python3
"""Hand-validation sample for the three-way strictness classification.

Draws a stratified sample (by label, and by confidence band within label) and
prints it for a human to mark. Accuracy claimed without this step is not a claim.

    trialcriteria validate --n 90 > sample.txt
"""
import argparse
import collections
import json
import os
import random

from . import config


def main():
    CACHE = config.get("TC_CACHE")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=90)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    rows = json.load(open(os.path.join(CACHE, "strictness.json")))
    by = collections.defaultdict(list)
    for r in rows:
        band = "hi" if (r.get("conf") or 0) >= 0.7 else "lo"
        by[(r["label"], band)].append(r)

    rnd = random.Random(a.seed)
    per = max(1, a.n // max(len(by), 1))
    print("STRICTNESS VALIDATION SAMPLE  (mark each: Y = model right, N = wrong)\n")
    print("labels: W = wholly excluded, C = conditional, N = not an exclusion\n")
    i = 0
    for (label, band), rs in sorted(by.items()):
        print("=" * 78)
        print("%s | confidence %s | n=%d in this cell" % (label.upper(), band, len(rs)))
        print("=" * 78)
        for r in rnd.sample(rs, min(per, len(rs))):
            i += 1
            print("\n%2d. [%s conf=%.2f] %s" % (i, r["topic"], r.get("conf") or 0, r["nct"]))
            print("    %s" % r["text"])
            print("    model says: %s      correct? ___" % label)
    print("\n\n%d items. Counts of each cell in the full set:" % i)
    for k, v in sorted(by.items(), key=lambda x: -len(x[1])):
        print("   %-20s %-3s %6d" % (k[0], k[1], len(v)))
