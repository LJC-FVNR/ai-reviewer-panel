#!/usr/bin/env python3
"""Recompute the paper's headline numbers from the released bundle, and fail if any of them disagree.

This is the artifact's whole point. A release that ships reviews and analysis scripts written against the
author's directory layout is not checkable: the scripts read paths that are not in the bundle, and nobody finds
out until someone tries. So this script reads only what the bundle contains, in the bundle's own layout,
reimplements each statistic from the review JSONs, and compares the result with the value printed in the paper.

The expected values below are transcribed from the submitted PDF. A mismatch is therefore one of three things,
all worth knowing: a wrong number in the paper, a bundle that is missing something, or a definition the paper
states less precisely than it computes.

  python3 reproduce.py [--bundle release/aina2026_agent_reviewers]

Takes about seven minutes on one core, nearly all of it the randomisation nulls at the end: each of those draws
200,000 sign assignments, and the corpus they run over grew from sixteen papers to forty-eight.
"""
from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import itertools
import json
import math
import os
import random
import re
import statistics as st

GRADES = ["Reject", "Reject and Resubmit", "Major Revision", "Minor Revision", "Accept"]
ORDER = {g: i for i, g in enumerate(GRADES)}

# Every value here is what the paper prints, with the section that prints it. tol is what counts as agreement:
# 0.001 for a z, 0.5 for a percentage the paper rounds to whole numbers.
EXPECT = [
    # (section, name, expected, tol)
    # Section 1's corpus, arm by arm. tol is 0 because these are counts of files, and the roster totals are
    # here as well as their parts: an itemisation that does not add up is the failure a reader would catch.
    ("1", "corpus: total reviews", 2647, 0),
    ("1", "corpus: 5-model roster reviews", 2135, 0),
    ("1", "corpus: 8-slot roster reviews", 512, 0),
    ("3", "corpus: accepted reviews", 160, 0),
    ("3", "corpus: rejected reviews", 320, 0),
    ("6", "corpus: presentation study reviews", 2647, 0),
    ("6", "corpus: transform reviews", 470, 0),
    ("6", "corpus: transform_rejected reviews", 790, 0),
    ("E", "corpus: drift_5model reviews", 555, 0),
    ("E", "corpus: dayrep_5model reviews", 160, 0),
    ("3", "corpus: vendor_panel reviews", 256, 0),
    ("H", "corpus: vendor_transform reviews", 192, 0),
    ("H", "corpus: vendor_drift reviews", 64, 0),
    # The frame the sampling frame is drawn from, counted in the file that ships rather than quoted from the
    # venue. It is printed twice, once in the release list and once in section 10, and it is the only external
    # figure in the paper that the bundle can settle by itself: the frame is an artifact, so its size is a
    # property of a released file and not a fact about a website that may since have changed.
    ("10", "frame: ICLR 2026 submissions", 19814, 0),
    # Appendix A's counts behind those percentages.
    ("A", "accepted: Major Revision count", 110, 0),
    ("A", "high-rated rejected: Major Revision count", 110, 0),
    ("A", "accepted: Reject and Resubmit count", 11, 0),
    ("A", "high-rated rejected: Reject and Resubmit count", 32, 0),
    ("A", "low-rated rejected: Reject and Resubmit count", 80, 0),
    # Appendix A's corpus measurements. Four tools read the 48 third-party submissions the study already
    # scored: what the extractor drops from each document, how often a review charges the author for a property
    # of the drop, whether the papers that lost more are the papers charged more, and whether the charge costs
    # the paper any score. Every row below is a number the appendix prints, at the precision it prints it, and
    # the tolerance is half that last place -- 0.02 on a bootstrap bound, which is resampled and moves.
    #
    # The two-column document table.
    ("A", "extract, accepted: median document words", 18786, 0.5),
    ("A", "extract, declined: median document words", 10964, 0.5),
    ("A", "extract, accepted: median supplied words", 5097, 0),
    ("A", "extract, declined: median supplied words", 4532, 0.5),
    ("A", "extract, accepted: median share of the body supplied", 0.835, 0.0005),
    ("A", "extract, declined: median share of the body supplied", 0.757, 0.0005),
    ("A", "extract, accepted: median back-matter words", 11844, 0.5),
    ("A", "extract, declined: median back-matter words", 5216, 0.5),
    ("A", "extract, accepted: supplied texts with back matter", 0, 0),
    ("A", "extract, declined: supplied texts with back matter", 0, 0),
    ("A", "extract, accepted: papers pointing into missing back matter", 8, 0),
    ("A", "extract, declined: papers pointing into missing back matter", 25, 0),
    ("A", "extract, accepted: median pointers where any", 6, 0),
    ("A", "extract, declined: median pointers where any", 6, 0),
    ("A", "extract, accepted: median captions in the document", 22, 0.5),
    ("A", "extract, declined: median captions in the document", 14, 0.5),
    ("A", "extract, accepted: median captions supplied", 6, 0),
    ("A", "extract, declined: median captions supplied", 7, 0),
    # The count the section turns on: a supplied text that tells the reviewer to consult back matter no supplied
    # text contains. It is the sum of the two arms above, and it is printed as a total because the mechanism is a
    # property of the pipeline rather than of either corpus.
    ("A", "extract: papers pointing into missing back matter, of 48", 33, 0),
    # How often a review charges a property of that text, population by population. Numerator, denominator and
    # rate all have rows: a rate alone cannot say whether an arm shipped short, and the paper prints all three.
    ("A", "extract, accepted 16, five slots: charging reviews", 82, 0),
    ("A", "extract, accepted 16, five slots: reviews", 320, 0),
    ("A", "extract, accepted 16, five slots: charge rate", 0.256, 0.0005),
    ("A", "extract, declined 32, five slots: charging reviews", 76, 0),
    ("A", "extract, declined 32, five slots: reviews", 320, 0),
    # Half a thousandth, not a quarter of one: 76 of 320 is exactly 0.2375, so the rate sits on the
    # rounding boundary and a tolerance of half the last printed place fails on the floating-point
    # representation of the gap rather than on any disagreement. The other three rates are nowhere near
    # a boundary and keep the half-place tolerance.
    ("A", "extract, declined 32, five slots: charge rate", 0.237, 0.001),
    ("A", "extract, accepted 16, eight slots: charging reviews", 50, 0),
    ("A", "extract, accepted 16, eight slots: reviews", 256, 0),
    ("A", "extract, accepted 16, eight slots: charge rate", 0.195, 0.0005),
    ("A", "extract: reviews read", 896, 0),
    ("A", "extract: charging reviews", 208, 0),
    # Are the charged reviews the reviews of the papers that lost something. The predictor is a density, and the
    # control is the supplied text's own length, so each read is printed twice: once plain and once net of it.
    ("A", "extract, declined 32, both sittings: rho, pointer density vs charge rate", 0.388, 0.0005),
    ("A", "extract, declined 32, both sittings: p", 0.0282, 0.00005),
    ("A", "extract, declined 32, both sittings: rho net of supplied length", 0.369, 0.0005),
    ("A", "extract, declined 32, both sittings: p net of length", 0.0378, 0.00005),
    ("A", "extract, accepted 16, both rosters: rho, pointer density vs charge rate", 0.200, 0.0005),
    ("A", "extract, accepted 16, both rosters: p", 0.4582, 0.00005),
    ("A", "extract, accepted 16, both rosters: rho net of supplied length", 0.218, 0.0005),
    ("A", "extract, accepted 16, both rosters: p net of length", 0.4181, 0.00005),
    # And what the charge costs, paired within paper. All four reads are printed, with their intervals and their
    # pooled counterparts: the four disagree in sign, and a table that showed one of them would be a result.
    ("A", "extract, accepted 16, five slots: paired gap, median", -0.141, 0.0005),
    ("A", "extract, accepted 16, five slots: paired gap CI low", -0.346, 0.02),
    ("A", "extract, accepted 16, five slots: paired gap CI high", -0.070, 0.02),
    ("A", "extract, accepted 16, five slots: papers with a positive gap", 3, 0),
    ("A", "extract, accepted 16, five slots: papers with both", 16, 0),
    ("A", "extract, accepted 16, five slots: pooled gap", -0.031, 0.0005),
    ("A", "extract, accepted 16, five slots: pooled AUC", 0.485, 0.0005),
    ("A", "extract, declined 32, five slots: paired gap, median", -0.083, 0.0005),
    ("A", "extract, declined 32, five slots: paired gap CI low", -0.322, 0.02),
    ("A", "extract, declined 32, five slots: paired gap CI high", 0.028, 0.02),
    ("A", "extract, declined 32, five slots: papers with a positive gap", 10, 0),
    ("A", "extract, declined 32, five slots: papers with both", 28, 0),
    ("A", "extract, declined 32, five slots: pooled gap", 0.284, 0.0005),
    ("A", "extract, declined 32, five slots: pooled AUC", 0.592, 0.0005),
    ("A", "extract, accepted 16, eight slots: paired gap, median", 0.046, 0.0005),
    ("A", "extract, accepted 16, eight slots: paired gap CI low", -0.128, 0.02),
    ("A", "extract, accepted 16, eight slots: paired gap CI high", 0.191, 0.02),
    ("A", "extract, accepted 16, eight slots: papers with a positive gap", 8, 0),
    ("A", "extract, accepted 16, eight slots: papers with both", 14, 0),
    ("A", "extract, accepted 16, eight slots: pooled gap", 0.113, 0.0005),
    ("A", "extract, accepted 16, eight slots: pooled AUC", 0.537, 0.0005),
    # The largest of those four gaps as a size, which is the number the section is read against: the pre-
    # registered re-run band is 0.160 z, so a table of four gaps none of which reaches it is the finding, and
    # without this row the sentence saying so rests on a reader doing the comparison.
    ("A", "extract: largest |paired gap|, of four reads", 0.141, 0.0005),
    ("3", "accepted: Major Revision %", 68.8, 0.5),
    ("3", "accepted: Minor Revision %", 23.8, 0.5),
    ("3", "accepted: Accept count", 1, 0),
    ("3", "rejected: Reject %", 3.4, 0.5),
    ("3", "rejected: Reject and Resubmit %", 35.0, 0.5),
    ("3", "rejected: Major Revision %", 56.2, 0.5),
    ("3", "rejected: Accept count", 0, 0),
    ("3", "all 480: Accept count", 1, 0),
    # The denominator that count is one of, and the share it makes. "One review in 480" is the paper's most
    # quoted figure and only its numerator had a row: an arm that shipped short would move the rate and leave
    # the sentence reading as though nothing had changed.
    ("3", "all 480: reviews", 480, 0),
    ("3", "all 480: Accept %", 0.21, 0.005),
    # The count the acceptance sentence is about, which is not the same count as the top label's. The prompt
    # defines Accept as a clear accept and Minor Revision as a borderline one at the venue's own bar, so a
    # panel recommending acceptance is a panel awarding either -- 39 of the 160 reviews of published papers, 17
    # of the 320 of declined ones, and 73 of the 256 the second roster wrote. Kept beside the single Accept
    # above rather than replacing it: the two counts answer different questions and the paper prints both.
    ("3", "at or above the bar: accepted reviews", 39, 0),
    ("3", "at or above the bar: declined reviews", 17, 0),
    ("3", "at or above the bar: 5-model reviews", 56, 0),
    ("3", "at or above the bar: 8-slot reviews", 73, 0),
    ("3", "bar 1 panels (every reviewer Minor+)", 0, 0),
    ("3", "bar 2 panels (any Accept)", 1, 0),
    ("3", "bar 3 panels (modal Minor+)", 5, 0),
    ("3", "bar 3 papers in >=1 panel", 4, 0),
    ("3", "bar 3 papers in both panels", 1, 0),
    ("3", "bar 4 panels (every reviewer Major+)", 24, 0),
    ("3", "bar 4 papers in both panels", 12, 0),
    ("2", "re-run band, median |dz| over 16", 0.160, 0.002),
    ("B", "re-run band p90", 0.333, 0.002),
    # The rest of the yardstick paragraph. The interpolated p90 is here because the appendix quotes it as what
    # the other convention returns, and a rejected convention has to be quoted at its own value.
    ("B", "re-run band p90, interpolated", 0.350, 0.002),
    ("B", "re-run band, mean |dz|", 0.189, 0.002),
    ("B", "re-run band, signed sd", 0.231, 0.002),
    ("B", "5-model: grade re-run mean abs step", 0.1708, 0.00005),
    ("B", "5-model: modal grade kept, papers", 45, 0),
    ("2", "adjacent-paper gap, median", 0.115, 0.002),
    # The median gap says what a typical neighbouring pair is worth and cannot say how much of the field the
    # band covers, which is the claim the paragraph makes. Both sides of that are counted.
    ("2", "reference field: adjacent pairs", 15, 0),
    ("2", "reference field: adjacent pairs inside the re-run band", 10, 0),
    ("5", "rho, composite vs venue rating, 32 declined", 0.51, 0.002),
    ("5", "AUC, high- vs low-rated declined", 0.77, 0.002),
    # The same criterion applied to the grade instead of the composite, which appendix D prints beside the
    # composite with an interval on the difference. Two readings, because the first assumes the five levels
    # are equally spaced and the second assumes nothing: the mean of the levels coded 0 to 4, and the share
    # of a paper's reviews at or above the level the prompt maps to the venue's bar. The body printed the two
    # correlations and a pair of AUCs of its own for a while; the AUCs went with that table, so their rows
    # went too rather than stand as expectations for values no page states. The appendix's own AUC column
    # asks a different question -- the published sixteen against all 32 declined -- and has its rows below.
    ("D", "mean grade: rho vs venue rating, 32 declined", 0.564, 0.002),
    ("D", "bar share: rho vs venue rating, 32 declined", 0.561, 0.002),
    # The screening claim's own count, which had no row: section 5 says only 3 of 32 declined papers clear the
    # published field's median, and the opening figure now draws that threshold. It is a single digit, so
    # unchecked.py does not examine it and nothing else would have noticed it going stale -- and it is the
    # least stable number in the section, because it counts papers on one side of a median that moves whenever
    # the accepted panel is re-run. The two quantities it is built from each have a row; their comparison did
    # not.
    ("5", "declined papers above the published-field median", 3, 0),
    ("7", "AUC, published vs declined (pooled)", 0.85, 0.002),
    ("F", "AUC, published vs declined: CI low", 0.725, 0.02),
    ("F", "AUC, published vs declined: CI high", 0.947, 0.02),
    # Appendix D in full. Point estimates carry half of their last printed place; the two bootstrap intervals
    # carry 0.02, the seed allowance this file documents at the boot_ci call, because a percentile interval
    # from 4000 resamples is not reproducible to three places across generators.
    ("D", "rho p, composite vs venue rating", 0.0029, 0.00005),
    ("D", "rho CI low", 0.189, 0.02),
    ("D", "rho CI high", 0.744, 0.02),
    ("D", "kendall tau, composite vs rating", 0.393, 0.0005),
    ("D", "kendall tau p", 0.0032, 0.00005),
    ("D", "declined low-arm mean composite", -1.503, 0.0005),
    ("D", "declined high-arm mean composite", -0.654, 0.0005),
    ("D", "arm gap, z", 0.848, 0.0005),
    ("D", "arm gap / sd of all 32", 0.95, 0.0005),
    ("D", "AUC CI low", 0.59, 0.02),
    ("D", "AUC CI high", 0.91, 0.02),
    # What the body's grade-as-order table leaves to the appendix: the same two readings against the venue's
    # decision rather than its rating, and the interval on the difference between each reading and the
    # composite. The difference is a paired quantity -- one set of papers, three columns -- so the resample
    # draws papers once and applies the draw to all three, and both intervals contain zero: on these 32 papers
    # the composite's twelve calibrated channels order no better and no worse than the grade does. The
    # difference of two correlations is not a quantity a percentile interval reproduces to three places, so
    # these four bounds carry the same 0.02 seed allowance the other bootstrap rows do.
    ("D", "mean grade: AUC, published vs declined", 0.821, 0.002),
    ("D", "bar share: AUC, published vs declined", 0.76, 0.002),
    ("D", "mean grade: rho minus composite rho", 0.054, 0.002),
    ("D", "mean grade: rho minus composite rho, CI low", -0.035, 0.02),
    ("D", "mean grade: rho minus composite rho, CI high", 0.167, 0.02),
    ("D", "bar share: rho minus composite rho", 0.051, 0.002),
    ("D", "bar share: rho minus composite rho, CI low", -0.215, 0.02),
    ("D", "bar share: rho minus composite rho, CI high", 0.312, 0.02),
    ("D", "Mann-Whitney p, high vs low arm", 0.0098, 0.00005),
    ("D", "declined median composite", -0.881, 0.0005),
    ("D", "declined papers above the published median", 3, 0),
    # The two arms against the rating. These are the coefficients that were printed against scoring hour, so
    # they are the rows most worth having a second implementation of.
    ("D", "low-rated arm: rho with rating", -0.043, 0.0005),
    ("D", "low-rated arm: p", 0.87, 0.005),
    ("D", "high-rated arm: rho with rating", 0.479, 0.0005),
    ("D", "high-rated arm: p", 0.06, 0.0005),
    ("5", "low-rated arm: CI low", -0.503, 0.02),
    ("5", "low-rated arm: CI high", 0.42, 0.02),
    ("5", "high-rated arm: CI low", -0.039, 0.02),
    ("5", "high-rated arm: CI high", 0.85, 0.02),
    ("5", "pooled rank covariance: % between arms", 82, 0.5),
    ("D", "pooled rank covariance: % between arms, one place", 81.6, 0.05),
    ("D", "pooled rank covariance: % within arms, one place", 18.4, 0.05),
    ("5", "high-rated arm: lowest rating", 5.0, 0.05),
    ("5", "high-rated arm: highest rating", 5.5, 0.05),
    ("D", "low-rated arm: partial rho, length held", -0.288, 0.0005),
    ("D", "high-rated arm: partial rho, length held", 0.397, 0.0005),
    ("D", "low-rated arm: distinct ratings over 16", 3, 0),
    ("D", "high-rated arm: distinct ratings over 16", 4, 0),
    ("D", "low-rated arm: papers at the modal rating", 11, 0),
    ("D", "high-rated arm: papers at the modal rating", 7, 0),
    ("D", "low-rated arm: within-arm rating sd", 0.21, 0.005),
    ("D", "high-rated arm: within-arm rating sd", 0.21, 0.005),
    ("D", "pooled rating sd, 32", 1.55, 0.005),
    ("5", "arm mean rating gap", 3.077, 0.0005),   # moved into section 5's design paragraph
    ("D", "declined arm rating span", 3.50, 0.005),
    ("D", "published arm rating span", 3.50, 0.005),
    ("5", "published arm: lowest rating", 4.5, 0.05),
    ("5", "published arm: highest rating", 8.0, 0.05),
    ("C", "low-rated arm: modal rating", 2.0, 0.005),
    ("D", "high-rated arm: modal rating", 5.0, 0.005),
    # The same mode at the one decimal place the sentence prints it to. A row whose tolerance implies three
    # places searches for "5.00" and "5.000", neither of which is on any page, so the row above checks the
    # quantity and covers no printed numeral; the ratings sit on a half-point grid, which is what makes one
    # place enough to pin it.
    ("D", "high-rated arm: modal rating, as printed", 5.0, 0.05),
    ("D", "published arm: rho with rating", 0.304, 0.0005),
    ("D", "published arm: p", 0.27, 0.005),
    ("D", "published arm: rho, overall_recommendation raw", 0.112, 0.0005),
    ("D", "published arm: p, overall_recommendation", 0.69, 0.005),
    ("D", "declined minus published rho", 0.207, 0.0005),
    ("D", "declined minus published: CI low", -0.367, 0.02),
    ("D", "declined minus published: CI high", 0.891, 0.02),
    ("D", "published arm: CI low", -0.344, 0.02),
    ("D", "published arm: CI high", 0.771, 0.02),
    ("D", "declined arm rating IQ width", 3.23, 0.005),
    ("D", "published arm rating IQ width", 1.50, 0.005),
    ("D", "published arm papers with a rating", 15, 0),
    ("D", "length: partial rho with human rating", 0.267, 0.0005),
    ("D", "length: partial p, human rating", 0.139, 0.0005),
    ("D", "length band: low bound", 4047, 0),
    ("D", "length band: high bound", 4775, 0),
    ("D", "length band: low-arm papers", 8, 0),
    ("D", "length band: high-arm papers", 8, 0),
    ("D", "length band: gap, z", 0.443, 0.0005),
    ("D", "length band: AUC", 0.719, 0.0005),
    ("D", "drift: mean later minus earlier, z", -0.027, 0.0005),
    ("D", "drift: median later minus earlier, z", -0.019, 0.0005),
    ("D", "drift: Wilcoxon p", 0.6, 0.005),
    ("D", "drift: rho, dcomposite vs hours between panels", -0.12, 0.0005),
    ("D", "drift: p", 0.51, 0.005),
    ("D", "scoring hour: rho with composite, pooled", 0.018, 0.0005),
    ("D", "scoring hour: p", 0.92, 0.005),
    ("D", "cross-arm pairs, total", 256, 0),
    ("D", "cross-arm pairs, lower-rated at least higher-rated", 59, 0),
    ("D", "panel-to-panel lag, median seconds", 80, 0.5),
    ("D", "scoring queue span, minutes", 139, 0.5),
    ("6", "T1 median dcomposite", -0.0085, 0.002),
    ("6", "T3 median dcomposite", -0.1384, 0.002),
    ("6", "T2 median dcomposite", 0.0214, 0.002),
    # The criterion's two conjuncts, as section 6 and appendix E apply them to each arm.
    ("6", "T1 mean |dcomposite|", 0.148, 0.0005),
    ("E", "T2 mean |dcomposite|", 0.176, 0.0005),
    ("E", "T3 mean |dcomposite|", 0.200, 0.0005),
    ("6", "T1: modal grade kept, papers", 42, 0),
    ("6", "T1: modal grade kept, of", 46, 0),
    ("E", "T1: modal grade kept, share", 0.913, 0.0005),
    ("E", "T2: modal grade kept, papers", 42, 0),
    ("E", "T2: modal grade kept, of", 48, 0),
    ("E", "T3: modal grade kept, papers", 42, 0),
    ("E", "T3: modal grade kept, of", 47, 0),
    # The results table's two corpus columns, which stood in it unrecomputed while every other cell of the row
    # they sit in had a row here. One of the six even passed the coverage check backwards, because a channel
    # median three appendices away rounds to −0.058 as well. The tolerance is the pooled columns': half of the
    # last printed place, since a median of a corpus half is one arithmetic path from the shipped reviews.
    ("6", "T1 median dcomposite, accepted", -0.0583, 0.00005),
    ("6", "T1 median dcomposite, declined", +0.0107, 0.00005),
    ("6", "T2 median dcomposite, accepted", +0.0214, 0.00005),
    ("6", "T2 median dcomposite, declined", +0.0197, 0.00005),
    ("6", "T3 median dcomposite, accepted", -0.2126, 0.00005),
    ("6", "T3 median dcomposite, declined", -0.1121, 0.00005),
    ("6", "T1 sign split, negative", 23, 0),
    ("6", "T3 sign split, negative", 38, 0),
    ("6", "T2 sign split, negative", 22, 0),
    ("4", "variance: paper %, declined 32", 64.8, 0.05),
    ("4", "variance: reviewer %, declined 32", 5.9, 0.05),
    ("C", "variance: reviewer %, low-rated 16", 11.3, 0.05),
    ("C", "variance: reviewer %, high-rated 16", 9.1, 0.05),
    ("4", "variance: reviewer %, published 16", 18.8, 0.05),
    ("4", "variance: paper %, published 16", 39.1, 0.05),
    # The ladder's two middle rungs and its third column. Only the ends of the table were checked, and the
    # middle rungs are the table's argument: the claim is that the reviewer's share climbs monotonically as the
    # population narrows, which is a statement about four rows in order, not about the first and the last.
    ("C", "variance: paper %, low-rated 16", 54.2, 0.05),
    ("C", "variance: paper %, high-rated 16", 60.1, 0.05),
    ("C", "variance: residual %, declined 32", 29.2, 0.05),
    ("C", "variance: residual %, low-rated 16", 34.5, 0.05),
    ("C", "variance: residual %, high-rated 16", 30.7, 0.05),
    ("C", "variance: residual %, published 16", 42.1, 0.05),
    ("C", "variance: reviewer/paper, declined 32", 0.09, 0.005),
    ("C", "variance: reviewer/paper, low-rated 16", 0.21, 0.005),
    ("C", "variance: reviewer/paper, high-rated 16", 0.15, 0.005),
    ("C", "variance: reviewer/paper, published 16", 0.48, 0.005),
    ("C", "slot baseline spread, declined 32", 0.67, 0.005),
    # The two middle rungs of the leniency ladder, whose magnitudes collide with an AUC and a CI bound
    # elsewhere in the paper, so until now they were covered only by a row about a different quantity.
    ("C", "slot baseline spread, low-rated 16", 0.88, 0.0051),
    ("C", "slot baseline spread, high-rated 16", 0.78, 0.005),
    ("C", "slot baseline spread, published 16", 0.97, 0.005),
    ("C", "solo-slot rho, lowest", 0.381, 0.002),
    ("C", "solo-slot rho, highest", 0.556, 0.002),
    ("4", "panel rho minus mean-solo rho", 0.041, 0.002),
    # The interval around that null, and the selection-biased bound printed beside it. 0.02 is the seed
    # allowance every percentile interval in this file carries.
    ("4", "aggregation gap: CI low", -0.02, 0.02),
    ("4", "aggregation gap: CI high", 0.1, 0.02),
    ("C", "panel minus best slot", -0.046, 0.002),
    ("C", "panel minus best slot: CI low", -0.191, 0.02),
    ("C", "panel minus best slot: CI high", 0.012, 0.02),
    ("F", "drop-one AUC, lowest", 0.758, 0.002),
    ("F", "drop-one AUC, highest", 0.773, 0.002),
    ("F", "drop-one rho, lowest", 0.493, 0.002),
    ("F", "drop-one rho, highest", 0.525, 0.002),
    ("4", "inter-slot agreement, median of 10 pairs", 0.87, 0.002),
    ("C", "inter-slot agreement, minimum pair", 0.802, 0.002),
    ("C", "inter-slot agreement, low-rated 16", 0.846, 0.002),
    ("C", "inter-slot agreement, high-rated 16", 0.859, 0.002),
    ("C", "inter-slot agreement, published 16", 0.710, 0.002),
    ("C", "leniency shift, smallest slot", 0.5, 0.005),
    ("C", "leniency shift, largest slot", 1.12, 0.0051),
    # The equal spread of the two middle rungs, which the appendix attributes to the sampling rule rather than
    # to the panel. Three rows, because the equality is the claim and the low arm's two endpoints are printed.
    ("C", "low-rated arm: rating range", 0.500, 0.0005),
    ("C", "high-rated arm: rating range", 0.500, 0.0005),
    ("C", "low-rated arm: lowest rating", 2.000, 0.0005),
    ("C", "low-rated arm: highest rating", 2.500, 0.0005),
    # The pool behind that rule, which the appendix now states rather than alluding to. The three counts are the
    # disclosure an extreme-group design owes a reader: a target is uninformative until the population it was
    # chosen inside is a number.
    ("C", "pool: papers drawn from", 250, 0),
    ("C", "pool: eligible for the low arm", 58, 0),
    ("C", "pool: eligible for the high arm", 29, 0),
    ("C", "pool: lowest rating", 0.5, 0.05),
    ("C", "pool: highest rating", 6.0, 0.05),
    # The trade the draw made, both sides of it. The separation is the side on which drawing to interior targets
    # is the harder choice, and the spread is the side on which it is the cost, being what narrowed each arm
    # into the truncation Study 3 reports. Four rows because the appendix prints the comparison as a table and
    # a table of two columns is two measurements, not one with a caveat.
    ("C", "as drawn: within-arm rating sd", 0.212, 0.0005),
    ("C", "extremes draw: within-arm rating sd", 0.366, 0.0005),
    ("C", "extremes draw: arm mean rating gap", 3.731, 0.0005),
    # Counted against the arms as shipped, so a reader with the bundle can settle them without the targets.
    ("C", "pool: eligible below the low arm", 9, 0),
    ("C", "pool: eligible above the high arm", 2, 0),
    ("C", "panel retest rho, declined 32", 0.981, 0.002),
    ("C", "reviewer variance component, published 16", 0.111, 0.002),
    ("C", "sd of slot baselines, published 16", 0.352, 0.002),
    ("6", "T1 |median| / own band", 0.05, 0.005),
    ("6", "T3 |median| / own band", 0.86, 0.008),
    ("6", "T2 |median| / own band", 0.13, 0.005),
    # What each arm resolves, printed in the appendix's resolution table and in the body's scope note. These
    # answer a reader who counts forty-eight manuscripts, so they are the rows most likely to be recomputed by
    # someone who does not trust the count, and they are checked to the last place they are printed to. Nothing
    # here is resampled: the interval they price is the exact order-statistic one on the median, whose coverage
    # is a binomial tail rather than a percentile of a resampling, so the same numbers come back without a seed.
    # The counterfactual column holds the arm's measured spread and evaluates the same arithmetic at sixteen.
    # The table stops at three places, and these rows are the reason. The measurement file prices the interval on
    # the per-paper column the release ships, which is rounded to four places; recomputing the same interval from
    # the reviews moves the half-width in the fifth place, and that is enough to move a fourth printed digit,
    # because a half-width is a difference of two order statistics and inherits both of their roundings. Three
    # places is where the two reads agree, and a z of a hundredth is already finer than anything the table is
    # read for.
    ("E", "T1 resolves", 0.099, 0.0005),
    ("E", "T1 resolves / band", 0.62, 0.005),
    ("E", "T1 resolves at sixteen", 0.168, 0.0005),
    ("E", "T1 resolves at sixteen / band", 1.05, 0.005),
    ("E", "T2 resolves", 0.094, 0.0005),
    ("E", "T2 resolves / band", 0.59, 0.005),
    ("E", "T2 resolves at sixteen", 0.163, 0.0005),
    ("E", "T2 resolves at sixteen / band", 1.02, 0.005),
    ("E", "T3 resolves", 0.098, 0.0005),
    ("E", "T3 resolves / band", 0.61, 0.005),
    ("E", "T3 resolves at sixteen", 0.168, 0.0005),
    ("E", "T3 resolves at sixteen / band", 1.05, 0.005),
    # The grade axis of the arm the body argues from. Every one of these is printed in section 6 or in F3(b),
    # and none of them was checked here until the figure started drawing both rosters on one axis.
    #
    # The three rows that stood here checked the retest on the published sixteen -- 80 cells, 81.2 per cent,
    # 0.188 -- while the manuscript's grade claims moved to the day-matched forty-eight and are printed as
    # proportions. A row expecting a percentage cannot see the 0.8292 a reader reads, so the paper's own headline
    # agreement went unchecked behind three rows that passed against a superseded measurement.
    ("2", "5-model: modal grade holds on identical text", 0.9375, 0.00005),
    ("2", "5-model: grade re-run cell agreement", 0.8292, 0.00005),
    ("E", "5-model: grade re-run cell agreement, three places", 0.829, 0.0005),
    ("E", "5-model: modal grade holds on identical text, three places", 0.938, 0.0005),
    ("E", "T1: grade cells differing from both readings, share", 0.091, 0.0005),
    ("E", "T2: grade cells differing from both readings, share", 0.104, 0.0005),
    ("E", "T3: grade cells differing from both readings, share", 0.132, 0.0005),
    ("E", "T1: grade step / own re-run step", 1.03, 0.005),
    ("E", "T2: grade step / own re-run step", 1.12, 0.005),
    ("E", "T3: grade step / own re-run step", 1.26, 0.005),
    ("E", "grade cells that ever flip, share", 0.225, 0.0005),
    ("D", "length: rho with composite", 0.502, 0.0005),
    ("D", "length: rho with human rating", 0.597, 0.0005),
    ("D", "length: partial rho with composite", 0.268, 0.0005),
    ("D", "length: partial p", 0.14, 0.005),

    # The second roster: eight slots, six vendors, its own frozen parameters. Section H unless the body
    # prints the number too, in which case the body's section and the body's rounding.
    ("3", "8-slot: Accept count", 16, 0),
    # The share the same table prints beside that count, which is the number the comparison with the five-model
    # roster's 0.21% is actually made on. Both rosters state a rate and only one of them had a row for it.
    ("3", "8-slot: Accept %", 6.2, 0.05),
    ("3", "8-slot: slots returning any Accept", 1, 0),
    ("3", "8-slot: Accepts from the one slot that says it", 16, 0),
    ("H", "8-slot: most R&R from one slot", 29, 0),
    ("3", "8-slot: panels with any Accept", 16, 0),
    ("H", "8-slot: Reject count", 1, 0),
    ("H", "8-slot: Reject and Resubmit count", 67, 0),
    ("H", "8-slot: Major Revision count", 115, 0),
    ("H", "8-slot: Minor Revision count", 57, 0),
    ("H", "8-slot: panels with every reviewer Minor+", 0, 0),
    ("H", "8-slot: papers with any Accept, >=1 panel", 9, 0),
    ("H", "8-slot: papers with any Accept, both panels", 7, 0),
    ("H", "8-slot: variance paper %", 23.7, 0.05),
    ("H", "8-slot: variance reviewer %", 53.2, 0.05),
    ("H", "8-slot: variance reviewer/paper", 2.24, 0.005),
    ("H", "8-slot: slot baseline spread", 3.06, 0.005),
    ("C", "8-slot: reviewer variance component", 1.067, 0.002),
    ("C", "8-slot: sd of slot baselines", 1.045, 0.002),
    ("4", "8-slot: vendor share of between-slot SS %", 98.9, 0.05),
    ("H", "8-slot: within-OpenAI persona spread", 0.41, 0.005),
    ("H", "8-slot: lowest vendor mean", 3.85, 0.005),
    ("H", "8-slot: highest vendor mean", 6.69, 0.005),
    # The roster table's mean-recommendation column, slot by slot, at the two places it prints.
    ("H", "8-slot: mean recommendation, slot C1", 4.03, 0.005),
    ("H", "8-slot: mean recommendation, slot C2", 5.41, 0.005),
    ("H", "8-slot: mean recommendation, slot C3", 5.69, 0.005),
    ("H", "8-slot: mean recommendation, slot C4", 6.69, 0.005),
    ("H", "8-slot: mean recommendation, slot C5", 5.38, 0.005),
    ("H", "8-slot: mean recommendation, slot C6", 3.63, 0.005),
    ("H", "8-slot: mean recommendation, slot C7", 3.91, 0.005),
    ("H", "8-slot: mean recommendation, slot C8", 4.91, 0.005),
    ("H", "8-slot: reviews by the slots that return no Accept", 224, 0),
    ("H", "8-slot: re-run band, median |dz|", 0.0597, 0.0002),
    ("H", "8-slot: re-run band, as frozen in the parameters", 0.0597, 0.0002),
    ("H", "8-slot: re-run band p90", 0.263, 0.002),
    ("H", "8-slot: adjacent-paper gap, median", 0.0921, 0.0002),
    # The same two bands as the roster table prints them, at three places rather than four. A row at four
    # places passes whatever the third digit on the page says, so the width the reader sees needs its own row:
    # the five-model column already has one for each band, and its 0.160 and 0.115 are what every ratio in
    # section 6 is divided by.
    ("H", "8-slot: re-run band, as printed in the roster table", 0.060, 0.0005),
    ("H", "8-slot: adjacent-paper gap, as printed in the roster table", 0.092, 0.0005),
    ("H", "8-slot: composite minimum", -1.25, 0.005),
    ("H", "8-slot: composite maximum", 1.20, 0.005),
    ("H", "8-slot: panel retest rho", 0.935, 0.002),
    ("H", "8-slot: inter-slot agreement, median of 28 pairs", 0.707, 0.002),
    ("H", "8-slot: inter-slot agreement, minimum pair", 0.265, 0.002),
    ("H", "8-slot: inter-slot agreement, same-vendor pairs", 0.862, 0.002),
    ("H", "8-slot: inter-slot agreement, cross-vendor pairs", 0.700, 0.002),
    ("5", "roster swap: rho over the 16 published papers", 0.971, 0.002),
    ("H", "roster swap: rho CI low", 0.864, 0.02),
    ("H", "roster swap: rho CI high", 1.000, 0.02),
    ("H", "roster swap: drop-one rho, lowest", 0.964, 0.002),
    ("H", "roster swap: drop-one rho, highest", 0.975, 0.002),
    # The same swap for the grade read as an order. The composite's 0.971 is an agreement between two calibrated
    # scales; the grade has no calibration, so its order crossing a roster change is a separate result -- and it
    # crosses, at a little less. Both readings, since the appendix reports both against the rating too.
    ("H", "roster swap: mean grade rho over the 16 published papers", 0.907, 0.002),
    ("H", "roster swap: bar share rho over the 16 published papers", 0.890, 0.002),
    ("H", "roster swap: median level shift", 0.127, 0.002),
    ("H", "roster swap: p90 level shift", 0.303, 0.002),
    ("H", "roster swap: max level shift", 0.518, 0.002),
    ("H", "validity, published: papers with venue ratings", 15, 0),
    ("H", "validity, published: 8-slot rho", 0.202, 0.002),
    ("H", "validity, published: 5-model rho", 0.304, 0.002),
    # The two intervals the appendix leans on to say this comparison decides nothing. Both are claimed to
    # contain zero and each other, which is an arithmetic property of four bounds, and it is the whole
    # argument of the paragraph: without them the two point estimates read as one roster beating the other.
    ("H", "validity, published: 8-slot rho CI low", -0.414, 0.02),
    ("H", "validity, published: 8-slot rho CI high", 0.683, 0.02),
    ("H", "validity, published: 5-model rho CI low", -0.344, 0.02),
    ("H", "validity, published: 5-model rho CI high", 0.771, 0.02),
    # The gap between the two point estimates, which is the quantity the paragraph declines to interpret. It is
    # the subtraction the reader performs anyway, so it gets a row rather than being left as the difference of
    # two rows: those are printed to three places and this to two, and nothing checked that the coarser figure
    # is what the finer pair gives.
    ("H", "validity, published: 5-model minus 8-slot rho", 0.10, 0.005),
    ("H", "8-slot: rho severity vs output tokens", -0.43, 0.005),
    ("H", "8-slot: lowest median output tokens", 2057, 0.5),
    ("H", "8-slot: highest median output tokens", 10427, 0.5),

    # The transform arm on that roster, raw and drift-corrected. Only the last column of each triple is
    # cross-roster legal: a delta in units of the roster's own re-run band.
    ("H", "8-slot T1: raw median dz", -0.142, 0.002),
    ("H", "8-slot T2: raw median dz", -0.092, 0.002),
    ("H", "8-slot T3: raw median dz", -0.077, 0.002),
    ("H", "8-slot T1: raw papers down of 8", 6, 0),
    ("H", "8-slot T2: raw papers down of 8", 7, 0),
    ("H", "8-slot T3: raw papers down of 8", 6, 0),
    ("H", "8-slot T1: raw |median| / own band", 2.38, 0.005),
    ("H", "8-slot T2: raw |median| / own band", 1.54, 0.005),
    ("H", "8-slot T3: raw |median| / own band", 1.29, 0.005),
    ("H", "8-slot T1: corrected median dz", -0.180, 0.002),
    ("H", "8-slot T2: corrected median dz", -0.129, 0.002),
    ("H", "8-slot T3: corrected median dz", -0.114, 0.002),
    # The six interval bounds the same table prints, wide-tolerance for the reason boot_median_ci gives.
    ("H", "8-slot T1: corrected CI low", -0.262, 0.02),
    ("H", "8-slot T1: corrected CI high", +0.011, 0.02),
    ("H", "8-slot T2: corrected CI low", -0.208, 0.02),
    ("H", "8-slot T2: corrected CI high", -0.094, 0.02),
    ("H", "8-slot T3: corrected CI low", -0.224, 0.02),
    ("H", "8-slot T3: corrected CI high", -0.029, 0.02),
    ("H", "8-slot T1: corrected papers down of 8", 6, 0),
    ("H", "8-slot T2: corrected papers down of 8", 7, 0),
    ("H", "8-slot T3: corrected papers down of 8", 7, 0),
    ("H", "8-slot T1: corrected |median| / own band", 3.01, 0.005),
    ("H", "8-slot T2: corrected |median| / own band", 2.17, 0.005),
    ("H", "8-slot T3: corrected |median| / own band", 1.91, 0.005),
    ("H", "8-slot T1: paired median dz", -0.201, 0.002),
    ("H", "8-slot T2: paired median dz", -0.175, 0.002),
    ("H", "8-slot T3: paired median dz", -0.160, 0.002),
    ("H", "8-slot T1: slots with a negative median", 5, 0),
    ("H", "8-slot T2: slots with a negative median", 5, 0),
    ("6", "8-slot T3: slots with a negative median", 7, 0),
    # The per-slot table, appendix H. The count above passes for any eight values with the right signs, and
    # the table is where a claim about vendors is read off: T3 negative in seven of eight slots and in every
    # slot of five of the six vendors is an argument about which cells are which, not about how many are
    # negative. Printed at four places, so half of the last place is 0.00005.
    ("H", "8-slot T1 slot C1: median dz", -0.0706, 0.00005),
    ("H", "8-slot T1 slot C2: median dz", +0.0485, 0.00005),
    ("H", "8-slot T1 slot C3: median dz", -0.1442, 0.00005),
    ("H", "8-slot T1 slot C4: median dz", -0.4153, 0.00005),
    ("H", "8-slot T1 slot C5: median dz", -0.1991, 0.00005),
    ("H", "8-slot T1 slot C6: median dz", -0.1500, 0.00005),
    ("H", "8-slot T1 slot C7: median dz", +0.2545, 0.00005),
    ("H", "8-slot T1 slot C8: median dz", +0.0206, 0.00005),
    ("H", "8-slot T2 slot C1: median dz", -0.2224, 0.00005),
    ("H", "8-slot T2 slot C2: median dz", -0.0016, 0.00005),
    ("H", "8-slot T2 slot C3: median dz", -0.1726, 0.00005),
    ("H", "8-slot T2 slot C4: median dz", +0.0353, 0.00005),
    ("H", "8-slot T2 slot C5: median dz", -0.6823, 0.00005),
    ("H", "8-slot T2 slot C6: median dz", -0.1902, 0.00005),
    ("H", "8-slot T2 slot C7: median dz", +0.2995, 0.00005),
    ("H", "8-slot T2 slot C8: median dz", +0.0004, 0.00005),
    ("H", "8-slot T3 slot C1: median dz", -0.0812, 0.00005),
    ("H", "8-slot T3 slot C2: median dz", -0.0751, 0.00005),
    ("H", "8-slot T3 slot C3: median dz", -0.1948, 0.00005),
    ("H", "8-slot T3 slot C4: median dz", -0.0714, 0.00005),
    ("H", "8-slot T3 slot C5: median dz", -0.2562, 0.00005),
    ("H", "8-slot T3 slot C6: median dz", +0.0362, 0.00005),
    ("H", "8-slot T3 slot C7: median dz", -0.0469, 0.00005),
    ("H", "8-slot T3 slot C8: median dz", -0.1990, 0.00005),
    ("H", "8-slot T3 slot C1: papers down of 8", 5, 0),
    ("H", "8-slot T3 slot C2: papers down of 8", 4, 0),
    ("H", "8-slot T3 slot C3: papers down of 8", 6, 0),
    ("H", "8-slot T3 slot C4: papers down of 8", 4, 0),
    ("H", "8-slot T3 slot C5: papers down of 8", 5, 0),
    ("H", "8-slot T3 slot C6: papers down of 8", 3, 0),
    ("H", "8-slot T3 slot C7: papers down of 8", 4, 0),
    ("H", "8-slot T3 slot C8: papers down of 8", 6, 0),
    ("H", "8-slot T1 slot C4: median dz, as quoted in prose", -0.415, 0.0005),
    # 0.254, not the 0.255 the section was drafted with. The four-place table entry is +0.2545, which is
    # itself a rounding, and rounding it again put the third digit one out. This row is the reason the
    # same value appears twice above: the four-place row passes either way and cannot see this.
    ("H", "8-slot T1 slot C7: median dz, as quoted in prose", +0.254, 0.0005),
    # 1/256, which the paper prints as the exact null's floor wherever no sign assignment reached the
    # observed median. Two significant figures there and here, so half of the last place is 0.00005.
    ("E", "8-slot T1 composite: exact null finest resolution", 0.0039, 0.00005),
    ("H", "8-slot T1 non-allotted: exact null finest resolution", 0.0039, 0.00005),
    # The sign tests, each one a function of a count already checked above, which is what makes these rows
    # worth having: a p-value quoted beside a split is two claims, and only the split was recomputed. The last
    # of them is the eight-paper roster's, where the appendix argues from the test's coarseness -- eight papers
    # cannot reach 0.05 unless every one moves -- so there the resolution is load-bearing rather than
    # descriptive, and it is a property of n = 8 alone rather than of any observed count.
    ("6", "T1 sign test p at 23 of 46", 1.0, 0.005),
    ("6", "T2 sign test p at 22 of 48", 0.6655, 0.0005),
    # Printed as 0.000025, not 0.0000: the exact two-sided binomial at 38 of 47 is 2.4904e-05, and a
    # four-place cell rounds it to a value no test can return. The tolerance is half of the last place
    # printed, which a row at 0.0 with a four-place tolerance could not tell from zero.
    ("6", "T3 sign test p at 38 of 47", 0.000025, 0.0000005),
    ("H", "sign test resolution at n=8: p for 7 of 8", 0.070, 0.0005),
    # T2's median as Appendix E's table prints it, unsigned and at three places, against the four-place entry
    # in the body: a transform's "cost" is quoted in both registers and a row against one of them cannot see a
    # rounding that went the wrong way in the other.
    ("E", "T2 cost, as printed unsigned", 0.021, 0.0005),
    # The body table's three intervals, at the same 0.02 as every other bootstrap bound here. T1's is the
    # one that matters: it crosses zero in the bold column beside the sentence putting the composite inside
    # instrument noise, so it is the entry a reviewer who checks one number in this paper will check.
    ("6", "T1 CI low", -0.0672, 0.02),
    ("6", "T1 CI high", 0.0779, 0.02),
    ("6", "T3 CI low", -0.2034, 0.02),
    ("6", "T3 CI high", -0.0593, 0.02),
    ("6", "T2 CI low", -0.0287, 0.02),
    ("6", "T2 CI high", +0.1083, 0.02),
    ("H", "drift control: median offset", 0.0373, 0.0005),
    # The two CI bounds are the only entries whose tolerance is not a rounding width. reproduce.py runs its
    # own percentile bootstrap with its own seed, so agreement to the last digit would be agreement about a
    # random number generator; 0.02 z is tight enough to catch an interval on the wrong side of zero, which
    # is the claim the paper makes with it.
    ("H", "drift control: CI low", -0.028, 0.02),
    ("H", "drift control: CI high", 0.1328, 0.02),
    # 0.625, not 0.62: a value on a rounding boundary is a value that will not agree with itself at two
    # decimal places, so the appendix prints the three the analysis records.
    ("H", "drift control: |offset| / own band", 0.625, 0.002),
    ("H", "drift control: papers negative of 8", 2, 0),
    ("H", "8-slot: grade retest agreement %", 78.1, 0.05),
    ("H", "8-slot: grade retest cells", 128, 0),
    ("H", "8-slot: grade retest mean abs step", 0.219, 0.002),
    ("H", "8-slot T1: grade cells moved of 64", 4, 0),
    ("H", "8-slot T2: grade cells moved of 64", 5, 0),
    ("H", "8-slot T3: grade cells moved of 64", 3, 0),
    ("H", "8-slot T1: grade mean abs step", 0.195, 0.002),
    ("H", "8-slot T2: grade mean abs step", 0.211, 0.002),
    ("H", "8-slot T3: grade mean abs step", 0.180, 0.002),
    # The three arms' steps as ratios to this roster's own re-run step stood here. Appendix H prints the four
    # steps themselves, 0.195, 0.211, 0.180 and 0.219, and says in words that each arm moves the grade about as
    # far as a re-read does; it prints no ratio. A row against a quotient of two rows already here compares the
    # bundle with itself, and the three of them were reported as printed in appendix C, appendix D and section 5,
    # each a coincidental magnitude in a table about something else.
    ("H", "8-slot T1: modal grade kept of 8", 8, 0),
    ("H", "8-slot T2: modal grade kept of 8", 7, 0),
    ("H", "8-slot T3: modal grade kept of 8", 6, 0),
    ("H", "queue: mean position, T1", 9.1, 0.05),
    ("H", "queue: mean position, T2", 12.0, 0.05),
    ("H", "queue: mean position, T3", 13.4, 0.05),
    ("H", "queue: rho position vs delta", -0.09, 0.005),
    ("H", "queue: later minus earlier mean delta", -0.077, 0.002),
    # The three arm means above are compared against the position an arm would average if the shuffle ignored
    # it, and that expected value is printed without anything deriving it. It is not a stipulated parameter:
    # the queue is a fixed-seed shuffle of a fixed job list, so what an arm would average under no association
    # is a property of the list's length and is recomputable. The magnitude of the later-minus-earlier gap, too,
    # since the sentence quotes it unsigned and gives the direction in words.
    ("H", "queue: expected mean position", 11.5, 0.05),
    ("H", "queue: later minus earlier gap, as printed unsigned", 0.077, 0.002),

    # The dose check. Its answer is a dose-response in the one arm strong enough to carry one: the appendix
    # reports the joining arm's rho and p and the two weak arms' near-zero rhos, and argues from the dose ranges
    # that the three arms are not comparable in strength. The ranges and medians are therefore rows too, since
    # that argument rests on them. The eight-paper roster's three rhos were checked here as well, against a
    # roster disagreement the appendix used to report and no longer does; a rank correlation over eight papers
    # is printed nowhere now, and the three rows matched the re-run band's p90 and a channel median instead.
    ("E", "dose T1: fewest edits", 3, 0),
    ("E", "dose T1: most edits", 12, 0),
    ("E", "dose T1: median edits", 6.5, 0.001),
    ("E", "dose T2: fewest edits", 3, 0),
    ("E", "dose T2: most edits", 22, 0),
    ("E", "dose T2: median edits", 7.0, 0.001),
    ("E", "dose T3: fewest edits", 16, 0),
    ("E", "dose T3: most edits", 59, 0),
    ("E", "dose T3: median edits", 35.0, 0.001),
    ("E", "dose T1: rho edits vs delta, 5-model", 0.0146, 0.00005),
    ("E", "dose T2: rho edits vs delta, 5-model", 0.0019, 0.00005),
    ("E", "dose T3: rho edits vs delta, 5-model", -0.3143, 0.00005),
    # The five-model roster's own drift control. The two clean deltas are the only numbers in the paper that
    # are measured with no session boundary inside the contrast, so if any row here stops reproducing, the
    # appendix claim that §6's effects are not a between-session artefact goes with it.
    ("E", "N1b drift: median offset", 0.0156, 0.00005),
    ("E", "N1b drift: CI low", -0.0477, 0.02),
    ("E", "N1b drift: CI high", 0.0882, 0.02),
    ("E", "N1b drift: papers positive", 8, 0),
    ("E", "N1b band: median, this session", 0.0883, 0.00005),
    ("E", "N1b band: calibration median, same papers", 0.16, 0.002),
    ("E", "N1b band: smaller now", 10, 0),

    # The matched randomisation test. Three kinds of quantity live here and they get three kinds of tolerance,
    # because a single number would be either slack on the exact ones or wrong on the estimated ones.
    #
    #   deterministic -- every delta, every per-channel median, the variance factor, and the own-arm p and
    #       assignment count on the eight-slot roster, where eight papers let the sign null be listed rather
    #       than drawn. One arithmetic path from the shipped reviews, so half of the last printed place:
    #       0.0005 at three decimals.
    #   a sigma -- its denominator is a 200,000-draw standard deviation, whose relative error is about 0.16%
    #       either side. Two independent estimates therefore differ by up to a few hundredths at these
    #       magnitudes, which is 0.03.
    #   a pooled p -- a 200,000-draw share compared against a second, independent 200,000-draw share. The
    #       budget is 3.5 * sqrt(2p(1-p)/200000): about 0.002 at p = 0.03 and about 0.005 at p = 0.23. Split
    #       at 0.05 rather than carried per row, since above that line no printed p decides anything finer
    #       than whether it clears 0.05.
    #
    # A p the paper prints as a bound rather than a value is entered as the bound with the bound as its
    # tolerance, so the row passes for any computed value inside it and fails if the bound is overrun.
    ("6", "T1 composite: untouched papers in pool", 48, 0),
    ("6", "T1 composite: delta", -0.0085, 0.0005),
    ("6", "T3 composite: delta", -0.1384, 0.0005),
    ("6", "T2 composite: delta", 0.0214, 0.0005),
    ("6", "T1 composite: papers down", 23, 0),
    ("6", "T3 composite: papers down", 38, 0),
    ("6", "T2 composite: papers down", 22, 0),
    # The group resolution, which is where the leak claim is made and what F4's wing headers print.
    ("E", "T1 allotted: channels", 3, 0),
    ("E", "T1 non-allotted: channels", 9, 0),
    ("E", "T1 allotted: delta", -0.084, 0.0005),
    ("E", "T1 non-allotted: delta", -0.002, 0.0005),
    ("E", "T1 non-allotted: own-arm p", 0.5004, 0.003),
    ("E", "T1 non-allotted: pooled p", 0.4974, 0.002),
    # The same p at the two places F4's own wing header prints it, and its caption with it. An alias rather than
    # a second measurement, for the reason the modal-grade pair carries: a row at four places cannot be found on
    # a page that prints two, and coverage searched for by magnitude would otherwise hand the caption's value to
    # the eight-slot sigma of −0.44, a different measurement in a different appendix.
    ("E", "T1 non-allotted: pooled p at two places", 0.5, 0.005),
    ("E", "T3 allotted: delta", -0.414, 0.0005),
    ("E", "T3 non-allotted: delta", -0.109, 0.0005),
    # Both nulls put this group past every one of their 200,000 sign assignments but one, so the appendix prints
    # the floor as a bound and these two rows carry the floor itself. Written out rather than as 5e-06: the row
    # pattern audit_submission.py counts this table with reads decimals only, and a row it cannot see is a row
    # missing from the count appendix G prints.
    ("E", "T3 non-allotted: own-arm p", 0.000005, 0.000001),
    ("E", "T3 non-allotted: pooled p", 0.000005, 0.000001),
    # All twenty-four per-channel medians, because F4 draws all twenty-four and a number a figure draws is a
    # number the paper prints. Three of these disagree in their last place with the figures the section was
    # drafted from -- T1 reproducibility, T3 figure quality and, on the second roster, T3 reproducibility --
    # each one a three-place quote taken from an already-rounded number. The bundle's own rounding is what
    # these rows carry, so the prose has to move to them rather than the other way round.
    ("E", "T1 channel structure_compliance: delta", 0.05, 0.0005),
    ("E", "T1 channel clarity: delta", -0.087, 0.0005),
    ("E", "T1 channel figure_quality: delta", -0.189, 0.0005),
    ("E", "T1 channel reproducibility: delta", 0.009, 0.0005),
    ("E", "T1 channel statistical_soundness: delta", -0.024, 0.0005),
    ("E", "T1 channel related_work: delta", 0.029, 0.0005),
    ("E", "T1 channel overall_recommendation: delta", 0.002, 0.0005),
    ("E", "T1 channel breadth_generality: delta", 0.047, 0.0005),
    ("E", "T1 channel rigor: delta", 0.014, 0.0005),
    ("E", "T1 channel calibration_honesty: delta", -0.002, 0.0005),
    ("E", "T1 channel novelty: delta", -0.097, 0.0005),
    ("E", "T1 channel significance: delta", -0.051, 0.0005),
    ("E", "T3 channel clarity: delta", -0.723, 0.0005),
    ("E", "T3 channel structure_compliance: delta", -0.315, 0.0005),
    ("E", "T3 channel figure_quality: delta", -0.091, 0.0005),
    ("E", "T3 channel novelty: delta", 0.0, 0.0005),
    ("E", "T3 channel related_work: delta", 0.0, 0.0005),
    ("E", "T3 channel breadth_generality: delta", -0.015, 0.0005),
    ("E", "T3 channel calibration_honesty: delta", -0.037, 0.0005),
    ("E", "T3 channel reproducibility: delta", -0.082, 0.0005),
    ("E", "T3 channel significance: delta", -0.009, 0.0005),
    ("E", "T3 channel overall_recommendation: delta", -0.017, 0.0005),
    ("E", "T3 channel rigor: delta", -0.101, 0.0005),
    ("E", "T3 channel statistical_soundness: delta", -0.165, 0.0005),
    # The three channels whose own p-value the prose quotes. Two of them are quoted to say a channel does NOT
    # clear on its own, which is the reason the fixed-threshold count was dropped, and a claim of that shape
    # needs checking at least as much as a claim that something did clear.

    # The same test on the second roster, where T1 replicates and T3's leak does not.
    ("H", "matched variance factor", 0.866, 0.0005),
    ("H", "8-slot T1 composite: null sd", 0.0349, 0.001),
    ("H", "8-slot T1 allotted: null sd", 0.0789, 0.001),
    ("H", "8-slot T1 non-allotted: null sd", 0.0283, 0.001),
    ("H", "8-slot T1 composite: delta", -0.142, 0.0005),
    ("H", "8-slot T1 composite: sigma", -4.08, 0.03),
    ("H", "8-slot T1 allotted: delta", -0.142, 0.0005),
    ("E", "8-slot T1 non-allotted: delta", -0.137, 0.0005),
    ("H", "8-slot T1 non-allotted: sigma", -4.84, 0.03),
    ("H", "8-slot T1 non-allotted: own-arm p", 0.0, 0.0),
    ("H", "8-slot T1 non-allotted: sign assignments", 256, 0),
    ("H", "8-slot T1 non-allotted: pooled p", 0.0007, 0.0005),
    ("H", "8-slot T3 composite: delta", -0.077, 0.0005),
    ("H", "8-slot T3 composite: sigma", -2.21, 0.03),
    ("E", "8-slot T3 allotted: delta", -0.232, 0.0005),
    ("E", "8-slot T3 non-allotted: delta", -0.013, 0.0005),
    ("H", "8-slot T3 non-allotted: sigma", -0.44, 0.03),
    # Two places, because two places is what the table prints: 0.42. A row checked to four places passes
    # whatever the page says, which is how a printed value drifts from the value behind it.
    ("H", "8-slot T3 non-allotted: own-arm p", 0.4219, 0.005),
    ("H", "8-slot T3 non-allotted: pooled p", 0.3405, 0.005),
    # The eight-slot channels the prose names. T3's group null is a cancellation and the paper says so, which
    # means the upward channels are claim-bearing too and are checked alongside the downward ones. Breadth
    # gets both p-values: its pooled p clears 0.05 and its exact p does not, so it is the one channel here
    # that the paper's own two-null rule refuses, and no sentence may call it moved.
    ("E", "8-slot T1 channel reproducibility: delta", -0.205, 0.0005),
    ("E", "8-slot T1 channel significance: delta", -0.153, 0.0005),
    ("E", "8-slot T3 channel clarity: delta", -0.505, 0.0005),
    ("E", "8-slot T3 channel related_work: delta", -0.182, 0.0005),
    ("H", "8-slot T3 channel related_work: pooled p", 0.008, 0.002),
    ("H", "8-slot T3 channel related_work: own-arm p", 0.0469, 0.0005),
    ("E", "8-slot T3 channel breadth_generality: delta", -0.162, 0.0005),
    ("H", "8-slot T3 channel breadth_generality: pooled p", 0.010, 0.002),
    ("H", "8-slot T3 channel breadth_generality: own-arm p", 0.1484, 0.0005),
    ("E", "8-slot T3 channel calibration_honesty: delta", 0.065, 0.0005),
    ("E", "8-slot T3 channel reproducibility: delta", 0.049, 0.0005),
    ("E", "8-slot T3 channel novelty: delta", 0.013, 0.0005),
    # The eight-slot channels the prose does not name. They are on the page all the same: the generated table
    # in appendix E prints all twelve channels for both rosters, so every cell of it is a stated number and
    # wants an expectation. The five-model half already had all twenty-four; these sixteen are the rest of the
    # eight-slot half, and they close the gap the table opened when it replaced the prose listing. Two of them
    # round to the same three places -- structure compliance is -0.1037 and statistical soundness -0.1037 --
    # which is why the row name carries the channel rather than the value doing the identifying.
    ("E", "8-slot T1 channel structure_compliance: delta", -0.269, 0.0005),
    ("E", "8-slot T1 channel clarity: delta", -0.177, 0.0005),
    ("E", "8-slot T1 channel figure_quality: delta", -0.033, 0.0005),
    ("E", "8-slot T1 channel statistical_soundness: delta", -0.176, 0.0005),
    ("E", "8-slot T1 channel related_work: delta", -0.068, 0.0005),
    ("E", "8-slot T1 channel overall_recommendation: delta", -0.064, 0.0005),
    ("E", "8-slot T1 channel breadth_generality: delta", -0.103, 0.0005),
    ("E", "8-slot T1 channel rigor: delta", +0.027, 0.0005),
    ("E", "8-slot T1 channel calibration_honesty: delta", +0.023, 0.0005),
    ("E", "8-slot T1 channel novelty: delta", +0.009, 0.0005),
    ("E", "8-slot T3 channel structure_compliance: delta", -0.104, 0.0005),
    ("E", "8-slot T3 channel figure_quality: delta", -0.058, 0.0005),
    ("E", "8-slot T3 channel statistical_soundness: delta", -0.104, 0.0005),
    ("E", "8-slot T3 channel overall_recommendation: delta", -0.043, 0.0005),
    ("E", "8-slot T3 channel rigor: delta", -0.033, 0.0005),
    ("E", "8-slot T3 channel significance: delta", -0.074, 0.0005),
    # How the nine non-allotted channels split, and how the eight papers split. These are two different
    # denominators and the section conflated them: the papers go four down and four up, the channels go six
    # down and three up. Four and four over nine channels does not even add up, so both are rows here.
    ("H", "8-slot T3 non-allotted: papers down", 4, 0),
    ("H", "8-slot T3 non-allotted: channels down", 6, 0),
    # Appendix E's treatment-strength floor: how many paper-variant cells there are and how many fall under
    # their transform's minimum. Every one of those is withheld, which the block in main() asserts.
    ("E", "floor: paper-variant cells", 144, 0),
    ("E", "floor: cells under the floor", 3, 0),
    ("E", "floor: cells under the floor withheld", 3, 0),
]


def load(pat):
    """-> {path-tail: review}, skipping the empty placeholders a resumable run leaves behind."""
    out = {}
    for f in sorted(glob.glob(pat)):
        if os.path.getsize(f) > 2:
            out[f] = json.load(open(f))
    return out


def zmean(review, slot, mu, sd, metrics):
    """-> mean z of one review's metric scores against the frozen per-(slot, metric) parameters."""
    z = [(review["metrics"][m]["score"] - mu[f"{slot}|{m}"]) / sd[f"{slot}|{m}"]
         for m in metrics if m in review.get("metrics", {}) and sd.get(f"{slot}|{m}")]
    return st.mean(z) if z else None


def cells(root, mu, sd, metrics, pat="R?.json", levels=1):
    """-> {(unit, panel, slot): z}, the finest grain the bundle holds.

    Every aggregate below is derived from this one read. Two review trees have to be read -- one directory per
    paper, and one variant directory nested under the paper -- and writing a second glob to match the second
    layout is a second chance to read the wrong files, so the nesting depth is a parameter instead.

    pat selects the roster: the five-model slots are R1..R5, the eight-slot roster's are C1..C8, and in both a
    slot's name is the first two characters of its filename.
    """
    out: dict[tuple, float] = {}
    for f, r in load(f"{root}/{'/'.join(['*'] * levels)}/panel*/{pat}").items():
        parts = f.split("/")
        v = zmean(r, os.path.basename(f)[:2], mu, sd, metrics)
        if v is not None:
            out[("/".join(parts[-(levels + 2):-2]), parts[-2], os.path.basename(f)[:2])] = v
    return out


def composites(root, mu, sd, metrics, pat="R?.json"):
    """-> {paper: {panel: composite}}, the panel composite being the mean over its reviews."""
    out: dict[str, dict[str, list]] = {}
    for (paper, panel, _), v in cells(root, mu, sd, metrics, pat).items():
        out.setdefault(paper, {}).setdefault(panel, []).append(v)
    return {p: {k: st.mean(v) for k, v in d.items()} for p, d in out.items()}


def grades(root, pat="R?.json"):
    return [r.get("grade") or r.get("overall_grade") for r in load(f"{root}/*/panel*/{pat}").values()]


def grades_by(root, pat, key):
    """-> {key(path): [grade]}, for the two questions a flat grade list cannot answer: which slot said Accept,
    and which panels of which paper cleared a consensus bar."""
    out: dict[object, list] = {}
    for f, r in load(f"{root}/*/panel*/{pat}").items():
        out.setdefault(key(f), []).append(r.get("grade") or r.get("overall_grade"))
    return out


def _ranks(v):
    """Ranks, ties averaged, which the venue ratings have plenty of."""
    s = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
            j += 1
        for k in range(i, j + 1):
            r[s[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(xs, ys):
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else float("nan")


def auc(pos, neg):
    """Rank AUC = P(a random positive scores above a random negative), ties at half."""
    w = sum(1 if a > b else 0.5 if a == b else 0 for a in pos for b in neg)
    return w / (len(pos) * len(neg))


# --- The distribution functions the appendices' p-values need. -----------------------------------------------
# The analysis scripts that produced those p-values use scipy; the bundle may not have it, and a reproduction
# script that cannot run is the failure this file exists to prevent. So the two tail probabilities are
# implemented here in the standard library, and each was checked against scipy on this paper's own data before
# being trusted: the Spearman and Kendall p-values below agree with scipy to better than 1e-6, and the
# Mann-Whitney one agrees on both of its branches. That check is the reason these are allowed to carry a row.

def _betacf(a, b, x):
    """Continued fraction for the incomplete beta function, Lentz's method."""
    tiny, eps = 1e-30, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)),
                   -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + aa * d
            d = d if abs(d) > tiny else tiny
            c = 1.0 + aa / c
            c = c if abs(c) > tiny else tiny
            d = 1.0 / d
            h *= d * c
        if abs(d * c - 1.0) < eps:
            break
    return h


def betai(a, b, x):
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
          + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lb) * _betacf(b, a, 1.0 - x) / b


def t_p(t, df):
    """Two-sided p for Student's t on df degrees of freedom."""
    return betai(0.5 * df, 0.5, df / (df + t * t)) if df > 0 else float("nan")


def norm_p(z):
    """Two-sided p for the standard normal."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def spearman_p(xs, ys):
    """-> (rho, two-sided p). The p is the t approximation on n-2 df, which is what the analysis used."""
    r = spearman(xs, ys)
    n = len(xs)
    if not (abs(r) < 1) or n < 3:
        return r, 0.0
    return r, t_p(r * math.sqrt((n - 2) / (1 - r * r)), n - 2)


def kendall(xs, ys):
    """-> (tau-b, two-sided p) by the tie-corrected asymptotic variance.

    tau-b rather than tau-a because the venue ratings tie heavily: eleven of the sixteen low-arm papers share
    one rating, and tau-a would divide by pairs that carry no information about either ordering.
    """
    n = len(xs)
    con = dis = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = xs[i] - xs[j], ys[i] - ys[j]
            if a == 0 and b == 0:
                tx += 1
                ty += 1
            elif a == 0:
                tx += 1
            elif b == 0:
                ty += 1
            elif (a > 0) == (b > 0):
                con += 1
            else:
                dis += 1
    n0 = n * (n - 1) / 2

    def groups(v):
        c = collections.Counter(v)
        return [k for k in c.values() if k > 1]

    gx, gy = groups(xs), groups(ys)
    var = ((n * (n - 1) * (2 * n + 5)
            - sum(t * (t - 1) * (2 * t + 5) for t in gx)
            - sum(u * (u - 1) * (2 * u + 5) for u in gy)) / 18.0
           + sum(t * (t - 1) for t in gx) * sum(u * (u - 1) for u in gy) / (2.0 * n * (n - 1))
           + (sum(t * (t - 1) * (t - 2) for t in gx) * sum(u * (u - 1) * (u - 2) for u in gy))
           / (9.0 * n * (n - 1) * (n - 2)))
    tau = (con - dis) / math.sqrt((n0 - tx) * (n0 - ty))
    return tau, norm_p((con - dis) / math.sqrt(var))


def partial_spearman(y, x, z):
    """Spearman(y, x) holding z fixed, via rank residuals: the definition the bundle's own script uses.

    Not the Pearson partial-correlation formula applied to ranks, which is the other thing this name is used
    for and which gives +0.394 rather than +0.344 on the length control. Both are defensible; only one is what
    the number in the appendix means.
    """
    rz = _ranks(z)
    mz = st.mean(rz)
    szz = sum((a - mz) ** 2 for a in rz)

    def resid(v):
        mv = st.mean(v)
        b = sum((a - mz) * (c - mv) for a, c in zip(rz, v)) / szz
        return [c - (b * (a - mz) + mv) for a, c in zip(rz, v)]

    return spearman_p(resid(_ranks(y)), resid(_ranks(x)))


def mannwhitney_p(a, b):
    """Two-sided p for U, by the tie-corrected normal approximation with a continuity correction.

    The approximation and not the exact enumeration, because the approximation is what the analysis reported
    at these sample sizes and so is what the appendix prints. The exact value is smaller, 0.0014 against
    0.0021, so the printed figure is the conservative one of the two.
    """
    na, nb = len(a), len(b)
    u = sum(1 if p > q else 0.5 if p == q else 0 for p in a for q in b)
    n = na + nb
    ties = sum(t ** 3 - t for t in collections.Counter(a + b).values())
    sig = math.sqrt(na * nb / 12.0 * ((n + 1) - ties / (n * (n - 1))))
    return norm_p((abs(u - na * nb / 2.0) - 0.5) / sig)


def wilcoxon_p(d):
    """Two-sided p for the signed-rank statistic, by exact enumeration over the sign patterns.

    Exact rather than asymptotic here, because sixteen pairs is where the analysis used the exact form.
    """
    d = [x for x in d if x != 0]
    n = len(d)
    r = _ranks([abs(x) for x in d])
    w = sum(ri for ri, x in zip(r, d) if x > 0)
    dist = {0.0: 1}
    for ri in r:
        nxt = collections.Counter()
        for k, c in dist.items():
            nxt[k] += c
            nxt[k + ri] += c
        dist = nxt
    lo = min(w, sum(r) - w)
    return min(1.0, 2.0 * sum(c for k, c in dist.items() if k <= lo) / 2 ** n)


def boot_ci(fn, *args, seed=20260830, n=4000, paired=False):
    """Percentile bootstrap of any statistic, with the same caveat boot_median_ci carries about seeds.

    `paired` resamples one index vector and applies it to every argument, which is required for a statistic
    that is a property of the pairing: drawing each vector its own indices destroys the association and
    returns an interval around zero whatever the truth is.

    A draw whose statistic is not finite is dropped rather than sorted. spearman() returns NaN on a constant
    column instead of raising, and a coarse column has constant resamples: the share of a paper's reviews at
    or above the acceptance bar is zero for 24 of the 32 declined papers, so about one draw in ten thousand
    lands entirely on those. Two NaNs in four thousand values are enough to make the sort meaningless, which
    is how a percentile interval comes to move by 0.16 with the seed. Dropped draws are capped rather than
    ignored, because an interval computed over the draws that happened to be defined is an interval over a
    population nobody chose.
    """
    rng = random.Random(seed)
    out, dropped = [], 0
    for _ in range(n):
        if paired:
            idx = [rng.randrange(len(args[0])) for _ in args[0]]
            rs = [[a[i] for i in idx] for a in args]
        else:
            rs = [[a[rng.randrange(len(a))] for _ in a] for a in args]
        try:
            v = fn(*rs)
        except (ZeroDivisionError, ValueError):
            v = float("nan")
        if v == v and abs(v) != math.inf:
            out.append(v)
        else:
            dropped += 1
    assert dropped <= n // 100, f"bootstrap undefined on {dropped} of {n} draws"
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def decomp(obs):
    """Two-way decomposition of the raw overall-recommendation channel: paper, reviewer slot, residual.

    obs is (paper, slot, score). The design is balanced -- every paper x slot x panel cell is filled -- so the
    paper and slot effects are orthogonal and the two sums of squares subtract cleanly from the total.

    Two sets of numbers come back, because only one of them travels between rosters. The percentage shares are
    what the paper prints per roster, and they are NOT comparable across rosters: SS_slot carries (k-1) degrees
    of freedom, so it grows with the number of slots even if every slot is exchangeable. The variance
    components (Searle's estimators for the balanced two-way random model) divide each sum of squares by its df
    and net out the residual, which removes that dependence -- var_slot estimates the same population quantity
    at k=5 and k=8, which is why the paper's five-against-eight comparison uses these and not the shares.
    """
    papers = sorted({o[0] for o in obs})
    slots = sorted({o[1] for o in obs})
    a, b = len(papers), len(slots)
    n = len(obs) / (a * b)                                       # replicates per cell = panels
    gm = st.mean(o[2] for o in obs)
    ss_tot = sum((o[2] - gm) ** 2 for o in obs)
    ss, means = {}, {}
    for i, name in ((0, "paper"), (1, "slot")):
        g: dict[str, list] = {}
        for o in obs:
            g.setdefault(o[i], []).append(o[2])
        ss[name] = sum(len(v) * (st.mean(v) - gm) ** 2 for v in g.values())
        means[name] = {k: st.mean(v) for k, v in g.items()}
    cell: dict[tuple, list] = {}
    for o in obs:
        cell.setdefault((o[0], o[1]), []).append(o[2])
    ss_err = ss_tot - sum(len(v) * (st.mean(v) - gm) ** 2 for v in cell.values())
    ss_int = ss_tot - ss_err - ss["paper"] - ss["slot"]
    ms_err = ss_err / (a * b * (n - 1)) if n > 1 else float("nan")
    ms_int = ss_int / ((a - 1) * (b - 1))
    sm = list(means["slot"].values())
    return dict(paper_pct=100 * ss["paper"] / ss_tot, slot_pct=100 * ss["slot"] / ss_tot,
                # What the two named shares leave over, which the ladder prints as its third column. Computed
                # as a share of the total rather than as 100 minus the other two, so that a row failing to add
                # up is visible here instead of being arranged away.
                residual_pct=100 * (ss_tot - ss["paper"] - ss["slot"]) / ss_tot,
                ratio=ss["slot"] / ss["paper"], spread=max(sm) - min(sm), slot_sd=st.stdev(sm),
                var_paper=max(0.0, (ss["paper"] / (a - 1) - ms_int) / (b * n)),
                var_slot=max(0.0, (ss["slot"] / (b - 1) - ms_int) / (a * n)))


def nested(obs, vendor_of):
    """-> vendor's share of the between-slot sum of squares, and the vendor means.

    Three of the eight slots are personas of one OpenAI model, so vendor and slot-within-vendor are separately
    estimable: if reviewer identity is really vendor identity, the vendor line takes nearly all of it. The
    vendor groups are unbalanced (3, 1, 1, 1, 1, 1), so vendor means are weighted by slot count -- a Type-I
    decomposition with vendor entered first, which is the only order in which the question makes sense.
    """
    slots: dict[str, list] = {}
    for o in obs:
        slots.setdefault(o[1], []).append(o[2])
    sm = {s: st.mean(v) for s, v in slots.items()}
    gm = st.mean(o[2] for o in obs)
    ven: dict[str, list] = {}
    for s, m in sm.items():
        ven.setdefault(vendor_of[s], []).append((m, len(slots[s])))
    ss_slot = sum(len(v) * (sm[s] - gm) ** 2 for s, v in slots.items())
    ss_ven = sum(sum(k for _, k in mem) * (sum(m * k for m, k in mem) / sum(k for _, k in mem) - gm) ** 2
                 for mem in ven.values())
    return dict(vendor_share=100 * ss_ven / ss_slot,
                vendor_means={v: sum(m * k for m, k in mem) / sum(k for _, k in mem)
                              for v, mem in ven.items()},
                within_vendor_spread={v: max(m for m, _ in mem) - min(m for m, _ in mem)
                                      for v, mem in ven.items() if len(mem) > 1})


def overall(root, keep=None, pat="R?.json"):
    """-> [(paper, slot, raw overall_recommendation score)] for the variance decomposition."""
    return [(f.split("/")[-3], os.path.basename(f)[:2], float(r["metrics"]["overall_recommendation"]["score"]))
            for f, r in load(f"{root}/*/panel*/{pat}").items()
            if (keep is None or keep(f.split("/")[-3])) and "overall_recommendation" in r.get("metrics", {})]


def per_slot(root, mu, sd, metrics, keep=None, pat="R?.json"):
    """-> {slot: {paper: composite}}, each slot's own ordering, averaged over its panels first so that slot
    disagreement is not read off a single noisy panel."""
    acc: dict[str, dict[str, list]] = {}
    for (paper, _, slot), v in cells(root, mu, sd, metrics, pat).items():
        if keep is None or keep(paper):
            acc.setdefault(slot, {}).setdefault(paper, []).append(v)
    return {s: {p: st.mean(v) for p, v in d.items()} for s, d in acc.items()}


def boot_median_ci(xs, seed=20260830, n=20000):
    """Percentile bootstrap of the median. The paper's own scripts use their own seeds, so this will not
    reproduce a CI bound to the last digit and the tolerances for CI entries say so; what it checks is that
    the interval sits where the paper puts it, which is the claim being made.

    20,000 draws rather than the 4,000 the other bootstrap here uses, because the bootstrap distribution of
    a median is supported on the sample's order statistics: a percentile of it lands on one of them or on
    its neighbour, and where the sample is thinly spread there the seed decides which. One bound in section
    6's table has neighbours 0.027 apart, more than the allowance these rows carry, so at 4,000 draws it
    disagreed with the manuscript by the width of a gap in the data rather than by any error."""
    rng = random.Random(seed)
    k = len(xs)
    b = sorted(st.median([xs[rng.randrange(k)] for _ in range(k)]) for _ in range(n))
    return b[int(0.025 * n)], b[int(0.975 * n)]


# --- the day-matched contrast --------------------------------------------------------------------------------
# The presentation study's own reading layer. It is separate from cells()/composites() above for one reason:
# every statistic in it depends on WHICH SITTING a panel was read in, and a reading table that drops the day
# cannot express the contrast the section reports. Everything else -- the z, the channel set, the panel mean --
# is the same definition, checked against the shipped per-paper composites at the top of main().

# The accepted arm is keyed by arXiv identifier and the declined arm by its release label, so the two trees
# can be read into one table: no paper id appears in both.
DMTREES = (("drift_5model", "accepted"), ("transform_rejected", "declined"))
CONDITIONS = ("baseline", "T1_endmatter", "T2_concede", "T3_lengthen")


def licensed(metrics):
    """-> {transform: the channels that edit may legitimately reach}, over one roster's channel list.

    Fixed from the metric definitions before any outcome was seen, and the only judgement in any of this. The
    two presentation edits share their allotment. Claim withdrawal changes content, so it is licensed
    everywhere except the one channel it cannot touch -- which is why a leak in that arm means something
    different, and why its two groups are eleven channels and one rather than three and nine.

    Derived from the roster's own channel list rather than typed out, so the eleven cannot fall out of step
    with the twelve if a channel is ever added or renamed.
    """
    return {"T1_endmatter": {"structure_compliance", "clarity", "figure_quality"},
            "T3_lengthen": {"clarity", "structure_compliance", "figure_quality"},
            "T2_concede": set(metrics) - {"figure_quality"}}
# A variant panel against a two-panel same-day baseline mean carries sigma^2/1 + sigma^2/2; a
# panel-against-panel re-run difference carries 2 sigma^2. So a re-run difference is multiplied by this before
# it calibrates a delta, or the arm is held to a band wider than its own noise.
MSCALE = ((1 / 1 + 1 / 2) / 2) ** 0.5


def dmtable(B, mu, sd):
    """-> {(paper, condition, panel): {day, corpus, ch: {channel: [z]}, grades: {slot: grade}}}.

    One parse of both day-matched trees, at the finest grain the contrast needs.

    A panel short of the full slot complement is dropped here and nowhere else. Such a panel is one
    reviewer's reading carrying a panel's weight, and one of them was briefly the largest single value in the
    declined arm.

    The scoring day is not recorded inside a review, so it travels beside them in the bundle. Its own note
    says how it was recovered and what it was checked against; recovering it here from file timestamps would
    read the day the bundle was unpacked.
    """
    days = json.load(open(f"{B}/data/panel_days.json"))["panels"]
    nslot = len({k.split("|")[0] for k in mu})
    out: dict[tuple, dict] = {}
    for tree, corpus in DMTREES:
        for f, r in load(f"{B}/reviews/{tree}/*/*/panel*/R?.json").items():
            p = f.split("/")
            slot = os.path.basename(f)[:-5]
            e = out.setdefault((p[-4], p[-3], p[-2]),
                               {"day": days[os.path.relpath(os.path.dirname(f), B)], "corpus": corpus,
                                "ch": {}, "grades": {}, "slots": set()})
            e["slots"].add(slot)
            e["grades"][slot] = r.get("grade") or r.get("overall_grade")
            for c, md in r.get("metrics", {}).items():
                k = f"{slot}|{c}"
                if k in mu and sd.get(k) and isinstance(md.get("score"), (int, float)):
                    e["ch"].setdefault(c, []).append((md["score"] - mu[k]) / sd[k])
    return {k: v for k, v in out.items() if len(v["slots"]) == nslot}


def dm_axis(R, cols):
    """-> {paper: {condition: {panel: mean z over the axis}}}.

    The axis is a set of channels, and a panel's score on it is the mean z over its (slot, channel) cells --
    the composite's rule, narrowed to a subset of the twelve instead of all of them. No day here: which panels
    a contrast uses is settled by dm_pairs below, from the day structure alone, so that a single-channel axis
    and the composite cannot end up differencing against different baseline panels.
    """
    out: dict[str, dict] = {}
    for (paper, cond, panel), e in R.items():
        zs = [z for c in cols for z in e["ch"].get(c, ())]
        if zs:
            out.setdefault(paper, {}).setdefault(cond, {})[panel] = st.mean(zs)
    return out


def dm_pairs(R, transform):
    """-> {paper: {"variant": [panels], "base": [two panels], "rerun": [two], "any": [two]}}, day held fixed.

    One rule in one place, because four readings depend on it: the delta, the re-run band, the sign null's pool
    and the grade. Two definitions of "the baseline this is measured against" is how a section comes to report
    a delta and a grade step that were taken against different text.

    `base` is the first TWO baseline panels of the variant's own day. Two, not every same-day panel that
    exists: a later pass added two more baseline panels to part of the accepted arm while the declined arm only
    ever has two, so averaging all of them would leave an accepted-against-declined comparison partly a
    comparison of baseline precision. Not panel1 and panel2 by name either -- some variant panels were scored
    the day after that paper's first two baseline panels, and naming the panels drops those papers silently.

    `rerun` is the pair that calibrates the sign null, and it comes from the day the delta was measured on: a
    pair from a day the arm was never treated on would set the null's width from the wrong sitting. `any` is
    the paper's first two panels sharing any day, which is what an untouched paper offers and what the grade
    ladder's ceiling is measured on -- one denominator for all three arms, since the section prints their three
    steps as ratios to it and three ratios against three yardsticks are not comparable.

    Both are collected for every paper that has a pair rather than only the treated ones. An untouched paper
    has no variant day to match and still belongs in the pool.
    """
    days: dict[str, dict] = {}
    for (paper, cond, panel), e in R.items():
        days.setdefault(paper, {}).setdefault(cond, {})[panel] = e["day"]
    out = {}
    for paper, conds in sorted(days.items()):
        base = conds.get("baseline") or {}
        var = conds.get(transform) or {}
        vdays = sorted(set(var.values()))
        # One re-run value per paper is well defined only while that paper's treated panels share a day. If
        # they ever do not, the band and the sign null need a day apiece, and this has to say so rather than
        # pick one of the two.
        assert len(vdays) <= 1, f"{paper}'s {transform} panels span {vdays}"
        e = {"variant": sorted(var), "base": [], "rerun": [], "any": []}
        # `transform=None` asks for the treatment-free reading: no variant, so `base` stays empty and `rerun`
        # falls through to `any`. It is how the grade ceiling is taken without naming an arm.
        for day in vdays + sorted(set(base.values())):
            names = [n for n in sorted(base) if base[n] == day][:2]
            if len(names) == 2:
                e["rerun"] = names
                break
        for day in sorted(set(base.values())):
            names = [n for n in sorted(base) if base[n] == day][:2]
            if len(names) == 2:
                e["any"] = names
                break
        if vdays:
            names = [n for n in sorted(base) if base[n] == vdays[0]][:2]
            if len(names) == 2:
                e["base"] = names
        out[paper] = e
    return out


def dm_matched(R, cols, transform):
    """-> ({paper: delta}, {paper: re-run difference, matched}) on the axis spanned by cols."""
    A = dm_axis(R, cols)
    P = dm_pairs(R, transform)
    deltas, rerun = {}, {}
    for paper, e in P.items():
        base = (A.get(paper) or {}).get("baseline") or {}
        var = (A.get(paper) or {}).get(transform) or {}
        if len(e["rerun"]) == 2 and all(n in base for n in e["rerun"]):
            rerun[paper] = (base[e["rerun"][1]] - base[e["rerun"][0]]) * MSCALE
        if var and len(e["base"]) == 2 and all(n in base for n in e["base"]):
            deltas[paper] = st.mean(var.values()) - st.mean(base[n] for n in e["base"])
    return deltas, rerun


def modal(grades):
    """-> the grade a venue reads off a panel: modal over its slots, ties broken DOWN toward Reject.

    The tie-break is the instrument's rule and not a convenience here. Two readings of one text that tie
    differently would otherwise be recorded as a grade change, which is the quantity this is used to measure.
    """
    gs = [g for g in grades.values() if g in ORDER]
    if not gs:
        return None
    best = max(gs.count(g) for g in set(gs))
    return min((g for g in set(gs) if gs.count(g) == best), key=lambda g: ORDER[g])


def strings(obj):
    """Every string leaf of a review, so a pattern is matched against one field and not across two."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)
    elif isinstance(obj, str):
        yield obj

# What a review charges the author for, split by whether the thing it charges is in the submitted document or
# only in the text the extractor supplied. Appendix A reports these counts over the corpus -- 1,216 untouched
# reviews of 48 third-party submissions -- and the patterns live here rather than beside that appendix because a
# count of reviews that "name an extract-only property" is a definition before it is a measurement: while the
# definition sat in the analyst's head the proportion could not be recomputed from any released tree.
#
# Deliberately narrow, and narrow about the property rather than about the wording. Both patterns began as the
# literal phrasings a handful of reviews happened to use, which counts phrasings and not the thing they
# describe: a pattern written that way can only fall on reviews it was not written from, and it did, reporting
# no cross-reference complaint on a set where two reviews make one in different words. They are rewritten here
# to name the property. EXTRACT_ONLY matches a review charging something the extract did rather than something
# the document does -- the supplied text, an unavailable appendix, an extraction glitch -- rather than merely
# mentioning extraction, which several reviews do because extraction is part of what these papers are about.
# XREF_DENSITY needs both halves of the complaint in one field: the manuscript's own cross-references or
# appendix pointers, and a reading cost charged to them. Neither pattern quotes a review.
#
# The flags these produce ship per review in data/extract_corpus.json, because the reviews of the declined
# submissions ship as scores only and the rate cannot be recounted from them. The block in main() that reads
# that file re-derives every flag of the two populations whose reviews DO ship in full, with these patterns,
# and fails on a disagreement. So the definition is not merely documented beside the count: a pattern edited
# without the file being rebuilt stops the run.
EXTRACT_ONLY = (r"(?i)(this extract\b|supplied (manuscript|text|appendices)|provided (manuscript|text)"
                r"|extract(ed|ion)[ /](text|typography|glitch)|unavailable appendi"
                r"|appendices (are |were )?(not |un)available"
                r"|not (present|included|available) in the (supplied|provided|attached|extracted))")
XREF_TARGET = (r"(?i)(cross-referenc|forward referenc|backward section reference"
               r"|appendix[- ](reference|pointer|heav)|references to appendices|pointers to appendices)")
XREF_COST = (r"(?i)(dense|density|heav|impede|slow|hard(er)? to|difficult|burden|navigat"
             r"|standalone|self-contain)")


def charges(review, pat):
    """True if any single string in the review matches pat, which may be a (target, cost) conjunction."""
    target, cost = pat if isinstance(pat, tuple) else (pat, None)
    for field in strings(review):
        if re.search(target, field) and (cost is None or re.search(cost, field)):
            return True
    return False


# A third property: a review that names extraction, sets it aside in so many words, and charges the
# manuscript's prose anyway. It is the one charge extraction cannot explain away, since the reviewer making it
# has already discounted extraction themselves, and it is counted for that reason rather than for its size,
# which runs from none to eleven reviews depending on the population.
#
# The pattern is the concession, not the complaint after it, since the complaints are worded every way a reader
# can dislike compressed prose and matching those would again count phrasings rather than the property.
DISCOUNT_EXTRACT = (r"(?i)(beyond|even (?:discounting|accounting for|setting aside|excluding|"
                    r"after allowing for)|apart from|aside from|independent of|net of|controlling for)"
                    r"[^.]{0,45}extract(?:ion|ed)?(?: artifacts?| artefacts?|ion|ed text)?")

CHARGES = (("charge an extract-only property", EXTRACT_ONLY),
           ("charge cross-reference density", (XREF_TARGET, XREF_COST)),
           ("discount extraction and charge the prose", DISCOUNT_EXTRACT))


# Both the patterns above and this helper are module level so that anything else describing these counts
# measures them with the same rule the expectation table checks -- the corpus tools import them from here for
# that reason. A brief written for a rewrite of appendix A's evidence paragraph first carried its own
# hand-written patterns and reported a different count than this table's: the paragraph would have printed a
# number no gate could reproduce.

def main():
    # Runs both from inside the unpacked bundle, where it sits at the root beside reviews/, and from the
    # working directory that builds the bundle. A reader following the README types no argument.
    here = os.path.dirname(os.path.abspath(__file__))
    default = here if os.path.isdir(f"{here}/reviews") else f"{here}/release/aina2026_agent_reviewers"
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=default)
    a = ap.parse_args()
    B = a.bundle
    calib = json.load(open(f"{B}/calibration/calibration_params_portable.json"))
    mu, sd, metrics = calib["mu"], calib["sd"], calib["metrics"]
    got = {}

    # --- the composite definition, checked against the shipped parameters before anything is built on it ----
    acc = composites(f"{B}/reviews/accepted", mu, sd, metrics)
    paper_comp = {p: st.mean(d.values()) for p, d in acc.items()}
    ref = calib["per_paper_composite"]
    worst = max(abs(paper_comp[p] - ref[p]) for p in ref)
    print(f"composite definition reproduces the shipped per-paper values to {worst:.2e} "
          f"over {len(ref)} published papers")
    # 1e-4, not 1e-9: the portable parameter file stores mu, sd and the reference composites rounded to four
    # decimals, so an exact recomputation cannot agree closer than that grid allows. Anything above it would
    # mean the composite is defined differently here than where the parameters were fitted.
    assert worst < 1e-4, "the composite recomputed here is not the composite the calibration file records"

    # --- section 1: how large the corpus is, arm by arm -----------------------------------------------------
    # The first number in the paper is a count of reviews, and until now it was the one class of claim nothing
    # here recomputed: every row below this point reads an arm and checks a statistic of it, so an arm that
    # shipped short would change the statistic slightly and pass, while the sentence promising 2,972 reviews
    # went unread. The roster totals are sums of these, not separate counts, because that is the arithmetic
    # a reader does and the place the itemisation could fail to add up.
    ARMS = (("accepted", "5-model", "3"), ("rejected", "5-model", "3"), ("transform", "5-model", "6"),
            ("transform_rejected", "5-model", "6"), ("drift_5model", "5-model", "E"),
            ("dayrep_5model", "5-model", "E"), ("vendor_panel", "8-slot", "3"),
            ("vendor_transform", "8-slot", "H"), ("vendor_drift", "8-slot", "H"))
    # Depth varies: the transform arms hold one directory per variant under each paper. Counted by walking the
    # arm rather than by a per-arm glob, so a review filed at an unexpected depth is counted rather than missed.
    # The rejected arm's untouched panels are the baselines of that corpus's transform arm: the same reviews
    # ship under reviews/rejected and under reviews/transform_rejected/*/baseline. The totals count each review
    # once, after asserting that every file of the first tree is the file of the same paper, panel and slot in
    # the second. Matching by path, not by content: score-only copies of two different reviews can coincide.
    n_rev = {}
    for arm, _, _ in ARMS:
        n_rev[arm] = sum(1 for f in glob.glob(f"{B}/reviews/{arm}/**/[RC]?.json", recursive=True)
                         if os.path.getsize(f) > 2)
        got[f"corpus: {arm} reviews"] = n_rev[arm]
    for f in glob.glob(f"{B}/reviews/rejected/*/panel*/R?.json"):
        q = f.split("/")
        twin = f"{B}/reviews/transform_rejected/{q[-3]}/baseline/{q[-2]}/{q[-1]}"
        assert os.path.exists(twin) and open(f, "rb").read() == open(twin, "rb").read(), f
    shared = n_rev["rejected"]
    for roster in ("5-model", "8-slot"):
        got[f"corpus: {roster} roster reviews"] = (sum(n_rev[a] for a, r, _ in ARMS if r == roster)
                                                   - (shared if roster == "5-model" else 0))
    got["corpus: total reviews"] = sum(n_rev.values()) - shared
    got["corpus: presentation study reviews"] = got["corpus: total reviews"]
    got["frame: ICLR 2026 submissions"] = len(json.load(open(f"{B}/frame/iclr2026_frame.json")))
    # The self-review is outside the total on purpose: it supports no claim, and §1 counts the study corpus.
    # Asserted rather than left implicit, because the count above is a sum over a directory listing and a
    # future arm would join it silently.
    assert not {"self", "self_earlier_build"} & set(n_rev), "the self-review is being counted as study data"

    # --- section 3: the grade distribution and the consensus ladder ----------------------------------------
    for arm, root, n in (("accepted", f"{B}/reviews/accepted", 160), ("rejected", f"{B}/reviews/rejected", 320)):
        g = grades(root)
        assert len(g) == n, f"{arm}: {len(g)} reviews, expected {n}"
        for grade in GRADES:
            got[f"{arm}: {grade} %"] = 100 * g.count(grade) / len(g)
            got[f"{arm}: {grade} count"] = g.count(grade)
    got["all 480: Accept count"] = got["accepted: Accept count"] + got["rejected: Accept count"]
    # The denominator that count is one of, and the rate the two make. It is the table's total row, and the
    # sentence built on it -- one review in 480 said Accept -- is the paper's most quoted single figure, so the
    # 480 needs a row as much as the 1 does. Summed from the two arms rather than written down, so an arm that
    # shipped short shows here instead of quietly raising the rate.
    got["all 480: reviews"] = sum(len(grades(r)) for r in (f"{B}/reviews/accepted", f"{B}/reviews/rejected"))
    got["all 480: Accept %"] = 100 * got["all 480: Accept count"] / got["all 480: reviews"]

    by_panel: dict[tuple, list] = {}
    for f, r in load(f"{B}/reviews/accepted/*/panel*/R?.json").items():
        by_panel.setdefault((f.split("/")[-3], f.split("/")[-2]), []).append(r.get("grade"))
    bars = {
        1: lambda gs: all(ORDER[x] >= ORDER["Minor Revision"] for x in gs),
        2: lambda gs: any(x == "Accept" for x in gs),
        3: lambda gs: ORDER[st.mode(gs)] >= ORDER["Minor Revision"],
        4: lambda gs: all(ORDER[x] >= ORDER["Major Revision"] for x in gs),
    }
    for b, pred in bars.items():
        hit = {k: pred(v) for k, v in by_panel.items()}
        got[f"bar {b} panels (" + {1: "every reviewer Minor+", 2: "any Accept", 3: "modal Minor+",
                                   4: "every reviewer Major+"}[b] + ")"] = sum(hit.values())
        papers = {p for p, _ in hit}
        got[f"bar {b} papers in >=1 panel"] = sum(any(hit[(p, k)] for _, k in hit if _ == p) for p in papers)
        got[f"bar {b} papers in both panels"] = sum(all(hit[(p, k)] for _, k in hit if _ == p) for p in papers)

    # --- sections 2 and 5: the two yardsticks -------------------------------------------------------------
    steps = sorted(abs(d["panel1"] - d["panel2"]) for d in acc.values() if len(d) == 2)
    got["re-run band, median |dz| over 16"] = st.median(steps)
    # The order statistic, not an interpolated quantile. With 16 values the two conventions differ by 0.017 --
    # 0.333 against 0.350 -- so the choice has to be stated rather than left to whichever library runs. The
    # paper's Appendix A states it and says what the other convention gives; a reader who reaches for
    # numpy.percentile's default and finds 0.350 has found this line, not an error.
    got["re-run band p90"] = steps[int(0.9 * (len(steps) - 1))]
    # The interpolated p90 as well, because the appendix names it: it is what a reader gets from a statistics
    # library's default, and a number quoted as the value of a rejected convention has to be the value that
    # convention actually returns or the paragraph is arguing against a straw figure. Linear interpolation
    # between order statistics, which is numpy.percentile's default.
    pos = 0.9 * (len(steps) - 1)
    lo = int(pos)
    got["re-run band p90, interpolated"] = steps[lo] + (pos - lo) * (steps[min(lo + 1, len(steps) - 1)] - steps[lo])
    # The three companions the band is reported with. The median is the band every ratio in the paper divides
    # by, so it is checked above; these are the shape of the same sixteen differences, and the signed sd is the
    # one that is not a function of the absolute values -- it reads the direction of each re-run, which is the
    # quantity that would show a panel drifting one way rather than simply being noisy.
    got["re-run band, mean |dz|"] = st.mean(steps)
    # Population divisor, which is what yardsticks.py used to produce the figure on the page: over sixteen pairs
    # the two conventions give 0.231 and 0.239, a 3.5% difference and larger than the gap between the two p90
    # conventions the paragraph does declare. Matched to the instrument rather than chosen here, for the same
    # reason the p90 is an order statistic: the band is a fixed property of this corpus that later comparisons
    # divide by, so it has one definition, and this file's job is to recompute that one rather than to pick.
    got["re-run band, signed sd"] = st.pstdev(d["panel2"] - d["panel1"] for d in acc.values() if len(d) == 2)
    order = sorted(paper_comp.values())
    got["adjacent-paper gap, median"] = st.median([b - a for a, b in zip(order, order[1:])])
    # How much of the reference field the band covers. The median gap is below the band, and five of the fifteen
    # gaps are above it, so a sentence saying neighbouring papers fall inside the instrument's scatter holds of
    # the typical pair and not of every pair. The count is the quantity the paragraph can state.
    got["reference field: adjacent pairs"] = len(order) - 1
    got["reference field: adjacent pairs inside the re-run band"] = sum(
        1 for a, b in zip(order, order[1:]) if b - a < got["re-run band, median |dz| over 16"])

    # --- section 5: the ranking claim, inside the declined arm --------------------------------------------
    rej = composites(f"{B}/reviews/rejected", mu, sd, metrics)
    rej_comp = {p: st.mean(d.values()) for p, d in rej.items()}
    ratings = json.load(open(f"{B}/data/rejected_arm_ratings.json"))["papers"]
    keys = sorted(rej_comp)
    got["rho, composite vs venue rating, 32 declined"] = spearman(
        [rej_comp[k] for k in keys], [ratings[k]["rating_mean"] for k in keys])
    hi = [rej_comp[k] for k in keys if ratings[k]["arm"] == "high"]
    lo = [rej_comp[k] for k in keys if ratings[k]["arm"] == "low"]
    got["AUC, high- vs low-rated declined"] = auc(hi, lo)
    got["AUC, published vs declined (pooled)"] = auc(list(paper_comp.values()), list(rej_comp.values()))
    # The interval the confound battery attaches to that separation, and the reason it is there: 0.840 is the
    # most favourable number in the paper about the panel's agreement with the venue, so the appendix prints the
    # width around it rather than the point alone. Unpaired, since the two arms are different papers and each
    # resamples within itself.
    got["AUC, published vs declined: CI low"], got["AUC, published vs declined: CI high"] = boot_ci(
        auc, list(paper_comp.values()), list(rej_comp.values()))

    # --- appendix A: the counts behind section 3's percentages ---------------------------------------------
    # Percentages are what the body prints and counts are what the appendix prints, and a percentage of 160 is
    # not enough to reconstruct a count a reader can compare: the appendix's point is that the same 110 of 160
    # is modal on both sides of the venue's own boundary, which is an equality between two integers and reads
    # as a coincidence worth checking. Split by the released rating arm, the same field section 5 splits on.
    rej_g = grades_by(f"{B}/reviews/rejected", "R?.json", lambda f: f.split("/")[-3])
    for arm in ("high", "low"):
        g = [x for k, v in rej_g.items() if ratings[k]["arm"] == arm for x in v]
        assert len(g) == 160, f"{arm}-rated rejected: {len(g)} reviews, expected 160"
        for grade in ("Major Revision", "Reject and Resubmit"):
            got[f"{arm}-rated rejected: {grade} count"] = g.count(grade)

    # --- appendix D: the ranking study in full, recomputed rather than read ---------------------------------
    # Every statistic in appendix D, from the review files and the released rating table. The reason it is all
    # here and not read out of analysis_results.json is that agreement with the analysis output is worth
    # nothing when the analysis output is where a defect lives: two of this appendix's coefficients turned out
    # to be correlations against a different variable than the one they were labelled with, and both of them
    # matched the analysis file exactly. What catches that class is a second implementation over the released
    # data, which is what these rows are.
    human = [ratings[k]["rating_mean"] for k in keys]
    words = [ratings[k]["deid_words"] for k in keys]
    armof = [ratings[k]["arm"] for k in keys]
    comp = [rej_comp[k] for k in keys]

    got["rho p, composite vs venue rating"] = spearman_p(comp, human)[1]
    got["rho CI low"], got["rho CI high"] = boot_ci(spearman, comp, human, paired=True)
    got["kendall tau, composite vs rating"], got["kendall tau p"] = kendall(comp, human)
    got["declined low-arm mean composite"] = st.mean(lo)
    got["declined high-arm mean composite"] = st.mean(hi)
    got["arm gap, z"] = st.mean(hi) - st.mean(lo)
    # Named for the divisor, because the conventional statistic is a different number. Dividing the gap by the
    # pooled within-group sd -- Cohen's d proper -- gives 1.208, and the paper prints the smaller figure: an
    # effect size should not grow because its author picked the more flattering of two definitions.
    got["arm gap / sd of all 32"] = got["arm gap, z"] / st.pstdev(comp)
    got["AUC CI low"], got["AUC CI high"] = boot_ci(auc, hi, lo)
    got["Mann-Whitney p, high vs low arm"] = mannwhitney_p(hi, lo)
    got["declined median composite"] = st.median(comp)
    got["declined papers above the published median"] = sum(
        1 for c in comp if c > st.median(paper_comp.values()))
    # The same count under the name section 5 prints it by. Two rows for one quantity, because the sentence in
    # the body and the row in appendix D's table are two print sites and either can go stale alone; the
    # arithmetic is written once so they cannot disagree about what was counted.
    got["declined papers above the published-field median"] = got["declined papers above the published median"]

    # --- sections 3 and 5: the same grades read as an order, not as a label ---------------------------------
    # The grade appears twice in the paper for two different reasons, and these rows are the second one. As a
    # label it is what section 3 measures: which grade a review awards, and whether that grade means what the
    # prompt's mapping says it means. As an order it is a number per paper -- the five levels coded 0 to 4 and
    # averaged over the paper's ten reviews, or the share of those reviews at or above the level the prompt
    # maps to the venue's acceptance bar -- and a number per paper can be correlated with the venue's rating
    # exactly as the composite is. Nothing about the label's failure settles the order's, so both are here,
    # against the same two criteria: the rating over the 32 declined papers, and the venue's own decision.
    #
    # Computed at this point in the file because appendix D's columns are the ones the comparison needs, and
    # recomputed here rather than read from grade_order.json for the reason this whole file exists: an analysis
    # script and its output agree by construction.
    BAR = ORDER["Minor Revision"]
    acc_g = grades_by(f"{B}/reviews/accepted", "R?.json", lambda f: f.split("/")[-3])
    ven_g = grades_by(f"{B}/reviews/vendor_panel", "C?.json", lambda f: f.split("/")[-3])
    at_bar = lambda gs: sum(1 for g in gs if ORDER[g] >= BAR)  # noqa: E731 -- read twice, three lines apart
    got["at or above the bar: accepted reviews"] = sum(at_bar(v) for v in acc_g.values())
    got["at or above the bar: declined reviews"] = sum(at_bar(v) for v in rej_g.values())
    got["at or above the bar: 5-model reviews"] = (got["at or above the bar: accepted reviews"]
                                                   + got["at or above the bar: declined reviews"])
    got["at or above the bar: 8-slot reviews"] = sum(at_bar(v) for v in ven_g.values())
    # The top label's own counts are above, under the names section 3 prints them by: one review in 480 on this
    # roster and sixteen of 256 on the other. What is new here is the pair of labels the prompt puts at or
    # above the venue's bar, which is the count the acceptance claim is actually about.

    # Equal-interval coding of an ordinal ladder for the first reading and no interval assumption at all for
    # the second, which is why both are reported: the two readings are the two ways a reader would try this,
    # and a comparison that holds under only one of them is a comparison about the coding.
    def paper_grade(gs):
        return st.mean(ORDER[g] for g in gs)

    def paper_bar(gs):
        return st.mean(ORDER[g] >= BAR for g in gs)

    for label, read in (("mean grade", paper_grade), ("bar share", paper_bar)):
        col = [read(rej_g[k]) for k in keys]
        got[f"{label}: rho vs venue rating, 32 declined"] = spearman(col, human)
        got[f"{label}: AUC, high- vs low-rated declined"] = auc(
            [c for c, a in zip(col, armof) if a == "high"], [c for c, a in zip(col, armof) if a == "low"])
        got[f"{label}: AUC, published vs declined"] = auc([read(v) for v in acc_g.values()], col)
        # The difference between two correlations measured on one set of papers is a property of the pairing,
        # so the interval resamples papers once and applies the draw to both readings and the criterion.
        gap = lambda x, c, h: spearman(x, h) - spearman(c, h)  # noqa: E731 -- the statistic being resampled
        got[f"{label}: rho minus composite rho"] = gap(col, comp, human)
        got[f"{label}: rho minus composite rho, CI low"], got[f"{label}: rho minus composite rho, CI high"] = (
            boot_ci(gap, col, comp, human, paired=True))
        # And across the roster change, on the sixteen papers both rosters read. Appendix H reports this
        # agreement for the composite; the grade has no calibration to carry an order from one roster to
        # another, so whether its order survives the swap is a separate question with a separate answer.
        both = sorted(set(ven_g) & set(acc_g))
        got[f"roster swap: {label} rho over the 16 published papers"] = spearman(
            [read(acc_g[k]) for k in both], [read(ven_g[k]) for k in both])

    # The two arms against the rating, separately. These are the coefficients that were measured against
    # scoring hour, so the row names say which variable they hold.
    for tag, want in (("low-rated arm", "low"), ("high-rated arm", "high")):
        c = [x for x, a in zip(comp, armof) if a == want]
        h = [x for x, a in zip(human, armof) if a == want]
        w = [x for x, a in zip(words, armof) if a == want]
        got[f"{tag}: rho with rating"], got[f"{tag}: p"] = spearman_p(c, h)
        # Section 5's table prints each arm's correlation with its own interval, so a reader can see that the
        # higher-rated arm's interval clears zero while the lower-rated arm's spans it.
        got[f"{tag}: CI low"], got[f"{tag}: CI high"] = boot_ci(spearman, c, h, paired=True)
        got[f"{tag}: partial rho, length held"], got[f"{tag}: partial p"] = partial_spearman(c, h, w)
        # The truncation that makes the two arms different kinds of evidence, and the reason the appendix reads
        # the null and the positive asymmetrically rather than as one uniform result.
        got[f"{tag}: distinct ratings over 16"] = len(set(h))
        got[f"{tag}: papers at the modal rating"] = max(h.count(x) for x in set(h))
        got[f"{tag}: modal rating"] = max(set(h), key=h.count)
        got[f"{tag}: modal rating, as printed"] = got[f"{tag}: modal rating"]
        # Population sd, which is the convention the appendix's 0.21 and 1.55 are printed under. The sample
        # convention gives 0.22 and 1.58, so the choice is visible in the last digit of both and is stated
        # here rather than left to whichever spelling of "sd" a reader assumes.
        got[f"{tag}: within-arm rating sd"] = st.pstdev(h)
        # The range as well, because the appendix's claim about the two middle rungs is that they hold an
        # *identical* range while sd and IQR disagree about which is wider. An equality between two arms is not
        # visible in either arm's sd, and it is the half of the sentence attributed to the sampling rule.
        got[f"{tag}: rating range"] = max(h) - min(h)
        got[f"{tag}: lowest rating"] = min(h)
        got[f"{tag}: highest rating"] = max(h)
    got["pooled rating sd, 32"] = st.pstdev(human)
    # How much of the pooled rank correlation is separation between the arms and how much is order inside them.
    # The numerator of Spearman's rho over all 32 papers, a sum of rank cross-deviations, splits exactly into a
    # between-arm term (each arm's mean ranks against the grand mean, weighted by arm size) and the within-arm
    # remainder; both are computed on the pooled ranks, so the two shares add to 100.
    prx, pry = _ranks(comp), _ranks(human)
    gmx, gmy = st.mean(prx), st.mean(pry)
    cross = sum((a - gmx) * (b - gmy) for a, b in zip(prx, pry))
    between = 0.0
    for want in ("low", "high"):
        ax = [a for a, g in zip(prx, armof) if g == want]
        ay = [b for b, g in zip(pry, armof) if g == want]
        between += len(ax) * (st.mean(ax) - gmx) * (st.mean(ay) - gmy)
    got["pooled rank covariance: % between arms"] = 100 * between / cross
    got["pooled rank covariance: % within arms"] = 100 * (cross - between) / cross
    # Appendix D prints the split to one decimal place, section 5 to whole per cent.
    got["pooled rank covariance: % between arms, one place"] = got["pooled rank covariance: % between arms"]
    got["pooled rank covariance: % within arms, one place"] = got["pooled rank covariance: % within arms"]

    # The length confound. Recomputable because the release ships each declined paper's word count under its
    # own label, which is the same reason its ratings ship: they are public at the venue, so withholding the
    # label-to-submission mapping is what the de-identification rests on, not withholding the covariates.
    got["length: rho with composite"] = spearman(comp, words)
    got["length: rho with human rating"] = spearman(human, words)
    got["length: partial rho with human rating"], got["length: partial p, human rating"] = partial_spearman(
        comp, human, words)
    got["length: partial rho with composite"], got["length: partial p"] = partial_spearman(comp, words, human)
    # The band is the word range both arms occupy: larger of the two minimums to smaller of the two maximums.
    # The same rule defines the scoring-hour window below, and it is stated here because two different windows
    # in one appendix built by two different rules would be a reader's problem, not a footnote.
    wl = [w for w, a in zip(words, armof) if a == "low"]
    wh = [w for w, a in zip(words, armof) if a == "high"]
    got["length band: low bound"] = max(min(wl), min(wh))
    got["length band: high bound"] = min(max(wl), max(wh))
    inband = [(c, a) for c, a, w in zip(comp, armof, words)
              if got["length band: low bound"] <= w <= got["length band: high bound"]]
    bl = [c for c, a in inband if a == "low"]
    bh = [c for c, a in inband if a == "high"]
    got["length band: low-arm papers"], got["length band: high-arm papers"] = len(bl), len(bh)
    got["length band: gap, z"] = st.mean(bh) - st.mean(bl)
    got["length band: AUC"] = auc(bh, bl)

    # How much the declined sample's two rated arms overlap in composite -- the lower- and higher-rated halves
    # of the same 32 papers, which is why it is 16 x 16 and not 16 x 32. Deliberately *not* a gap measured
    # inside a composite window: selecting on the outcome and then reporting the shrunken difference measures
    # the selection rule, and it would read as a result. The pair count selects on nothing and is exactly
    # 1 - AUC, so it is the same measurement the paragraph already stands beside, restated as something a
    # reader can act on.
    got["cross-arm pairs, total"] = len(lo) * len(hi)
    got["cross-arm pairs, lower-rated at least higher-rated"] = sum(1 for x in lo for y in hi if x >= y)
    got["cross-arm pairs, % lower-rated at least higher-rated"] = (
        100 * got["cross-arm pairs, lower-rated at least higher-rated"] / got["cross-arm pairs, total"])
    assert abs(got["cross-arm pairs, % lower-rated at least higher-rated"] / 100
               - (1 - got["AUC, high- vs low-rated declined"])) < 1e-9, "the pair count is not 1 - AUC"

    # Drift between a paper's two panels. panel1 precedes panel2 in all 32 papers, so the pairing needs no
    # timestamp; the hours between them do, and reviews carry none, so that one column is read from the
    # released analysis table. The correlation is between each paper's change in composite and the hours
    # between its two panels, which the appendix has to say, because three other readings of "within-paper
    # rho" are available and one of them lands within 0.00003 of a different coefficient in the same section.
    d2 = [rej[k]["panel2"] - rej[k]["panel1"] for k in keys if {"panel1", "panel2"} <= set(rej[k])]
    got["drift: mean later minus earlier, z"] = st.mean(d2)
    got["drift: median later minus earlier, z"] = st.median(d2)
    got["drift: Wilcoxon p"] = wilcoxon_p(d2)
    clock = {p["forum"]: p for p in json.load(
        open(f"{B}/data/analysis_results.json"))["papers"]}
    lag = [(max(x["t"] for x in clock[k]["panels"]) - min(x["t"] for x in clock[k]["panels"])) for k in keys]
    got["drift: rho, dcomposite vs hours between panels"], got["drift: p"] = spearman_p(
        d2, [x / 3600 for x in lag])
    # What that comparison can see. Its two panels run under a minute apart in a queue that ran for an hour
    # and a half, so it bounds a repeat reading and not drift across the queue: 1% of the interval the
    # challenge asks about. The control that does reach the queue is the hour window below.
    got["panel-to-panel lag, median seconds"] = st.median(lag)
    hours = [clock[k]["scored_h"] for k in keys]
    # Scoring order tracks the sample file's target ratings across the two arms. Inside the higher-rated arm it
    # does not track the composite, so the arm's own correlation with the rating is read with the hour held
    # fixed as well, which is the check section 5 cites for that arm.
    hc = [c for c, g in zip(comp, armof) if g == "high"]
    hr = [x for x, g in zip(human, armof) if g == "high"]
    hh = [x for x, g in zip(hours, armof) if g == "high"]
    got["high-rated arm: rho, composite vs scoring hour"] = spearman(hc, hh)
    got["high-rated arm: partial rho, scoring hour held"], got["high-rated arm: partial p, scoring hour held"] = (
        partial_spearman(hc, hr, hh))
    got["scoring queue span, minutes"] = 60 * (max(hours) - min(hours))

    # Scoring order. The pooled correlation is a selection artefact of the sample file's order; the control is
    # the restriction to the hours both arms were scored in, which conditions on the confounder rather than on
    # the outcome. It is the only test in this appendix with leverage on queue-scale drift, and it costs more
    # than half the separation.
    got["scoring hour: rho with composite, pooled"], got["scoring hour: p"] = spearman_p(comp, hours)
    hl = [h for h, a in zip(hours, armof) if a == "low"]
    hh = [h for h, a in zip(hours, armof) if a == "high"]
    got["scoring hour window: low bound"] = max(min(hl), min(hh))
    got["scoring hour window: high bound"] = min(max(hl), max(hh))
    inwin = [(c, a) for c, a, h in zip(comp, armof, hours)
             if got["scoring hour window: low bound"] <= h <= got["scoring hour window: high bound"]]
    kl = [c for c, a in inwin if a == "low"]
    kh = [c for c, a in inwin if a == "high"]
    got["scoring hour window: low-arm papers"], got["scoring hour window: high-arm papers"] = len(kl), len(kh)
    got["scoring hour window: gap, z"] = st.mean(kh) - st.mean(kl)
    got["scoring hour window: AUC"] = auc(kh, kl)

    # The two arms' rating spreads, which is how the appendix argues that the concentrated arm is the one a
    # programme committee actually faces. numpy's linear interpolation, stated because the order-statistic
    # convention gives a different width on 15 and 16 values and this file has no numpy in it.
    def pctl(v, q):
        s = sorted(v)
        i = q * (len(s) - 1)
        j = int(i)
        return s[j] if j + 1 == len(s) else s[j] + (i - j) * (s[j + 1] - s[j])

    pubmap = json.load(open(f"{B}/data/accepted_arm_human_ratings.json"))
    pubrat = [v["human"] for v in pubmap.values() if isinstance(v, dict) and "human" in v]
    got["published arm papers with a rating"] = len(pubrat)
    got["published arm rating IQ width"] = pctl(pubrat, 0.75) - pctl(pubrat, 0.25)
    got["declined arm rating IQ width"] = pctl(human, 0.75) - pctl(human, 0.25)
    got["declined arm rating span"] = max(human) - min(human)
    got["published arm rating span"] = max(pubrat) - min(pubrat)
    got["published arm: lowest rating"], got["published arm: highest rating"] = min(pubrat), max(pubrat)
    got["arm mean rating gap"] = (st.mean([x for x, a in zip(human, armof) if a == "high"])
                                 - st.mean([x for x, a in zip(human, armof) if a == "low"]))
    # The population the two arms came out of, and what the draw declined to take from it. Appendix C's account
    # of its own sampling is the one part of the design that rested on a file rather than on a measurement, so
    # these rows read the pool's rating distribution and recompute the counts the appendix states.
    #
    # Everything here is thresholded at values the paper does not print. The eligibility cut-offs have to be in
    # this file, because the two counts below are what they select; that costs nothing, since a cut-off is
    # recoverable from the released distribution and the count the appendix prints beside it. The draw's two
    # targets are a different matter and are not here: no row needs them, and they are the one parameter of the
    # rule the released ratings do not already imply. What the release does permit is stated in the README.
    pool = json.load(open(f"{B}/data/pool_rating_distribution.json"))["rating_means"]
    LOW_MAX, HIGH_MIN, PER_ARM = 3.0, 5.0, 16
    got["pool: papers drawn from"] = len(pool)
    got["pool: lowest rating"] = min(pool)
    got["pool: highest rating"] = max(pool)
    low_e = sorted(x for x in pool if x <= LOW_MAX)
    high_e = sorted((x for x in pool if x >= HIGH_MIN), reverse=True)
    got["pool: eligible for the low arm"] = len(low_e)
    got["pool: eligible for the high arm"] = len(high_e)
    # The counterfactual: the most extreme sixteen of each eligible set, against the sixteen actually drawn.
    # Well defined without the tie-break that the real draw needed, because every tie at the extremes is a tie
    # between equal ratings, so which of them is taken cannot move a mean or a spread. The targeted draw's own
    # ties were between *unequal* ratings and were settled on identifiers, which is why this column is the one
    # a reader can check and the draw itself is not.
    x_low, x_high = low_e[:PER_ARM], high_e[:PER_ARM]
    got["extremes draw: low arm mean rating"] = st.mean(x_low)
    got["extremes draw: high arm mean rating"] = st.mean(x_high)
    got["extremes draw: arm mean rating gap"] = st.mean(x_high) - st.mean(x_low)
    # Population sd per arm then averaged, matching the convention the arms' own 0.212 is printed under above.
    got["extremes draw: within-arm rating sd"] = st.mean([st.pstdev(x_low), st.pstdev(x_high)])
    got["as drawn: within-arm rating sd"] = st.mean(
        [st.pstdev([x for x, a in zip(human, armof) if a == want]) for want in ("low", "high")])
    # What the targeted draw passed over. Both counts are against the arms as shipped rather than against the
    # targets, so they stay true of the sample a reader holds even though the targets are not released.
    got["pool: eligible below the low arm"] = sum(
        1 for x in low_e if x < min(x for x, a in zip(human, armof) if a == "low"))
    got["pool: eligible above the high arm"] = sum(
        1 for x in high_e if x > max(x for x, a in zip(human, armof) if a == "high"))

    # Criterion validity inside the concentrated arm, which is the comparison a programme committee's own
    # distribution makes. Its interest is that the arm the paper would rather be judged on is the arm with the
    # lower coefficient, so it is reported with the difference and both intervals rather than on its own.
    prated = sorted(k for k in paper_comp
                    if isinstance(pubmap.get(k), dict) and "human" in pubmap[k])
    pc = [paper_comp[k] for k in prated]
    pr = [pubmap[k]["human"] for k in prated]
    got["published arm: rho with rating"], got["published arm: p"] = spearman_p(pc, pr)
    got["published arm: CI low"], got["published arm: CI high"] = boot_ci(spearman, pc, pr, paired=True)
    # The single channel, as the venue's own scale gives it: the raw 1-10 score, not its calibrated z. The
    # z-scored version of the same channel is +0.205, so the definition is load-bearing and the row says which
    # one it is. Raw is the right one here, because the claim is about a number a reader could read off a form.
    solo1 = {}
    for f, r in load(f"{B}/reviews/accepted/*/panel*/R?.json").items():
        solo1.setdefault(f.split("/")[-3], []).append(r["metrics"]["overall_recommendation"]["score"])
    got["published arm: rho, overall_recommendation raw"], got["published arm: p, overall_recommendation"] = \
        spearman_p([st.mean(solo1[k]) for k in prated], pr)
    got["declined minus published rho"] = got["rho, composite vs venue rating, 32 declined"] \
        - got["published arm: rho with rating"]
    # Two independent samples of different sizes, so neither boot_ci mode fits: each arm needs its own paired
    # resample. Same seed and same 4000 draws as every other interval in this file.
    rng = random.Random(20260830)
    diffs = []
    for _ in range(4000):
        ia = [rng.randrange(len(pc)) for _ in pc]
        ir = [rng.randrange(len(comp)) for _ in comp]
        try:
            diffs.append(spearman([comp[i] for i in ir], [human[i] for i in ir])
                         - spearman([pc[i] for i in ia], [pr[i] for i in ia]))
        except (ZeroDivisionError, ValueError):
            pass
    diffs.sort()
    got["declined minus published: CI low"] = diffs[int(0.025 * len(diffs))]
    got["declined minus published: CI high"] = diffs[int(0.975 * len(diffs))]

    # --- section 4: where the ranking signal goes, and what averaging buys -------------------------------
    arm = {k: v["arm"] for k, v in ratings.items()}
    for label, root, keep in (("declined 32", f"{B}/reviews/rejected", None),
                              ("low-rated 16", f"{B}/reviews/rejected", lambda p: arm[p] == "low"),
                              ("high-rated 16", f"{B}/reviews/rejected", lambda p: arm[p] == "high"),
                              ("published 16", f"{B}/reviews/accepted", None)):
        d = decomp(overall(root, keep))
        got[f"variance: paper %, {label}"] = d["paper_pct"]
        got[f"variance: reviewer %, {label}"] = d["slot_pct"]
        got[f"variance: residual %, {label}"] = d["residual_pct"]
        got[f"variance: reviewer/paper, {label}"] = d["ratio"]
        got[f"slot baseline spread, {label}"] = d["spread"]
        # The df-adjusted components, which is what the five-against-eight comparison in section 4 uses.
        got[f"reviewer variance component, {label}"] = d["var_slot"]
        got[f"sd of slot baselines, {label}"] = d["slot_sd"]

    # Aggregation: does the five-slot mean rank better than one slot? Against the venue's own ratings, which
    # is the only external criterion in the study, so this is the test the abstract's second claim rests on.
    solo = per_slot(f"{B}/reviews/rejected", mu, sd, metrics)
    srho = sorted(spearman([d[k] for k in keys], [ratings[k]["rating_mean"] for k in keys])
                  for d in solo.values())
    got["solo-slot rho, lowest"], got["solo-slot rho, highest"] = srho[0], srho[-1]
    got["panel rho minus mean-solo rho"] = got["rho, composite vs venue rating, 32 declined"] - st.mean(srho)
    drop = sorted(spearman([st.mean(solo[s][k] for s in solo if s != x) for k in keys],
                           [ratings[k]["rating_mean"] for k in keys]) for x in solo)
    got["drop-one rho, lowest"], got["drop-one rho, highest"] = drop[0], drop[-1]
    # The same five panels of four, scored on the other criterion the study uses. The confound battery answers
    # "one strong reviewer carries the ranking" with both ranges, and only the correlation half of the answer
    # was recomputed here: an AUC range is a different function of the same drop, and a claim that no single
    # slot carries the result is a claim about the weakest of the five.
    drop_auc = sorted(auc([st.mean(solo[s][k] for s in solo if s != x) for k in keys if arm[k] == "high"],
                          [st.mean(solo[s][k] for s in solo if s != x) for k in keys if arm[k] == "low"])
                      for x in solo)
    got["drop-one AUC, lowest"], got["drop-one AUC, highest"] = drop_auc[0], drop_auc[-1]

    # The interval around the aggregation null. This is the paper's own negative result -- averaging five slots
    # buys +0.043 of rank correlation over the mean single slot -- and an interval that contains zero is what
    # makes it a null rather than a small effect, so it is the one number in the claim a reader would check.
    # Nothing recomputed it, which is the same shape as the bootstrap interval in section 6's table that this
    # file was extended to cover. Paired on papers: resampling each slot's vector separately would break the
    # pairing that makes the difference a difference, and return an interval around zero whatever is true.
    hr = [ratings[k]["rating_mean"] for k in keys]
    slot_names = sorted(solo)
    vecs = [[solo[s][k] for k in keys] for s in slot_names]
    panel_vec = [st.mean(v[i] for v in vecs) for i in range(len(keys))]
    # The mean of the five slot means is the panel composite only while every slot reviewed every paper the
    # same number of times. It does here, and asserting it is what keeps this interval an interval around the
    # published point estimate rather than around a slightly different statistic.
    assert max(abs(panel_vec[i] - rej_comp[k]) for i, k in enumerate(keys)) < 1e-12, \
        "the mean of the per-slot means is not the panel composite: the roster is unbalanced somewhere"

    def agg_gap(*v):
        """-> panel rho minus the mean of the five solo rhos, on one resample. Last vector is the criterion."""
        return spearman(v[0], v[-1]) - st.mean(spearman(x, v[-1]) for x in v[1:-1])

    def best_gap(*v):
        """-> panel rho minus the *best* solo rho. Best is re-chosen inside each resample, which is what makes
        the bound selection-biased and is why the appendix prints it as a bound rather than a comparison."""
        return spearman(v[0], v[-1]) - max(spearman(x, v[-1]) for x in v[1:-1])

    got["aggregation gap: CI low"], got["aggregation gap: CI high"] = \
        boot_ci(agg_gap, panel_vec, *vecs, hr, paired=True)
    got["panel minus best slot"] = best_gap(panel_vec, *vecs, hr)
    got["panel minus best slot: CI low"], got["panel minus best slot: CI high"] = \
        boot_ci(best_gap, panel_vec, *vecs, hr, paired=True)

    for label, root, n in (("", f"{B}/reviews/rejected", 32), (", published 16", f"{B}/reviews/accepted", 16)):
        ps = per_slot(root, mu, sd, metrics)
        pairs = sorted(spearman([ps[a][k] for k in sorted(ps[a])], [ps[b][k] for k in sorted(ps[a])])
                       for a, b in itertools.combinations(sorted(ps), 2))
        if label:
            got[f"inter-slot agreement{label}"] = st.median(pairs)
        else:
            got["inter-slot agreement, median of 10 pairs"] = st.median(pairs)
            got["inter-slot agreement, minimum pair"] = pairs[0]
    # The same agreement inside each rated half. The ladder reads it as flat across all three declined
    # populations and falling only on the accepted set, and a median over the pooled 32 cannot support that:
    # pooling two halves that disagree about level raises every pairwise correlation between slots, so the
    # within-half figures are the ones the claim needs.
    for lab, sel in ((", low-rated 16", "low"), (", high-rated 16", "high")):
        ks = [k for k in keys if arm[k] == sel]
        got[f"inter-slot agreement{lab}"] = st.median(
            spearman([solo[a][k] for k in ks], [solo[b][k] for k in ks])
            for a, b in itertools.combinations(sorted(solo), 2))

    # The per-slot leniency shift between the extreme populations, on the raw channel rather than the composite,
    # since the composite removes exactly this. Both ends of the range are positive, and that is the claim: the
    # slots differ in baseline yet all five move the same way with quality, so one slot shifting the other way
    # would break the sentence while leaving the printed range's width alone.
    def slot_means(o):
        return {s: st.mean(x[2] for x in o if x[1] == s) for s in sorted({x[1] for x in o})}

    lo_m, hi_m = slot_means(overall(f"{B}/reviews/rejected")), slot_means(overall(f"{B}/reviews/accepted"))
    shift5 = sorted(hi_m[s] - lo_m[s] for s in lo_m)
    got["leniency shift, smallest slot"], got["leniency shift, largest slot"] = shift5[0], shift5[-1]

    got["panel retest rho, declined 32"] = spearman(
        *([[rej[p][f"panel{i}"] for p in sorted(rej) if len(rej[p]) == 2] for i in (1, 2)]))

    # --- section 6: what a presentation edit is worth -----------------------------------------------------
    # The contrast is DAY-MATCHED and spans both corpora, which is two departures from the pilot this block
    # used to reproduce, and both of them change the estimand rather than sharpen it.
    #
    # Day-matched: each variant panel is differenced against baseline panels read in the variant's own
    # sitting. Untouched text does not read the same on two days, so a contrast that spans a sitting boundary
    # carries that offset inside the treatment effect. Holding the day fixed costs one baseline panel's worth
    # of precision and removes a bias.
    #
    # Both corpora: sixteen accepted papers and thirty-two declined submissions, forty-eight in all, because
    # at sixteen the smallest effect the design could resolve was about as large as the band the effect is
    # judged against. Papers, not extra panels, buy that down -- so the arms below are the pooled ones, and
    # each corpus is reported beside the pool rather than in place of it.
    dm = dmtable(B, mu, sd)
    dm_corpus = {paper: e["corpus"] for (paper, _, _), e in dm.items()}
    five_delta: dict[str, dict[str, float]] = {}
    dm_rerun: dict[str, dict[str, float]] = {}
    for variant, short in (("T1_endmatter", "T1"), ("T3_lengthen", "T3"), ("T2_concede", "T2")):
        d, rerun = dm_matched(dm, metrics, variant)
        # Keyed by paper id, not carried as a list: the dose check at the end of this file pairs these
        # against edit counts, and two lists in two orders pair silently.
        five_delta[variant] = d
        dm_rerun[variant] = rerun
        vals = sorted(d.values())
        got[f"{short} arm: papers"] = len(vals)
        got[f"{short} median dcomposite"] = st.median(vals)
        got[f"{short} sign split, negative"] = sum(1 for x in vals if x < 0)
        got[f"{short} sign split, positive"] = sum(1 for x in vals if x > 0)
        # The band the criterion names, fixed before scoring. The contrast's own band is measured further
        # down and printed beside it; substituting it here would let the instrument's precision set the
        # threshold it is judged against.
        got[f"{short} |median| / own band"] = abs(st.median(vals)) / got["re-run band, median |dz| over 16"]
        # The criterion's composite conjunct names a mean of absolute changes, which no table prints, so the
        # sentence that applies it has a row of its own.
        got[f"{short} mean |dcomposite|"] = st.mean(abs(x) for x in vals)
        # The body table's interval. T1's crosses zero, in bold, in the headline table, so it is the entry a
        # reviewer who verifies one thing will verify. The two bounds are wide-tolerance for the reason
        # boot_median_ci gives -- a different seed moves a percentile of 4,000 resamples of a median -- and
        # what they establish is that the interval sits where the table puts it.
        got[f"{short} CI low"], got[f"{short} CI high"] = boot_median_ci(vals)
        # What the arm resolves, for the appendix's resolution table. The interval priced here is not the one
        # on the line above: a percentile bootstrap of a median over forty-seven papers lands on a handful of
        # neighbouring order statistics, so its half-width moves with the seed, and a share of a band computed
        # from it could only be checked at a tolerance wide enough to admit any answer. The order-statistic
        # interval needs no seed, its coverage is at least the nominal ninety-five per cent, and it is the wider
        # of the two on every arm here. Half of it is converted to a detectable effect by the ratio of two
        # normal deviates, then rescaled by the root of the count for the sixteen-manuscript column.
        res_n = len(vals)
        res_k = max(j for j in range(1, res_n // 2 + 1)
                    if 2 * sum(math.comb(res_n, i) for i in range(j)) / 2 ** res_n <= 0.05)
        res_cover = 1 - 2 * sum(math.comb(res_n, i) for i in range(res_k)) / 2 ** res_n
        res_half = (vals[res_n - res_k] - vals[res_k - 1]) / 2
        res_ratio = (1.959963985 + 0.841621234) / st.NormalDist().inv_cdf((1 + res_cover) / 2)
        res_band = got["re-run band, median |dz| over 16"]
        for label, at_n in (("", res_n), (" at sixteen", 16)):
            res_mde = res_half * res_ratio * math.sqrt(res_n / at_n)
            got[f"{short} resolves{label}"] = res_mde
            got[f"{short} resolves{label} / band"] = res_mde / res_band
        # The two corpus columns. A pooled median that both halves disagree with would be the finding, so
        # each half is a row of its own rather than a sentence about the pool.
        for lab, sel in (("accepted", "accepted"), ("declined", "declined")):
            half = sorted(v for p, v in d.items() if dm_corpus.get(p) == sel)
            got[f"{short} median dcomposite, {lab}"] = st.median(half)
            got[f"{short} sign split, {lab} negative"] = sum(1 for x in half if x < 0)
            got[f"{short} arm: {lab} papers"] = len(half)

    # The five-model panel's grade repeatability on the published sixteen was computed here, from the two panels
    # over byte-identical text: 80 cells, 81.2 per cent agreeing, a mean step of 0.188. Section 2 and appendix B
    # took the grade's own noise from it and now take all three equivalents from the day-matched forty-eight
    # instead, so nothing on the page came from it any more and the three keys it wrote were read by no row.
    #
    # The DAY-MATCHED grade axis, which is what section 6 argues from. A cell is (paper, slot). The variant arm
    # has one panel and the baseline pair has two, so each variant grade is compared against each of the two in
    # turn and the re-run compares the two against each other: one reading against one reading on both sides.
    # Differencing the variant against the pair's MEAN instead would hand it the smaller variance of a mean of
    # two, and every arm would then move the grade less than a re-run by construction rather than by
    # measurement -- which is exactly what the superseded reading said.
    #
    # The re-run reference is taken without naming an arm, because the section prints the three arms' steps as
    # ratios to one yardstick and three ratios against three yardsticks are not comparable.
    GR = {k: e["grades"] for k, e in dm.items()}
    rsteps, ragree, rdis, rcells, held = [], [], 0, 0, []
    for paper, e in dm_pairs(dm, None).items():
        if len(e["any"]) != 2:
            continue
        ga, gb = (GR[(paper, "baseline", n)] for n in e["any"])
        # Two readings of the same text, at the grain a venue reads: the modal grade over the panel's slots.
        ma, mb = modal(ga), modal(gb)
        if ma and mb:
            held.append(ma == mb)
        for slot in sorted(set(ga) & set(gb)):
            a, b = ga[slot], gb[slot]
            if a not in ORDER or b not in ORDER:
                continue
            rcells += 1
            rdis += a != b
            ragree.append(a == b)
            rsteps.append(abs(ORDER[a] - ORDER[b]))
    got["5-model: modal grade retest papers"] = len(held)
    got["5-model: modal grade holds on identical text"] = st.mean(held)
    # The same two quantities as the page gives them: appendix B counts the papers whose grade held, and section
    # 6 and appendix E round the proportion to three places. Aliases rather than second measurements, because a
    # row at three places cannot see a fourth digit go wrong and a row at four cannot be found on a page that
    # prints three.
    got["5-model: modal grade kept, papers"] = sum(held)
    got["5-model: modal grade holds on identical text, three places"] = st.mean(held)
    got["5-model: grade re-run cells"] = rcells
    got["5-model: grade re-run cells that disagree"] = rdis
    got["5-model: grade re-run cells that disagree, share"] = rdis / rcells
    got["5-model: grade re-run mean abs step"] = st.mean(rsteps)
    got["5-model: grade re-run cell agreement %"] = 100 * st.mean(ragree)
    # And as a proportion, which is the form every one of the four places printing it uses. The percentage row
    # here is the older one and it is kept: appendix H states the second roster's agreement as a percentage, so
    # both units are on the page and a single row would leave one of them unchecked.
    got["5-model: grade re-run cell agreement"] = st.mean(ragree)
    got["5-model: grade re-run cell agreement, three places"] = st.mean(ragree)
    # Why the two rows above it coincide, rather than a reader having to notice that they do: no re-read moved a
    # grade by two rungs, so a mean absolute step and a disagreement rate are the same number here. They are not
    # the same statistic, and an arm that moved one cell two rungs would separate them.
    got["5-model: grade re-run largest step"] = max(rsteps)

    flips: dict[tuple, int] = {}
    shares, vpanels = {}, []
    for variant, short in (("T1_endmatter", "T1"), ("T2_concede", "T2"), ("T3_lengthen", "T3")):
        steps, agree, ncells, diff = [], [], 0, 0
        for paper, e in dm_pairs(dm, variant).items():
            if not e["variant"] or len(e["base"]) != 2:
                continue
            vpanels.append(len(e["variant"]))
            pair = [GR[(paper, "baseline", n)] for n in e["base"]]
            for vp in e["variant"]:
                gv = GR[(paper, variant, vp)]
                for slot in sorted(gv):
                    a, b = pair[0].get(slot), pair[1].get(slot)
                    if not (a and b):
                        continue
                    ncells += 1
                    if gv[slot] != a and gv[slot] != b:
                        diff += 1
                        flips[(paper, slot)] = flips.get((paper, slot), 0) + 1
                    for g in (a, b):
                        agree.append(gv[slot] == g)
                        if gv[slot] in ORDER and g in ORDER:
                            steps.append(abs(ORDER[gv[slot]] - ORDER[g]))
        got[f"{short}: grade cells"] = ncells
        got[f"{short}: grade cells differing from both readings"] = diff
        shares[short] = got[f"{short}: grade cells differing from both readings, share"] = diff / ncells
        got[f"{short}: grade paired mean abs step"] = st.mean(steps)
        got[f"{short}: grade paired cell agreement %"] = 100 * st.mean(agree)
        got[f"{short}: grade step / own re-run step"] = (st.mean(steps)
                                                        / got["5-model: grade re-run mean abs step"])
        # The criterion's grade conjunct, at the grain it names: one comparison per paper, the variant panel's
        # modal grade against the modal grade over both baseline panels' slots pooled. A mode of the two
        # per-panel modes has no tie-break when they disagree, so the slots are pooled first.
        kept = []
        for paper, e in dm_pairs(dm, variant).items():
            if not e["variant"] or len(e["base"]) != 2:
                continue
            mb = modal({f"{i}|{s}": g for i, n in enumerate(e["base"])
                        for s, g in GR[(paper, "baseline", n)].items()})
            mv = modal(GR[(paper, variant, e["variant"][0])])
            if mb and mv:
                kept.append(mv == mb)
        got[f"{short}: modal grade kept, papers"] = sum(kept)
        got[f"{short}: modal grade kept, of"] = len(kept)
        got[f"{short}: modal grade kept, share"] = sum(kept) / len(kept)
    # The scale factor above and the pairing here both assume one variant panel per paper. If an arm ever gets a
    # second, this row moves off 1 and the two of them are wrong together, so it is checked rather than assumed.
    got["day-matched variant panels, largest arm"] = max(vpanels)
    # The prose gives the flip rates as a range, so both ends are rows: a range whose endpoints are not
    # recomputed is one claim checked nowhere.
    got["grade flip share, smallest arm"] = min(shares.values())
    got["grade flip share, largest arm"] = max(shares.values())
    got["grade cells that ever flip"] = len(flips)
    got["grade cells that ever flip, share"] = len(flips) / got["5-model: grade re-run cells"]
    got["grade cells flipping under all three"] = sum(1 for n in flips.values() if n == 3)

    # --- appendix H: the second roster, on the same 16 papers ----------------------------------------------
    # Eight slots over six vendors, its own frozen mu/sd, its own noise band. Everything here is a
    # within-roster quantity except three, and those three are the only ones the paper compares across
    # rosters: the rank correlation between the two orderings, a delta's sign, and a delta's size in units of
    # the roster's own band. A raw z from one roster and a raw z from the other are not the same unit.
    c8 = json.load(open(f"{B}/calibration/calibration_params_cursor8.json"))
    m8, s8, k8 = c8["mu"], c8["sd"], c8["metrics"]
    band8 = c8["test_retest_noise"]["median_abs_between_panel_composite_gap"]
    vend = {s["slot"]: s["vendor"] for s in
            json.load(open(f"{B}/instrument/slots_cursor8.json"))["slots"]}
    V = f"{B}/reviews/vendor_panel"

    g8 = grades(V, "C?.json")
    assert len(g8) == 256, f"eight-slot arm: {len(g8)} reviews, expected 256"
    for grade in GRADES:
        got[f"8-slot: {grade} count"] = g8.count(grade)
    # The rate, not only the count: the grade table sets this roster's Accept share against the five-model
    # roster's, and that comparison is the one sentence in section 3 where the second roster changes what the
    # section concludes. Both shares now have a row over their own denominator.
    got["8-slot: Accept %"] = 100 * got["8-slot: Accept count"] / len(g8)
    slot_g = grades_by(V, "C?.json", lambda f: os.path.basename(f)[:2])
    got["8-slot: slots returning any Accept"] = sum(1 for v in slot_g.values() if "Accept" in v)
    got["8-slot: Accepts from the one slot that says it"] = max(v.count("Accept") for v in slot_g.values())
    got["8-slot: most R&R from one slot"] = max(v.count("Reject and Resubmit") for v in slot_g.values())

    bp8 = grades_by(V, "C?.json", lambda f: (f.split("/")[-3], f.split("/")[-2]))
    got["8-slot: panels with every reviewer Minor+"] = sum(
        all(ORDER[x] >= ORDER["Minor Revision"] for x in v) for v in bp8.values())
    hit8 = {k: any(x == "Accept" for x in v) for k, v in bp8.items()}
    got["8-slot: panels with any Accept"] = sum(hit8.values())
    ps8 = {p for p, _ in hit8}
    got["8-slot: papers with any Accept, >=1 panel"] = sum(
        any(hit8[(p, k)] for q, k in hit8 if q == p) for p in ps8)
    got["8-slot: papers with any Accept, both panels"] = sum(
        all(hit8[(p, k)] for q, k in hit8 if q == p) for p in ps8)

    obs8 = overall(V, pat="C?.json")
    d8 = decomp(obs8)
    got["8-slot: variance paper %"] = d8["paper_pct"]
    got["8-slot: variance reviewer %"] = d8["slot_pct"]
    got["8-slot: variance reviewer/paper"] = d8["ratio"]
    got["8-slot: slot baseline spread"] = d8["spread"]
    got["8-slot: reviewer variance component"] = d8["var_slot"]
    got["8-slot: sd of slot baselines"] = d8["slot_sd"]
    nd8 = nested(obs8, vend)
    got["8-slot: vendor share of between-slot SS %"] = nd8["vendor_share"]
    got["8-slot: within-OpenAI persona spread"] = nd8["within_vendor_spread"]["openai"]
    got["8-slot: lowest vendor mean"] = min(nd8["vendor_means"].values())
    got["8-slot: highest vendor mean"] = max(nd8["vendor_means"].values())
    # The column those two summarise, slot by slot. A vendor mean is an average of its slots, so it can be
    # right while the individual figures are wrong: OpenAI's three slots at 4.03, 3.63 and 3.91 average to the
    # 3.85 checked above whatever any one of them says, and the table's argument is about the ends of this
    # column rather than about any average in it.
    slot8_mean = {s: st.mean(o[2] for o in obs8 if o[1] == s) for s in sorted({o[1] for o in obs8})}
    for s, m in slot8_mean.items():
        got[f"8-slot: mean recommendation, slot {s}"] = m
    # And the count behind "the other seven slots return none in 224". Derived from which slots actually award
    # no Accept rather than by naming the one that does, so that if a second slot ever awards one the count
    # falls out of step with the sentence instead of agreeing with a stale reading of it.
    g8 = grades_by(V, "C?.json", lambda f: os.path.basename(f)[:2])
    got["8-slot: reviews by the slots that return no Accept"] = sum(
        len(v) for v in g8.values() if "Accept" not in v)

    pan8 = composites(V, m8, s8, k8, "C?.json")
    comp8 = {p: st.mean(d.values()) for p, d in pan8.items()}
    keys8 = sorted(comp8)
    steps8 = sorted(abs(d["panel1"] - d["panel2"]) for d in pan8.values() if len(d) == 2)
    got["8-slot: re-run band, median |dz|"] = st.median(steps8)
    # And the band the transform ratios are actually divided by, which lives in the parameter file. If these
    # two disagree, every "x times its own band" in the appendix is against a band nothing recomputes.
    got["8-slot: re-run band, as frozen in the parameters"] = band8
    got["8-slot: re-run band p90"] = steps8[int(0.9 * (len(steps8) - 1))]
    ord8 = sorted(comp8.values())
    got["8-slot: adjacent-paper gap, median"] = st.median([b - a for a, b in zip(ord8, ord8[1:])])
    # The same two quantities again, for the rows that hold the roster table's three-place printing to half of
    # its last place. Aliases, not second computations: a row against a separate derivation would let the table
    # and the appendix's four-place cells drift apart, which is the disagreement these rows exist to catch.
    got["8-slot: re-run band, as printed in the roster table"] = got["8-slot: re-run band, median |dz|"]
    got["8-slot: adjacent-paper gap, as printed in the roster table"] = got["8-slot: adjacent-paper gap, median"]
    got["8-slot: composite minimum"] = ord8[0]
    got["8-slot: composite maximum"] = ord8[-1]
    got["8-slot: panel retest rho"] = spearman(
        *([[pan8[p][f"panel{i}"] for p in keys8 if len(pan8[p]) == 2] for i in (1, 2)]))

    slot8 = per_slot(V, m8, s8, k8, pat="C?.json")
    pairs8 = {(x, y): spearman([slot8[x][k] for k in keys8], [slot8[y][k] for k in keys8])
              for x, y in itertools.combinations(sorted(slot8), 2)}
    got["8-slot: inter-slot agreement, median of 28 pairs"] = st.median(pairs8.values())
    got["8-slot: inter-slot agreement, minimum pair"] = min(pairs8.values())
    got["8-slot: inter-slot agreement, same-vendor pairs"] = st.median(
        [v for (x, y), v in pairs8.items() if vend[x] == vend[y]])
    got["8-slot: inter-slot agreement, cross-vendor pairs"] = st.median(
        [v for (x, y), v in pairs8.items() if vend[x] != vend[y]])

    # The roster swap, at panel resolution: the quantity a level shift has to be measured against is a single
    # panel's re-run of itself, so both sides stay unaveraged.
    swap = sorted(abs(acc[p][x] - pan8[p][y]) for p in keys8
                  for x in ("panel1", "panel2") for y in ("panel1", "panel2"))
    got["roster swap: median level shift"] = st.median(swap)
    got["roster swap: p90 level shift"] = swap[int(0.9 * (len(swap) - 1))]
    got["roster swap: max level shift"] = max(swap)
    got["roster swap: rho over the 16 published papers"] = spearman(
        [comp8[p] for p in keys8], [paper_comp[p] for p in keys8])
    # Paired on papers: the statistic is a property of the association between the two rosters, and drawing
    # each roster its own papers would return an interval around zero however well they agree.
    got["roster swap: rho CI low"], got["roster swap: rho CI high"] = boot_ci(
        spearman, [comp8[p] for p in keys8], [paper_comp[p] for p in keys8], paired=True)
    d1 = sorted(spearman([comp8[keys8[j]] for j in range(len(keys8)) if j != i],
                         [paper_comp[keys8[j]] for j in range(len(keys8)) if j != i])
                for i in range(len(keys8)))
    got["roster swap: drop-one rho, lowest"], got["roster swap: drop-one rho, highest"] = d1[0], d1[-1]

    hr = json.load(open(f"{B}/data/accepted_arm_human_ratings.json"))
    hk = [p for p in keys8 if p in hr]
    got["validity, published: papers with venue ratings"] = len(hk)
    got["validity, published: 8-slot rho"] = spearman([comp8[p] for p in hk], [hr[p]["human"] for p in hk])
    got["validity, published: 5-model rho"] = spearman([paper_comp[p] for p in hk],
                                                       [hr[p]["human"] for p in hk])
    # Fifteen papers, so these are wide, and their width is the point: the appendix reads them as saying the
    # comparison between rosters is undecided rather than as one roster tracking the venue better.
    got["validity, published: 8-slot rho CI low"], got["validity, published: 8-slot rho CI high"] = \
        boot_ci(spearman, [comp8[p] for p in hk], [hr[p]["human"] for p in hk], paired=True)
    got["validity, published: 5-model rho CI low"], got["validity, published: 5-model rho CI high"] = \
        boot_ci(spearman, [paper_comp[p] for p in hk], [hr[p]["human"] for p in hk], paired=True)
    got["validity, published: 5-model minus 8-slot rho"] = (got["validity, published: 5-model rho"]
                                                            - got["validity, published: 8-slot rho"])

    usage = json.load(open(f"{B}/data/vendor_panel_usage.json"))["output_tokens"]
    sev = {s: st.mean(o[2] for o in obs8 if o[1] == s) for s in sorted(usage)}
    tok = {s: st.median(v.values()) for s, v in usage.items()}
    got["8-slot: rho severity vs output tokens"] = spearman([tok[s] for s in sorted(sev)],
                                                            [sev[s] for s in sorted(sev)])
    got["8-slot: lowest median output tokens"] = min(tok.values())
    got["8-slot: highest median output tokens"] = max(tok.values())

    # --- appendix H: the transform arm on that roster, and the control that corrects it --------------------
    vc = cells(f"{B}/reviews/vendor_transform", m8, s8, k8, "C?.json", levels=2)
    assert len(vc) == 192, f"eight-slot transform arm: {len(vc)} reviews, expected 192"
    vunit: dict[str, dict[str, float]] = {}
    for (unit, _, s), v in vc.items():
        vunit.setdefault(unit, {})[s] = v
    tp = sorted({u.split("/")[0] for u in vunit})
    b8: dict[tuple, list] = {}
    for (p, _, s), v in cells(V, m8, s8, k8, "C?.json").items():
        b8.setdefault((p, s), []).append(v)
    b8 = {k: st.mean(v) for k, v in b8.items()}

    dcell: dict[str, list] = {}
    for (p, _, s), v in cells(f"{B}/reviews/vendor_drift", m8, s8, k8, "C?.json").items():
        dcell.setdefault(p, []).append(v)
    assert sum(len(v) for v in dcell.values()) == 64, "the drift control is not 64 reviews"
    dr = {p: st.mean(dcell[p]) - comp8[p] for p in tp}
    drift = st.median(dr.values())
    got["drift control: median offset"] = drift
    got["drift control: CI low"], got["drift control: CI high"] = boot_median_ci(list(dr.values()))
    got["drift control: |offset| / own band"] = abs(drift) / band8
    got["drift control: papers negative of 8"] = sum(1 for x in dr.values() if x < 0)

    for variant, short in (("T1_endmatter", "T1"), ("T2_concede", "T2"), ("T3_lengthen", "T3")):
        raw = [st.mean(vunit[f"{p}/{variant}"].values()) - comp8[p] for p in tp]
        got[f"8-slot {short}: raw median dz"] = st.median(raw)
        got[f"8-slot {short}: raw papers down of 8"] = sum(1 for x in raw if x < 0)
        got[f"8-slot {short}: raw |median| / own band"] = abs(st.median(raw)) / band8
        # The COMMON offset is subtracted, not the per-paper one: the control is a single panel, so
        # per-paper subtraction would inject its noise into every delta to remove a shift that is by
        # hypothesis shared. The paired form is the robustness line beside it.
        corr = [x - drift for x in raw]
        got[f"8-slot {short}: corrected median dz"] = st.median(corr)
        # The interval the table prints beside that median, in the column after it. Unreproduced until now,
        # and this is the second table in the manuscript where the estimate carried a row and its interval
        # did not: T1's spans zero here as well, which is the entry a reader checks first.
        got[f"8-slot {short}: corrected CI low"], got[f"8-slot {short}: corrected CI high"] = \
            boot_median_ci(corr)
        got[f"8-slot {short}: corrected papers down of 8"] = sum(1 for x in corr if x < 0)
        got[f"8-slot {short}: corrected |median| / own band"] = abs(st.median(corr)) / band8
        got[f"8-slot {short}: paired median dz"] = st.median([x - dr[p] for x, p in zip(raw, tp)])
        per = {s: st.median([vunit[f"{p}/{variant}"][s] - b8[(p, s)] for p in tp]) for s in sorted(vend)}
        got[f"8-slot {short}: slots with a negative median"] = sum(1 for v in per.values() if v < 0)
        # The per-slot table itself, twenty-four medians and eight paper counts, which the count above was
        # standing in for. A count of negatives is not the table: it passes for any set of eight values with
        # the right signs, and the table is what the appendix prints and what a claim about vendors is read
        # off. Four decimal places there, so the tolerance is 0.00005.
        for s, v in per.items():
            got[f"8-slot {short} slot {s}: median dz"] = v
            if short == "T1" and s in ("C4", "C7"):
                # The prose quotes these two at three places, as the arm's one large positive and one large
                # negative. Same value, second row, because half of the third place is a different tolerance
                # from half of the fourth: a three-place quote taken from an already-rounded four-place
                # number is exactly how three figures in appendix E came to have the wrong last digit.
                got[f"8-slot T1 slot {s}: median dz, as quoted in prose"] = v
            if short == "T3":
                got[f"8-slot T3 slot {s}: papers down of 8"] = sum(
                    1 for p in tp if vunit[f"{p}/{variant}"][s] - b8[(p, s)] < 0)

    # The grade axis, against the ceiling it has to be judged against: this roster's own per-cell agreement
    # with itself on byte-identical text. A cell counts as moved only if the variant grade matches NEITHER
    # baseline panel, which is the strict reading and the one that makes the arms look worst.
    bg8 = grades_by(V, "C?.json", lambda f: (f.split("/")[-3], os.path.basename(f)[:2]))
    vg8 = {(u.split("/")[0], u.split("/")[1], s): None for u in vunit for s in vunit[u]}
    for f, r in load(f"{B}/reviews/vendor_transform/*/*/panel*/C?.json").items():
        vg8[(f.split("/")[-4], f.split("/")[-3], os.path.basename(f)[:2])] = r.get("grade")
    pairs = [g for g in bg8.values() if len(g) == 2]
    got["8-slot: grade retest agreement %"] = 100 * st.mean(1 if len(set(g)) == 1 else 0 for g in pairs)
    got["8-slot: grade retest cells"] = len(pairs)
    got["8-slot: grade retest mean abs step"] = st.mean(
        abs(ORDER[g[0]] - ORDER[g[1]]) for g in pairs if all(x in ORDER for x in g))
    for variant, short in (("T1_endmatter", "T1"), ("T2_concede", "T2"), ("T3_lengthen", "T3")):
        moved, steps, kept = 0, [], 0
        for p in tp:
            bl, vl = [], []
            for s in sorted(vend):
                gv, gb = vg8[(p, variant, s)], bg8[(p, s)]
                moved += gv not in gb
                bl += [ORDER[x] for x in gb if x in ORDER]
                if gv in ORDER:
                    vl.append(ORDER[gv])
                if gv in ORDER and all(x in ORDER for x in gb):
                    steps.append(abs(ORDER[gv] - st.mean(ORDER[x] for x in gb)))
            kept += bool(vl) and bool(bl) and st.mode(vl) == st.mode(bl)
        got[f"8-slot {short}: grade cells moved of 64"] = moved
        got[f"8-slot {short}: grade mean abs step"] = st.mean(steps)
        got[f"8-slot {short}: modal grade kept of 8"] = kept
        # The ratio F3(b) plots, and the one form in which the two rosters may be compared at all. It is a
        # quotient of two numbers checked just above, so it cannot disagree with them -- it is here because a
        # figure axis is a claim, and the reader should not have to divide two appendix numbers to test it.
        got[f"8-slot {short}: grade step / own re-run step"] = (
            st.mean(steps) / got["8-slot: grade retest mean abs step"])

    # Queue position, recomputed from run_n2.sh's fixed-seed shuffle over the directory names in this tree
    # rather than read off file timestamps, so the design's balance is checkable without trusting a clock.
    VARIANTS = ["T1_endmatter", "T2_concede", "T3_lengthen"]
    jobs = [f"{p}/{v}" for p in tp for v in VARIANTS if f"{p}/{v}" in vunit]
    random.Random(20260830).shuffle(jobs)
    qi = {j: i for i, j in enumerate(jobs)}
    for variant, short in (("T1_endmatter", "T1"), ("T2_concede", "T2"), ("T3_lengthen", "T3")):
        got[f"queue: mean position, {short}"] = st.mean(qi[f"{p}/{variant}"] for p in tp)
    allj = sorted((qi[u], st.mean(vunit[u].values()) - comp8[u.split("/")[0]]) for u in vunit)
    got["queue: rho position vs delta"] = spearman([x for x, _ in allj], [y for _, y in allj])
    half = len(allj) // 2
    got["queue: later minus earlier mean delta"] = (st.mean(y for _, y in allj[half:])
                                                    - st.mean(y for _, y in allj[:half]))
    got["queue: later minus earlier gap, as printed unsigned"] = abs(
        got["queue: later minus earlier mean delta"])
    # What each arm's mean position would be if the shuffle carried no information about the arm: the mean of
    # every position in the queue, since the three arms partition it into equal thirds. Taken over the actual
    # positions rather than as (n - 1) / 2, so that a queue built from a short job list gives the mean of the
    # queue that ran instead of the mean of the queue that was intended.
    got["queue: expected mean position"] = st.mean(qi.values())

    # --- appendix E: does the effect scale with how much of the paper was edited? --------------------------
    # It does not, on either roster, and the appendix says so. This is here because an appendix null that no
    # released code recomputes is a null a reader has to take on trust.
    # Both manifests, read into one map. The two arms are keyed differently on purpose -- the accepted arm by
    # its arXiv identifier, the declined arm by the release label that stands in for a submission id -- and the
    # two key spaces cannot collide, so a merge is safe and a merge is what the pooled dose is over.
    man = {}
    for f in ("pia_manifest.json", "pia_manifest_declined.json"):
        man.update(json.load(open(f"{B}/data/{f}"))["variants"])
    for variant, short in (("T1_endmatter", "T1"), ("T2_concede", "T2"), ("T3_lengthen", "T3")):
        # The dose is a property of the generated variant, so the range and median are taken over the arm the
        # appendix reads out, and each roster's correlation is taken over that roster's own papers. One paper
        # list served both rosters while the two arms held the same papers; it stopped being one list when the
        # five-model arm grew, and pairing one roster's edit counts against the other's deltas raises nothing.
        dd = five_delta[variant]
        pids = sorted(p for p in dd if p in man)
        assert len(pids) == len(dd), f"{short}: no edit count for {sorted(set(dd) - set(man))}"
        e = [man[p][variant]["edits"] for p in pids]
        got[f"dose {short}: papers"] = len(pids)
        got[f"dose {short}: fewest edits"] = min(e)
        got[f"dose {short}: most edits"] = max(e)
        got[f"dose {short}: median edits"] = st.median(e)
        got[f"dose {short}: rho edits vs delta, 5-model"] = spearman(e, [dd[p] for p in pids])
        p8 = [p for p in tp if f"{p}/{variant}" in vunit]
        got[f"dose {short}: rho edits vs delta, 8-slot"] = spearman(
            [man[p][variant]["edits"] for p in p8],
            [st.mean(vunit[f"{p}/{variant}"].values()) - comp8[p] for p in p8])

    # --- appendix E: the five-model roster's OWN drift control (N1b) ---------------------------------------
    # Reported in the same form as the eight-slot control above -- median offset, median-bootstrap CI, papers
    # by sign -- because the two are meant to be compared, and a mean here against a median there would make
    # the comparison rest on the choice of statistic. The clean deltas take the same form as §6's table for
    # the same reason: they are that table's numbers with the session boundary removed instead of corrected.
    nb: dict[str, dict[str, list]] = {}
    for (unit, panel, _), v in cells(f"{B}/reviews/drift_5model", mu, sd, metrics, levels=2).items():
        nb.setdefault(unit, {}).setdefault(panel, []).append(v)
    # The review count for this arm is already derived once, from the ARMS walk above. A second writer here
    # would agree until the day the two reads diverged, and then the row would report whichever ran last.
    n1b_reviews = sum(len(x) for d in nb.values() for x in d.values())
    assert n1b_reviews == got["corpus: drift_5model reviews"], (
        f"this block reads {n1b_reviews} drift reviews, the corpus walk counted "
        f"{got['corpus: drift_5model reviews']}")
    npan = {u: {k: st.mean(v) for k, v in d.items()} for u, d in nb.items()}
    n1b_p = sorted(u.split("/")[0] for u in npan if u.endswith("/baseline"))
    base = {p: npan[f"{p}/baseline"] for p in n1b_p}
    # Pass one's two panels, named rather than taken as "all of them": pass two added two more, and the drift
    # this row reports is the calibration-to-pass-one offset, which is the boundary section 6's deltas cross.
    P1 = ("panel1", "panel2")
    dr5 = {p: st.mean(base[p][k] for k in P1) - st.mean(acc[p].values()) for p in n1b_p}
    got["N1b drift: median offset"] = st.median(dr5.values())
    got["N1b drift: CI low"], got["N1b drift: CI high"] = boot_median_ci(list(dr5.values()))
    got["N1b drift: papers positive"] = sum(1 for x in dr5.values() if x > 0)
    got["N1b drift: papers"] = len(dr5)
    # The band this session, and the calibration band on these same eight papers. Both, because quoting the
    # first alone invites reading a heavy-tailed noise quantity's regression to the mean as a tighter panel.
    got["N1b band: median, this session"] = st.median(
        abs(base[p]["panel1"] - base[p]["panel2"]) for p in n1b_p)
    got["N1b band: calibration median, same papers"] = st.median(
        abs(acc[p]["panel1"] - acc[p]["panel2"]) for p in n1b_p)
    got["N1b band: smaller now"] = sum(
        abs(base[p]["panel1"] - base[p]["panel2"]) < abs(acc[p]["panel1"] - acc[p]["panel2"])
        for p in n1b_p)
    # The regression the appendix reads off those two bands, which is the argument for not quoting the smaller
    # one as a second yardstick. It is a claim about WHICH papers moved, so it needs the ordered gaps and not
    # only their median: the appendix named three values as "the three largest" when they are the first, third
    # and fourth, and a row against the median cannot see that. Both halves are checked as counts, because the
    # sentence is a statement about set membership and a value can be right inside a false claim about its rank.
    now = {p: abs(base[p]["panel1"] - base[p]["panel2"]) for p in n1b_p}
    then = {p: abs(acc[p]["panel1"] - acc[p]["panel2"]) for p in n1b_p}
    by_size = sorted(n1b_p, key=lambda p: -then[p])
    for i, nth in enumerate(("largest", "second largest", "third largest", "fourth largest")):
        got[f"calibration gap, {nth}"] = then[by_size[i]]
    got["calibration gaps: how many of the four largest collapsed"] = sum(
        now[p] < then[p] for p in by_size[:4])
    got["calibration gaps: how many of the four smallest grew"] = sum(
        now[p] > then[p] for p in by_size[4:])
    # Which baseline panels a variant is differenced against is decided by which pass scored it. T1 and T3 were
    # scored in the first pass and T2 in the second, each beside its own two baseline panels, so a variant
    # taking the other pass's baselines would put the pass boundary back inside the contrast this arm exists to
    # remove. The pairing is read off the panels present rather than assumed, and a variant whose pass is not
    # in the bundle contributes no rows at all rather than rows built from the wrong control.
    PASS_OF = {"T1_endmatter": ("panel1", "panel2"), "T3_lengthen": ("panel1", "panel2"),
               "T2_concede": ("panel3", "panel4")}
    for variant, short in (("T1_endmatter", "T1"), ("T3_lengthen", "T3"), ("T2_concede", "T2")):
        pa, pb = PASS_OF[variant]
        cell = [p for p in n1b_p if f"{p}/{variant}" in npan and pa in base[p] and pb in base[p]]
        if not cell:
            continue
        cl = [npan[f"{p}/{variant}"]["panel1"] - st.mean([base[p][pa], base[p][pb]]) for p in cell]
        got[f"N1b {short}: clean median dz"] = st.median(cl)
        got[f"N1b {short}: CI low"], got[f"N1b {short}: CI high"] = boot_median_ci(cl)
        got[f"N1b {short}: papers down"] = sum(1 for x in cl if x < 0)
        got[f"N1b {short}: papers"] = len(cl)
        got[f"N1b {short}: |median| / own band"] = (abs(st.median(cl))
                                                   / got["re-run band, median |dz| over 16"])
        got[f"N1b {short}: band in its own pass"] = st.median(
            abs(base[p][pa] - base[p][pb]) for p in cell)
        # The exact paired-distance test under each baseline panel as the anchor. Treated distance against
        # noise distance, one pair per paper, and the p-value is the share of all 2^8 sign assignments whose
        # median difference reaches the observed one. The anchor was fixed before the queue ran, so the second
        # value is not a robustness check that passed -- it is the same data answering 0.031 instead of 0.109,
        # which is the appendix's reason for not resting anything on either.
        for anchor, other, tag in ((0, 1, "declared anchor"), (1, 0, "other anchor")):
            b = [(base[p][pa], base[p][pb]) for p in cell]
            d = [abs(npan[f"{p}/{variant}"]["panel1"] - b[i][anchor]) - abs(b[i][other] - b[i][anchor])
                 for i, p in enumerate(cell)]
            obs = st.median(d)
            got[f"N1b {short} paired: exact swap p, {tag}"] = sum(
                st.median(x) >= obs for x in itertools.product(*[(v, -v) for v in d])) / 2 ** len(d)

    # The pass boundary, priced the same way the session boundary above is: byte-identical text, two panels on
    # each side. It is here because T2's number is only comparable to T1's if crossing between passes costs
    # nothing, and that is a measurement rather than a property of having used one script.
    both = [p for p in n1b_p if all(k in base[p] for k in ("panel1", "panel2", "panel3", "panel4"))]
    if both:
        step = [st.mean([base[p]["panel3"], base[p]["panel4"]])
                - st.mean([base[p]["panel1"], base[p]["panel2"]]) for p in both]
        got["N1b pass boundary: median offset"] = st.median(step)
        got["N1b pass boundary: CI low"], got["N1b pass boundary: CI high"] = boot_median_ci(step)
        got["N1b pass boundary: papers positive"] = sum(1 for x in step if x > 0)

    # --- appendix A: what the text pipeline drops, and what the reviewers charge for it -------------------
    # The appendix's artifact class is measured over the corpus rather than argued: all 48 papers, both arms,
    # every untouched review. Neither input of that measurement can ship -- the submitted documents are third
    # parties' and the supplied texts are de-identified derivatives of them -- so the release carries the
    # derived rows, and every number the appendix prints is recomputed here from them.
    #
    # The cross-check comes first, because it is what makes that file evidence rather than assertion: for the
    # two populations whose reviews ship in full, each review's charge flag is re-derived from the shipped
    # review text with the patterns above, and a disagreement stops the run. The declined arm's reviews ship
    # as scores only and cannot be checked that way. One pattern produced both sides, and this is where that
    # claim is tested rather than stated.
    ec = json.load(open(f"{B}/data/extract_corpus.json"))
    docs, pops = ec["documents"], ec["populations"]
    SHIPPED_FULL = {"accepted 16, five slots, untouched":
                    (f"{B}/reviews/drift_5model", "*/baseline/panel*/R?.json"),
                    "accepted 16, eight slots, untouched":
                    (f"{B}/reviews/vendor_panel", "*/panel*/[A-Z][0-9].json")}
    epat = dict(CHARGES)["charge an extract-only property"]
    for pop, (root, g) in SHIPPED_FULL.items():
        mine: dict[str, list] = {}
        for f in sorted(glob.glob(f"{root}/{g}")):
            mine.setdefault(os.path.relpath(f, root).split("/")[0], []).append(
                charges(json.load(open(f)), epat))
        theirs: dict[str, list] = {}
        for r in pops[pop]["reviews"]:
            theirs.setdefault(r["paper"], []).append(r["charge"])
        assert ({p: (len(v), sum(v)) for p, v in mine.items()}
                == {p: (len(v), sum(v)) for p, v in theirs.items()}), \
            f"{pop}: the shipped reviews do not produce the flags data/extract_corpus.json records"

    def med(rows, key):
        vals = [r[key] for r in rows.values() if r[key] is not None]
        return st.median(vals)

    ARMS_A = (("accepted 16, preprint text", "accepted"), ("declined 32, as-submitted PDF", "declined"))
    for dpop, tag in ARMS_A:
        rows = docs[dpop]
        for key, what in (("document_words", "median document words"),
                          ("reviewer_words", "median supplied words"),
                          ("back_words", "median back-matter words"),
                          ("body_share", "median share of the body supplied"),
                          ("captions", "median captions in the document"),
                          ("reviewer_captions", "median captions supplied")):
            got[f"extract, {tag}: {what}"] = med(rows, key)
        # A supplied text that contains back matter has a body shorter than itself, so the count the appendix
        # states is a property of two word counts that ship rather than of a flag that does not: the split at
        # the reference list returns the whole text as the body exactly when it finds no reference list.
        got[f"extract, {tag}: supplied texts with back matter"] = sum(
            1 for r in rows.values() if r["reviewer_words"] != r["reviewer_body_words"])
        ptr = [r["appendix_pointers"] for r in rows.values() if r["appendix_pointers"]]
        got[f"extract, {tag}: papers pointing into missing back matter"] = len(ptr)
        got[f"extract, {tag}: median pointers where any"] = st.median(ptr)
    got["extract: papers pointing into missing back matter, of 48"] = sum(
        got[f"extract, {t}: papers pointing into missing back matter"] for _, t in ARMS_A)

    # The rate at which a review makes the charge, population by population. Not pooled: the two corpora reach
    # the panel through different pipelines and the two rosters are different reviewers, so one pooled rate
    # would be the rate of a corpus nobody scored. The total is a row as well, since the appendix states it.
    SHORT = {"accepted 16, five slots, untouched": "accepted 16, five slots",
             "declined 32, five slots, untouched": "declined 32, five slots",
             "accepted 16, eight slots, untouched": "accepted 16, eight slots"}
    for pop, short in SHORT.items():
        rows = pops[pop]["reviews"]
        got[f"extract, {short}: reviews"] = len(rows)
        got[f"extract, {short}: charging reviews"] = sum(1 for r in rows if r["charge"])
        got[f"extract, {short}: charge rate"] = got[f"extract, {short}: charging reviews"] / len(rows)
    got["extract: reviews read"] = sum(got[f"extract, {s}: reviews"] for s in SHORT.values())
    got["extract: charging reviews"] = sum(got[f"extract, {s}: charging reviews"] for s in SHORT.values())

    # Whether the reviews that make the charge are the reviews of the papers whose supplied text lost the most.
    # The predictor is a density and not a count, because a pointer count is a length in disguise: a longer
    # submission has more back matter to lose and more text to be charged for. Holding the supplied length
    # fixed is what separates the two, and that is the second reading of each pair.
    #
    # Both reads of a corpus are averaged into one rate per paper. The number of papers is what the corpus
    # holds; the only precision left to buy is in the outcome, and a paper's rate off ten or twenty reviews is
    # a noisy estimate of it. Averaging halves that noise -- and noise in the outcome biases an association
    # towards zero, which is the direction that would make the null on the sixteen uninformative.
    READS = (("declined 32, both sittings", "declined 32, as-submitted PDF",
              ("declined 32, five slots, untouched",)),
             ("accepted 16, both rosters", "accepted 16, preprint text",
              ("accepted 16, five slots, untouched", "accepted 16, eight slots, untouched")))
    for tag, dpop, members in READS:
        d = docs[dpop]
        papers = sorted(d)
        rate = []
        for paper in papers:
            per = []
            for m in members:
                rs = [r for r in pops[m]["reviews"] if r["paper"] == paper]
                per.append(sum(1 for r in rs if r["charge"]) / len(rs))
            rate.append(st.mean(per))
        dens = [1000 * d[paper]["appendix_pointers"] / max(d[paper]["reviewer_words"], 1) for paper in papers]
        got[f"extract, {tag}: papers"] = len(papers)
        got[f"extract, {tag}: rho, pointer density vs charge rate"], got[f"extract, {tag}: p"] = \
            spearman_p(dens, rate)
        got[f"extract, {tag}: rho net of supplied length"], got[f"extract, {tag}: p net of length"] = \
            partial_spearman(rate, dens, [d[paper]["reviewer_words"] for paper in papers])

    # And whether the charge costs the paper score. Paired within paper, because papers differ from one another
    # far more than the reviews of any one of them differ, so a pooled split of 1,216 reviews reports that
    # between-paper variance as though it were the effect. The pooled reading is computed as well: in the
    # declined arm it reverses the sign, it is what anyone who split without pairing would report, and the
    # appendix states it as the trap rather than leaving a reader to walk into it.
    gapmed = {}
    for pop, short in SHORT.items():
        by_paper: dict[str, list] = {}
        for r in pops[pop]["reviews"]:
            by_paper.setdefault(r["paper"], []).append(r)
        gaps = []
        for paper, rs in sorted(by_paper.items()):
            hit = [r["z"] for r in rs if r["charge"]]
            miss = [r["z"] for r in rs if not r["charge"]]
            if hit and miss:
                gaps.append(st.mean(hit) - st.mean(miss))
        gapmed[short] = st.median(gaps)
        got[f"extract, {short}: paired gap, median"] = st.median(gaps)
        got[f"extract, {short}: papers with both"] = len(gaps)
        got[f"extract, {short}: papers with a positive gap"] = sum(1 for g in gaps if g > 0)
        got[f"extract, {short}: paired gap CI low"], got[f"extract, {short}: paired gap CI high"] = \
            boot_ci(lambda g: st.median(g), gaps)
        hit = [r["z"] for r in pops[pop]["reviews"] if r["charge"]]
        miss = [r["z"] for r in pops[pop]["reviews"] if not r["charge"]]
        got[f"extract, {short}: pooled gap"] = st.mean(hit) - st.mean(miss)
        got[f"extract, {short}: pooled AUC"] = auc(hit, miss)
    # The sentence those four gaps are for: not one of them is as large as the movement the same panel shows on
    # identical text. That is a claim about the largest of the four, so the largest is what carries the row.
    got["extract: largest |paired gap|, of four reads"] = max(abs(v) for v in gapmed.values())

    # --- section 6 and appendices E, H: the matched randomisation null -------------------------------------
    # The criterion's own comparison, made exact. Reimplemented here from the review files rather than read
    # out of pia_null.json, because a null is the number a reader is most likely to suspect of having been
    # chosen after the fact, so it has to be recomputable without the analysis code that produced it.
    #
    # Three definitions, and none of them has a threshold in it:
    #
    #   axis    a set of channels. A paper's score on an axis is the mean z over (slot, channel) within a
    #           panel, then the mean over that paper's panels -- composite()'s rule above, narrowed to a
    #           subset of the channels instead of all twelve.
    #   delta   the median over the treated papers of variant minus baseline on that axis.
    #   null    the papers' own (panel 2 - panel 1) on untouched text, on the same axis, with the signs
    #           randomised. The baseline panels ran interleaved over byte-identical prompts, so which one is
    #           "panel 1" is arbitrary, every re-run difference is as likely to carry one sign as the other,
    #           and the resulting distribution of the median is centred at zero by construction rather than by
    #           subtraction. A bootstrap of the same differences would instead keep whatever offset each
    #           channel's pool happens to carry, which at these sizes is not small.
    #
    # The scale factor is the one place the two rosters differ, and it is derived rather than typed. A
    # single-panel difference carries 2 sigma^2. A delta of a v-panel variant mean against a two-panel
    # baseline mean carries sigma^2/v + sigma^2/2. So the null's differences are multiplied by
    # sqrt((1/v + 1/2) / 2): 1/sqrt(2) where the variant arm has two panels, sqrt(3)/2 where it has one.
    # Without it the null is sqrt(2) too wide and every sigma below is understated.
    #
    # The allotment is the only judgement in any of this, and it is a judgement about what an edit can
    # justify touching, fixed from the metric definitions before the scores were seen. T1 and T3 share it, so
    # the two presentation arms have the same two groups; the claim-strength control has its own.
    ALLOT = licensed(metrics)
    VARIANTS = (("T1_endmatter", "T1"), ("T2_concede", "T2"), ("T3_lengthen", "T3"))

    def ztable(pat, m, s):
        """-> {(paper, panel): {channel: [z over slots]}}, one parse of the tree. paper/panel/slot come from
        the path, and the paper is taken from the directory above the panel rather than a fixed position, so
        the baseline tree (paper/panel) and the variant tree (paper/variant/panel) both read correctly.

        The name that decides which of the two shapes a path has is the condition, so it is tested against the
        condition list. Testing it against the allotment instead worked only while every nested directory was
        a transform: a tree that files its baselines under `paper/baseline/panelN` would key every one of them
        to the panel's own name, silently, and the pool built from them would be a pool of one panel each."""
        out: dict[tuple, dict] = {}
        for f, r in load(pat).items():
            parts = f.split("/")
            panel, slot = parts[-2], os.path.basename(f)[:-5]
            paper = parts[-4] if parts[-3] in CONDITIONS else parts[-3]
            for c, md in r.get("metrics", {}).items():
                key = f"{slot}|{c}"
                if key in m and s.get(key) and isinstance(md.get("score"), (int, float)):
                    out.setdefault((paper, panel), {}).setdefault(c, []).append(
                        (md["score"] - m[key]) / s[key])
        return out

    def per_paper(zt, cols):
        """-> {paper: [mean z per panel]} on the axis spanned by cols."""
        out: dict[str, dict] = {}
        for (paper, panel), chans in zt.items():
            zs = [z for c in cols for z in chans.get(c, ())]
            if zs:
                out.setdefault(paper, {})[panel] = st.mean(zs)
        return {p: [v for _, v in sorted(d.items())] for p, d in out.items()}

    def sd0(xs):
        mn = st.mean(xs)
        return (sum((x - mn) ** 2 for x in xs) / len(xs)) ** 0.5

    def exact_null(pool):
        """-> sorted medians over all 2^len(pool) sign assignments of the treated papers' own differences."""
        return sorted(st.median([x * g for x, g in zip(pool, sgn)])
                      for sgn in itertools.product((1, -1), repeat=len(pool)))

    def pooled_null(pool, k, seed, draws=200_000):
        """-> sorted medians over k of len(pool) drawn without replacement, signs randomised.

        A different seed from the analysis script on purpose. Matching a Monte Carlo by copying its seed
        proves only that the same code ran twice; drawing independently and agreeing inside Monte Carlo error
        proves the printed value is not an artefact of one stream.

        The draw count matches the analysis script's, which costs about two seconds an axis and is worth it
        for one reason: this null's standard deviation is the denominator of every sigma the paper prints, so
        an estimate loose in its third digit would force a tolerance loose in the second, and "-4.84 sigma"
        would be checked to +/- 0.08. At this count the relative error of a sample sd is about 0.16% either
        side, so the sigmas below are checkable to a few hundredths -- which is the precision they are
        printed at. Reducing the count is not a speed optimisation, it is a weaker check.
        """
        rng = random.Random(seed)
        return sorted(st.median([x * rng.choice((1, -1)) for x in rng.sample(pool, k)])
                      for _ in range(draws))

    def share(nulls, v, exact):
        """One-sided share at or below v. The +1 is the Monte Carlo correction; an enumeration needs none."""
        n = sum(1 for x in nulls if x <= v)
        return n / len(nulls) if exact else (n + 1) / (len(nulls) + 1)

    def share_two(nulls, v, exact):
        """The two-sided share, which is the nearer tail doubled.

        Available for nothing because the null is built by randomising the sign of every paper's difference,
        so the set of assignments is closed under a global flip and the distribution is exactly symmetric
        about zero. The upper tail therefore needs no second null.

        It is reported beside the one-sided p and never in place of it. One arm here is predicted to move a
        channel UP -- withdrawing a claim of significance should raise a reading of how honestly a paper
        describes its own evidence -- and a lower tail cannot see that at all. The leak family and its
        multiplicity correction stay one-sided and downward, as declared.
        """
        lo = share(nulls, v, exact)
        n = sum(1 for x in nulls if x >= v)
        hi = n / len(nulls) if exact else (n + 1) / (len(nulls) + 1)
        return min(1.0, 2 * min(lo, hi))

    def seed_of(*parts):
        """-> a seed derived from a row's name, so no two nulls here share a stream.

        Written out rather than taken from hash(), which is salted per process: a reproduction script whose
        numbers depend on the environment it happened to run in is the one thing this file may not be.
        """
        s = 90210
        for part in parts:
            for ch in str(part):
                s = (s * 131 + ord(ch)) % 2_147_483_647
        return s

    def bh_survivors(fam, q=0.05):
        """-> the channels a Benjamini-Hochberg step-up at q keeps, over one arm's non-allotted family.

        fam is (channel, p). The largest rank whose p clears its own threshold carries every smaller rank with
        it, which is why the loop keeps the last index that clears rather than stopping at the first that does
        not.
        """
        rows = sorted(fam, key=lambda r: r[1])
        keep = 0
        for i, (_, p) in enumerate(rows, 1):
            if p <= i * q / len(rows):
                keep = i
        return {c for c, _ in rows[:keep]}

    def null_test(key, d, pool, draws):
        """Both nulls for one axis, every row they support, and the family p the step-up above consumes.

        Two nulls, not one. The first draws len(d) of the pool, so it prices the arm against the whole
        roster's re-run spread; the second uses the treated papers' OWN differences, so a paper that happens
        to be noisy cannot be penalised by a null built without it. pia_null.py calls an axis moved only when
        both clear 0.05, and the family p below is the weaker of the two for the same reason: the claim is
        that this edit moved the reading, and it should not rest on whichever null came out kinder.

        Where the arm is small enough the second null is ENUMERATED over all 2^n sign assignments and needs
        no Monte Carlo correction; past ENUM_MAX papers it is sampled, which is the same null drawn rather
        than listed. Refusing there would have been worse than it looks -- an axis is moved only when both
        nulls clear, so an absent sign null turns the flag off for every axis in the larger arm, and a
        growing sample would have read as a vanishing effect.
        """
        obs = st.median(sorted(d.values()))
        own = [pool[p] for p in sorted(d) if p in pool]
        npool = pooled_null([pool[p] for p in sorted(pool)], len(d), seed_of(key, "pool"), draws)
        paired = len(own) == len(d)
        enum = paired and len(d) <= ENUM_MAX
        nown = (exact_null(own) if enum else
                pooled_null(own, len(own), seed_of(key, "own"), draws) if paired else None)
        got[f"{key}: delta"] = obs
        got[f"{key}: papers"] = len(d)
        got[f"{key}: papers down"] = sum(1 for x in d.values() if x < 0)
        got[f"{key}: null sd"] = sd = sd0(npool)
        # The multiple the appendix prints, divided here rather than by hand. It is always this axis's own
        # null: the same shift is a different number of sd on a roster whose re-run spread is wider, so a
        # multiple carried across rosters describes neither. One of them had been transcribed instead of
        # divided, and matched no roster, arm or axis in the outputs it was supposed to have come from.
        got[f"{key}: sigma"] = obs / sd if sd else float("nan")
        got[f"{key}: untouched papers in pool"] = len(pool)
        got[f"{key}: pooled p"] = pp = share(npool, obs, False)
        got[f"{key}: pooled p, two-sided"] = p2 = share_two(npool, obs, False)
        if nown is None:
            return obs, pp, p2
        got[f"{key}: own-arm p"] = pe = share(nown, obs, enum)
        got[f"{key}: own-arm p, two-sided"] = p2e = share_two(nown, obs, enum)
        got[f"{key}: sign assignments"] = len(nown)
        if enum:
            # The floor the paper prints as a bound. It is one over the count above, but the count is what a
            # reader checks and the bound is what a reader reads, and a bound printed to a precision its own
            # denominator cannot support is its own defect. Only an enumeration has one: a sampled null's
            # floor is a property of the draw count and says nothing about how many arrangements exist.
            got[f"{key}: exact null finest resolution"] = 1.0 / len(nown)
        got[f"{key}: moved"] = int(pp < 0.05 and pe < 0.05)
        return obs, max(pp, pe), max(p2, p2e)

    # The two rosters. What differs between them, beyond which reviews they read, is how a paper's delta and
    # its own re-run difference are obtained. The five-model contrast is day-matched, so both come from
    # dm_matched and both depend on which sitting that arm was read in; the eight-slot roster read one sitting,
    # so its two baseline panels are its pool whatever the arm. Everything downstream is one procedure and is
    # written once, because a second copy of it under a flag is how two rosters come to disagree by arithmetic.
    z8b = ztable(f"{B}/reviews/vendor_panel/*/panel*/C?.json", m8, s8)
    z8v = {v: ztable(f"{B}/reviews/vendor_transform/*/{v}/panel*/C?.json", m8, s8) for v, _ in VARIANTS}
    # One factor, not one per roster: each arm of each roster now reads one variant panel against a two-panel
    # same-day baseline mean, so both carry the same variance and the pilot's second factor was an artefact of
    # its two variant panels.
    got["matched variance factor"] = MSCALE
    ENUM_MAX = 16          # 2**16 medians of sixteen numbers is affordable without numpy; 2**47 is not

    def slot_read(cols, variant):
        """The eight-slot roster's deltas and re-run pool on one axis, in dm_matched's shape."""
        bp = per_paper(z8b, cols)
        vp = per_paper(z8v[variant], cols)
        return ({p: st.mean(v) - st.mean(bp[p]) for p, v in vp.items() if p in bp},
                {p: (v[1] - v[0]) * MSCALE for p, v in bp.items() if len(v) >= 2})

    for tag, read, cols_all, gdraws, cdraws in (
            ("", lambda cols, v: dm_matched(dm, cols, v), metrics, 200_000, 50_000),
            ("8-slot ", slot_read, k8, 200_000, 50_000)):
        for variant, short in VARIANTS:
            allot = licensed(cols_all)[variant]
            # Group axes first, then every channel on its own. The channel rows are what F4 draws, and a
            # number a figure draws is a number the paper prints: a group that agrees while a drawn channel is
            # wrong is still a paper with a wrong number in it.
            axes = [("composite", cols_all, gdraws),
                    ("allotted", [c for c in cols_all if c in allot], gdraws),
                    ("non-allotted", [c for c in cols_all if c not in allot], gdraws)]
            axes += [(f"channel {c}", [c], cdraws) for c in cols_all]
            fam = []
            for axname, cols, draws in axes:
                if not cols:
                    continue
                d, pool = read(cols, variant)
                obs, pf, pf2 = null_test(f"{tag}{short} {axname}", d, pool, draws)
                # The size of the group, taken from the allotment rather than from the prose. Three and nine
                # are what the paper calls licensed and unlicensed, and they are the denominators the step-up
                # below corrects over, so a rubric that gained a metric would show up here first.
                got[f"{tag}{short} {axname}: channels"] = len(cols)
                if len(cols) == 1 and cols[0] not in allot:
                    fam.append((cols[0], obs, pf, pf2))
            # How many of the non-allotted channels moved down, which is not how many papers moved down. A
            # group near zero can be nine small movements or a cancellation of large ones, and the paper says
            # which, so both denominators are counted rather than one being read as the other.
            got[f"{tag}{short} non-allotted: channels down"] = sum(1 for _, o, _, _ in fam if o < 0)
            # And the multiplicity correction, which is the whole of the paper's negative claim about the arm
            # that behaved: nine channels an edit was not licensed to reach, none of them surviving a step-up
            # over the nine. Recomputed here per channel as well as counted, because a count of survivors that
            # agrees while naming different channels is not the same result.
            for side, idx in ((r"", 2), (", two-sided", 3)):
                surv = bh_survivors([(r[0], r[idx]) for r in fam])
                got[f"{tag}{short} non-allotted: BH survivors{side}"] = len(surv)
                for c, *_ in fam:
                    got[f"{tag}{short} channel {c}: BH survivor{side}"] = int(c in surv)

    # The relocation arm's group p as F4 prints it, alongside the four-place value the appendix prose gives. One
    # measurement under two roundings, so the coarse one is an alias of the fine one and not a second reading.
    got["T1 non-allotted: pooled p at two places"] = got["T1 non-allotted: pooled p"]

    # --- appendix E: the pre-declared strength floor --------------------------------------------------------
    # The floor is a minimum edit count per transform. Every paper-variant cell under it is withheld, so no
    # reading in the bundle comes from a variant below its floor; asserted from the manifest's own edit counts.
    MIN_EDITS = {"T1_endmatter": 3, "T2_concede": 3, "T3_lengthen": 15}
    under = [(p, v) for p, d in man.items() for v, r in d.items()
             if v in MIN_EDITS and r["edits"] < MIN_EDITS[v]]
    got["floor: paper-variant cells"] = len(man) * len(MIN_EDITS)
    got["floor: cells under the floor"] = len(under)
    read_under = sorted((p, v) for p, v in under if p in five_delta[v])
    assert not read_under, f"below-floor variants carry a reading: {read_under}"
    got["floor: cells under the floor withheld"] = len(under)

    # --- the sign tests, derived from counts checked above ------------------------------------------------
    # Each of these p-values is quoted beside its split, and until now only the split was recomputed: a count
    # of 7 of 8 with the p-value of 6 of 8 beside it reads as one measurement and is two. Taken from `got`
    # rather than recounted, so a p-value cannot come out right against a count the rest of this file disputes.
    def sign_p(down, n):
        """-> the exact two-sided binomial p for `down` of `n` moving one way, under a fair-coin null.

        `n` is required. It used to default to eight, which was the size of every arm here when this was
        written; when one arm grew, a default would have gone on pricing its splits against the old
        denominator and produced a p-value that is arithmetically fine and about a different experiment.
        """
        tail = sum(math.comb(n, i) for i in range(min(down, n - down) + 1))
        return min(1.0, 2 * tail / 2 ** n)

    for t in ("T1", "T2", "T3"):
        nt = got[f"{t} arm: papers"]
        got[f"{t} sign test p at {got[f'{t} sign split, negative']} of {nt}"] = \
            sign_p(got[f"{t} sign split, negative"], nt)
    nd = got["N1b drift: papers"]
    got[f"N1b drift sign test p at {got['N1b drift: papers positive']} positive of {nd}"] = \
        sign_p(got["N1b drift: papers positive"], nd)
    # The one figure here that is not about an observed split: what the eight-slot design could reach if every
    # paper had moved. It is the caveat appendix H opens with, so it is a claim about that roster's n = 8.
    got["sign test resolution at n=8: p for 7 of 8"] = sign_p(7, 8)

    # And the two medians the prose states as costs, which drop the sign a cost does not carry.
    got["T1 cost, as printed unsigned"] = abs(got["T1 median dcomposite"])
    got["T2 cost, as printed unsigned"] = abs(got["T2 median dcomposite"])
    # Their ratio, which is the paper's one direct comparison of presentation against claim strength, and the
    # noise ratio at the one place the appendix quotes it to.
    got["T1 cost / T2 cost"] = got["T1 cost, as printed unsigned"] / got["T2 cost, as printed unsigned"]
    got["T1 |median| / own band, as printed at one place"] = got["T1 |median| / own band"]

    # Every number the appendix prints is rounded, and rounding an already-rounded figure a second time is how
    # four last digits went wrong the last time this paragraph was rewritten. DUMP6=1 prints what the bundle
    # actually computes, at six places, so the prose and the EXPECT row below are both taken from the same read.
    if os.environ.get("DUMP6"):
        for k in sorted(got):
            v = got[k]
            print(f"  {k:<52} {v:+.6f}" if isinstance(v, float) else f"  {k:<52} {v}")
    print()
    # A row is a promise about one printed number, and the table is edited by hand at every rewrite. Two rows
    # with the same name are either a paste that happened twice, which overstates how much of the paper is
    # checked, or two different expectations of one quantity, where the printed page can only satisfy one of
    # them and the run reports both. This shipped as a duplicated cross-arm pair count, so the guard is here.
    dupes = sorted({n for n in (r[1] for r in EXPECT) if [r[1] for r in EXPECT].count(n) > 1})
    assert not dupes, f"the expectation table names the same quantity twice: {dupes}"
    bad = 0
    for sec, name, want, tol in EXPECT:
        have = got.get(name)
        ok = have is not None and abs(have - want) <= tol
        bad += not ok
        shown = "missing" if have is None else (f"{have:+.3f}" if isinstance(have, float) else f"{have}")
        print(f"  {'ok  ' if ok else 'FAIL'} S{sec:<3} {name:<44} paper {want:>7}   bundle {shown:>8}")
    print(f"\n{len(EXPECT) - bad}/{len(EXPECT)} of the paper's headline numbers reproduce from the bundle")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
