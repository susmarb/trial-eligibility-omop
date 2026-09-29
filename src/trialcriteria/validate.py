#!/usr/bin/env python3
"""Draw a hand-validation sample for the three-way strictness classification.

Accuracy claimed without this step is not a claim.

Two properties this sampler has, and the first version did not:

**Blinded.** The model's label is written to a separate answer key, not onto the
sheet. An annotator shown a label agrees with it more often than one who is not,
so an unblinded sheet measures suggestibility rather than accuracy. Pass
`--show-labels` only to review a finished marking, never to produce one.

**Full text.** The stored classification carries a truncated copy of the
criterion. The truncation falls at the *end* of the sentence, which is exactly
where an escape hatch lives (`provided that`, `unless`, `may participate if`), so
marking from it is biased against the conditional label. The full criterion is
recovered here by re-parsing the source trial, which needs no model run.

The sheet also marks how far the classifier itself could see. Text past that
point was **not** available to the model, so a disagreement there is a window
problem, not a classifier error. `score` reports the two separately.

    trialcriteria validate --n 74 > sheet.txt     # mark this
    trialcriteria score sheet.txt                 # then this
"""
import argparse
import collections
import json
import os
import random
import sys

from . import config
from . import tree as CT

# the classifier's input window, from strictness.py
MODEL_WINDOW = 400
CUT = "  <<< the classifier saw nothing past this point >>>"


def _corpus_index(cache):
    """nct -> trial record, for recovering full criterion text.

    Picks the LARGEST corpus in the cache. Several may be present from pilot
    runs at different sizes, and a smaller one silently fails to recover most
    of the sample rather than raising anything.
    """
    corpora = [f for f in os.listdir(cache)
               if f.startswith("onc-") and f.endswith(".json")]
    if not corpora:
        return {}
    biggest = max(corpora, key=lambda f: os.path.getsize(os.path.join(cache, f)))
    rows = json.load(open(os.path.join(cache, biggest)))
    return {r["nct"]: r for r in rows}


_LEAVES = {}


def full_text(row, index):
    """The complete criterion, or the stored truncation if it cannot be found.

    Matches on a 60-character prefix and accepts only an unambiguous hit, so a
    trial repeating a criterion never silently supplies the wrong one.
    """
    tr = index.get(row["nct"])
    if not tr:
        return row["text"], False
    if row["nct"] not in _LEAVES:
        try:
            _LEAVES[row["nct"]] = [
                lf.text for lf in CT.parse(tr["criteria"])["exclusion"].leaves()]
        except Exception:
            _LEAVES[row["nct"]] = []
    hits = [t for t in _LEAVES[row["nct"]] if t.startswith(row["text"][:60])]
    return (hits[0], True) if len(hits) == 1 else (row["text"], False)


def render(text, truncated_at=MODEL_WINDOW):
    """The criterion, with the classifier's input window marked."""
    if len(text) <= truncated_at:
        return "    " + text
    return "    %s\n%s\n    %s" % (text[:truncated_at], CUT, text[truncated_at:])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=74)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--key", default=None,
                    help="where to write the answer key (default: <cache>/validation-key.json)")
    ap.add_argument("--show-labels", action="store_true",
                    help="NOT for marking: reveals the model's answer on the sheet")
    a = ap.parse_args()

    cache = config.get("TC_CACHE")
    rows = json.load(open(os.path.join(cache, "strictness.json")))
    index = _corpus_index(cache)

    by = collections.defaultdict(list)
    for r in rows:
        band = "hi" if (r.get("conf") or 0) >= 0.7 else "lo"
        by[(r["label"], band)].append(r)

    rnd = random.Random(a.seed)
    per = max(1, a.n // max(len(by), 1))
    drawn, taken = [], set()
    for (label, band), rs in sorted(by.items()):
        for r in rnd.sample(rs, min(per, len(rs))):
            drawn.append((label, band, r))
            taken.add(id(r))
    # small cells leave the sample short of --n; top it up at random so the
    # requested size is the size delivered
    pool = [(label, band, r) for (label, band), rs in sorted(by.items())
            for r in rs if id(r) not in taken]
    rnd.shuffle(pool)
    drawn.extend(pool[:max(0, a.n - len(drawn))])
    rnd.shuffle(drawn)          # so labels do not run in blocks

    print("STRICTNESS VALIDATION SHEET")
    print("=" * 78)
    print("""
For each criterion below, decide how it treats patients with the named
condition, and write your answer on the `you:` line.

    W   wholly excluded   anyone with the condition is barred, no route back in
    C   conditional       barred UNLESS / EXCEPT / PROVIDED THAT something holds
    N   not an exclusion  this sentence does not exclude for that condition
    ?   genuinely unresolvable from the sentence

The judgement is grammatical, not clinical: does the sentence carry an escape
hatch? A handful of `?` is a result, not a failure. Do not look up the trial.

The model's answers are NOT on this sheet, on purpose. Score with:

    trialcriteria score <this file>
""")
    answers, recovered = [], 0
    for i, (label, band, r) in enumerate(drawn, 1):
        text, ok = full_text(r, index)
        recovered += ok
        answers.append({"i": i, "nct": r["nct"], "topic": r["topic"],
                        "label": label, "conf": r.get("conf"), "band": band,
                        "full_len": len(text), "recovered": ok})
        print("=" * 78)
        print("%2d. [%s] %s" % (i, r["topic"], r["nct"]))
        print(render(text))
        if a.show_labels:
            print("    model said: %s (conf %.2f)" % (label, r.get("conf") or 0))
        print("\n    you: ___   (W / C / N / ?)\n")

    keypath = a.key or os.path.join(cache, "validation-key.json")
    json.dump(answers, open(keypath, "w"), indent=1)

    # diagnostics go to stderr: the sheet is a document that gets shared, and a
    # local filesystem path has no business travelling with it
    print("=" * 78)
    print("%d items. Mark each `you:` line, then run `trialcriteria score` on "
          "this file." % len(drawn))
    print("%d items, full text recovered for %d, answer key -> %s"
          % (len(drawn), recovered, keypath), file=sys.stderr)
