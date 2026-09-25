"""ClinicalTrials.gov API v2 client. Everything is cached on disk.

One trial is one JSON file under the cache, so a re-run costs nothing and the
registry is queried once per study. The registry is public data: no credentials,
no patient records, no restricted environment.
"""
import json
import os
import re
import urllib.error
import urllib.request

from . import config

STUDY = "https://clinicaltrials.gov/api/v2/studies/%s"


def _get(url, path, timeout=60):
    if os.path.exists(path):
        return open(path, encoding="utf-8", errors="replace").read()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    req = urllib.request.Request(
        url, headers={"user-agent": config.get("TC_USER_AGENT")})
    txt = urllib.request.urlopen(req, timeout=timeout).read().decode(
        "utf-8", "replace")
    open(path, "w", encoding="utf-8").write(txt)
    return txt


def trial(nct):
    """Eligibility criteria plus demographics for one NCT id, or None."""
    path = config.cache("trials", "%s.json" % nct)
    try:
        raw = _get(STUDY % nct, path)
    except urllib.error.HTTPError:
        return None
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    p = d.get("protocolSection", {})
    e = p.get("eligibilityModule", {})
    crit = e.get("eligibilityCriteria") or ""
    if not crit:
        return None
    return {
        "nct_id": nct,
        "title": p.get("identificationModule", {}).get("briefTitle"),
        "condition": "; ".join(
            p.get("conditionsModule", {}).get("conditions", [])[:6]),
        "sex": e.get("sex"),
        "min_age": e.get("minimumAge"),
        "max_age": e.get("maximumAge"),
        "accepts_healthy": e.get("healthyVolunteers"),
        "criteria": re.sub(r"\n{3,}", "\n\n", crit)[:6000],
    }
