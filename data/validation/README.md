# Manual annotation and validation

`strictness-sheet-unmarked.txt` contains 74 items selected for manual review,
stratified by the model’s label and confidence band. The sheet is awaiting human
annotation.

In this step, a person independently assigns a label to each criterion. These
annotations are then compared with the classifier’s predictions to assess its
accuracy. Until this assessment is complete, findings based on those predictions
remain preliminary.

## How to annotate the sheet

Read each criterion and write `W`, `C`, `N` or `?` on its `you:` line.

| Label | Meaning |
|---|---|
| **W** wholly excluded | The sentence excludes people with the condition without stating an exception. |
| **C** conditional | Participation is possible under stated conditions, often introduced by *unless*, *except*, *provided that* or *eligible if*. |
| **N** not an exclusion | The sentence does not exclude people on the basis of this condition. |
| **?** unresolved | The sentence alone does not provide enough information to assign a label. |

The review concerns the wording of the criterion rather than a clinical decision
about a patient. Look for conditions or exceptions that affect participation.
Use `?` where the wording is unclear; these items are recorded separately.

Please assign labels independently, without consulting the model’s answer key
or looking up the trial. The annotations should be provided by a person rather
than another model.

## How the sheet is prepared

The sheet is blinded: predictions are stored in a separate answer key so they
do not influence the reviewer’s labels. An earlier version displayed the model’s
answer alongside each item and is no longer used for validation.

The criterion text is recovered by re-parsing the source trial. This preserves
qualifying clauses that may have been omitted from the earlier 160-character
excerpts, including exceptions introduced near the end of a sentence.

For criteria longer than the classifier’s 400-character input window, the sheet
marks where the model’s input ended. The scoring report identifies disagreements
among these longer items for further review. Such a disagreement may relate to
missing context, but length alone does not establish its cause.

## Scoring the annotations

Keep a working copy of the sheet for your annotations. Once it has been reviewed,
compare it with the exact answer key generated for that sheet:

```bash
trialcriteria score marked-sheet.txt --key /path/to/matching-key.json
```

Replace the file paths with those for your marked sheet and its matching key.
The key is stored separately and is not included with the supplied sheet. A key
from a different sample cannot be substituted.

You can annotate the `you:` lines directly or provide a numbered list of answers,
such as `12 C`. Unresolved and unanswered items are reported separately.

## Interpreting the results

The report includes sample accuracy with a Wilson confidence interval, results
for each human-assigned label, and a confusion matrix showing how human labels
compare with model predictions. Differences between “wholly excluded” and
“conditional” are particularly relevant to the exclusion-wording analysis.

Because the sample is stratified by model label and confidence band, its overall
accuracy is not automatically representative of the full corpus. Review the
per-label results, unresolved items and input-window limitations alongside the
overall percentage.

## Reviewing confidence scores

In the original analysis, 165 of 32,919 classifications had confidence scores
above 0.7. The relationship between these scores and correctness still needs to
be assessed. The scoring report groups results by confidence band to support
that comparison; a low score does not necessarily mean that a label is wrong.
