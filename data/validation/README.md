# The blocking task

`strictness-sheet-unmarked.txt` holds **74 classifications drawn by
`trialcriteria validate`**, stratified by label and by confidence band. Nobody
has marked them.

Until they are marked, the classifier's accuracy is unmeasured and every number
resting on it is provisional. This is the single thing blocking a write-up.

## How to mark it

Each item shows a criterion. Write `W`, `C`, `N` or `?` on its `you:` line.

| | the sentence says |
|---|---|
| **W** wholly excluded | anyone with the condition is barred, no route back in |
| **C** conditional | barred *unless / except / provided that / eligible if* something holds |
| **N** not an exclusion | this sentence does not exclude for that condition at all |
| **?** | genuinely unresolvable from the sentence alone |

The judgement is **grammatical, not clinical**: does the sentence carry an escape
hatch? Most resolve on one reading. A handful of `?` is a result, not a failure.
Do not look the trial up; the classifier could not either.

Then:

```bash
trialcriteria score strictness-sheet-unmarked.txt
```

Marks are read as `<number> <letter>`, so marking the sheet in place and writing
a bare list of answers both work.

## Two properties this sheet has, and why

**It is blinded.** The model's answer is not on the sheet; it goes to a separate
answer key at draw time. An annotator shown a label agrees with it more often
than one who is not, so an unblinded sheet measures suggestibility rather than
accuracy. An earlier version of this file printed `model says: conditional` next
to every item and should not have been marked.

**It carries the full criterion.** The stored classification keeps a truncated
copy, and the truncation falls at the *end* of the sentence, which is exactly
where the escape hatch lives. Marking from it was biased against the conditional
label, the one the whole finding rests on. The full text is recovered by
re-parsing the source trial, which needs no model run.

Where a criterion runs past the classifier's own 400-character input window, the
sheet marks the cut point. Text past it was never shown to the model, so a
disagreement there is a **window problem, not a classifier error**, and `score`
counts the two separately.

## What the answer feeds

Overall accuracy with a Wilson interval, accuracy per label, and the confusion
matrix. The confusion matrix matters most: the finding *is* a shift between
wholly-excluded and conditional, so a systematic confusion between exactly those
two labels could produce the entire trend on its own. `score` calls that case out
by name.

## Note on confidence

In the full run, **165 of 32,919 classifications exceeded 0.7 confidence**, half
a percent, while the labels were largely correct on inspection. Confidence
thresholding looks unusable on this task, which matters because calibration is
the headline claim for this class of model. `score` reports accuracy by band so
that claim gets tested rather than assumed. Do not treat a low-confidence item as
a wrong one: that assumption is what the marking exists to check.
