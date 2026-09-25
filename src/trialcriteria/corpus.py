"""Build a year-stratified corpus of interventional oncology trials.

Lifted out of the superseded trend analysis (see `attic/`), because the *fetch*
is still needed even though that analysis is not. One request per page of 100,
paged with the registry's own continuation token, written once to the cache.

A full 2008-2024 corpus at 2,000 trials per year is roughly 34,000 studies and
about 90 MB of JSON. It is public registry data and is not redistributed with
this repository: rebuild it with

    trialcriteria fetch-corpus --per-year 2000 --from-year 2008 --to-year 2024
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

from . import config

API = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = ("NCTId,BriefTitle,OverallStatus,EligibilityCriteria,Sex,MinimumAge,"
          "MaximumAge,Phase,Condition,StartDate,StudyType")
ONC = ("cancer OR carcinoma OR neoplasm OR tumor OR lymphoma OR leukemia OR "
       "myeloma OR sarcoma OR melanoma")


def fetch_year(year, n, term_filter=ONC):
    out, token = [], None
    term = ('AREA[StudyType]INTERVENTIONAL AND '
            'AREA[StartDate]RANGE[%d-01-01,%d-12-31] AND (%s)'
            % (year, year, term_filter))
    while len(out) < n:
        q = {"query.term": term, "pageSize": "100", "fields": FIELDS}
        if token:
            q["pageToken"] = token
        url = API + "?" + urllib.parse.urlencode(q, safe="[]")
        req = urllib.request.Request(
            url, headers={"user-agent": config.get("TC_USER_AGENT")})
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=90).read().decode())
        except Exception as e:
            print("  ! %s %s" % (year, e), file=sys.stderr)
            break
        studies = d.get("studies", [])
        if not studies:
            break
        out.extend(studies)
        token = d.get("nextPageToken")
        if not token:
            break
    return out[:n]


def flat(s):
    """The five fields the downstream analyses actually read."""
    p = s.get("protocolSection", {})
    e = p.get("eligibilityModule", {})
    sd = (p.get("statusModule", {}).get("startDateStruct") or {}).get("date", "")
    return {"nct": p.get("identificationModule", {}).get("nctId"),
            "year": int(sd[:4]) if sd[:4].isdigit() else None,
            "criteria": e.get("eligibilityCriteria") or "",
            "phase": ";".join(p.get("designModule", {}).get("phases", []) or []),
            "cond": "; ".join(
                p.get("conditionsModule", {}).get("conditions", [])[:3])}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--per-year", type=int, default=2000)
    ap.add_argument("--from-year", type=int, default=2008)
    ap.add_argument("--to-year", type=int, default=2024)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    out = a.out or config.cache("onc-%d-%d-%d.json"
                                % (a.from_year, a.to_year, a.per_year))
    rows = []
    for year in range(a.from_year, a.to_year + 1):
        got = fetch_year(year, a.per_year)
        rows.extend(flat(s) for s in got)
        print("  %d  %5d studies  (%d total)" % (year, len(got), len(rows)),
              file=sys.stderr)
    rows = [r for r in rows if r["criteria"]]
    json.dump(rows, open(out, "w"))
    print("%d trials with criteria -> %s" % (len(rows), out), file=sys.stderr)
