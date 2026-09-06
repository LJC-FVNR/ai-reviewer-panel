#!/usr/bin/env python3
"""The two things the figures and the generated tables have to agree about: how a signed number is
spelled, and how a p-value that has hit the floor of its own null is spelled.

Matplotlib draws tick labels with a true minus, U+2212, because `axes.unicode_minus` defaults on. A string
built with an f-string gets an ASCII hyphen instead, so a panel that annotates itself with `f"{x:+.2f}"` prints
its numbers in a different glyph from its own axis. It is a two-pixel difference and invisible while every
annotated value happens to be positive, which is how F1 stayed consistent until an arm's correlation changed
sign; F3 had been mixed since it was written, printing the paper's three headline transform effects one way and
the axis beside them the other.

So: format every signed value through `sgn`, and let `audit_submission.py` sweep the rendered PDFs for the
mixed case. A convention no check enforces is a convention that holds until the next edit.
"""
from __future__ import annotations

import math

MINUS = "−"


def sgn(x, places=2, plus=True):
    """-> a signed number spelled the way matplotlib spells its tick labels.

    `plus=False` for a value whose sign is only worth showing when it is negative, which is what a p-value or a
    ratio wants; the default shows it either way, because a table of effects reads wrong without it.
    """
    s = f"{x:+.{places}f}" if plus else f"{x:.{places}f}"
    return s.replace("-", MINUS)


def pfmt(p, assignments, places=4, rel=False):
    """-> a randomisation p spelled the way this study spells one, a floored p as the bound it is.

    A randomisation p cannot resolve past one over its own assignment count, and both of pia_null.py's
    regimes bottom out there: a full enumeration divides the tail by the count and can return a true
    zero, and a sampled null adds one to both terms, so it bottoms out one step above zero. Printed at
    four places either of those reads "0.0000", which states a p of exactly zero -- a claim no finite
    randomisation can make, and one that means something quite different from what happened, which is
    that no assignment reached the observed value. A floor printed as "< 0.0000" is no better.

    So a p at or below the floor prints as a bound at two significant figures, which spells the
    eight-paper enumeration's floor as the 0.0039 the appendix already uses, the sixteen-paper one as
    0.000015, and the sampled null's as 0.000005. `rel` puts the relation in front for a figure
    annotation, where "p = 0.44" has to read as a sentence; a table column headed "p" does not want it.
    """
    if p is None or assignments is None:
        return "n/a"
    floor = 1.0 / assignments
    if p <= floor:
        d = -int(math.floor(math.log10(floor))) + 1
        return "< " + f"{floor:.{d}f}".rstrip("0")
    return ("= " if rel else "") + f"{p:.{places}f}"


def rng(lo, hi, places=2, plus=True):
    """-> "[lo, hi]" for an interval, so a bound's sign cannot be spelled differently from a point estimate."""
    return f"[{sgn(lo, places, plus)}, {sgn(hi, places, plus)}]"
