#!/usr/bin/env python3
"""Score a marked validation sheet against the model's answers.

Reads the marks out of a sheet marked by hand, joins them to the answer key
written when the sheet was drawn, and reports what a methods section needs:

* overall accuracy, and a **confidence interval**, because n is small
* **accuracy per label**, which matters more than the headline number here: the
  finding is a shift between two labels, so a systematic confusion between them
  would produce the trend on its own
* a **confusion matrix**, which is where such a systematic error shows up
* how many disagreements fall outside the classifier's input window, since those
  are a window problem and not a classifier error
* agreement by confidence band, to test whether reported confidence is worth
  anything on this task

Marks are read as `<item number> <letter>` anywhere in the file, so a sheet
edited in place and a bare list of answers both work.

    trialcriteria score sheet.txt
"""
import argparse
import collections
import json
import math
import os
import re

from . import config

MARK = re.compile(r"^\s*(?:(\d+)\s*[.):]?\s*)?you:\s*([WCN?])(?=\s|$)", re.I)
BARE = re.compile(r"^\s*(\d+)[.):]?\s+([WCN?])\s*$", re.I)
ITEM = re.compile(r"^\s*(\d+)\.\s+\[")
YOU = re.compile(r"^\s*you:", re.I)
LETTER = {"W": "wholly excluded", "C": "conditional", "N": "not an exclusion"}
SHORT = {v: k for k, v in LETTER.items()}


def read_marks(path):
    """Read explicit item numbers, preserving blanks and unresolved answers."""
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()
    marks = {}
    current = None
    position = 0
    for line in lines:
        heading = ITEM.match(line)
        if heading:
            current = int(heading.group(1))
            continue
        if YOU.match(line):
            position += 1
        match = BARE.match(line) or MARK.match(line)
        if not match:
            continue
        number = int(match.group(1)) if match.group(1) else current or position
        if number in marks:
            raise ValueError("duplicate mark for item %d" % number)
        marks[number] = match.group(2).upper()
    return marks


def wilson(k, n, z=1.96):
    """Wilson interval. Appropriate at this n; the normal approximation is not."""
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sheet")
    ap.add_argument("--key", default=None)
    a = ap.parse_args()

    keypath = a.key or os.path.join(config.get("TC_CACHE"), "validation-key.json")
    if not os.path.exists(keypath):
        raise SystemExit("no answer key at %s — draw the sheet first" % keypath)
    key = {k["i"]: k for k in json.load(open(keypath))}
    marks = read_marks(a.sheet)
    if not marks:
        raise SystemExit("no marks found in %s — each item needs a letter on its "
                         "`you:` line" % a.sheet)

    marked = [(i, m) for i, m in sorted(marks.items()) if i in key and m != "?"]
    unresolved = [i for i, m in marks.items() if m == "?"]
    missing = [i for i in key if i not in marks]

    right = [(i, m) for i, m in marked if LETTER[m] == key[i]["label"]]
    n, k = len(marked), len(right)
    lo, hi = wilson(k, n)

    print("VALIDATION RESULT")
    print("=" * 66)
    print("  marked            %d of %d" % (len(marks), len(key)))
    if missing:
        print("  UNMARKED          %d  (items %s)"
              % (len(missing), ", ".join(str(i) for i in sorted(missing)[:12])))
    print("  unresolvable (?)  %d  — excluded from accuracy, reported as a result"
          % len(unresolved))
    print("  scored            %d" % n)
    print()
    print("  ACCURACY          %d/%d = %.1f%%   95%% CI %.1f–%.1f%%"
          % (k, n, 100 * k / n if n else 0, 100 * lo, 100 * hi))

    print("\nPER LABEL (as the human marked it)")
    print("  %-20s %7s %7s  %s" % ("human label", "n", "correct", "accuracy"))
    per = collections.defaultdict(lambda: [0, 0])
    for i, m in marked:
        per[m][0] += 1
        per[m][1] += LETTER[m] == key[i]["label"]
    for letter in ("W", "C", "N"):
        cnt, ok = per[letter]
        print("  %-20s %7d %7d  %s"
              % (LETTER[letter], cnt, ok,
                 "%.1f%%" % (100 * ok / cnt) if cnt else "—"))

    print("\nCONFUSION  (rows = human, columns = model)")
    labels = ["W", "C", "N"]
    print("        %s" % "".join("%8s" % x for x in labels))
    conf = collections.Counter((m, SHORT[key[i]["label"]]) for i, m in marked)
    for h in labels:
        print("    %-4s%s" % (h, "".join("%8d" % conf[(h, mo)] for mo in labels)))
    off = {kk: v for kk, v in conf.items() if kk[0] != kk[1] and v}
    if off:
        worst = max(off.items(), key=lambda x: x[1])
        print("\n  largest confusion: human %s read as model %s, %d times."
              % (LETTER[worst[0][0]], LETTER[worst[0][1]], worst[1]))
        if {worst[0][0], worst[0][1]} == {"W", "C"}:
            print("  ** This is the pair the trend is made of. A systematic error")
            print("     here can produce the finding on its own. Report it.")

    win = [(i, m) for i, m in marked if key[i].get("full_len", 0) > 400]
    if win:
        bad = [1 for i, m in win if LETTER[m] != key[i]["label"]]
        print("\nINPUT WINDOW")
        print("  %d scored items run past the classifier's 400-character window;"
              % len(win))
        print("  %d of those disagree. A disagreement there is a window problem,"
              % len(bad))
        print("  not a classifier error, and is fixable by widening the window.")

    print("\nCONFIDENCE BAND")
    for band in ("hi", "lo"):
        sub = [(i, m) for i, m in marked if key[i].get("band") == band]
        ok = sum(1 for i, m in sub if LETTER[m] == key[i]["label"])
        print("  %-4s %3d items  %s" % (band, len(sub),
              "%.1f%% correct" % (100 * ok / len(sub)) if sub else "—"))
    print("\n  If the two bands do not separate, reported confidence carries no")
    print("  information on this task and must not be used to filter or escalate.")
