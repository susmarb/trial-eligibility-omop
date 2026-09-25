# The blocking task

`strictness-sample-unmarked.txt` holds **74 classifications drawn by
`trialcriteria validate`**, stratified by label and by confidence band. Nobody
has marked them.

Until they are marked, the classifier's accuracy is unmeasured and every number
resting on it is provisional. This is the single thing blocking a write-up.

## How to mark it

Each item shows a criterion sentence and the label the model assigned. Write `Y`
if the label is right, `N` if it is wrong, `?` if the sentence genuinely does not
resolve. Then count.

The judgement is **grammatical, not clinical**. The question is whether the
sentence carries an escape hatch:

| label | the sentence says |
|---|---|
| wholly excluded | anyone with the condition is barred, no route back in |
| conditional | barred *unless / except / provided that / eligible if* something holds |
| not an exclusion | the sentence does not exclude for this condition at all |

Most resolve on a single reading. A clinical reader is welcome but is not
required, and asking a trials coordinator to spend an hour on it is a reasonable
request.

## What the answer feeds

Accuracy, and per-label accuracy, go in the methods section of anything written
about the strictness trend. If accuracy differs by label, the trend has to be
corrected for it, because the finding *is* a shift between two of the labels.

## Note on confidence

In the full run, **165 of 32,919 classifications exceeded 0.7 confidence**, half
a percent, while the labels were largely correct on inspection. Confidence
thresholding is therefore unusable on this task, which matters because
calibration is the headline claim for this class of model. Do not filter the
sample by confidence, and do not assume a low-confidence item is a wrong one:
that assumption is exactly what the marking is there to test.
