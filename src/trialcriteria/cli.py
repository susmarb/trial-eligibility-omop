"""Single entry point. `trialcriteria <command> [options]`.

Each command delegates to the module that owns it, so a module stays runnable
and readable on its own.
"""
import sys

USAGE = """trialcriteria <command> [options]

  show NCT01234567         parse one trial's criteria and print the logic tree
  map --nct NCT01234567    anchor each criterion to an OMOP standard concept
  cohort [--build]         execute a cohort against an OMOP CDM
  fetch-corpus             build the year-stratified trial corpus (slow, ~90 MB)
  strictness [--limit N]   three-way exclusion classification over the corpus
  validate --n 90          draw a stratified sample for hand-validation
  config                   print every resolved setting and where it came from

Start with `trialcriteria show NCT03432533`: it needs nothing but a network
connection, and it is the part of this repository that matters most.
"""


def _show(argv):
    from . import ctgov
    from . import tree as CT
    nct = argv[0] if argv else "NCT03432533"
    tr = ctgov.trial(nct)
    if not tr:
        raise SystemExit("no such trial, or it publishes no criteria: %s" % nct)
    print("%s — %s\n" % (nct, tr["title"]))
    t = CT.parse(tr["criteria"])
    for section in ("inclusion", "exclusion"):
        print("== %s ==" % section.upper())
        print(t[section].show(), end="")
        print("   leaves: %d\n" % len(list(t[section].leaves())))


def _config(argv):
    import os

    from . import config
    print("resolved configuration (environment > .env > default)\n")
    for k, v in config.describe().items():
        origin = "env" if os.environ.get(k) else "default/.env"
        print("  %-30s %-12s %s" % (k, "[" + origin + "]", v or "(unset)"))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]
    # the delegated mains parse sys.argv themselves
    sys.argv = ["trialcriteria " + cmd] + rest
    if cmd == "show":
        _show(rest)
    elif cmd == "config":
        _config(rest)
    elif cmd == "map":
        from . import omop
        omop.main()
    elif cmd == "cohort":
        from . import cohort
        cohort.main()
    elif cmd == "fetch-corpus":
        from . import corpus
        corpus.main()
    elif cmd == "strictness":
        from . import strictness
        strictness.main()
    elif cmd == "validate":
        from . import validate
        validate.main()
    else:
        print(USAGE)
        raise SystemExit("unknown command: %s" % cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
