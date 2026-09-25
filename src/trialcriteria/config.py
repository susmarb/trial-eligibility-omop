"""Runtime configuration. Nothing machine-specific is hardcoded anywhere else.

Every path and endpoint is resolved here, in this order:

    1. an environment variable
    2. a `.env` file in the repository root (KEY=value, `#` comments)
    3. a documented default

Rationale: the first version of this code carried absolute paths to one
developer's machine inside two modules. That is the single most common reason a
research repository does not run for the second person who clones it.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DEFAULTS = {
    # where cached corpora, model output and the SQLite CDM live
    "TC_CACHE": os.path.join(ROOT, ".cache"),
    # OHDSI vocabulary service. The public demo instance is rate limited and is
    # someone else's server: load Athena locally for anything bulk.
    "TC_WEBAPI": "https://atlas-demo.ohdsi.org/WebAPI",
    # unpacked OMOP CDM in CSV form (see `make cdm`)
    "TC_CDM_DIR": os.path.join(ROOT, ".cache", "cdm", "GiBleed_5.3"),
    # local classifier: an importable module and a model identifier
    "TC_CLASSIFIER_MODULE": "laya_mlx",
    "TC_CLASSIFIER_MODEL": "aac6fef/laya-mlx",
    # optional: a site-packages directory to prepend to sys.path, for a model
    # installed in a separate virtualenv from the one running this code
    "TC_CLASSIFIER_SITE_PACKAGES": "",
    "TC_USER_AGENT": "trial-eligibility-omop/0.1 (research; contact in README)",
}

_dotenv_loaded = False


def _load_dotenv():
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get(key):
    """Resolved value for one configuration key."""
    _load_dotenv()
    if key not in _DEFAULTS:
        raise KeyError("unknown configuration key: %s" % key)
    return os.environ.get(key) or _DEFAULTS[key]


def cache(*parts):
    """A path inside the cache directory, whose parent is created."""
    p = os.path.join(get("TC_CACHE"), *parts)
    os.makedirs(os.path.dirname(p) or p, exist_ok=True)
    return p


def describe():
    """Every resolved setting, for `trialcriteria config`."""
    return {k: get(k) for k in sorted(_DEFAULTS)}
