"""The local, non-generative classifier: one loader, configured in one place.

The model is asked *typed* questions and returns a choice from a supplied option
set with a probability. It generates no text, so it cannot return a value that is
not on the list. That property is what makes the output safe to compose in code.

Any classifier exposing

    agent.predict(text, {name: {"type": "choice",
                                "instructions": str,
                                "criteria": [option, ...]}})
        -> {"answers": {name: {"choice": str, "confidence": float}}}

is a drop-in replacement. Set TC_CLASSIFIER_MODULE and TC_CLASSIFIER_MODEL.

Hardware note: the reference implementation is MLX and needs Apple Silicon and a
native arm64 Python. A Python running under Rosetta reports x86_64 and cannot
install mlx; `python3 -c "import platform; print(platform.machine())"` must say
`arm64`. If the model lives in its own virtualenv, point
TC_CLASSIFIER_SITE_PACKAGES at that environment's site-packages instead of
merging the two environments.
"""
import importlib
import sys

from . import config

_agent = None


def load(force=False):
    """The configured classifier, loaded once per process."""
    global _agent
    if _agent is not None and not force:
        return _agent
    extra = config.get("TC_CLASSIFIER_SITE_PACKAGES")
    if extra and extra not in sys.path:
        sys.path.insert(0, extra)
    module = config.get("TC_CLASSIFIER_MODULE")
    try:
        mod = importlib.import_module(module)
    except ImportError as e:
        raise SystemExit(
            "cannot import classifier module %r (%s).\n"
            "Set TC_CLASSIFIER_MODULE, or TC_CLASSIFIER_SITE_PACKAGES if the "
            "model lives in another virtualenv. See README, 'The classifier'."
            % (module, e)) from e
    _agent = mod.load(config.get("TC_CLASSIFIER_MODEL"))
    return _agent


def ask(text, question):
    """One typed question. Returns the answer dict for the single key given."""
    name = next(iter(question))
    return load().predict(text, question)["answers"][name]
