#!/usr/bin/env python3
"""Do restrictive eligibility criteria kill trials? A testable question, on public data.

The thesis: trials fail on **operations**, not science, and the single most-cited
operational cause is eligibility criteria that are more restrictive than the
science requires. Everyone says this. Nobody measures it at scale, because
nobody parses criteria into logic at scale.

We can now (`criteria_tree.py`), and ClinicalTrials.gov publishes both the
criteria and — for terminated trials — a free-text `whyStopped`. So:

    Do trials terminated for poor accrual carry measurably heavier
    eligibility burden than trials that completed?

If yes, criteria burden is a *predictive* signal available at protocol-design
time, before a single patient is screened — and it needs no patient data, no
hospital agreement, no GDPR regime. That is the whole point of this angle.

    python3 criteria_burden.py --fetch --n 400     # build the corpus (cached)
    python3 criteria_burden.py                     # analyse

Everything here is public registry data.
"""
import argparse
import json
import os
import re
import statistics
import sys
import urllib.parse
import urllib.request

import criteria_tree as CT

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ctg-cache")
API = "https://clinicaltrials.gov/api/v2/studies"

# free-text reasons that mean "we could not find patients"
ACCRUAL = re.compile(
    r"(?i)\b(slow|poor|low|insufficient|inadequate|lack of|unable to|difficult\w*)\s+"
    r"(\w+\s+){0,3}(accrual|enrol|recruit)|"
    r"\b(accrual|enrol\w*|recruit\w*)\s+(\w+\s+){0,2}(slow|poor|low|issues?|problems?|"
    r"challenges?|futility|failure)|\bfailure to (accrue|enrol|recruit)|"
    r"\bno (patients|subjects) (were )?(enrolled|accrued|recruited)")
# reasons unrelated to recruitment — the clean negative control
OTHER = re.compile(r"(?i)\b(safety|toxicit|adverse|efficacy|futility analysis|funding|"
                   r"business|sponsor decision|strategic|manufactur|covid|"
                   r"investigator left|pi left|left institution)")


def fetch(status, n, extra=""):
    """Page the registry for `n` studies with the given status."""
    out, token = [], None
    fields = ("NCTId,BriefTitle,OverallStatus,WhyStopped,EligibilityCriteria,"
              "Sex,MinimumAge,MaximumAge,EnrollmentCount,Phase,Condition,StartDate")
    while len(out) < n:
        q = {"query.term": "AREA[OverallStatus]%s%s" % (status, extra),
             "pageSize": "100", "fields": fields}
        if token:
            q["pageToken"] = token
        url = API + "?" + urllib.parse.urlencode(q, safe="[]")
        req = urllib.request.Request(url, headers={"user-agent": "trial-eligibility-omop/0.1"})
        d = json.loads(urllib.request.urlopen(req, timeout=90).read().decode())
        studies = d.get("studies", [])
        if not studies:
            break
        out.extend(studies)
        token = d.get("nextPageToken")
        if not token:
            break
        print("    %d…" % len(out), file=sys.stderr)
    return out[:n]


def flatten(s):
    p = s.get("protocolSection", {})
    e = p.get("eligibilityModule", {})
    st = p.get("statusModule", {})
    return {
        "nct": p.get("identificationModule", {}).get("nctId"),
        "title": p.get("identificationModule", {}).get("briefTitle", "")[:90],
        "status": st.get("overallStatus"),
        "why": st.get("whyStopped") or "",
        "criteria": e.get("eligibilityCriteria") or "",
        "sex": e.get("sex"),
        "min_age": e.get("minimumAge"),
        "max_age": e.get("maximumAge"),
        "enrolled": (p.get("designModule", {}).get("enrollmentInfo") or {}).get("count"),
        "phase": ";".join(p.get("designModule", {}).get("phases", []) or []),
        "cond": "; ".join(p.get("conditionsModule", {}).get("conditions", [])[:3]),
    }


def burden(t):
    """Structural measures of how hard a protocol is to satisfy."""
    tree = CT.parse(t["criteria"])
    inc = list(tree["inclusion"].leaves())
    exc = list(tree["exclusion"].leaves())

    def depth(node, d=0):
        return max([depth(c, d + 1) for c in node.children] or [d])

    groups = 0
    for sec in tree.values():
        stack = [sec]
        while stack:
            n = stack.pop()
            if n.op in ("OR", "N_OF"):
                groups += 1
            stack.extend(n.children)

    # numeric thresholds: lab cut-offs, scores, counts — the quiet killers
    nums = len(re.findall(r"[<>≤≥]\s*\d|\b\d+\s*(?:x\s*ULN|mg/dL|mmol|g/dL|/mm3|%)",
                          t["criteria"]))
    age_span = None
    try:
        lo = float(re.match(r"(\d+)", t["min_age"] or "").group(1))
        hi = float(re.match(r"(\d+)", t["max_age"] or "").group(1))
        age_span = hi - lo
    except Exception:
        pass
    return {
        "n_inclusion": len(inc), "n_exclusion": len(exc),
        "n_total": len(inc) + len(exc),
        "n_groups": groups, "max_depth": depth(tree["inclusion"]),
        "n_numeric": nums, "chars": len(t["criteria"]),
        "age_restricted": age_span is not None,
        "age_span": age_span,
        "sex_restricted": t["sex"] in ("MALE", "FEMALE"),
    }


def summarise(name, rows, keys):
    print("\n%-26s n=%d" % (name, len(rows)))
    for k in keys:
        v = [r["burden"][k] for r in rows if isinstance(r["burden"].get(k), (int, float))]
        if v:
            print("   %-14s median %7.1f   mean %7.1f" % (k, statistics.median(v),
                                                          statistics.mean(v)))
    for k in ("age_restricted", "sex_restricted"):
        v = [r["burden"][k] for r in rows]
        print("   %-14s %5.0f%% of trials" % (k, 100 * sum(v) / len(v)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--n", type=int, default=400, help="per group")
    args = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "burden-%d.json" % args.n)

    if args.fetch or not os.path.exists(path):
        print("fetching terminated…", file=sys.stderr)
        term = [flatten(s) for s in fetch("TERMINATED", args.n)]
        print("fetching completed…", file=sys.stderr)
        comp = [flatten(s) for s in fetch("COMPLETED", args.n)]
        json.dump({"terminated": term, "completed": comp}, open(path, "w"))
        print("cached -> %s" % path, file=sys.stderr)

    d = json.load(open(path))
    groups = {"accrual-terminated": [], "other-terminated": [], "completed": []}
    for t in d["terminated"]:
        if not t["criteria"]:
            continue
        if ACCRUAL.search(t["why"]):
            groups["accrual-terminated"].append(t)
        elif OTHER.search(t["why"]):
            groups["other-terminated"].append(t)
    for t in d["completed"]:
        if t["criteria"]:
            groups["completed"].append(t)

    for g in groups.values():
        for t in g:
            t["burden"] = burden(t)

    keys = ["n_total", "n_inclusion", "n_exclusion", "n_numeric", "n_groups", "chars"]
    print("=" * 62)
    print("ELIGIBILITY BURDEN vs TRIAL OUTCOME  (public registry data only)")
    print("=" * 62)
    for name in ("accrual-terminated", "other-terminated", "completed"):
        if groups[name]:
            summarise(name, groups[name], keys)

    a, c = groups["accrual-terminated"], groups["completed"]
    if a and c:
        print("\n" + "-" * 62)
        print("ACCRUAL-TERMINATED vs COMPLETED")
        for k in keys:
            va = [r["burden"][k] for r in a]
            vc = [r["burden"][k] for r in c]
            ma, mc = statistics.median(va), statistics.median(vc)
            if mc:
                print("   %-12s %7.1f vs %7.1f   %+.0f%%"
                      % (k, ma, mc, 100 * (ma - mc) / mc))
        print("\n   'other-terminated' is the control: if it looks like completed,")
        print("   the difference is about recruitment, not about dying generally.")

    print("\nSAMPLE accrual failures:")
    for t in a[:5]:
        print("   %s  %2d criteria  %s" % (t["nct"], t["burden"]["n_total"],
                                           t["why"][:58]))


if __name__ == "__main__":
    main()
