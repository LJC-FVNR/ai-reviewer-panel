#!/usr/bin/env python3
"""Guard the draft's numbers across a compression pass.

The draft has to lose roughly 45% of its prose to reach 9 pages, and prose is where the numbers live. Cutting
a paragraph that happened to be the only home of a confidence interval is the easy failure, and it is
invisible afterwards -- the surviving text reads fine. So: snapshot the multiset of numeric tokens before
cutting, compare after, and require every disappearance to be a deliberate one.

  python3 number_guard.py --save      before the pass
  python3 number_guard.py             after, and after every subsequent edit

Four outcomes, and only one of them fails. **GONE** is a number that appears nowhere in the draft any
more: that is the failure, because the claim it supported is now unsupported. **THINNED** is a number whose
count fell but which is still stated somewhere, which is what deleting a duplicated paragraph looks like
and is the goal of a compression pass, not a defect. **REFORMATTED** is the same value written differently
-- a sign added, a unit re-attached, a trailing comma gone -- which is a typographic change and not a lost
claim. **NEW** is worth a glance, because a number that appears during a *cut* came from somewhere and
should have come from an artifact.

The first version of this failed on every count decrease and wanted a growing exemption list after each
pass. An exemption list that grows once per edit is the gate switched off, so the predicate is what got
fixed instead: presence, not multiplicity. The same reasoning produced REFORMATTED, after unifying the
appendix's "[0.864, 1.0]" with the body's "[+0.864, +1.000]" produced four failures that were one decision
about punctuation. A sign *flip* is excluded from it deliberately, because +0.043 and -0.043 are different
claims about the same quantity, and that is the case a numeric gate exists to catch. DELIBERATE stays, for
the rare number a cut removes on purpose, and stays short enough to read.

The snapshot was re-based once, after build 8, going from 425 distinct tokens to 434 with nothing
unexplained outstanding. A snapshot only guards what was in it, so every figure that entered the draft
*after* it was taken -- which was all of the self-review measurements, the largest block of numbers in the
appendix -- could be trimmed away without this gate noticing. Re-basing waives nothing, since GONE was
empty of unexplained losses at the time, and it buys coverage of exactly the numbers most exposed to a
late language edit. It does mean the DELIBERATE entries below are now unreachable: they are the record of
what the compression pass cost, not a live exemption list.

Re-based a third time for the camera-ready, when the ranking study was read from the shuffled-order scoring of the
rejected corpus and the relocation arm applied its edit-count floor to every variant: the 110 tokens in GONE were the
values those readings replaced, each replacement checked by reproduce.py (589 of 589) and placed by where_printed.py.

Re-based a second time after build 12, from 434 distinct tokens to 588. What made it necessary is not a
language pass: the presentation study grew from sixteen papers to forty-eight and every result in it was
recomputed, so the 68 tokens standing in GONE were superseded measurements of the smaller corpus -- the
retired grade retest's 81.2 per cent and 0.188, the ratios spelled with a multiplication sign that the
lanes now carry as plain values, the review counts 240, 720 and 880 that 470, 790, 2,652 and 2,972
replaced, the old per-channel medians, and the sentence-length means of an earlier extract. This gate
cannot tell a superseded measurement from a lost claim, so what stood in for it are the gates that read
the CURRENT text in both directions and were all green at the re-base: reproduce.py recomputes 541 of the
page's numbers from the released bundle and all 541 agree, where_printed.py finds a section printing each
of those 541 or a written exemption and reports no stale one, unchecked.py finds every printed value
either claimed by a row, recomputed by a named other gate, or exempt with a recorded reason and no dead
entries, and channel_table.py --check rebuilds the three generated tables from the null file.

The difference from the first re-base is that this one keeps its history. number_guard.build12.json is the
snapshot that was replaced, so the multiset the 68 losses were measured against still exists and the
decision can be re-read rather than taken on this paragraph's word. A re-base that deletes what it waives
is the one move that would make this gate unauditable.

Re-based a third time after build 13, from 588 distinct tokens to 589, and for the same kind of reason: the
manuscript was re-scored by its own panels and its extract re-measured, so the 22 tokens standing in GONE
are the readings those two things replaced. Eighteen are the self-review -- the composite and the panel
pair, the two weakest and three strongest channels, the label-scatter endpoints, the post-rewrite mean and
the cluster gap and the last step, each of which appears in the same sentence at its new value. Three are
appendix A's extract table, which extract_audit.py recomputes from the submitted PDF: 5,282 words and 179
fused word pairs, about one word in 30, became 5,358 and 168, about one in 32. The last is 541, the length
of reproduce.py's expectation table, which is 543 rows now. The gates that read the current text were green
at the re-base, as they were at the second: reproduce.py agrees with all 543 rows, where_printed.py finds a
section printing each of them or a written exemption and reports no stale one, unchecked.py finds every
printed value claimed, recomputed elsewhere or exempt with a reason and no dead entry, and
channel_table.py --check rebuilds the three generated tables from the null file. number_guard.build13.json
is the snapshot this one replaced.

Re-based a fourth time at build 14, 589 distinct tokens to 600, for the same reason as the third: the
manuscript was re-scored on the body it is submitted with, and the 22 tokens standing in GONE are the
readings that re-score replaced. Twenty are the self-review, each of which appears in the same sentence at
its new value -- the composite and its distance to the field maximum, the panel pair and their gap, the two
weakest and three strongest channels, the label-scatter endpoints and their distance, the post-rewrite mean
and span, the cluster gap, and the last step with its two ratios. The twenty-first is 543, the length of
reproduce.py's expectation table, which is 559 rows now. The twenty-second is the cluster gap read a second
time, as 0.604 z, in the paragraph that rules out sentence length as the explanation; it is 0.635 z there
now. That one is worth naming separately, because it sat outside every passage the re-score rewrote and only
unchecked.py's list of printed values with no expectation row behind them found it: a re-score reaches the
sentences that report it, and a second reading of the same quantity elsewhere in the appendix is exactly what
a numeric gate is for. Nothing was cut to make room for any of them: the
appendix passages that carry them were rewritten value for value, and the two that changed direction say so
in words as well as in sign. The gates that read the current text were green at the re-base: reproduce.py
agrees with all 559 rows, where_printed.py finds a section printing each of them or a written exemption and
reports no stale one, unchecked.py finds every printed value claimed, recomputed elsewhere or exempt with a
reason and no dead entry, channel_table.py --check rebuilds the three generated tables from the null file,
quote_guard.py resolves every quotation in the submitted build's own reviews, and audit_submission.py is
clean. number_guard.build14.json is the snapshot this one replaced.

Re-based a fifth time when the paper stopped scoring its own manuscript, 600 distinct tokens to 588. The 51
tokens standing in GONE are that apparatus and nothing else, and unlike the four re-bases above this one
retires the measurements rather than replacing them with new readings: there is no submitted-manuscript
composite in the paper any more, so the values have no new spelling to be found at. Forty-eight are the
self-review -- the composite and its distance to the field maximum with the ratio to the band, the panel pair
and their gap, the label-scatter endpoints and their distance, the five named channels, the two per-review
grade means and their spread, the fourteen build composites including the pair that agreed to six decimals,
the two build-group means with their span and ratio, the cluster gap with its ratio, the last step with its
two ratios, the retitle step with its ratio, one panel disagreement, and the two byte counts with the
percentage between them. Two more are appendix A's table of this manuscript's own extract, 5,358 words and
168 fused pairs, which is the one artifact the release rule refuses by name; the appendix now measures the
extract of all 48 submissions the study scored, and the 44 tokens in NEW are that measurement, every one of
them a row reproduce.py recomputes from the released document measurements. The last is 559, the length of
the expectation table, which is 560 rows now. The gates that read the current text were green at the re-base:
reproduce.py agrees with all 560 rows from the staged bundle, where_printed.py finds a section printing each
of them or a written exemption with none stale, unchecked.py finds every printed value claimed, recomputed
elsewhere or exempt with a reason and no dead entry, channel_table.py --check rebuilds the three generated
tables, quote_guard.py resolves all five attributed quotations in the shipped reviews of the accepted papers,
audit_submission.py is clean, and the body is inside nine pages. number_guard.selfreview.json is the snapshot
this one replaced, named for what it held rather than for a build, because the builds it counted were
readings of this manuscript and the paper no longer takes them.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re

AN = os.path.dirname(os.path.abspath(__file__))
# Both markdown files, because moving a paragraph from the body to the appendix must not read as a loss.
SRCS = [f"{AN}/DRAFT.md", f"{AN}/APPENDIX.md"]
SNAP = f"{AN}/number_guard.json"

# A numeric token: optional sign, digits, optional decimals/commas, optional trailing unit. Deliberately
# includes the sign and the unit, because "+0.043" and "0.043" and "0.043 z" are different claims.
TOKEN = re.compile(r"[+−-]?\d[\d,]*(?:\.\d+)?\s*(?:%|z\b|×|pts?\b|points?\b)?")

# Numbers whose removal is intended. Keep the reason -- this is the record of what the cut cost.
DELIBERATE = {
    "0.0309": "superseded, with 0.0528 and 0.2670: the joining arm's dose-response p values are permutation p "
              "values drawn from one generator shared across the arms, and applying the edit floor to the "
              "relocation arm changed how many draws precede them. pooled_analyze.py now gives 0.0313, 0.0513 "
              "and 0.2664 for the same rho values.",
    "0.0528": "superseded by 0.0513; see 0.0309.",
    "0.2670": "superseded by 0.2664; see 0.0309.",
        "1.06": "a stale range end. Appendix E's range of what the arms would resolve at sixteen manuscripts is "
            "1.02 to 1.05 band widths under the edit floor, the end the resolution table's last column gives.",
    "579": "the length of reproduce.py's expectation table, which is 589 with the ten rows for the criterion's "
           "two conjuncts per arm.",
    "20.9": "removed with the sentence describing the sentence-splitting variant of T3 that was considered and "
            "not run. The variant's mean sentence length was design history rather than a result; the paper "
            "now states only the transform that was run (21.4 to 28.6 words).",
    "+0.766": "unified, not lost. Appendices D and H printed two bootstrap intervals for the same quantity, the "
              "five-model panel's correlation on the fifteen rated accepted papers: [-0.344, +0.771] in D and "
              "[-0.362, +0.766] in H, from two resampling runs. The camera-ready prints D's interval in both "
              "places and in section 5's table; reproduce.py checks both rows against it at the 0.02 bootstrap "
              "tolerance.",
    "-0.362": "unified with D's interval; see +0.766.",
    "0.54": "removed with the sentence that carried it. It quoted an inter-reviewer agreement of 0.43-0.54 "
            "measured on another panel and corpus and argued against it, an unattributed number rather than a "
            "result of this paper. The agreement this panel shows, +0.891, is printed beside it and unchanged. "
            "Its partner 0.43 survives only as the unrelated -0.43 of Appendix H, which the guard reports as "
            "REFORMATTED.",
    "0.0000": "corrected to 0.000025, not removed. Section 6's sign-test cell for the join arm printed a "
              "four-place rounding of a p the exact two-sided binomial at 38 of 47 returns as 2.4904e-05, so "
              "the page carried a p of zero, which no test returns. The cell now prints the value and its "
              "expectation row checks it to half of the last printed place; the old row expected 0.0 with a "
              "tolerance that could not tell the impossible cell from the real number.",
    "0.110 z": "removed with the two sentences that argued against it. They named a band 'sometimes quoted' "
               "as the test-retest band, traced it to another panel on another corpus, and dismissed it -- an "
               "argument with an unattributed number rather than a result of this paper. What those sentences "
               "were there to establish, that every band here is computed on this corpus and this panel, is "
               "what the sentence opening that paragraph already says, and the bands themselves are "
               "untouched: 0.160 z test-retest and a 0.115 z adjacent-paper gap.",
    "3.50": "not removed, re-united with its unit: 'span 3.50 rating points' -> 'span 3.50 points', "
            "which the tokeniser reads as the distinct token '3.50 points'. Same claim, same section.",
    "34": "corrected, not removed. The T3 join count per paper was stated as a median of 34; the eight "
          "per-paper counts in pia_variants/manifest.json are 21,23,27,34,35,41,51,55, whose median is "
          "34.5. Appendix E now carries the range and the median for all three arms.",
    "720": "superseded by 880. The five-model roster contributed 720 reviews until N1b's 160 -- the drift "
           "control for the roster the body argues from -- joined it. §1 now reads 1,392 total and 880 "
           "five-model, itemised 480 + 240 + 160. Nothing was cut; the roster grew.",
    # Fourteen figures from one paragraph, all of them measurements of an earlier build of this manuscript. The
    # self-review is scored on the build that is submitted, so when the body changed the paragraph was
    # re-measured, and these are the superseded values. Listed one by one rather than as a rule, because a rule
    # here would exempt the next real loss from the same paragraph. The replacements this note used to name
    # were themselves superseded at build 8, which changed the title and so changed the scored text: the
    # paragraph now reads +1.338 composite, panels +1.485 and +1.190 differing by 0.295 z, structure compliance
    # -1.275 and clarity +0.175 weakest, calibration honesty +3.107, reproducibility +2.578 and significance
    # +2.386 strongest. Those thirteen departures are not listed here, because the snapshot below predates the
    # build at which they entered, so the gate never held them and exempting them would claim a check it did
    # not run. The gate for that pass was lang_audit/appx_g8/check.py, which required each new value to appear
    # and each superseded one to be gone.
    **{k: "superseded: an earlier build's self-review score, re-measured on the submitted build"
       for k in ("+0.091 z", "-0.417 z", "+2.852 z", "+3.085 z", "+3.207 z", "0.483 z",
                 "+0.424", "+1.145", "+1.379", "+1.424", "+1.517", "+2.180", "+3.042", "+3.099")},
    "+1.093": "corrected to +1.094, not removed. The published field's highest composite is 1.093547; the "
              "number reaching the page had been rounded twice, once to the four decimals the portable "
              "parameter file stores and again to three, which turned 1.0935 into 1.093. The margin over it "
              "went from 0.063 to 0.062 for the same reason. Appendix G now prints both correctly, and the "
              "expectation table checks them to half of the last printed place instead of two units of it. "
              "That margin is now 0.244, which is a different change: the field's maximum is still +1.094 and "
              "this manuscript's composite was re-measured at build 8.",
    "-1.126": "the published field's lowest composite, dropped with the band it belonged to. The comparison "
              "the paragraph makes is against the top of that field, so it keeps the maximum (+1.093) and the "
              "median (-0.002) and no longer states the range. The sign collision this note used to warn "
              "about is gone with build 8: the panel composite that shared the magnitude was re-measured to "
              "+1.190, and no +1.126 is left in the draft.",
    # The same defect as +1.093 above, found by putting every figure in the matched-null section into
    # reproduce.py as an expectation and recomputing it from the bundle. Each of these was quoted to three
    # places from a value that had already been rounded once, so the last digit is wrong. Corrected, not
    # removed: the channel is still named in the same sentence, and reproduce.py now expects the corrected
    # form to half of the last printed place.
    "-0.284": "corrected to -0.285, not removed. T1's reproducibility median on the five-model roster is "
              "-0.284521 in the bundle. This one is claim-bearing: reproducibility is one of the two "
              "channels the section reports as surviving Benjamini-Hochberg control for T1, so the wrong "
              "digit sat inside the sentence that survives multiplicity control.",
    "-0.239": "corrected to -0.240, not removed. T3's figure-quality median on the five-model roster is "
              "-0.239515 in the bundle. The channel figure fig4.py draws two places and is unaffected either "
              "way -- named by its script rather than by its number, which moves when a figure is added. Note "
              "that "
              "+0.239 is a different quantity and is still in the draft.",
    "\u22120.277": "corrected to -0.276, not removed. The lower arm's length-controlled coefficient is "
                 "-0.2764706, which rounds to -0.276 at three places and to -0.2765 at four. This is the "
                 "sixth figure in the paper to arrive by way of the four-place console line rather than the "
                 "value, and the only one where the intermediate happened to sit exactly on a half, so the "
                 "second rounding moved a digit that a single rounding leaves alone. It is also the one the "
                 "chain caught by itself: reproduce.py's tolerance for a three-place estimate is half of the "
                 "last printed place, which -0.276471 against -0.277 exceeds by 0.00003.",
    # The five scoring-hour coefficients. All of them were printed where a correlation against the venue's
    # rating was claimed, so they are not corrections of a digit: the label named the wrong variable, and every
    # sentence built on them argued a limit the corrected numbers do not support. Listed one by one, because a
    # rule covering "the within-arm cluster" would also exempt the two values that were right.
    **{k: "removed with the claim it supported. A within-arm coefficient against scoring hour, printed where "
          "the composite against the venue's post-rebuttal mean rating was claimed. The corrected pair is "
          "-0.052 in the lower arm and +0.565 in the upper, which reverses the conclusion the old pair "
          "carried: the upper arm orders its own papers rather than failing to. Appendix D and Figure 1(b) "
          "now report both arms against the rating, and fig1.py derives its annotation from the arrays the "
          "panel draws so the label cannot name a different variable from the plot again."
       for k in ("+0.003", "+0.471", "-0.538", "0.066", "0.991")},
    "+0.026 z": "corrected to +0.025 z, not removed. The drift control's mean gap between a paper's later "
                "and earlier panel is 0.0254502 in the bundle. This one names the mechanism behind every "
                "entry in this cluster: analyze.py prints that quantity as `+0.0255` with a `:+.4f` format, "
                "and the three-place figure on the page was rounded off the console line rather than off the "
                "value. Round-tripping through a printed intermediate is the whole defect class, so the fix "
                "is not a list of corrections -- it is that reproduce.py now recomputes each of these from "
                "the released per-paper table and checks it to half of the last printed place. Appears twice, "
                "in Appendix D's prose and in the confound battery's row for the same test.",
    "+0.255": "corrected to +0.254, not removed. T1's eight-slot median in slot C7, quoted in the prose at "
              "three places. This one was rounded off the four-place table entry beside it rather than off "
              "the bundle: +0.2545 is already a rounded value, and rounding a rounded value again moved the "
              "third digit. The table entry itself is correct and still in the draft, one paragraph away, "
              "which is why the disagreement was invisible -- both numbers looked like the same measurement "
              "printed at two widths. Found by giving the prose's own precision its own expectation row: a "
              "row at four places passes either way and cannot see this.",
    "-0.080": "corrected to -0.064, not removed. The panel's deficit against the best single slot, which the "
              "next sentence of the same paragraph contradicted: it prints the best slot at rho = +0.658 and "
              "the panel at +0.595, whose difference is -0.064. Nothing recomputed the subtraction, so the two "
              "numbers sat one sentence apart disagreeing, and both of the ones a reader would check against "
              "were right. reproduce.py now recomputes the deficit and its interval, re-choosing the best slot "
              "inside each resample so the bound stays the selection-biased bound the appendix calls it.",
    # Nothing vanished for this one -- 0.366 was ADDED -- but the entry belongs here with the others, because the
    # defect was of the same kind and was found the same way. The appendix called 0.459, 0.281 and 0.244 "the
    # three largest" of the eight per-paper calibration gaps; they are the first, third and fourth, and 0.366
    # sat between them unmentioned. Both halves of the sentence were false: three of the four SMALLEST grew, not
    # three of three, since the fourth-smallest fell. Every printed value was right, which is why reading the
    # numbers could not find it -- the claim was about their ranks. reproduce.py now checks the four ordered
    # gaps and both counts, so a set-membership claim has a row rather than a plausible-looking triple.
    "194": "corrected to 465, then 566, then 578, then 588, not removed. Appendix G states how many of the paper's numbers "
           "reproduce.py recomputes, and that count is the one figure in the manuscript reproduce.py cannot "
           "check, because it is a count of reproduce.py itself: nothing read both sides of it while the "
           "expectation table grew from 194 rows to 588. audit_submission.py now compares the printed count, and "
           "the spelled-out count of bootstrap bounds beside it, against the table.",
    # Build 10, which the re-based snapshot above was taken in order to cover: the converter fix changed the
    # scored text, so appendix G's whole self-review paragraph was re-measured and appendix A's extract was
    # measured again on the new extract. These are the departures, and this is the first pass in which this gate
    # held them -- the build-8 note above had to decline the same list because the snapshot predated it.
    #
    # Ten of them are one quantity re-measured, listed rather than ruled, so that the next real loss from this
    # paragraph is not exempted by a pattern. Four carry a change of claim as well as of digit and are entered
    # separately below.
    **{k: "superseded at build 10: appendix G's self-review, re-measured on the submitted text. At that build "
          "the paragraph read +1.338 composite, panels +1.361 and +1.314 differing by 0.047 z, structure "
          "compliance -1.009 and clarity -0.501 weakest, builds 6-10 mean +1.178 spanning 0.372 z, and a cluster "
          "gap of 0.591 z or 3.69 times the re-run band; build 12 re-measured every one of those in turn, so "
          "those replacements are themselves replaced and the paragraph is what it says it is, the run on disk. "
          "Each replacement has an expectation row in reproduce.py, checked to half of its last printed place, "
          "and lang_audit/appx_g10/check.py required every superseded value here to be absent from the rewrite."
       for k in ("-1.275", "+1.485", "+1.190", "+1.196", "0.242 z", "0.573 z", "3.58",
                 "+3.107", "+2.578", "1.51")},
    "+0.175": "superseded at build 10 and a sign flip, which is why it is entered on its own: clarity was the "
              "second-weakest channel at +0.175 and is the second-weakest channel at -0.501, and at -0.283 after "
              "build 12 re-measured it. The word the "
              "paragraph uses is unchanged and the quantity crossed zero, so a reader comparing builds would be "
              "comparing a mild positive with a deficit. reproduce.py now also counts how many channels fall "
              "below the one named second-weakest, so the rank the sentence asserts is checked and not just the "
              "five values it prints.",
    "+2.386": "removed with the claim it supported. Significance was the third-strongest channel and is not: "
              "statistical soundness displaced it, at +2.810 then +2.836, and significance's own +2.398 no longer appears "
              "because the sentence names three channels and it is now fourth. Its expectation row went with it, "
              "replaced by one for statistical soundness and by two counts that check the ranking itself.",
    **{k: "removed with the claim it supported. At build 8 the highest-scoring Major Revision (+1.869) outscored "
          "the highest-scoring Minor Revision (+1.590), so the labels ran backwards against the scale. At build "
          "10 the best Major outscored one of seven Minors, a weaker version of the same finding; at build 12 it "
          "outscored none of six, the best Minor being +2.650 against +1.046, and the paragraph said the labels "
          "ordered those ten reviews correctly; at build 13 the best Major is +1.432 and outscores two of three "
          "Minors, so the disagreement is back and the paragraph reports it. Which version is true is a "
          "property of the run: both endpoints, "
          "their distance and the count of Minors below the best Major have expectation rows, and the count is "
          "the one that carries the direction."
       for k in ("+1.869", "+1.590")},
    "1.84": "removed with the claim it supported. The panel gap crossed back inside the re-run band: build 8's "
            "gap was 1.84 times it and build 10's was 0.29 of it, so the sentence that reported two panels "
            "disagreeing by more than a re-run did not survive that build. It has crossed again -- build 12's "
            "gap was 0.767 z, 4.79 times the band, and build 13's is 0.575 z, 3.59 times it -- and the appendix "
            "reports the multiple either way while "
            "declining to read one draw as evidence, which is the wording that survives a quantity this "
            "unstable. Build 8's own gap, 0.295 z, is still printed beside the title-only step and is computed "
            "from that build's archived reviews rather than from the current panels.",
    "1.53": "superseded at build 12: the margin over the published field's maximum fell from 0.244 z to 0.158, "
            "which is 0.99 of the 0.160 z re-run band where it was 1.53 times it. The claim is unchanged and was "
            "never resting on this multiple -- the sentence says the margin does not establish separation, and it "
            "said so at 1.53 times the band because the margin was already below the band's ninth decile. What "
            "moved is the direction of the comparison with the band itself, so the sentence read \"and below\" "
            "where it had read \"but below\". At build 13 the margin crossed zero: the composite is 0.078 z "
            "below that maximum rather than above it, 0.49 times the band, and the sentence states which side "
            "it now falls on.",
    "37": "superseded at build 12: appendix A's table counts the cross-references in this paper's own extracted "
          "text, and the two passes in this batch added two, so 37 submitted and 37 surviving became 39 and 39. "
          "Like every other row of that table it is exempt in unchecked.py rather than checked by reproduce.py, "
          "because the extract is the one artifact package_release.py may not ship, and extract_audit.py "
          "recomputes both sides of it from the submission.",
    "4,705": "superseded at build 10, and stale for two builds before that. It is the word count of build 7's "
             "extract, which is the build appendix A's table was measured on, and it stayed on the page while "
             "build 8 took the extract to 4,704 and build 9's body edits took it to 5,005. The submitted "
             "extract was 5,023 words at that build and is 5,358 now. The converter is therefore worth +18 and not the "
             "+318 this number "
             "implies, and it is worth less than the +37 the substitution predicts, because in a parenthesised "
             "cross-reference the new word arrives fused to the bracket as `(Section`.",
    "166": "superseded at build 10: appendix A's table is a measurement of this paper's own extracted text, and "
           "the converter fix changed the extract. The count was 167 fused adjacent pairs at build 10 and is 168 "
           "now, about one word in 30 and one in 32. Both figures are exempt in unchecked.py rather than checked by reproduce.py, because the extract "
           "is the one artifact package_release.py may not ship; extract_audit.py recomputes them from the "
           "submission itself. Note that this count is nearly unmoved for a reason and not by luck: it requires "
           "both halves of a fused pair to be ordinary words of two letters or more, so the reflow that the "
           "converter caused is mostly outside it.",
    "39": "relocated, not removed. The body's only bare 39 was the complement of the eight papers selected "
          "for disagreeing -- 'those eight fall -0.2784 below the other 39' -- in the paragraph the body gave "
          "up to make room for the per-channel figure. The contrast itself is unchanged and still stated, in "
          "appendix E, which prints the same subgroup gap and permutation p and writes the complement as a "
          "word: 'T1 cost the eight 0.2784 z more than the other thirty-nine at permutation p = 0.0016'. So "
          "the record survives at full precision and it is the numeral, not the claim, that left the draft.",
}


def tokens(text):
    """-> Counter of normalised numeric tokens. Section-number noise is excluded, since §5 is not data."""
    text = re.sub(r"\[@[^\]]*\]", " ", text)              # citation keys: liang2023feedback is not a number
    text = re.sub(r"§\s*\d+(\.\d+)*", " ", text)          # section cross-references
    text = re.sub(r"^\s*\d+\.\s", " ", text, flags=re.M)       # ordered-list markers
    text = re.sub(r"^#+\s*\d+(\.\d+)*\s", " ", text, flags=re.M)  # heading numbers
    out = collections.Counter()
    for m in TOKEN.finditer(text):
        t = re.sub(r"\s+", " ", m.group(0).strip()).replace("−", "-")
        if t in {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "0"}:
            continue   # bare small integers are prose ("two panels", "one venue"), not claims
        out[t] += 1
    return out


def shape(t):
    """-> (sign, digits). The sign is '' when the token carries none, which is what makes it match either."""
    m = re.match(r"([+-]?)(.*)", t)
    return m.group(1), re.sub(r"[^\d.]", "", m.group(2))


def reformatted_as(lost, present):
    """Is `lost` the same value as some token still in the draft, written differently?

    Same digits, and the signs must not contradict: one of the two may be absent, but + against - is a
    different claim and stays a failure.
    """
    sl, dl = shape(lost)
    if not dl:
        return None
    for p in present:
        sp, dp = shape(p)
        if dp == dl and (sl == sp or not sl or not sp):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="write the snapshot instead of checking it")
    a = ap.parse_args()

    now = tokens("\n".join(open(s, encoding="utf-8").read() for s in SRCS if os.path.exists(s)))
    if a.save:
        json.dump(dict(sorted(now.items())), open(SNAP, "w"), indent=1)
        print(f"snapshot: {len(now)} distinct numeric tokens, {sum(now.values())} occurrences "
              f"-> {SNAP}")
        return 0

    if not os.path.exists(SNAP):
        print(f"no snapshot at {SNAP}; run --save first")
        return 2
    before = collections.Counter(json.load(open(SNAP)))

    missing = sorted(k for k in before if now.get(k, 0) == 0)
    reformatted = {k: r for k in missing if (r := reformatted_as(k, now))}
    gone = [k for k in missing if k not in reformatted]
    thinned = sorted(k for k, v in before.items() if 0 < now.get(k, 0) < v)
    new = {k: v for k, v in now.items() if k not in before}
    unexplained = [k for k in gone if k not in DELIBERATE]

    print(f"snapshot {sum(before.values())} occurrences / {len(before)} distinct  ->  "
          f"now {sum(now.values())} / {len(now)}")
    if new:
        print(f"\nNEW ({len(new)}) -- appeared during a cut, so check each came from an artifact:")
        for k, v in sorted(new.items()):
            print(f"  {k:>12s} x{v}")
    if thinned:
        print(f"\nTHINNED ({len(thinned)}) -- still stated somewhere, count fell. This is what removing a "
              f"duplicated passage looks like:\n  " + "  ".join(thinned))
    if reformatted:
        print(f"\nREFORMATTED ({len(reformatted)}) -- same value, different typography:")
        for k, r in sorted(reformatted.items()):
            print(f"  {k:>12s} -> {r}")
    if gone:
        print(f"\nGONE ({len(gone)}) -- stated nowhere in the draft any more:")
        for k in gone:
            why = DELIBERATE.get(k)
            print(f"  {k:>12s}   {'[' + why + ']' if why else '<-- the claim it supported is now '
                                                             'unsupported'}")
    if unexplained:
        print(f"\n{len(unexplained)} number(s) vanished. Restore each, or add it to DELIBERATE with the "
              "reason it should be gone.")
        return 1
    print("\nnothing vanished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
