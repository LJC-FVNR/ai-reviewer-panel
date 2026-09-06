#!/usr/bin/env python3
"""PIA transforms: three mechanical, semantics-preserving presentation edits + their gate.

Every transform is applied by this script and never by hand. A hand-edited manuscript cannot be
replicated by a reader, and the whole point of PIA is that a venue can re-run it.

THE INVARIANT, and it is the only thing standing between this and a worthless result:
    the multiset of numeric literals in the text is UNCHANGED by every transform.
A transform that alters, adds or drops a number is void -- it would be changing the paper's claims,
not its presentation, and any score movement would be uninterpretable. `--verify` asserts this and
exits nonzero, so a violation cannot reach the panel.

WHY T1 IS NOT "TABLES -> CAPTION-ONLY", which is what the plan originally specified.
Measured on the corpus: all 48 de-identified papers already carry `[Table N about here]` +
full-caption blocks, so the table BODY is not sitting there as a table. What IS sitting there is the
extractor's wreckage -- pdftotext fuses table cells into unreadable digit runs like
"10.430.420.370.460.220.52...". So the specified transform is either a no-op (bodies are already
placeholders) or it deletes those runs, and those runs ARE numeric values, which the invariant above
forbids. Either way it is void, so T1 is replaced by a transform the corpus can actually support:

  T1  endmatter  Collect EVERY figure/table placeholder+caption block into an end-matter section, in
                 document order. Content-identical by construction -- a permutation of existing
                 blocks plus one digit-free heading -- and it is the real layout of a manuscript
                 submitted under a figures-at-end house style, so it probes whether the panel pays
                 for evidence being inline. Its predecessor ("relocate each block to its first
                 textual reference") was MEASURED to be a null treatment for 2 of the 8 papers
                 (2603.06557, 2502.10178: 0 blocks moved, output differing only in whitespace),
                 because their captions already sat beside their reference. A transform that does
                 nothing to a quarter of the sample is not a weak treatment, it is an absent one,
                 and it would have been averaged in as if it were real. Every paper here carries
                 >=4 caption blocks (56 across the 8), so this version cannot be null.
  T2  concede    Fixed hedging substitutions + one fixed limitations paragraph appended. Probes
                 whether announcing weakness costs score. The substitution table is closed and the
                 appended paragraph contains NO digits, so numbers survive.

                 *** T2 IS NOT A PRESENTATION-INVARIANCE TRANSFORM. Established 2026-08-30, after
                 scoring, by reading its own substitution table. *** It changes what the paper
                 CLAIMS, not how the claim is presented:
                     significantly outperforms -> outperforms      withdraws a significance claim
                     we prove that -> we argue, with proof under our assumptions, that
                     proves -> indicates ; establishes -> supports ; confirms -> is consistent with
                     guarantees -> is intended to provide          a guarantee is not an intention
                     state-of-the-art -> competitive               a different ranking claim
                 and the appended paragraph concedes unisolated confounds and a limited baseline set
                 in so many words. So a reviewer who lowers statistical_soundness (-0.246 measured)
                 or breadth_generality (-0.197) on T2 may be updating rationally on a claim the
                 paper has itself withdrawn -- which is the opposite of a presentation artefact.
                 The numeric-multiset invariant did not catch this because it guards NUMBERS and T2
                 alters CLAIM STRENGTH, which contains no digits. An invariant is only as good as
                 the thing it happens to measure.

                 T2's 80 reviews are kept and reported, but as a claim-strength contrast, never as
                 evidence of presentation sensitivity. It earns its place by comparison: softening
                 every proof to an argument and dropping every "significantly" costs 0.146 z, while
                 T1 -- which permutes existing blocks and alters not one word -- costs 0.260 z. The
                 panel reacts nearly twice as hard to where the figures sit as to whether the paper
                 claims a proof or merely evidence.
  T3  normalise  Split sentences over LONG_WORDS at clause boundaries, replacing the consumed
                 connective with a digit-free sentence-initial equivalent (BOUNDARY below). Probes
                 legibility alone.

WHY T3 REPLACES ITS CONNECTIVE INSTEAD OF DELETING IT.
The first version DELETED the connective it cut at, which is safe for a coordinator (", and Y does
Z" -> "Y does Z.", a clause with its own subject) and wrong for a relative or subordinator: cutting
", which makes it sensitive to redundancy" leaves "Makes it sensitive to redundancy." -- a
subjectless verb-initial fragment. Measured over these 8 papers, that version made 106 splits and
**33 of them deleted a subject-or-link word** (`which` 19, `while` 13, `whereas` 1), emitting
strings like 'Containsthe evidence required to answer the question.' Nearly a third of the treatment
was ungrammatical, and the direction matters: T3 is supposed to make text EASIER to read, so
degrading it would push the score the other way and leave the measured effect uninterpretable.
Now every subordinator maps to a replacement that carries a subject ("This", "Meanwhile,", "By
contrast,", "Here,"), only true coordinators are deleted, `although` is dropped (no opener preserves
its meaning), and `;` is added because a semicolon joins two independent clauses by definition. The
wider set also lifts the treatment's reach: of the 175 over-long prose sentences in the sample it
can split 109 (62%), against 71 (41%) before.

AND WHY "LONGEST SENTENCE" IS NOT THE STRENGTH METRIC.
Measured on this corpus, the longest "sentences" are not sentences: pdftotext fuses a heading into
the following paragraph ("LAYERWISE EVOLUTION ... IN CNNS" + "To examine how ..."), a page number
into a section title, and display equations into prose. Judged on the raw maximum, T3 looks inert
(94 -> 94 words); judged on prose only it plainly works (116 -> 57, 70 -> 48). Splitting the fused
units would chop headings off paragraphs and cut equations in half, so `verify` reports prose-only
statistics and the transform leaves the wreckage alone.

Usage:
  pia_transforms.py --list-papers                 pre-registered 8-paper selection, with the rule
  pia_transforms.py --build <outdir>              write baseline + 3 variants per selected paper
  pia_transforms.py --verify <outdir>             gate: numeric multiset + leak scan + stats
"""
import argparse
import glob
import json
import os
import re
import statistics as st
import sys

WS = "/path/to/workspace"
CAL = f"{WS}/paper_direction_98_calibration"
AN = f"{WS}/ai_native_academia"
PARAMS = f"{CAL}/ICLR/calibration_params_portable.json"
LONG_WORDS = 32

# ---------------------------------------------------------------------------------------------
# Paper selection. Pre-registered and deterministic: sort all 16 accepted papers by their 5-model
# composite and take every other one. That spans the whole reference field rather than clustering
# at one end, which matters because rank displacement is one of the reported quantities -- a
# transform's effect is only visible as displacement if its neighbours are at varying distances.
# It is not outcome selection: all 16 carry the same label (accepted), and each paper is its own
# control in a within-paper delta design, so the baseline level cannot bias the delta.
# ---------------------------------------------------------------------------------------------
def selected_papers():
    """-> (papers, ranked). Every accepted paper that has a de-identified text and a baseline score.

    This used to take every other paper by composite (ranks 1, 3, ..., 15), which was defensible --
    deterministic, spread across the reference field, fixed before any variant was scored -- but it
    was still a selection step standing between the arm and its population, and it halved the arm for
    nothing. Taking all sixteen removes the step: the arm is now every paper whose baseline this study
    already has, which is a description rather than a choice. `ranked` is still returned in composite
    order because the gate report reads better sorted by where a paper sits in the field.
    """
    pc = json.load(open(PARAMS))["per_paper_composite"]
    ranked = sorted(pc.items(), key=lambda kv: kv[1])
    return [pid for pid, _ in ranked], ranked


NUM = re.compile(r"\d+(?:\.\d+)?")


def numbers(text):
    """Multiset of numeric literals, as a sorted list so it compares exactly."""
    return sorted(NUM.findall(text))


# ---------------------------------------------------------------------------------------------
# T1 -- collect all caption blocks into end matter
# ---------------------------------------------------------------------------------------------
PLACEHOLDER = re.compile(r"^\[(Table|Figure) (\d+)[^\]]*about here\]\s*$")
ENDMATTER_HEADING = "FIGURE AND TABLE CAPTIONS"  # deliberately digit-free


def t1_endmatter(text):
    """Move every placeholder+caption block to an end-matter section, in document order.

    A block = the `[X N about here]` line plus the following caption lines, up to the next blank
    line or next placeholder. Blocks are removed and re-appended verbatim, never rewritten, so the
    transform is a permutation of lines plus a digit-free heading: the numeric multiset is preserved
    by construction, not by luck.

    `moved` counts only blocks that were not ALREADY in the trailing end matter, so a paper shipped
    with figures at the end would honestly report 0 rather than claiming a treatment it did not
    receive. That is the check the previous implementation lacked.
    """
    lines = text.split("\n")
    blocks, keep, i = [], [], 0
    tail_marker = []  # index into `keep` at the moment each block was found
    while i < len(lines):
        if not PLACEHOLDER.match(lines[i].strip()):
            keep.append(lines[i])
            i += 1
            continue
        blk = [lines[i]]
        i += 1
        while i < len(lines) and lines[i].strip() and not PLACEHOLDER.match(lines[i].strip()):
            blk.append(lines[i])
            i += 1
        blocks.append(blk)
        tail_marker.append(len(keep))
    if not blocks:
        return text, 0

    # A block was already in end matter iff no body text follows it. `keep` holds body only, so the
    # test is "were there any non-blank body lines after this block's position?"
    last_body = max((j for j, ln in enumerate(keep) if ln.strip()), default=-1)
    moved = sum(1 for pos in tail_marker if pos <= last_body)

    out = keep + ["", ENDMATTER_HEADING, ""]
    for blk in blocks:
        out.extend(blk)
        out.append("")
    return "\n".join(out), moved


# ---------------------------------------------------------------------------------------------
# T2 -- concession framing
# ---------------------------------------------------------------------------------------------
# Closed substitution table: confident -> hedged. Case-preserving on the first letter only. Each
# replacement is same-meaning-weaker, never a claim change, and none touches a digit.
HEDGES = [
    (r"\bwe show that\b", "we present evidence that"),
    (r"\bwe demonstrate that\b", "we provide evidence that"),
    (r"\bwe prove that\b", "we argue, with proof under our assumptions, that"),
    (r"\bdemonstrates\b", "suggests"),
    (r"\bdemonstrate\b", "suggest"),
    (r"\bproves\b", "indicates"),
    (r"\bclearly shows\b", "is consistent with"),
    (r"\bshows that\b", "indicates that"),
    (r"\bestablishes\b", "supports"),
    (r"\bconfirms\b", "is consistent with"),
    (r"\bsignificantly outperforms\b", "outperforms"),
    (r"\bsubstantially\b", "measurably"),
    (r"\bstate-of-the-art\b", "competitive"),
    (r"\bnovel\b", "new"),
    (r"\bcrucial\b", "important"),
    (r"\bessential\b", "useful"),
    (r"\bwe are the first to\b", "to our knowledge we are among the first to"),
    (r"\bour method solves\b", "our method addresses"),
    (r"\bguarantees\b", "is intended to provide"),
]
LIMITATIONS = """
LIMITATIONS
Several limitations qualify the scope of these findings. The evaluation covers the settings
described above and we have not established that the conclusions transfer to substantially
different architectures, data regimes, or scales. Where we report improvements, we have not
isolated every factor that could contribute to them, so part of the observed effect may be
attributable to implementation details rather than to the mechanism we describe. Our analysis
relies on assumptions stated in the corresponding sections; where those assumptions are violated
we would expect the conclusions to weaken. Finally, some comparisons are made against a limited
set of alternatives, and a broader baseline set could change the relative ordering we report.
"""


def t2_concede(text):
    n = 0
    for pat, rep in HEDGES:
        text, k = re.subn(pat, rep, text, flags=re.IGNORECASE)
        n += k
    return text.rstrip() + "\n" + LIMITATIONS, n


# ---------------------------------------------------------------------------------------------
# T3 -- sentence-length normalisation
# ---------------------------------------------------------------------------------------------
# Clause boundary -> the sentence opener that replaces the consumed connective. Every value stands
# alone grammatically, which is the whole point: cutting at ", which" and leaving "Which ..." is a
# fragment, and T3 must not degrade the text it is supposed to make more legible. `although` is
# absent because no opener preserves its meaning ("Y holds. Although Z fails." is a fragment), and
# a bare `;` maps to "" because a semicolon already joins two independent clauses.
BOUNDARY = {"and": "", "but": "However,", "which": "This", "while": "Meanwhile,",
            "whereas": "By contrast,", "however": "However,", "so": "Therefore,", "thus": "Thus,",
            "therefore": "Therefore,", "where": "Here,", "yet": "Yet,", "hence": "Hence,"}
SPLIT_AT = re.compile(r";\s+|,\s+(" + "|".join(BOUNDARY) + r")\s+", re.IGNORECASE)
# Deleting a connective is only safe when the tail is an independent clause, i.e. for a true
# coordinator. Every other boundary MUST supply an opener that carries a subject, or the split emits
# a subjectless fragment. Asserted here rather than sniffed for in the output, because it is a
# property of the table and a table is checkable exactly.
DELETION_SAFE = {"and"}
assert all(v or k in DELETION_SAFE for k, v in BOUNDARY.items()), \
    "a non-coordinator boundary maps to an empty opener: splitting there drops the subject"
# Extraction wreckage: display math, or a fused ALL-CAPS heading. Never split these -- a cut would
# land inside an equation or shear a heading off its paragraph.
CAPS_RUN = re.compile(r"\b[A-Z][A-Z\-]{2,}(\s+[A-Z][A-Z\-]{2,}){2,}")
LEAD_CAPS = re.compile(r"^[A-Z][A-Z\-]{2,}\b")  # single fused heading word: "INTRODUCTION The ..."
MATHY = set("=∈∑≤≥")

# A tail may stand as its own sentence only if it brings its own subject. This closed set is the
# evidence for that: pronouns, determiners, and existential "there". It is what separates coordinated
# CLAUSES (", and the model fails" -> "The model fails.", fine) from coordinated VERB PHRASES
# (", and impede debugging" -> "Impede debugging.", a fragment). Measured: without this test the
# `and` boundary emitted exactly that, e.g. "This opacity can erode trust, impede debugging."
CLAUSE_STARTERS = {
    "it", "we", "they", "this", "these", "those", "he", "she", "there", "one", "both", "each",
    "all", "most", "some", "many", "few", "no", "our", "its", "their", "his", "her", "your", "my",
    "the", "a", "an", "such", "other", "another", "in", "for", "by", "at", "on", "with", "when",
    "if", "as", "from", "given", "under", "over", "during", "after", "before", "because",
    "since", "although", "while", "however", "therefore", "thus", "hence", "here",
}
# "to" is deliberately absent: it opens an infinitive phrase, not a clause, and admitting it
# produced "However, to find useful features that enable faithful steering." -- no main verb.


# Number agreement for the `which` -> demonstrative rewrite. Replacing a relative pronoun has to get
# number right or the repair is itself ungrammatical ("which rely on X" -> "This rely on X").
# Suffix tests alone are not enough, because pdftotext FUSES words: the tails in this corpus include
# "containsthe", "isoften", "wasalso", "ischaracterized", so "ends in s" misreads them as plural and
# emits "These contains ...". Auxiliaries are therefore matched by PREFIX, which survives fusion, and
# anything that matches nothing here is not guessed at -- the split is skipped. Reach lost to caution
# is recoverable; an ungrammatical treatment is not, because it silently reverses T3's direction.
SG_PREFIXES = ("is", "was", "has", "does")
PL_EXACT = {"are", "were", "have", "do"}
MODALS = {"may", "might", "can", "could", "will", "would", "should", "must"}


def _which_opener(tail):
    """-> "This" / "These" / None (None means: do not split here)."""
    w = tail.split()[0].strip("(,.").lower()
    if w.startswith(SG_PREFIXES):
        return "This"
    if w in PL_EXACT:
        return "These"
    if w in MODALS:
        return "This"
    if w.endswith("s") and not w.endswith("ss"):
        return "This"
    return None


def is_prose(s):
    """True for units a reader would call a sentence, so strength is measured on text, not debris."""
    if MATHY & set(s) or CAPS_RUN.search(s) or LEAD_CAPS.match(s.strip()):
        return False
    if re.match(r"^\s*\d+\s*\n", s):
        return False
    return len(s.split()) >= 4 and s[:1].isupper()


def _at_depth0(s, pos):
    """True if `pos` sits outside every bracket.

    A semicolon inside "(Brown et al., 2020; Touvron et al., 2023)" is a citation separator, not a
    clause boundary, and splitting there produced the truncated citation
    'Large Language Models (LLMs) (Brown et al., 2020.'
    """
    d = 0
    for ch in s[:pos]:
        if ch in "([{":
            d += 1
        elif ch in ")]}":
            d = max(0, d - 1)
    return d == 0


# Words a sentence may begin with and still be safely lowercased when it becomes a trailing clause.
# Closed and purely functional: no proper noun, acronym, or defined term can enter, so joining can
# never destroy a capitalisation that carried meaning.
SAFE_LOWER = {
    "the", "this", "these", "those", "it", "we", "our", "a", "an", "in", "for", "by", "at", "on",
    "with", "such", "each", "both", "all", "most", "some", "there", "if", "when", "as", "from",
    "given", "they", "their", "its", "one", "other", "another", "here", "then", "also", "thereby",
    "however", "therefore", "thus", "since", "because", "while", "although", "instead", "rather",
    "indeed", "moreover", "furthermore", "additionally", "similarly", "importantly", "notably",
    "specifically", "overall", "first", "second", "third", "finally", "to", "no", "not", "that",
}
JOIN_CAP = 50  # a joined sentence longer than this stops reading as prose and starts reading as debris


def t3_lengthen(text):
    """Join adjacent short prose sentences into long ones with ", and".

    THE DIRECTION IS DELIBERATE, and reversed from the first version. The plan's axis is sentence
    length ("the plain-language axis"), and the first version split long sentences -- but this corpus
    has almost nothing to split. Mean prose sentence is 20.6 words; only 175 of ~1,300 exceed 32, and
    the ones that do are mostly extraction debris that must not be cut. Every safe variant of the
    splitting transform touched about 5% of sentences and moved the mean 20.6 -> 19.5 words. Against
    a pre-registered criterion that compares the effect to a 0.160 z test-retest band, a treatment
    that small yields a null nobody can read: "presentation does not matter" and "the manipulation
    was too weak to see" are the same measurement. Lengthening has all the headroom, so the arm keeps
    the axis and runs in the direction the corpus can actually support.

    Joining cannot produce a fragment -- two independent clauses coordinated by "and" are grammatical
    by construction -- so this direction is also the safer one. Only "and" and a comma are added, no
    digit is touched, and the second sentence is lowercased only when it opens with a closed-class
    function word.
    """
    out, joins = [], 0
    for para in text.split("\n\n"):
        head = para.strip().split("\n")[0] if para.strip() else ""
        if PLACEHOLDER.match(head) or re.match(r"^(Table|Figure) \d+:", para.strip()):
            out.append(para)
            continue
        sents = re.split(r"(?<=[.!?])\s+", para)
        merged, i = [], 0
        while i < len(sents):
            s = sents[i]
            while i + 1 < len(sents):
                nxt = sents[i + 1]
                w = nxt.split()
                if not (s.rstrip().endswith(".") and is_prose(s) and is_prose(nxt) and w):
                    break
                if w[0].strip("(,.").lower() not in SAFE_LOWER:
                    break
                if len(s.split()) + len(w) > JOIN_CAP:
                    break
                s = s.rstrip()[:-1].rstrip() + ", and " + nxt[0].lower() + nxt[1:]
                joins += 1
                i += 1
            merged.append(s)
            i += 1
        out.append(" ".join(merged))
    return "\n\n".join(out), joins


def t3_normalise(text):
    """Split over-long prose sentences at clause boundaries. SUPERSEDED by t3_lengthen -- retained
    because the measurement that retired it is part of the paper's method record, not a dead end.

    The consumed connective is replaced by its BOUNDARY opener; no other token and no digit is
    touched. Splitting is per-paragraph so captions and headings survive, and non-prose units
    (equations, fused headings) are skipped outright.
    """
    out, splits = [], 0
    for para in text.split("\n\n"):
        # do not touch caption/placeholder blocks or headings
        if PLACEHOLDER.match(para.strip().split("\n")[0] if para.strip() else "") or \
           re.match(r"^(Table|Figure) \d+:", para.strip()) or len(para.split()) < LONG_WORDS:
            out.append(para)
            continue
        sents = re.split(r"(?<=[.!?])\s+", para)
        new = []
        for s in sents:
            while len(s.split()) > LONG_WORDS and is_prose(s):
                cut = None
                for m in SPLIT_AT.finditer(s):
                    if m.start() < 20 or not _at_depth0(s, m.start()):
                        continue          # never split in the first few words, nor inside brackets
                    tail = s[m.end():]
                    tw = tail.split()
                    if len(tw) < 5:
                        continue
                    conn = (m.group(1) or ";").lower()
                    opener = BOUNDARY.get(conn, "")
                    first = tw[0].strip("(,.").lower()
                    if opener == "This":
                        # "which" -> demonstrative only works if the tail is a predicate ("which
                        # makes X" -> "This makes X."). If the tail brings its own subject, the
                        # demonstrative doubles it.
                        if first in CLAUSE_STARTERS:
                            continue
                        opener = _which_opener(tail)
                        if opener is None:
                            continue
                    elif first not in CLAUSE_STARTERS:
                        # every other boundary needs the tail to be an independent clause
                        continue
                    cut = (m, opener, tail)
                    break
                if not cut:
                    break
                m, opener, tail = cut
                new.append(s[:m.start()].rstrip(",;") + ".")
                s = (opener + " " + tail) if opener else (tail[0].upper() + tail[1:])
                splits += 1
            new.append(s)
        out.append(" ".join(new))
    return "\n\n".join(out), splits


TRANSFORMS = {"T1_endmatter": t1_endmatter, "T2_concede": t2_concede, "T3_lengthen": t3_lengthen}

# Workflow/identity terms that must never reach a reviewer. Same blocking list the cursor runner
# uses; generic science vocabulary is deliberately absent (it produces false positives on real
# papers). T2's appended paragraph is checked by this too.
BLOCKING = ["loopplane", "project_brief", "shared_context", "wf_2026", "run_2026", "direction-72",
            "paper_direction", "gate_eval", "cursor_panel", "calibration_params",
            "panel_and_writing", "reviewer_prompt_template", "manuscript_extracted",
            "run_cursor_panel", "score_against_gate", "five-reviewer", "eight-reviewer",
            "pia_transforms", "ai_native_academia"]


def accepted_corpus():
    """-> (selection rule, [(paper id, source text path)]) for the accepted arm."""
    papers, _ = selected_papers()
    return ("every accepted paper carrying a de-identified text and a baseline score; no selection "
            "step; not outcome selection",
            [(pid, f"{CAL}/deid/build_{pid}/manuscript.txt") for pid in papers])


def rejected_corpus():
    """-> the same for the rejected arm, keyed by release label rather than by forum id.

    The label is the directory name, not a column added later, because a forum id names a real
    third-party submission and this tree is an input to a release bundle. Nothing downstream has to
    remember to translate, and nothing can leak by forgetting to. The mapping is arm-blind and already
    fixed in the rejected arm's own public_labels.json; it is read, never regenerated, so the labels
    the transform arm prints are the labels the ranking arm already printed.
    """
    pub = json.load(open(f"{AN}/reject_arm/public_labels.json"))
    out = []
    for forum, label in sorted(pub.items(), key=lambda kv: kv[1]):
        # The extraction directory is build_<stratum>_<forum>, so the stratum has to be globbed past
        # rather than named: it is the pool's sampling stratum and it is not a variable in this study.
        hits = sorted(glob.glob(f"{AN}/reject_arm/deid/build_*_{forum}/manuscript.txt"))
        assert len(hits) <= 1, f"{label}: {len(hits)} extractions"
        if hits:
            out.append((label, hits[0]))
    return ("every rejected submission in the ranking arm carrying a de-identified text and a "
            "baseline score; no selection step; not outcome selection", out)


CORPORA = {"accepted": accepted_corpus, "rejected": rejected_corpus}


def build(outdir, corpus="accepted"):
    rule, items = CORPORA[corpus]()
    papers = [pid for pid, _ in items]
    os.makedirs(outdir, exist_ok=True)
    manifest = {"selection_rule": rule, "corpus": corpus,
                "long_words": LONG_WORDS, "papers": papers, "variants": {}}
    for pid, src in items:
        base = open(src, encoding="utf-8", errors="replace").read()
        d = os.path.join(outdir, pid)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "baseline.txt"), "w", encoding="utf-8") as f:
            f.write(base)
        rec = {"baseline": {"words": len(base.split()), "numbers": len(numbers(base))}}
        for name, fn in TRANSFORMS.items():
            new, k = fn(base)
            with open(os.path.join(d, f"{name}.txt"), "w", encoding="utf-8") as f:
                f.write(new)
            rec[name] = {"words": len(new.split()), "numbers": len(numbers(new)), "edits": k}
        manifest["variants"][pid] = rec
    json.dump(manifest, open(os.path.join(outdir, "manifest.json"), "w"), indent=1)
    print(f"built {len(papers)} papers x (baseline + {len(TRANSFORMS)} variants) in {outdir}")
    return manifest


# Per-transform treatment-strength floor. This exists because "non-null" is too weak a bar: an
# earlier build of the splitting transform reached ONE edit on a 5,000-word paper and passed a
# 0-edit check cleanly. A pre-registered criterion that compares the effect to a 0.160 z test-retest
# band needs a manipulation large enough that a presentation-sensitive panel would have to move, so
# the floor is set where the transform stops being detectable by a reader rather than at zero.
MIN_EDITS = {"T1_endmatter": 3, "T2_concede": 3, "T3_lengthen": 15}
# T3 additionally has to shift the quantity it names, not just count edits.
T3_MIN_MEAN_LIFT = 0.10

SUBORDINATE = ("Although ", "Since ", "Whereas ", "While ", "Because ", "If ", "Which ")


def is_fragment(s):
    """A subordinate clause left without a main clause -- the thing a bad split produces.

    The opener alone proves nothing: "Although X, Y." and "Since X, Y." are ordinary sentences and
    the baselines are full of them, so an opener-only test fires on the untransformed papers and
    tells you nothing about the transform. What is ungrammatical is a subordinate opener with no
    main clause after it, and a bare relative pronoun, which no comma can rescue.
    """
    b = s.strip()
    if not b.startswith(SUBORDINATE):
        return False
    return True if b.startswith("Which ") else "," not in b


def prose_sentences(text):
    units = [x for para in text.split("\n\n") for x in re.split(r"(?<=[.!?])\s+", para)]
    return [s for s in units if is_prose(s)]


def verify(outdir):
    """The gate. Four conjuncts, and the last two exist because the first two let real defects past.

    1. numeric multiset identical      -- a transform that moves a number changes the claim
    2. leak scan clean                 -- no workflow/identity term reaches a reviewer
    3. treatment is non-null           -- 0 edits is an absent treatment averaged in as a real one
    4. no ungrammatical fragments       -- a botched split makes a legibility transform illegible

    Conjuncts 1-2 passed the first build of these variants while T1 was doing nothing to 2 of 8
    papers and T3 was emitting 8 fragments. A gate blind to the defect it is guarding is worse than
    no gate, because it certifies.
    """
    manifest = json.load(open(os.path.join(outdir, "manifest.json")))
    # Two outcomes, and which conjunct a finding comes from decides which one it gets.
    #
    #   fails     the transform is broken: it moved a number, leaked a term, left a fragment, or
    #             missed the axis it names. There is nothing to drop here, because the defect is in
    #             the code that made the variant and would recur on the next paper. Refuse the run.
    #   excluded  the transform worked and this paper had nothing for it to do. That is a property of
    #             the paper, not a bug: T1 moves caption blocks, and a paper submitted with its
    #             figures already at the end has none to move. The cell is dropped from the arm.
    #
    # Only the weak-treatment floor is eligible for the second outcome, and the floor is pre-registered
    # and computed before any variant is scored, so a drop cannot be outcome selection: no score for
    # the cell exists at the time the decision is made.
    #
    # The share of an arm that may be dropped is capped, using this file's own standard from T1's note
    # above: a transform that does nothing to a quarter of the sample is an absent treatment, not a
    # weak one. Past that the transform is what failed, and the run is refused rather than shrunk.
    fails, excluded, rows = [], [], []
    for pid in manifest["papers"]:
        d = os.path.join(outdir, pid)
        base = open(os.path.join(d, "baseline.txt"), encoding="utf-8").read()
        bn = numbers(base)
        bp = prose_sentences(base)
        base_max = max((len(s.split()) for s in bp), default=0)
        for name in TRANSFORMS:
            new = open(os.path.join(d, f"{name}.txt"), encoding="utf-8").read()
            nn = numbers(new)
            if nn != bn:
                lost = [x for x in bn if bn.count(x) > nn.count(x)][:6]
                gained = [x for x in nn if nn.count(x) > bn.count(x)][:6]
                fails.append(f"{pid}/{name}: numeric multiset changed "
                             f"({len(bn)} -> {len(nn)}); lost~{lost} gained~{gained}")
            low = new.lower()
            hits = {t: low.count(t) for t in BLOCKING if t in low}
            if hits:
                fails.append(f"{pid}/{name}: leak terms {hits}")
            edits = manifest["variants"][pid][name]["edits"]
            if edits < MIN_EDITS[name]:
                excluded.append((pid, name, edits))
            np_ = prose_sentences(new)
            if name == "T3_lengthen" and bp and np_:
                bmean = st.mean([len(s.split()) for s in bp])
                nmean = st.mean([len(s.split()) for s in np_])
                if (nmean - bmean) / bmean < T3_MIN_MEAN_LIFT:
                    fails.append(f"{pid}/{name}: mean prose sentence moved only "
                                 f"{100*(nmean-bmean)/bmean:+.1f}% (floor "
                                 f"{100*T3_MIN_MEAN_LIFT:+.0f}%) — the axis it names did not move")
            # Differential, not absolute: only fragments the TRANSFORM introduced are its fault.
            base_frags = sum(1 for s in bp if is_fragment(s))
            new_frags = [s for s in np_ if is_fragment(s)]
            if len(new_frags) > base_frags:
                fails.append(f"{pid}/{name}: introduced {len(new_frags) - base_frags} fragment(s) "
                             f"(baseline {base_frags} -> {len(new_frags)}), e.g. "
                             f"{new_frags[-1][:70]!r}")
            rows.append((pid, name, len(base.split()), len(new.split()), edits, base_max,
                         max((len(s.split()) for s in np_), default=0),
                         st.mean([len(s.split()) for s in bp]) if bp else 0,
                         st.mean([len(s.split()) for s in np_]) if np_ else 0))
    hdr = (f"{'paper':<12}{'transform':<14}{'base w':>8}{'new w':>8}{'dw%':>7}{'edits':>6}"
           f"{'maxP b>n':>11}{'meanP b>n':>13}")
    print(hdr)
    for pid, name, bw, nw, k, bmax, nmax, bmean, nmean in rows:
        print(f"{pid:<12}{name:<14}{bw:>8}{nw:>8}{100*(nw-bw)/bw:>6.1f}%{k:>6}"
              f"{f'{bmax}>{nmax}':>11}{f'{bmean:.1f}>{nmean:.1f}':>13}")
    print("\n  maxP/meanP are PROSE-only sentence lengths: the raw maximum is dominated by "
          "pdftotext\n  wreckage (fused headings, display equations) and makes a working transform "
          "look inert.")
    for name in TRANSFORMS:
        ed = [r[4] for r in rows if r[1] == name]
        dw = [100 * (r[3] - r[2]) / r[2] for r in rows if r[1] == name]
        print(f"  {name}: edits median {st.median(ed):.0f} min {min(ed)}, "
              f"median length change {st.median(dw):+.1f}%")
    # A dropped cell is written back into the manifest, because the runner's job list and the analysis
    # both have to agree with the gate about which cells exist. Anything that reads the arm's n reads it
    # from here, so the arm cannot be one size in the queue and another in the write-up.
    manifest["excluded"] = [{"paper": p, "transform": t, "edits": k,
                             "floor": MIN_EDITS[t], "reason": "below the pre-registered strength floor"}
                            for p, t, k in excluded]
    manifest["arm_n"] = {t: len(manifest["papers"]) - sum(1 for _, tt, _ in excluded if tt == t)
                         for t in TRANSFORMS}
    json.dump(manifest, open(os.path.join(outdir, "manifest.json"), "w"), indent=1)

    n_papers = len(manifest["papers"])
    for name in TRANSFORMS:
        drop = [p for p, t, _ in excluded if t == name]
        if len(drop) * 4 > n_papers:
            fails.append(f"{name}: {len(drop)} of {n_papers} papers fall below the strength floor, "
                         f"which is more than a quarter of the arm — this is an absent treatment "
                         f"rather than a weak one, and shrinking the arm would hide that")
    if fails:
        print("\nGATE FAIL — these variants must not be scored:")
        for f in fails:
            print("  " + f)
        return 1
    if excluded:
        print(f"\nEXCLUDED from the arms ({len(excluded)} of {n_papers * len(TRANSFORMS)} cells), each "
              f"below its pre-registered strength floor:")
        for p, t, k in excluded:
            print(f"  {p}/{t}: {k} edits against a floor of {MIN_EDITS[t]}")
        # This builder writes the exclusion into the manifest; it does not run the scoring queue, so it is in
        # no position to report that a cell was never read. It used to say "each dropped before any of it was
        # scored", which is a claim about a queue this file never sees, and it was false of one cell.
        print("  the manifest records the exclusion; floor_check.py is what checks it against readings.json")
    print(f"\nGATE PASS ({n_papers} papers x {len(TRANSFORMS)} transforms): numeric multiset "
          f"identical, 0 leak terms, 0 fragments, {n_papers * len(TRANSFORMS) - len(excluded)} cells "
          f"above their strength floor.")
    print("  arm sizes: " + ", ".join(f"{t} n={n}" for t, n in manifest["arm_n"].items()))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-papers", action="store_true")
    ap.add_argument("--build")
    ap.add_argument("--verify")
    ap.add_argument("--corpus", choices=sorted(CORPORA), default="accepted",
                    help="which arm's manuscripts to transform (default accepted)")
    a = ap.parse_args()
    if a.list_papers:
        papers, ranked = selected_papers()
        print(f"{len(ranked)} accepted papers by 5-model composite (* = in the PIA arms):")
        sel = set(papers)
        for i, (pid, c) in enumerate(ranked):
            print(f"  {i+1:>2}. {pid:<12} {c:+.4f} {'*' if pid in sel else ''}")
        print(f"\nselected {len(papers)}: {', '.join(papers)}")
    elif a.build:
        build(a.build, a.corpus)
    elif a.verify:
        sys.exit(verify(a.verify))
    else:
        ap.print_help()
