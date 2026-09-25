"""Clinical trial eligibility criteria: parse, map to OMOP, execute as a cohort.

    tree        criteria text -> logic tree (AND / OR / n-of-m), Kleene evaluation
    ctgov       ClinicalTrials.gov API v2 client, cached
    corpus      bulk fetch of a year-stratified trial corpus
    omop        leaf -> OMOP standard concept, by retrieval + constrained choice
    cohort      an OMOP-anchored tree executed as SQL against a CDM
    classifier  local non-generative classifier, loaded from configuration
    strictness  three-way exclusion classification over a corpus
    validate    stratified hand-validation sampler
"""
__version__ = "0.1.0"
