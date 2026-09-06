# The Grade Says Little, the Score Orders: AI Reviewer Panels Against a Venue's Ratings and Decisions -- release bundle

Artifacts for the paper of that title, submitted anonymously to the NeurIPS 2026 AI-Native Academia workshop.
Everything needed to recheck every number in it is here, and one script does the rechecking.

## Start here

    python3 reproduce.py

Standard library only, no network, a few minutes. It reads *only this directory*, recomputes the paper's
numbers from the review files up, prints one line per number against the value the paper prints, and exits
non-zero if any of them disagrees. If it prints all ok, the paper's arithmetic is confirmed against its own
data by code that shares nothing with the code that produced the paper.

Two disagreements it found are worth knowing about, because both are conventions rather than errors: the
composite can only agree with `calibration/calibration_params_portable.json` to that file's four-decimal
rounding, and a p90 over sixteen values is a choice of order statistic (the paper's Appendix A states which,
and what the interpolating convention would give instead).

## What is here

    reproduce.py                    recomputes the paper's numbers from this tree, and fails if any disagree
    instrument/                     the reviewer prompt, the metric schema, the parser, the runner, the gate,
                                    and slots.json / slots_cursor8.json -- both rosters, WITH effort tiers
    calibration/                    the frozen mu/sd each roster's composite is a z-score against, and the
                                    arXiv ids of the 16 published papers they were fitted on
    reviews/accepted/               160 reviews of those 16 published papers, in full
    reviews/rejected/               320 reviews of 32 declined submissions, R01--R32, SCORES ONLY (see below)
    reviews/transform/              470 reviews of the presentation-transform variants
    reviews/transform_rejected/     790 reviews of the same transforms applied to the declined
                                    submissions, R01--R32, SCORES ONLY -- the arm that takes the presentation
                                    result from 16 papers to 48, each paper's variant and baselines in one sitting
    reviews/drift_5model/           560 five-model reviews inside the variants' own sitting: every
                                    baseline text four times and each variant once, so the transform contrast
                                    can be taken with no session boundary in it rather than corrected for one
    reviews/dayrep_5model/          160 five-model reviews of the eight papers the figure arm's effect
                                    sits in, re-scored one day later -- the arm that tells a paper set apart
                                    from a sitting
    reviews/vendor_panel/           256 reviews of the same 16 papers by a second roster: eight slots,
                                    six vendors, its own calibration
    reviews/vendor_transform/       192 second-roster reviews of the same transform variants
    reviews/vendor_drift/           64 second-roster reviews of UNTOUCHED text, scored in the variant
                                    sessions -- the control the transform deltas are corrected against
    data/                           the analysis outputs the paper's figures and tables were built from,
                                    including extract_corpus.json: per corpus paper, what the text supplied to
                                    the reviewer lost against the submitted document, and per review, whether
                                    it charged a property of that text and what composite it gave
    frame/                          every ICLR 2026 submission with the venue's own outcome label, 19,814 rows
    scripts/                        the analysis, figure, transform, de-identification and audit scripts
    logs/                           run logs
    SOURCES.md                      how to regenerate every scored text, with checksums
    MANIFEST.sha256                 sha256sum -c MANIFEST.sha256

## The carve-outs, and what they do not buy

**The 32 declined submissions.** They are third-party manuscripts whose authors did not publish them, so they
appear as `R01`--`R32` in shuffled order, the label carrying no arm. Their reviews ship as scores only: every
number the paper computes is in them, but the free-text fields are withheld because a review's summary
paraphrases its subject closely enough to identify it. Their PDFs and de-identified texts are not
redistributed. Their public post-rebuttal rating means *are* released, by label, in
`data/rejected_arm_ratings.json`, because the criterion-validity result is unverifiable without them.

That last release is also the carve-out's limit, and it is worth one plain sentence: the ratings are the
venue's own public values, so withholding the mapping keeps the paper from naming anyone rather than making
anyone anonymous.

**The authors' own manuscripts.** Absent from every corpus, with no exception. Every score in the paper is a
score of a third-party ICLR 2026 submission, and every paper the instrument is demonstrated on is one of the
16 published papers or one of the 32 declined ones. Nothing here is scored to make a point about the
document you are reading.

**The two inputs of appendix A that cannot ship.** Its extract measurements compare each corpus paper's
submitted document with the text the panel was handed, and neither side is redistributable: the documents are
third-party submissions and the supplied texts are de-identified derivatives of them. So the release carries
the derived rows instead, in `data/extract_corpus.json` -- counts, ratios and one boolean per review, with no
document text, no review text and no forum id. `reproduce.py` recomputes every number the appendix prints from
that file, and for the two populations whose reviews ship in full it re-derives each review's charge flag from
the shipped review text and fails on a disagreement, so the file is checkable rather than merely quoted.

## What will not reproduce, and why

*Re-running either panel.* Sending these prompts to the same model names today will not return these reviews.
Model endpoints drift, and a slot's identity includes its effort tier -- `instrument/slots.json` and
`instrument/slots_cursor8.json` record both. That is why the calibration parameters are frozen and shipped
rather than refitted on demand.

*The scripts in `scripts/`.* They are the record of what was actually run, against a working directory, and
they will not execute against this tree: their paths are rewritten to `/path/to/workspace`, and some of them
read files that are deliberately not released -- above all the label mapping. Read them to see what was done.
Run `reproduce.py` to check that it was done right.

*5 annotation fields of `instrument/metrics_schema.json`.* The schema began life in an earlier study
of journal articles and was carried over unchanged, so 5 of its `title` and `description` strings
still describe that corpus and its task numbering: `title`, `description`, `properties/grade/description`, `properties/publishability_probability/description`, `$defs/scored_metric/properties/score/description`. Two of them matter to a reader,
because they name a journal's bar for quantities this paper scores against a conference's. None of it was shown
to a reviewer: the prompt each model received is `instrument/reviewer_prompt_iclr.md` with the manuscript
substituted for its one placeholder, and the schema is read only afterwards, by `instrument/parse_review.py`,
to validate what came back. No run script reads it at all, which the packager checks rather than states. The
prompt asks for the probability of acceptance at ICLR 2026 and for a 1-10 recommendation on ICLR's bar, in
those words, so where the two disagree the prompt is what the panel answered. The file ships exactly as it was
used rather than tidied, because it is evidence; only its `$id`, which pointed at a directory this bundle does
not contain, is repointed at itself.

## Comparing the two rosters

The eight-slot arm asks whether a finding recurs on a second roster, not whether a number reproduces there.
Each roster is z-scored against its own frozen mu/sd, and each has its own re-run band -- 0.160 for the
five-model panel, 0.0597 for the eight-slot one -- so a delta of the same nominal size means something
different in each. What is comparable is a delta's **sign**, and its size **in units of the roster's own
band**; the appendix reports both that way, and `reproduce.py` checks both.

Two asymmetries are worth knowing before reading the transform deltas. The baselines were scored over two
panels and the variants over one, so the variant composites are noisier than the baselines -- which makes
the comparison against the band conservative, not generous. And the second roster's arm varies the roster
at a fixed population, so what recurs there is the finding rather than the first arm's number.
