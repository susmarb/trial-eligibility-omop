#!/usr/bin/env python3
"""Did cancer trial eligibility actually broaden after the 2017 guidance?

ASCO and Friends of Cancer Research, then FDA, recommended that cancer trials stop
routinely excluding patients for brain metastases, HIV/HBV/HCV, prior or concurrent
malignancies, mild organ dysfunction, and age. Everyone agrees it was right.
**Nobody has measured whether protocols changed**, because it requires parsing the
eligibility criteria of thousands of trials.

We can parse them (`criteria_tree.py`). So:

    prevalence of each TARGETED exclusion, by trial start year, in oncology trials
    versus the same for UNTARGETED criteria, which should not move

The second half is the control and it is the whole point. If everything drifts
together the finding is about protocols getting shorter, not about the guidance.
Pre-registered prediction: targeted exclusions fall after 2017; control criteria flat.

    python3 eligibility_trend.py --fetch --per-year 400
    python3 eligibility_trend.py                       # analyse the cache

Public registry data. No patients, no permissions, no secure environment.
"""
import argparse
import collections
import json
import os
import re
import sys
import urllib.parse
import urllib.request

import criteria_tree as CT

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ctg-cache")
API = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = ("NCTId,BriefTitle,OverallStatus,EligibilityCriteria,Sex,MinimumAge,"
          "MaximumAge,Phase,Condition,StartDate,StudyType")

# --- the criteria the 2017 guidance explicitly targeted
TARGETED = {
    "brain metastases": r"(?i)\b(brain|cns|cerebral|leptomening)\w*\s+(metasta|involv|"
                        r"lesion|disease)|\bmetasta\w*\s+to\s+the\s+(brain|cns)",
    "HIV / hepatitis": r"(?i)\b(hiv|human immunodeficiency|hepatitis\s*[bc]\b|hbv|hcv)\b",
    "prior malignancy": r"(?i)\b(prior|previous|second|other|concurrent|history of)\s+"
                        r"(\w+\s+){0,2}(malignan|cancer|neoplasm|carcinoma)",
    "organ function (renal)": r"(?i)\b(creatinine|egfr|gfr|creatinine clearance)\b",
    "organ function (hepatic)": r"(?i)\b(bilirubin|\bast\b|\balt\b|transaminase|sgot|sgpt)\b",
}
# --- criteria the guidance did NOT address: the control
CONTROL = {
    "informed consent": r"(?i)\binformed consent\b",
    "pregnancy": r"(?i)\b(pregnan|breast[- ]?feed|lactat)\w*",
    "performance status": r"(?i)\b(ecog|karnofsky|kps|performance status)\b",
    "contraception": r"(?i)\bcontracept\w*|childbearing potential",
    "measurable disease": r"(?i)\b(recist|measurable disease|evaluable disease)\b",
}
ALL = {**{k: (v, "targeted") for k, v in TARGETED.items()},
       **{k: (v, "control") for k, v in CONTROL.items()}}
COMPILED = {k: (re.compile(v), grp) for k, (v, grp) in ALL.items()}

ONC = ("cancer OR carcinoma OR neoplasm OR tumor OR lymphoma OR leukemia OR "
       "myeloma OR sarcoma OR melanoma")


def fetch_year(year, n):
    out, token = [], None
    term = (f'AREA[StudyType]INTERVENTIONAL AND '
            f'AREA[StartDate]RANGE[{year}-01-01,{year}-12-31] AND ({ONC})')
    while len(out) < n:
        q = {"query.term": term, "pageSize": "100", "fields": FIELDS}
        if token:
            q["pageToken"] = token
        url = API + "?" + urllib.parse.urlencode(q, safe="[]")
        req = urllib.request.Request(url, headers={"user-agent": "trial-eligibility-omop/0.1"})
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=90).read().decode())
        except Exception as e:
            print("  ! %s %s" % (year, e), file=sys.stderr)
            break
        s = d.get("studies", [])
        if not s:
            break
        out.extend(s)
        token = d.get("nextPageToken")
        if not token:
            break
    return out[:n]


def flat(s):
    p = s.get("protocolSection", {})
    e = p.get("eligibilityModule", {})
    sd = (p.get("statusModule", {}).get("startDateStruct") or {}).get("date", "")
    return {"nct": p.get("identificationModule", {}).get("nctId"),
            "year": int(sd[:4]) if sd[:4].isdigit() else None,
            "criteria": e.get("eligibilityCriteria") or "",
            "phase": ";".join(p.get("designModule", {}).get("phases", []) or []),
            "cond": "; ".join(p.get("conditionsModule", {}).get("conditions", [])[:3])}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--per-year", type=int, default=400)
    ap.add_argument("--from-year", type=int, default=2010)
    ap.add_argument("--to-year", type=int, default=2024)
    args = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "onc-%d-%d-%d.json" % (args.from_year, args.to_year,
                                                      args.per_year))

    if args.fetch or not os.path.exists(path):
        allrows = []
        for y in range(args.from_year, args.to_year + 1):
            rows = [flat(s) for s in fetch_year(y, args.per_year)]
            rows = [r for r in rows if r["criteria"] and r["year"] == y]
            allrows.extend(rows)
            print("  %d: %d trials" % (y, len(rows)), file=sys.stderr)
        json.dump(allrows, open(path, "w"))
        print("cached %d -> %s" % (len(allrows), path), file=sys.stderr)

    rows = json.load(open(path))
    by_year = collections.defaultdict(list)
    for r in rows:
        by_year[r["year"]].append(r)

    # presence of each criterion type, per trial, per year
    pres = collections.defaultdict(lambda: collections.Counter())
    nleaf = collections.defaultdict(list)
    inc_pres = collections.defaultdict(lambda: collections.Counter())
    for y, rs in by_year.items():
        for r in rs:
            tree = CT.parse(r["criteria"])
            leaves = list(tree["inclusion"].leaves()) + list(tree["exclusion"].leaves())
            nleaf[y].append(len(leaves))
            # the claim is about EXCLUSION criteria: mentioning brain metastases in
            # an inclusion criterion ("must have brain metastases") is the opposite.
            exc_text = " \n ".join(l.text for l in tree["exclusion"].leaves())
            inc_text = " \n ".join(l.text for l in tree["inclusion"].leaves())
            for name, (rx, _) in COMPILED.items():
                if rx.search(exc_text):
                    pres[y][name] += 1
                if rx.search(inc_text):
                    inc_pres[y][name] += 1

    years = sorted(by_year)
    print("\n" + "=" * 92)
    print("ONCOLOGY TRIAL ELIGIBILITY BY START YEAR — did the 2017 guidance change protocols?")
    print("=" * 92)
    print("%-26s %s" % ("criterion", " ".join("%5d" % y for y in years)))
    print("%-26s %s" % ("n trials", " ".join("%5d" % len(by_year[y]) for y in years)))
    print("-" * 92)

    def row(name):
        return [100 * pres[y][name] / max(len(by_year[y]), 1) for y in years]

    def pre_post(name):
        pre = [v for y, v in zip(years, row(name)) if y <= 2016]
        post = [v for y, v in zip(years, row(name)) if y >= 2019]
        if not pre or not post:
            return None
        return sum(pre) / len(pre), sum(post) / len(post)

    for grp, label in (("targeted", "TARGETED BY THE 2017 GUIDANCE"),
                       ("control", "NOT TARGETED (control)")):
        print("\n  %s" % label)
        for name, (_, g) in ALL.items():
            if g != grp:
                continue
            vals = row(name)
            print("  %-24s %s" % (name, " ".join("%4.0f%%" % v for v in vals)))
        print("  %-24s %s" % ("", ""))

    print("\n" + "-" * 92)
    print("PRE-2017 (≤2016) vs POST (≥2019) MEAN PREVALENCE")
    print("%-26s %>8s %>8s %>9s".replace("%>", "%") % ("criterion", "pre", "post", "change"))
    for grp in ("targeted", "control"):
        print("  -- %s" % grp)
        for name, (_, g) in ALL.items():
            if g != grp:
                continue
            pp = pre_post(name)
            if not pp:
                continue
            a, b = pp
            arrow = "DOWN" if b < a - 2 else ("UP" if b > a + 2 else "flat")
            print("  %-24s %7.1f%% %7.1f%%  %+6.1f  %s" % (name, a, b, b - a, arrow))

    med = {y: sorted(nleaf[y])[len(nleaf[y]) // 2] if nleaf[y] else 0 for y in years}
    print("\n  median criteria per trial: %s"
          % " ".join("%d:%d" % (y, med[y]) for y in years))
    print("\n  SANITY: same criterion appearing in INCLUSION text (should be rare for")
    print("  brain mets / HIV; a high number means the regex is catching the wrong thing)")
    for name in ("brain metastases","HIV / hepatitis","prior malignancy"):
        v=[100*inc_pres[y][name]/max(len(by_year[y]),1) for y in years]
        print("  %-24s %s" % (name, " ".join("%4.0f%%" % x for x in v)))

    print("\n  Prediction under test: targeted exclusions fall after 2017, control flat.")
    print("  If BOTH fall, the finding is protocols getting shorter, not the guidance.")


if __name__ == "__main__":
    main()
