# attic — analyses that were run and did not survive

These are kept so that nobody repeats them. They are **not** a backlog. Each one
was taken far enough to get an answer, and the answer was no.

None of them are imported by the package. They still carry their original
top-level imports (`criteria_tree`, `.ctg-cache` paths) and will not run as they
stand. That is deliberate: reviving one is a decision, not an accident.

## `eligibility_trend.py` — superseded, and wrong in an interesting way

Measured the **presence or absence** of targeted criteria by year. That cannot
distinguish

    "Patients with HIV are excluded."                      excluded
    "HIV-positive patients with CD4 > 350 are eligible."   conditional

so it counted a field becoming *more* inclusive as becoming *stricter*, and
reported HIV exclusions rising. The three-way classification in
`strictness.py` replaces it.

Its bulk fetch was worth keeping and now lives in `trialcriteria/corpus.py`.

## `criteria_burden.py`, `criteria_killers.py` — criteria burden and accrual failure

The hypothesis was that trials with more or stricter criteria terminate for poor
accrual more often. It looked strong at n=400, weakened at n=5,000, and
**disappeared entirely** once trials were matched on indication: among
non-oncology trials, those terminated for accrual carried 17 criteria and those
terminated for other reasons also carried 17. The headline number, a 2.20x odds
ratio on performance status, was an oncology confound.

Do not re-run this at a larger n. The problem was never statistical power.

## One result from this line that did hold

Threshold *values* are frozen. Across 17 years, seven common laboratory
thresholds have identical medians every single year: platelets 100k, ANC 1.5k,
creatinine clearance 50, bilirubin 1.5x ULN, AST/ALT 2.5x ULN, life expectancy 3
months. Median criteria per trial went from 18 in 2008 to 17 in 2024. The numbers
are inherited, not chosen. That is a real finding and cheap to firm up.
