#!/usr/bin/env python3
"""Map parsed eligibility criteria onto OMOP standard concepts.

This is what turns the corpus from *descriptive* (here is what criteria say)
into *executable* (here is a cohort definition any OMOP CDM can run).

The architecture is the one that keeps winning: **retrieve candidates, then
decide** — never generate. OHDSI's vocabulary supplies real concepts; the
decision model only picks among them, so it cannot invent a `concept_id` that
does not exist. That is a hard safety property, not a prompt instruction.

    criterion text ─▶ key clinical phrase (regex)
                  ─▶ OHDSI WebAPI concept search      (candidates, real ids)
                  ─▶ typed decision: which candidate   (choice over candidates)
                  ─▶ leaf becomes {concept_id, domain, comparator, value}

Prior art, stated plainly: **OHDSI Criteria2Query** already turns free-text
inclusion criteria into OMOP cohort definitions. The difference here is the
output shape. Criteria2Query produces a cohort query; this preserves the
**logic tree** (AND / OR / n-of-m, nesting intact) so a single patient can be
evaluated criterion-by-criterion with an auditable reason, rather than only
counted in or out of a cohort.

Vocabulary access is the public OHDSI demo WebAPI, which is rate-limited and
not for bulk work. For a real run, load Athena locally.

    trialcriteria map --nct NCT03432533        # map one trial
    trialcriteria map --nct NCT04060368        # a trial with lab thresholds
"""
import argparse
import difflib
import json
import re
import time
import urllib.parse
import urllib.request

from . import classifier, config, ctgov
from . import tree as CT

# endpoint is configuration, never a literal: see trialcriteria/config.py
WEBAPI = config.get("TC_WEBAPI")

# comparator + value, so a threshold survives as a predicate rather than prose
COMP = re.compile(
    r"(?P<op>≥|>=|≤|<=|>|<|at least|no more than|not exceed|greater than|less than)"
    r"\s*(?P<val>[\d,]+(?:\.\d+)?)\s*(?P<unit>%|mg/dL|mmol/L|g/dL|/mm3|10\^?9/L|"
    r"x\s*ULN|×\s*ULN|mL/min|years?|months?|weeks?|days?)?", re.I)
OPMAP = {"≥": ">=", ">=": ">=", "at least": ">=", "greater than": ">",
         ">": ">", "≤": "<=", "<=": "<=", "no more than": "<=",
         "not exceed": "<=", "less than": "<", "<": "<"}

# the clinically meaningful noun phrase to look up, per criterion
PHRASE = [
    (r"(?i)\b(brain|cns|cerebral|leptomeningeal)\s+metasta\w*",
     "secondary malignant neoplasm of brain", ["Condition"]),
    (r"(?i)\b(hiv|human immunodeficiency virus)\b",
     "human immunodeficiency virus infection", ["Condition"]),
    (r"(?i)\bhepatitis\s*b\b|\bhbv\b", "viral hepatitis B", ["Condition"]),
    (r"(?i)\bhepatitis\s*c\b|\bhcv\b", "viral hepatitis C", ["Condition"]),
    (r"(?i)\bplatelet\w*", "platelet count", ["Measurement"]),
    (r"(?i)\b(neutrophil|anc)\b", "neutrophil count", ["Measurement"]),
    (r"(?i)\b(h(a)?emoglobin|hgb)\b", "hemoglobin", ["Measurement"]),
    (r"(?i)\bcreatinine clearance\b", "creatinine clearance", ["Measurement"]),
    (r"(?i)\bcreatinine\b", "creatinine", ["Measurement"]),
    (r"(?i)\bbilirubin\b", "bilirubin", ["Measurement"]),
    (r"(?i)\b(ast|aspartate aminotransferase|sgot)\b",
     "aspartate aminotransferase", ["Measurement"]),
    (r"(?i)\b(alt|alanine aminotransferase|sgpt)\b", "alanine aminotransferase", ["Measurement"]),
    (r"(?i)\becog\b|performance status", "ECOG performance status", ["Measurement", "Observation"]),
    (r"(?i)\bejection fraction|lvef\b", "ejection fraction", ["Measurement"]),
    (r"(?i)\bpregnan\w*", "pregnancy", ["Condition"]),
    (r"(?i)\b(prior|second|other)\s+\w*\s*malignan\w*",
     "malignant neoplastic disease", ["Condition"]),
]
PHRASE = [(re.compile(p), q, d) for p, q, d in PHRASE]


STOP = set("""a an the of to in on for with without and or not no any all patients
patient subject subjects must has have had is are be been who whom which that
at least more than greater less prior previous other within days weeks months
years age aged time study trial screening baseline randomization visit per as
by from documented known history evidence signed provided able willing during
if unless except including such this these those their there will would may can
assessed determined investigator opinion adequate clinically significant""".split())

def generic_phrase(text, nwords=3):
    """Fallback: the leading content words of the criterion, as a search term."""
    t = re.sub(r"[^A-Za-z0-9 \-]", " ", text.lower())
    words = [w for w in t.split() if w not in STOP and len(w) > 3 and not w.isdigit()]
    return " ".join(words[:nwords]) if len(words) >= 2 else None


def webapi_search(term, domains=None, n=8, timeout=60):
    """Filtered concept retrieval.

    The naive GET /vocabulary/search/<term> is a lexical match over every concept
    name, standard or not, and returns menus like "13 weeks gestation of
    pregnancy" for "pregnancy". POST returns the full result set, which we then
    restrict to **valid standard concepts** in the expected domain and rank by
    name similarity. Candidate quality is the whole game: the model can only be
    as right as the menu it is given."""
    req = urllib.request.Request(
        WEBAPI + "/vocabulary/search",
        data=json.dumps({"QUERY": term}).encode(),
        headers={"Content-Type": "application/json", "accept": "application/json",
                 "user-agent": config.get("TC_USER_AGENT")}, method="POST")
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
    except Exception:
        return []
    out = [c for c in d if c.get("STANDARD_CONCEPT") == "S"
           and c.get("INVALID_REASON") == "V"]
    if domains:
        out = [c for c in out if c["DOMAIN_ID"] in domains]
    t = term.lower()
    out.sort(key=lambda c: (-difflib.SequenceMatcher(
        None, t, c["CONCEPT_NAME"].lower()).ratio(), len(c["CONCEPT_NAME"])))
    return [{"concept_id": c["CONCEPT_ID"], "name": c["CONCEPT_NAME"],
             "domain": c["DOMAIN_ID"], "vocab": c["VOCABULARY_ID"],
             "standard": c["STANDARD_CONCEPT"]} for c in out[:n]]


def load_agent():
    """The configured local classifier (see trialcriteria/classifier.py)."""
    return classifier.load()


def map_leaf(leaf_text, section, agent, cache):
    """One criterion -> an OMOP-anchored predicate, or None."""
    phrase, domains = None, None
    for rx, q, d in PHRASE:
        if rx.search(leaf_text):
            phrase, domains = q, d
            break
    if not phrase:
        phrase = generic_phrase(leaf_text)
    if not phrase:
        return None

    if phrase not in cache:
        cache[phrase] = webapi_search(phrase, domains)
        time.sleep(0.35)                       # public demo instance: be polite
    cands = cache[phrase]
    if not cands:
        return None

    # the model only ever CHOOSES among real concepts
    options = {"%d | %s (%s)" % (c["concept_id"], c["name"][:60], c["domain"]): ""
               for c in cands}
    options["none of these"] = "No listed concept matches this criterion."
    pick = agent.predict(
        "CRITERION (%s section): %s" % (section, leaf_text[:400]),
        {"concept": {"type": "choice",
                     "instructions": ("Which OMOP concept does this eligibility "
                                      "criterion refer to? Choose the concept that "
                                      "names the clinical entity being tested."),
                     "criteria": list(options)}})["answers"]["concept"]
    if pick["choice"] == "none of these":
        return None
    cid = int(pick["choice"].split("|")[0].strip())
    chosen = next((c for c in cands if c["concept_id"] == cid), None)
    if not chosen:
        return None

    m = COMP.search(leaf_text)
    pred = None
    if m:
        pred = {"op": OPMAP.get(m.group("op").lower(), m.group("op")),
                "value": float(m.group("val").replace(",", "")),
                "unit": (m.group("unit") or "").strip() or None}
    return {"text": leaf_text[:160], "section": section, "concept": chosen,
            "predicate": pred, "confidence": pick.get("confidence")}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nct", default="NCT03432533")
    ap.add_argument("--json", metavar="FILE")
    args = ap.parse_args()

    tr = ctgov.trial(args.nct)
    if not tr:
        raise SystemExit("no such trial")
    tree = CT.parse(tr["criteria"])
    agent, cache = load_agent(), {}

    print("%s — %s\n" % (args.nct, tr["title"][:80]))
    mapped, total = [], 0
    for section in ("inclusion", "exclusion"):
        for lf in tree[section].leaves():
            total += 1
            r = map_leaf(lf.text, section, agent, cache)
            if r:
                mapped.append(r)

    print("%d of %d criteria anchored to an OMOP concept\n" % (len(mapped), total))
    print("%-9s %-10s %-34s %-13s %s" % ("section", "concept", "name", "domain", "predicate"))
    print("-" * 104)
    for r in mapped:
        c, p = r["concept"], r["predicate"]
        pred = "%s %g %s" % (p["op"], p["value"], p["unit"] or "") if p else "—"
        print("%-9s %-10d %-34s %-13s %s"
              % (r["section"][:9], c["concept_id"], c["name"][:34], c["domain"][:13], pred))
    print("\nEvery concept_id above came from the OHDSI vocabulary. The model chose")
    print("among retrieved candidates and could not invent one.")
    if args.json:
        json.dump(mapped, open(args.json, "w"), indent=1)
