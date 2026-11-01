#!/usr/bin/env python3
"""Build the release bundle the paper promises, and prove it kept the carve-outs.

The bundle is DERIVED into a staging tree and then swept, rather than assembled by deleting things from a copy
of the working directory. The working directory contains the forum ids of 32 declined ICLR submissions, the
label mapping, 421 MB of their PDFs and their de-identified full texts; a bundle built by subtraction ships
whichever of those the author forgot about, and nothing downstream ever notices.

What the carve-outs cost, and what they do not buy:

  the 32 declined submissions   Labelled R01--R32 in shuffled order, so the label carries no arm. Their
      reviews ship as SCORES ONLY: a review's own summary paraphrases the paper it reviewed, which identifies
      it as surely as a title does. Their PDFs and de-identified texts are not redistributed. Their public
      post-rebuttal ratings ARE released, paired with our composites, because §5's rho is unverifiable
      without them. Those ratings are the venue's own public values, so withholding the mapping keeps this
      paper from naming anyone rather than making anyone anonymous, and the README says which it is.

  our own manuscripts   Absent from every corpus, with no exception, and no review of one ships. Every
      score in the bundle is a score of a third-party ICLR 2026 submission.

  appendix A's two inputs   Its extract measurements compare each corpus paper's submitted document against
      the text the panel was handed, and neither side is redistributable. The derived rows ship instead, in
      data/extract_corpus.json, and reproduce.py re-derives the charge flags of the two populations whose
      reviews ship in full, so the file is checkable rather than merely quoted.

  python3 package_release.py [--tar]

Exit 0 only if every count and every sweep passes. A FAIL here means the bundle must not be published.
"""
from __future__ import annotations

import argparse
import getpass
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

AN = os.path.dirname(os.path.abspath(__file__))
CAL = os.path.join(os.path.dirname(AN), "paper_direction_98_calibration")
REJ = f"{AN}/reject_arm"
STAGE = f"{AN}/release/aina2026_agent_reviewers"
WORKSPACE = os.path.dirname(AN)                       # rewritten out of every staged script
PLACEHOLDER = "/path/to/workspace"

# Who the author is, worked out at run time. Writing the name into the sweep would put in the bundle the
# string the sweep exists to keep out, and would tie a general tool to one person's machine.
HOME = os.path.expanduser("~")
IDENTITY = sorted({getpass.getuser(), os.path.basename(HOME)} - {"", "root"})

# Credentials are recognised by shape, not by name: a script that reads $CURSOR_API_KEY has to say so, and a
# script that contains 40 characters of base64 after "Bearer" has leaked. Values are never printed.
#
# The sk- rule needs a left boundary. Without it, it fires on the "sk-" inside any longer hyphenated word --
# a reviewer proposing a "mask-all-but-X-segment" baseline tripped it, which is a false positive that teaches
# whoever meets it to stop believing the check. A key never begins mid-word, so requiring a non-alphanumeric
# to its left costs nothing real.
CRED_PATTERNS = [rb"(?<![A-Za-z0-9])sk-[A-Za-z0-9_\-]{16,}", rb"Bearer\s+[A-Za-z0-9._\-]{16,}",
                 rb"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[\"\']?[A-Za-z0-9._\-]{16,}"]

# Free-text fields of a review. Kept for published papers and for this one; dropped for the 32 declined
# submissions, because each of them describes its subject closely enough to name it.
FREE_TEXT = ("summary", "strengths", "key_concerns", "questions_for_authors", "calibration_check")

# Sibling project directories, and the two of them the bundle is allowed to name.
#
# The bundle holds ICLR reviews and nothing else. A shipped file that names another project in this workspace
# points the reader at data that is not here, in a paper that never mentions it -- and most of those projects
# are the authors' own manuscripts, which is worse than a dangling reference in an anonymous submission. Two
# siblings are genuine provenance and the scripts have to say so: the calibration field the composite is a
# z-score against, and the directory the eight-slot roster is defined in.
#
# So the rule is an allowlist with a DERIVED complement, not a list of what was excluded. Naming the excluded
# corpora would put in the bundle the strings the rule exists to keep out -- this file ships too, and the first
# version of the check failed on itself for exactly that reason -- and a typed list stops covering the moment a
# new project appears beside this one. Deriving it means a directory is forbidden until it is declared.
PROVENANCE_SIBLINGS = {"paper_direction_98_calibration", "paper_direction_72"}


def forbidden_siblings():
    """-> [(pattern, why)] for every workspace directory that is neither this project nor declared provenance.

    One subtlety: an allowed name may extend a forbidden one, and here one does. The pattern therefore refuses
    the bare name only where it is not the head of an allowed name, or the rule would fire on every legitimate
    mention of the calibration directory."""
    here = os.path.basename(AN)
    sibs = sorted(d for d in os.listdir(WORKSPACE)
                  if os.path.isdir(os.path.join(WORKSPACE, d)) and not d.startswith("."))
    allowed = PROVENANCE_SIBLINGS | {here}
    missing = allowed - set(sibs)
    if missing:                                  # an allowlist naming nothing real is an allowlist of nothing
        raise SystemExit(f"PROVENANCE_SIBLINGS names {sorted(missing)}, which is not beside this project")
    out = []
    for d in sibs:
        if d in allowed:
            continue
        tails = [a[len(d):] for a in allowed if a.startswith(d) and a != d]
        guard = ("(?!" + "|".join(re.escape(t) for t in tails) + ")") if tails else ""
        out.append(((re.escape(d) + guard).encode(),
                    "a workspace directory that is neither this project nor declared provenance"))
    return out

MANUSCRIPT_MD = ("DRAFT.md", "APPENDIX.md")     # the paper's own source, which is the document the reader has


def working_records():
    """-> [pattern] for every markdown record of this project that the bundle does not contain.

    The scripts were written next to a set of working documents -- the plan a run was blocked on, the audit that
    settled a confound, the record a decision rule was fixed in -- and their comments cited them by filename, the
    way one cites a file one can open. A reader of the release cannot open any of them, so the citation resolves
    nowhere and the comment reads as a note to the authors rather than as an account of the run. The fix is in the
    comment, not here: state the measurement or the rule, which is the part the citation was standing in for.

    Derived the same way as forbidden_siblings(), and for the same reason: this file ships, so a typed list of the
    documents to keep out would ship their names. The allowlist is the manuscript source, whose own name is not a
    working note, and the complement is whatever else is beside this script and did not make it into the tree.
    """
    here = {os.path.basename(p) for p in glob.glob(f"{STAGE}/**/*.md", recursive=True)}
    return [re.escape(os.path.basename(p).encode()) for p in sorted(glob.glob(f"{AN}/*.md"))
            if os.path.basename(p) not in MANUSCRIPT_MD and os.path.basename(p) not in here]


fails: list[str] = []


def check(ok, label, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}{'  -- ' + str(detail) if detail and not ok else ''}")
    if not ok:
        fails.append(label)
    return ok


def redact_script(text):
    """A released script must not carry the author's home directory. It carries a placeholder instead, which
    the README tells the reader to set -- a path that has to be edited is better than a path that identifies."""
    return text.replace(WORKSPACE, PLACEHOLDER).replace(HOME, PLACEHOLDER)


def relabel(text, labels):
    """Rewrite an analysis output keyed by OpenReview forum id into one keyed by the released label, and drop
    every title. These two files are why the sweep exists: analysis_results.json paired our composites with
    the forum ids, which is the withheld mapping, published."""
    for forum, label in labels.items():
        text = text.replace(forum, label)
    obj = json.loads(text)

    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in ("title", "titles", "forum_url", "url")}
        return [strip(v) for v in o] if isinstance(o, list) else o
    return json.dumps(strip(obj), indent=1)


def unresolved_paper_paths():
    """-> the paths the paper names in `code spans` that a reader cannot find in the staged bundle.

    The paper tells the reader where to look, and a reader who looks is following a string. Those strings were
    written next to the working tree, so two of them named a working directory that the staging step renames on
    its way into the release, and nothing noticed: reproduce.py exercises the paths the *scripts* use, not the
    paths the *prose* promises. A token with a slash has to match a real bundle path; a bare filename resolves
    anywhere in the tree, since that is how the README tells the reader to read one.
    """
    here = {os.path.relpath(os.path.join(r, f), STAGE)
            for r, _, fs in os.walk(STAGE) for f in fs}
    here |= {os.path.relpath(os.path.join(r, d), STAGE)
             for r, ds, _ in os.walk(STAGE) for d in ds}
    named, bad = set(), []
    for src in (f"{AN}/DRAFT.md", f"{AN}/APPENDIX.md"):
        for m in re.finditer(r"`([^`]+)`", open(src, encoding="utf-8").read()):
            t = m.group(1).strip()
            if re.match(r"https?://", t):
                continue
            if "/" in t or re.search(r"\.(py|sh|json|jsonl|txt|csv|md)$", t):
                named.add(t)
    for t in sorted(named):
        s = t.strip("/")
        if s in here or glob.glob(f"{STAGE}/{s}"):
            continue
        if "/" not in s and any(os.path.basename(h) == s for h in here):
            continue
        bad.append(t)
    return len(named), bad


def stale_schema_fields(schema):
    """-> the schema's annotation fields that still describe the corpus it was first written for.

    The schema is the downstream validator, not the prompt: `instrument/run_iso.sh` never interpolates it, so
    none of these strings was shown to a reviewer, and `instrument/reviewer_prompt_iclr.md` is what was. But
    two of them describe fields the paper uses, and they describe them against a journal's bar rather than the
    conference the prompt names, so a reader checking what a scored quantity meant finds the wrong venue in the
    file that looks most authoritative.

    They are reported rather than rewritten, and the line between the two is worth stating because this file
    does both. A `$id` is a LOCATOR: its only job is to resolve, it cannot mislead anyone about what was
    measured, and left alone it is a URI into a directory the bundle does not contain, so it is repointed. A
    `description` is a STATEMENT about what a field means, and rewriting the instrument's own account of itself
    -- in a paper about what instruments do -- would substitute the packager's words for the artifact's. So the
    statements ship exactly as they were used, and the README says which ones are stale and what overrides them.
    """
    OTHER_VENUE = re.compile(r"\bNMI\b")
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("title", "description") and isinstance(v, str) and OTHER_VENUE.search(v):
                    out.append("/".join(path + [k]) if path else k)
                else:
                    walk(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [str(i)])
    walk(schema, [])
    return out


def stale_fields_phrase(stale):
    """The one rendering of that list, so the README and the check that reads it back cannot differ."""
    return "`, `".join(stale)


SRC_OF = {}     # shipped panel directory -> the source panel directory it was copied from


def put(src, dst_rel, transform=None):
    """Copy one file into the staging tree, optionally rewriting it. -> True if it landed."""
    if not os.path.exists(src):
        return False
    dst = f"{STAGE}/{dst_rel}"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if transform is None:
        shutil.copy2(src, dst)
    else:
        open(dst, "w", encoding="utf-8").write(transform(open(src, encoding="utf-8").read()))
        shutil.copystat(src, dst)     # a rewritten review keeps the day it was scored on
    if re.search(r"/panel\d+/[RC]\d\.json$", dst_rel):
        SRC_OF[os.path.dirname(dst_rel)] = os.path.dirname(src)
    return True


def scores_only(text):
    """A review reduced to what the analysis uses: every number, no prose."""
    r = json.loads(text)
    out = {k: v for k, v in r.items() if k not in FREE_TEXT and k != "metrics"}
    out["metrics"] = {m: {"score": v["score"]} for m, v in r.get("metrics", {}).items()}
    out["_redacted"] = ("free text and per-metric justifications withheld: a review paraphrases its subject. "
                        "Every number this paper reports is computed from the fields above.")
    return json.dumps(out, indent=1)


def paper_title():
    """-> the submitted title, read from the file the panel's extract opens with.

    Typed here once, and it went stale the day the paper was retitled: the bundle introduced itself as
    artifacts for a paper of a title that no longer existed, while every count in the same file was derived
    and correct. So the title is derived too, from the one place it is defined."""
    m = re.search(r"\\title\{(.+?)\}", open(f"{AN}/paper/main.tex", encoding="utf-8").read(), re.S)
    if not m:
        return None
    # LaTeX escapes and line breaks are the author's, not the reader's.
    return re.sub(r"\s+", " ", m.group(1).replace("\\\\", " ").replace("\\", "")).strip()


def readme(n, n_pub, n_dec, title, stale):
    """The bundle's front door. Written here rather than kept as a static file so the counts it quotes are the
    counts of the tree that shipped, and cannot drift away from it."""
    stale_fields = stale_fields_phrase(stale)
    t = f"""# {title} -- release bundle

Artifacts for the paper of that title by Jiecheng Lu and Shihao Yang (Georgia Institute of Technology), presented
at the NeurIPS 2026 workshop AI-Native Academia: Authorship, Peer Review, and Conference Governance under AI.
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
                                    arXiv ids of the {n_pub} published papers they were fitted on
    reviews/accepted/               {n['accepted']} reviews of those {n_pub} published papers, in full
    reviews/rejected/               {n['rejected']} reviews of {n_dec} rejected submissions, R01--R32, SCORES ONLY (see below):
                                    their two untouched panels, which are also the baselines that
                                    reviews/transform_rejected/ holds for the same papers
    reviews/transform/              {n['transform']} reviews of the presentation-transform variants
    reviews/transform_rejected/     {n['transform_rejected']} reviews of the same transforms applied to the rejected
                                    submissions, R01--R32, SCORES ONLY -- each paper's variants and its two
                                    baseline panels in one sitting, with the paper order shuffled
    reviews/drift_5model/           {n['drift5']} five-model reviews inside the variants' own sitting: every
                                    baseline text four times and each variant once, so the transform contrast
                                    can be taken with no session boundary in it rather than corrected for one
    reviews/dayrep_5model/          {n['dayrep']} five-model reviews of eight accepted papers in a second sitting,
                                    two baseline panels and one panel each of T1 and T3 -- the arm that tells
                                    a paper set apart from a sitting
    reviews/vendor_panel/           {n['vendor']} reviews of the same {n_pub} papers by a second roster: eight slots,
                                    six vendors, its own calibration
    reviews/vendor_transform/       {n['vendor_transform']} second-roster reviews of the same transform variants
    reviews/vendor_drift/           {n['vendor_drift']} second-roster reviews of UNTOUCHED text, scored in the variant
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

**The {n_dec} rejected submissions.** They are third-party manuscripts whose authors did not publish them, so they
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
{n_pub} published papers or one of the {n_dec} declined ones. Nothing here is scored to make a point about the
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

*{len(stale)} annotation fields of `instrument/metrics_schema.json`.* The schema is shared with a study of
journal articles, so {len(stale)} of its `title` and `description` strings describe that corpus and its task
numbering: `{stale_fields}`. Two of them matter to a reader,
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
"""
    open(f"{STAGE}/README.md", "w").write(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tar", action="store_true", help="also write release/<name>.tar.gz")
    a = ap.parse_args()

    labels = json.load(open(f"{REJ}/public_labels.json"))          # read to FORBID, never to copy
    deid_ix = json.load(open(f"{REJ}/deid_index.json"))
    calib = json.load(open(f"{CAL}/ICLR/calibration_params_portable.json"))
    accepted_ids = sorted(calib["per_paper_composite"])
    forums = sorted(labels)

    # Titles of the 32, so the sweep can forbid them. Whichever file has them, we only ever read.
    titles = {}
    for src in (f"{REJ}/iclr2026_interp_pool.json", f"{REJ}/sample_preregistered.json"):
        if not os.path.exists(src):
            continue
        blob = json.load(open(src))
        rows = blob if isinstance(blob, list) else sum((v for v in blob.values() if isinstance(v, list)), [])
        for r in rows:
            if isinstance(r, dict) and r.get("forum") in labels and r.get("title"):
                titles[r["forum"]] = r["title"]
    print(f"{len(forums)} declined submissions, {len(titles)} titles known to the sweep, "
          f"{len(accepted_ids)} published papers")

    if os.path.exists(STAGE):
        shutil.rmtree(STAGE)
    os.makedirs(STAGE)

    n = dict(accepted=0, rejected=0, transform=0, transform_rejected=0, vendor=0, vendor_transform=0,
             vendor_drift=0,
             drift5=0, dayrep=0, scripts=0, data=0)

    print("\ninstrument")
    for f in ("reviewer_prompt_iclr.md", "metrics_schema.json", "parse_review.py", "run_iso.sh",
              "score_against_gate.py"):
        check(put(f"{CAL}/ICLR/{f}", f"instrument/{f}",
                  transform=redact_script if f.endswith((".py", ".sh")) else None), f"instrument/{f}")
    # The schema's $id was a URI under the dropped venue's corpus directory, where the schema was first
    # written. It is an identifier and not a constraint, so repointing it at the file's own place in the
    # bundle changes nothing a validator does -- which is asserted below rather than assumed, by comparing
    # every other key against the source. A schema that identifies itself by a corpus the reader cannot see
    # is a dangling reference wearing a URL.
    sch_src = json.load(open(f"{CAL}/ICLR/metrics_schema.json"))
    sch = dict(sch_src, **{"$id": "metrics_schema.json"})
    check({k: v for k, v in sch.items() if k != "$id"} == {k: v for k, v in sch_src.items() if k != "$id"},
          "the metric schema ships unchanged apart from its $id")
    json.dump(sch, open(f"{STAGE}/instrument/metrics_schema.json", "w"), indent=1)
    # The slot specification is the identity of the panel, effort tier included: a release that says
    # "GPT-5.5" has not said which reviewer ran.
    slots = [dict(slot="R1", runner="codex", model="gpt-5.5", effort="xhigh"),
             dict(slot="R2", runner="codex", model="gpt-5.4", effort="xhigh"),
             dict(slot="R3", runner="claude", model="us.anthropic.claude-opus-4-8[1m]", effort="default"),
             dict(slot="R4", runner="claude", model="us.anthropic.claude-opus-4-7[1m]", effort="default"),
             dict(slot="R5", runner="claude", model="us.anthropic.claude-sonnet-4-6[1m]", effort="default")]
    json.dump(dict(note="Effort tier is part of a slot's identity; re-calibrate if any field changes.",
                   slots=slots), open(f"{STAGE}/instrument/slots.json", "w"), indent=1)
    # The second roster, read out of the run's own verification file rather than retyped, so the released
    # spec cannot disagree with the models that answered. Six vendors is the whole point of the arm, so the
    # vendor is part of the spec and not an inference from the model name.
    VENDOR = {"C1": "openai", "C2": "xai", "C3": "moonshot", "C4": "google",
              "C5": "zhipu", "C6": "openai", "C7": "openai", "C8": "anthropic"}
    c8 = []
    for ln in open(f"{AN}/n0_cursor8_iclr/model_verification.txt"):
        m = re.match(r"\s*OK\s+(C\d)\s+(\S+)\s+(.*\S)\s*$", ln)
        if m:
            c8.append(dict(slot=m.group(1), runner="cursor", model=m.group(2), display=m.group(3),
                           vendor=VENDOR[m.group(1)]))
    check(len(c8) == 8, "the eight-slot roster spec, read from the run's verification file", len(c8))
    json.dump(dict(note="Read from n0's model_verification.txt at packaging time. Three slots are the same "
                        "vendor at different sizes, on purpose: it is what makes the vendor share of the "
                        "reviewer variance estimable.", slots=c8),
              open(f"{STAGE}/instrument/slots_cursor8.json", "w"), indent=1)

    print("\ncalibration")
    check(put(f"{CAL}/ICLR/calibration_params_portable.json", "calibration/calibration_params_portable.json"),
          "calibration parameters")
    # A second roster needs its own mu/sd. Borrowing the five-model parameters would z-score eight slots
    # against five other slots' means, which is the same error as borrowing a noise band.
    check(put(f"{AN}/n0_cursor8_iclr/calibration_params_cursor8_iclr.json",
              "calibration/calibration_params_cursor8.json"), "eight-slot calibration parameters")
    check(put(f"{CAL}/compute_calibration.py", "scripts/compute_calibration.py",
              transform=redact_script), "compute_calibration.py")
    open(f"{STAGE}/calibration/papers.txt", "w").write(
        "The 16 accepted ICLR 2026 papers mu/sd and the gate are fitted on, as arXiv ids.\n"
        "Preprint-stage text, fetched from arXiv, de-identified by scripts/deid_conference.py.\n\n"
        + "\n".join(accepted_ids) + "\n")

    print("\nreviews")
    for pid in accepted_ids:
        for f in sorted(glob.glob(f"{CAL}/reviews/{pid}/panel*/R?.json")):
            if os.path.getsize(f) > 2:
                n["accepted"] += put(f, f"reviews/accepted/{pid}/" + "/".join(f.split("/")[-2:]))
    for forum, label in labels.items():
        for f in sorted(glob.glob(f"{REJ}/reviews/*_{forum}/panel*/R?.json")):
            if os.path.getsize(f) > 2:
                n["rejected"] += put(f, f"reviews/rejected/{label}/" + "/".join(f.split("/")[-2:]),
                                     transform=scores_only)
    for f in sorted(glob.glob(f"{AN}/n1_pia_5model/reviews/*__*/panel*/R?.json")):
        if os.path.getsize(f) > 2:
            pid, variant = f.split("/")[-3].split("__", 1)   # "<arxiv id>__<variant>" is one directory
            n["transform"] += put(f, f"reviews/transform/{pid}/{variant}/" + "/".join(f.split("/")[-2:]))
    # The five-model roster's OWN drift control (N1b): on all 16 accepted papers, four panels of byte-identical
    # baseline text and one panel of each variant, in one shuffled queue inside the variants' own sitting. It
    # ships beside the arm it corrects because it is what lets every contrast in the section be taken with no
    # session boundary inside it, rather than corrected for one afterwards.
    for f in sorted(glob.glob(f"{AN}/n1b_drift_5model/reviews/*/*/panel*/R?.json")):
        if os.path.getsize(f) > 2:
            n["drift5"] += put(f, "reviews/drift_5model/" + "/".join(f.split("/")[-4:]))
    # The replication (N1d): the eight papers the figure arm's whole effect sits in, re-scored a day later --
    # two baseline panels and one panel each of T1 and T3. This is the arm that separates a paper set from a
    # sitting, so it ships whole: the two readings of the same eight papers are the comparison, and a reader
    # who has only one of them cannot make it.
    for f in sorted(glob.glob(f"{AN}/n1d_dayrep_5model/reviews/*/*/panel*/R?.json")):
        if os.path.getsize(f) > 2:
            n["dayrep"] += put(f, "reviews/dayrep_5model/" + "/".join(f.split("/")[-4:]))
    # The same three transforms on the declined submissions, keyed by released label. SCORES ONLY, and for a
    # different reason from the arms above: those arms review published manuscripts, so a review that
    # paraphrases one reveals nothing that is not already public. These review third-party submissions that
    # were not accepted anywhere. Withholding the texts does nothing if a review of the text ships whole, and
    # the filename rule that keeps manuscripts out of the bundle cannot see prose inside a review.
    for f in sorted(glob.glob(f"{AN}/n1c_reject_5model/reviews/*/*/panel*/R?.json")):
        if os.path.getsize(f) > 2:
            n["transform_rejected"] += put(f, "reviews/transform_rejected/" + "/".join(f.split("/")[-4:]),
                                           transform=scores_only)
    # The second roster, on the same 16 published papers and the same three transforms. Full text kept, as
    # for the accepted arm: these are published manuscripts, so a review that paraphrases one identifies
    # nothing that is not already public.
    for f in sorted(glob.glob(f"{AN}/n0_cursor8_iclr/reviews/*/panel*/C?.json")):
        if os.path.getsize(f) > 2:
            n["vendor"] += put(f, "reviews/vendor_panel/" + "/".join(f.split("/")[-3:]))
    for f in sorted(glob.glob(f"{AN}/n2_pia_cursor8/reviews/*/*/panel*/C?.json")):
        if os.path.getsize(f) > 2:
            n["vendor_transform"] += put(f, "reviews/vendor_transform/" + "/".join(f.split("/")[-4:]))
    # The drift control: the SAME baseline text, re-scored in the variant sessions. It is what separates
    # "the edit did it" from "the later session did it", so it ships beside the arm it corrects.
    for f in sorted(glob.glob(f"{AN}/n3_drift_cursor8/reviews/*/panel*/C?.json")):
        if os.path.getsize(f) > 2:
            n["vendor_drift"] += put(f, "reviews/vendor_drift/" + "/".join(f.split("/")[-3:]))
    # No reviews of this paper ship, and none are scored. An instrument demonstrated on its own submission
    # measures one document with no control, and the appendix that used to report it has been rewritten around
    # the forty-eight corpus papers, which have both. What replaced the release of those reviews is the release
    # of the rows behind the corpus measurement: data/extract_corpus.json, staged below.
    check(n["accepted"] == 160, "160 reviews of published papers", n["accepted"])
    check(n["rejected"] == 320, "320 reviews of declined submissions (scores only)", n["rejected"])
    check(n["transform"] == 470, "470 reviews of transformed published papers", n["transform"])
    check(n["transform_rejected"] == 790, "790 reviews of transformed declined submissions (scores only)",
          n["transform_rejected"])
    check(n["drift5"] == 555, "555 five-model reviews inside the variants' own sitting: every baseline text "
          "four times and each variant once", n["drift5"])
    check(n["dayrep"] == 160, "160 five-model reviews of the eight papers, re-scored one day later",
          n["dayrep"])
    check(n["vendor"] == 256, "256 reviews from the eight-slot roster", n["vendor"])
    check(n["vendor_transform"] == 192, "192 eight-slot reviews of the transform variants",
          n["vendor_transform"])
    check(n["vendor_drift"] == 64, "64 eight-slot reviews of untouched text (the drift control)",
          n["vendor_drift"])

    print("\ndata and scripts")
    os.makedirs(f"{STAGE}/data", exist_ok=True)
    # The day each shipped panel was scored on. Every contrast in the presentation study holds the day fixed,
    # because reading an untouched manuscript in a different sitting carries an offset large enough to swamp an
    # edit -- so the day is not bookkeeping here, it is the selection rule the result rests on. And it lives
    # nowhere inside a review: it is the mode of the panel's own file times in the tree the analysis ran on.
    # Timestamps survive tar and do not survive much else, so the rule ships as data as well, derived by the
    # same function the analysis calls, and reproduce.py reads this file rather than trusting the transport.
    sys.path.insert(0, AN)
    import readings                                                        # noqa: E402  (path set above)
    days = {d: readings.panel_day(s) for d, s in sorted(SRC_OF.items())}
    json.dump(dict(note="The calendar day each panel of reviews was scored, as the mode of that panel's own "
                        "file modification times in the tree the analysis ran on. It is a property of the run "
                        "and not of the review text, so it cannot be recovered from the JSON. Every contrast "
                        "in the presentation study is taken inside one day; reproduce.py reads this file to "
                        "rebuild that pairing, and checks it against the file times wherever those survived "
                        "transport.",
                   panels=days),
              open(f"{STAGE}/data/panel_days.json", "w"), indent=1)
    print(f"    data/panel_days.json           {len(days)} panels, "
          f"{len(set(days.values()))} distinct days")
    # The paired numbers that make §5 checkable: our composite beside the venue's own rating, by label.
    pairs = {labels[f]: dict(rating_mean=v["rating_mean"], arm=v["arm"], deid_words=v["deid_words"])
             for f, v in deid_ix.items()}
    json.dump(dict(note="Public post-rebuttal rating means of the 32 declined submissions, by released label. "
                        "The label->submission mapping is withheld (see README). Ratings are public at the "
                        "venue, so re-identification is possible for a determined reader.",
                   papers=dict(sorted(pairs.items()))),
              open(f"{STAGE}/data/rejected_arm_ratings.json", "w"), indent=1)
    # The population those 32 were drawn out of, as ratings and nothing else. Appendix C states the pool size,
    # both eligibility counts and what an extremes draw would have separated by, and every one of those is a
    # property of this bag of numbers, so without it the appendix has six figures the bundle cannot settle.
    #
    # Sorted and stripped of identifiers, which is not decoration. A rating carries no identity on its own; a
    # rating beside a forum id would hand a reader the pool, and the pool plus the selection rule is the label
    # mapping this release withholds. So the ids are dropped here rather than in a later sweep, and the sort
    # destroys the file order that would otherwise pair the two lists up positionally.
    #
    # Of the selection parameters, the draw's two targets and its tie-break stay out of the bundle, since they
    # are the step from the two eligible sets to the drawn 32; the sweep below is what enforces that, and they
    # shipped as unused literals in reproduce.py until it went in. The eligibility cut-offs are the exception
    # and are in reproduce.py, because two released counts are what they select, so a reader who wants a cut-off
    # reads it off this distribution and the count the appendix prints beside it. None of this is what makes the
    # labels weak, and the README says what does.
    pool = sorted(v["rating_mean"] for v in json.load(open(f"{REJ}/iclr2026_interp_reviews.json")).values()
                  if ("Rejected_Submission" in v["venueid"] or v["decision"].startswith("Reject"))
                  and v["nrev"] >= 3)
    check(len(pool) == 250, "250 ratings in the pool the ranking sample was drawn from", len(pool))
    json.dump(dict(note="Public post-rebuttal mean ratings of the 250 declined ICLR 2026 submissions in the "
                        "sampled primary area carrying at least three reviews: the population the 32 of "
                        "data/rejected_arm_ratings.json were drawn from. Ratings only, sorted, with no "
                        "identifiers. The draw's two targets and its tie-break are not released, so the draw "
                        "cannot be repeated from this file. See README.",
                   n=len(pool), rating_means=pool),
              open(f"{STAGE}/data/pool_rating_distribution.json", "w"), indent=1)
    n["data"] += 1
    # inventory.json and inventory_experiments.py used to ship here and no longer do. They are the working
    # tree's corpus census, and a census of the working tree is not a census of the bundle: they enumerated
    # 481 ICLR reviews where the paper reports 1,392, omitted all four of the runs that supply the difference,
    # and gave rows to a dropped venue and to the authors' other manuscripts, none of whose data is here.
    # Nothing in the paper or the README named either file. What they were for, the README does properly: its
    # per-directory counts are derived from the staged tree, so they cannot say a number the bundle does not
    # contain. forbidden_siblings() is the gate that keeps this from coming back by another route.
    # pooled_analysis.json is section 6's own output and the input both of its figures read, so it ships with
    # the three files it was built from: readings.json, the per-panel table the contrast is taken over, which
    # is the level at which a reader can disagree with the day rule rather than with a summary of it;
    # sitting_check.json, which fixes the two accepted halves; and dayrep_analysis.json, the replication.
    for f in ("yardsticks.json", "reliability.json", "confounds.json", "consensus_bars.json",
              # The three readings of the same grades, which section 5's table and F2(b) both take their
              # numbers from rather than recomputing: the composite, the coded level averaged, and the share
              # at the bar. It ships beside grade_table.json because the two answer different questions of
              # one column -- what the level is, and what its order is worth.
              "grade_table.json", "grade_order.json", "n1_results.json", "number_guard.json",
              "strength_response.json", "n1b_results.json", "paired_noise.json",
              "pia_null.json", "pooled_analysis.json", "readings.json", "sitting_check.json",
              "dayrep_analysis.json", "sample_scope.json",
              # Appendix A's own input, and the only file in this list whose sources are withheld rather than
              # simply large: see the README's second carve-out. The two summaries beside it are what appendix
              # A's figure is drawn from, so a bundle without them ships a figure script that cannot redraw its
              # own figure. Both are derived rows: the declined submissions appear in them by release label
              # only, and the review text either carries is a review of one of the published papers, which
              # ships in full in reviews/ regardless.
              # Appendix E's floor check. It carries no paper identifier by construction -- a cell appears in
              # it as a tree, a transform and an edit count -- because the two cells it reports as withheld
              # are declined submissions, and a below-floor dose is a fact about someone else's paper.
              "floor_check.json",
              "extract_corpus.json", "extract_charge_corpus.json", "extract_cost.json"):
        n["data"] += put(f"{AN}/{f}", f"data/{f}")
    ec = json.load(open(f"{STAGE}/data/extract_corpus.json"))
    check(sum(len(v) for v in ec["documents"].values()) == 48
          and sum(len(v["reviews"]) for v in ec["populations"].values()) == 896,
          "extract_corpus.json: 48 documents and 896 untouched reviews",
          f"{sum(len(v) for v in ec['documents'].values())} documents, "
          f"{sum(len(v['reviews']) for v in ec['populations'].values())} reviews")
    for src, dst in (("n0_cursor8_iclr/n0_analysis.json", "n0_analysis.json"),
                     ("n0_cursor8_iclr/roster_swap.json", "roster_swap.json"),
                     ("n0_cursor8_iclr/cross_panel.json", "cross_panel.json"),
                     ("n2_pia_cursor8/n2_analysis.json", "n2_analysis.json")):
        n["data"] += put(f"{AN}/{src}", f"data/{dst}")
    # Counts only, no text: the per-paper word and edit counts the transform script recorded. Appendix E's
    # dose figures and the strength-response correlation are unverifiable without them, and they carry
    # nothing a reader could not recount from the arXiv source themselves. Both arms, because the dose the
    # appendix reads out is over the pooled roster: shipping one of the two makes two thirds of it unverifiable.
    # The declined arm's manifest is keyed by release label and names no submission, so it ships as it stands.
    n["data"] += put(f"{AN}/pia_variants/manifest.json", "data/pia_manifest.json")
    n["data"] += put(f"{AN}/pia_variants_reject/manifest.json", "data/pia_manifest_declined.json",
                     transform=lambda t: relabel(t, labels))
    # Output-token counts per review, derived from the run metadata rather than shipping it: the metadata
    # files also carry a per-call session id, which is of no use to a reader and is not ours to publish.
    usage: dict[str, dict[str, int]] = {}
    for f in sorted(glob.glob(f"{AN}/n0_cursor8_iclr/reviews/*/panel*/C?.out.meta.json")):
        meta = json.load(open(f))
        tok = (meta.get("usage") or {}).get("outputTokens")
        if tok:
            usage.setdefault(meta.get("slot") or os.path.basename(f)[:2], {})[
                "/".join(f.split("/")[-3:-1])] = tok
    json.dump(dict(note="Output tokens per eight-slot review, by slot then paper/panel. Appendix H reports "
                        "the per-slot median and its rank correlation with severity.",
                   output_tokens=dict(sorted(usage.items()))),
              open(f"{STAGE}/data/vendor_panel_usage.json", "w"), indent=1)
    check(sum(len(v) for v in usage.values()) == 256, "output-token counts for all 256 eight-slot reviews",
          sum(len(v) for v in usage.values()))
    for f in ("accepted_arm_human_ratings.json", "criterion_validity_accepted_arm.json",
              "variance_decomp.json", "arm_area_quota.json"):
        n["data"] += put(f"{REJ}/{f}", f"data/{f}")
    # Keyed by forum id at rest, so they are rewritten rather than copied.
    for f in ("leak_report.json", "analysis_results.json"):
        n["data"] += put(f"{REJ}/{f}", f"data/{f}", transform=lambda t: relabel(t, labels))
    put(f"{REJ}/iclr2026_frame.json", "frame/iclr2026_frame.json")
    check(os.path.exists(f"{STAGE}/frame/iclr2026_frame.json"), "the 19,814-submission ICLR 2026 frame")
    for f in ("yardsticks.py", "reliability.py", "confounds.py", "consensus_bars.py", "grade_table.py",
              # Writes grade_order.json from the released reviews and the released calibration parameters, so
              # a reader who doubts that the grade orders these papers as well as the composite can run the
              # comparison in the bundle rather than take the table's word for it.
              "grade_order.py",
              "analyse_n1.py", "pia_transforms.py", "audit_t3_captions.py", "pia_null.py", "channel_table.py",
              "pooled_analyze.py", "dayrep_analyze.py",
              # The pre-registered strength floor, checked against what was scored rather than against what
              # the builder recorded. It imports the floor and the null from pia_null.py and pia_transforms.py
              # above rather than restating either, so the two readings it prints differ in their paper set
              # and in nothing else.
              "floor_check.py",
              # fig0.py draws the paper's opening figure and figstyle.py is imported by all five, so a
              # bundle without them cannot redraw a figure the manifest says it can. sample_scope.py is the
              # arithmetic behind what each arm resolves.
              "fig0.py", "fig1.py", "fig2.py", "fig3.py", "figstyle.py", "sample_scope.py",
              "fig4.py", "fig5.py", "fig6.py", "fig7.py", "fig8.py", "md2tex.py", "number_guard.py",
              "make_bib.py",
              "audit_submission.py",
              "package_release.py", "run_n1.sh", "run_n0.sh",
              "n0_analyze.py", "n2_analyze.py", "strength_response.py", "run_n2.sh",
              "run_n3.sh", "run_n1b.sh", "n1b_analyze.py", "paired_noise.py",
              # The four that measure appendix A's extract, and the fifth that assembles the one file they
              # produce for the release. None of them runs from inside the bundle: their inputs are the
              # submitted documents and the supplied texts, which are the two things it cannot carry. They
              # ship as the account of how data/extract_corpus.json was derived, and reproduce.py is where
              # the numbers are recomputed from it.
              "extract_fidelity_corpus.py", "extract_charge_corpus.py", "extract_link.py",
              "extract_cost.py", "extract_bundle.py"):
        n["scripts"] += put(f"{AN}/{f}", f"scripts/{f}", transform=redact_script)
    for f in ("deid_iclr_submission.py", "build_frame.py", "build_deid.py", "fetch_reviews.py", "analyze.py"):
        n["scripts"] += put(f"{REJ}/{f}", f"scripts/{f}", transform=redact_script)
    # Every analysis output a shipped figure or table script names has to be in the tree, because that is what
    # data/ is described as in the README: the outputs the paper's figures and tables were built from. It went
    # wrong the moment the newest analysis landed. fig4.py and channel_table.py read pia_null.json; the figure
    # was in the manifest, its input and the script that writes it were not, and nothing here noticed, because
    # reproduce.py carries its own implementation of that test and never opens the file. Matched on basenames,
    # since two are staged under a shorter one, and the alias says which.
    ALIAS = {"manifest.json": "pia_manifest.json"}
    staged = {os.path.basename(p) for p in glob.glob(f"{STAGE}/**/*.json", recursive=True)}
    for f in ("fig0.py", "fig1.py", "fig2.py", "fig3.py", "fig4.py", "fig5.py", "fig6.py", "fig7.py",
              "fig8.py", "channel_table.py", "grade_table.py", "sample_scope.py", "floor_check.py"):
        want = {ALIAS.get(j, j) for j in
                re.findall(r"([A-Za-z0-9_]+\.json)", open(f"{AN}/{f}", encoding="utf-8").read())}
        check(want <= staged, f"the inputs {f} names are in the bundle", f"missing {sorted(want - staged)}")
    n["scripts"] += put(f"{CAL}/deid_conference.py", "scripts/deid_conference.py", transform=redact_script)
    for f in ("n0_run.log", "n1_run.log", "n2_run.log"):
        put(f"{AN}/{f}", f"logs/{f}", transform=redact_script)
    put(f"{AN}/n3_drift_cursor8/n3.log", "logs/n3_run.log", transform=redact_script)
    put(f"{AN}/n1b_drift_5model/n1b.log", "logs/n1b_run.log", transform=redact_script)
    put(f"{AN}/n1b_drift_5model/jobs.txt", "logs/n1b_queue.txt")
    check(n["scripts"] >= 30, "analysis, figure, transform and audit scripts", n["scripts"])
    check(n["data"] >= 17, "analysis outputs", n["data"])

    # SOURCES.md: the recipe, not the text. Regenerating from arXiv reproduces the exact bytes, which a copy
    # of someone else's paper would not have licensed us to ship anyway.
    lines = ["# Where the texts come from", "",
             "No third-party manuscript text is redistributed here. Every text this study scored is",
             "regenerable, and the checksum below is what a regeneration must match byte for byte.", "",
             "## Published papers (16 calibration, all of which carry the transforms)", "",
             "arXiv ids are in `calibration/papers.txt`. `scripts/deid_conference.py` produces the scored",
             "text from the arXiv PDF; `scripts/pia_transforms.py` produces the three variants from that.", ""]
    for pid in sorted({os.path.basename(d) for d in glob.glob(f"{AN}/pia_variants/*") if os.path.isdir(d)}):
        for v in sorted(glob.glob(f"{AN}/pia_variants/{pid}/*.txt")):
            h = hashlib.sha256(open(v, "rb").read()).hexdigest()[:16]
            lines.append(f"    {pid}  {os.path.basename(v):<20} sha256:{h}  {len(open(v).read().split()):>5} words")
    lines += ["", "## Declined submissions (R01--R32)", "",
              "Not regenerable from here by design: the ids are withheld. `scripts/deid_iclr_submission.py` is",
              "the pipeline, and `data/rejected_arm_ratings.json` carries the public ratings by label so that",
              "the ranking result can be recomputed without the texts.", "",
              "These 32 also carry the three transforms, built by the same `scripts/pia_transforms.py` run",
              "with `--corpus rejected`, which keys its output by the same released labels. Their texts are",
              "withheld on the same ground as the baselines they are built from, and no checksum of them is",
              "printed here: a checksum a reader cannot recompute establishes nothing, and the labels are the",
              "only identifiers the arm uses anywhere.", ""]
    open(f"{STAGE}/SOURCES.md", "w").write("\n".join(lines) + "\n")

    # reproduce.py sits at the root, not in scripts/: it is the one file that reads THIS tree rather than the
    # working directory the analysis ran in, and it is what makes the release checkable instead of merely large.
    put(f"{AN}/reproduce.py", "reproduce.py", transform=redact_script)
    title = paper_title()
    check(bool(title), "the submitted title, read from paper/main.tex")
    stale = stale_schema_fields(json.load(open(f"{STAGE}/instrument/metrics_schema.json")))
    readme(n, len(accepted_ids), len(forums), title, stale)
    check(f"`{stale_fields_phrase(stale)}`" in open(f"{STAGE}/README.md", encoding="utf-8").read(),
          f"the README names all {len(stale)} stale schema annotations",
          "stale_schema_fields() and the README disagree about which fields carry the earlier venue")
    # The note above is only worth reading if the schema really is downstream of the prompt, so that is
    # measured and not asserted: a run script that concatenated the schema into a prompt would have put those
    # annotations in front of a reviewer, and the note would be the opposite of a disclosure.
    upstream = [os.path.basename(p) for p in sorted(glob.glob(f"{STAGE}/scripts/run_*.sh"))
                + [f"{STAGE}/instrument/run_iso.sh"]
                if "metrics_schema" in open(p, encoding="utf-8", errors="ignore").read()]
    check(not upstream, "the schema is downstream of the prompt: no run script reads it", upstream)
    check(title and open(f"{STAGE}/README.md", encoding="utf-8").readline().startswith(f"# {title} "),
          "the bundle introduces itself by the title the paper carries",
          f"README.md opens on something other than {title!r}")

    print("\nsweep of the staged tree")
    staged = sorted(p for p in glob.glob(f"{STAGE}/**/*", recursive=True) if os.path.isfile(p))

    # The frame is every ICLR 2026 submission, so of course the 32 are in it -- along with 19,782 others, and
    # with nothing marking which rows this study drew. Excluding them would itself point at them. So the frame
    # is exempt from the id and title rules, and the exemption is paid for by the two checks below rather than
    # asserted: no field may flag a sampled row, and the mapping must not be reconstructible from the frame.
    FRAME = "frame/iclr2026_frame.json"
    # The count is in the label rather than the names, because this file is inside the tree it sweeps. A sweep
    # with nothing to look for is not a passing sweep, so the number is on the line a reader of this run sees.
    records = working_records()
    check(bool(records), "the working-record sweep has names to look for")
    rules = [
        ("forum ids of declined submissions", [re.escape(f.encode()) for f in forums], {FRAME}),
        ("titles of declined submissions",
         [re.escape(t.encode()) for t in titles.values() if len(t) > 20], {FRAME}),
        ("absolute home paths", [rb"/(?:home|Users)/\w"], set()),
        ("author username", [re.escape(s.encode()) for s in IDENTITY], set()),
        # The camera-ready names its authors, so their two published addresses may appear; any other address is
        # a leak from the working tree.
        ("email address other than the authors'",
         [rb"(?<![\w.\-])(?!jlu414@gatech\.edu\b)(?!shihao\.yang@isye\.gatech\.edu\b)[\w.\-]+@[\w.\-]+\.[a-z]{2,}"], set()),
        ("released label beside a forum id", [re.escape(f.encode()) + rb'"?\s*[:=]\s*"?R\d\d'
                                                for f in forums], {FRAME}),
        ("pointer to a corpus the bundle does not contain", [p for p, _ in forbidden_siblings()], set()),
        (f"citation of a working record the bundle does not contain ({len(records)} swept)", records, set()),
    ]
    for label, pats, exempt in rules:
        bad = {}
        for p in staged:
            rel = os.path.relpath(p, STAGE)
            if rel in exempt:
                continue
            b = open(p, "rb").read()
            hit = sorted({m.decode(errors="replace")[:40] for pat in pats for m in re.findall(pat, b)})
            if hit:
                bad[rel] = hit
        check(not bad, f"no {label}", "; ".join(f"{k} {v[:2]}" for k, v in list(bad.items())[:3]))

    # The draw rule. Its two targets and its tie-break are the step from the eligible sets to the drawn 32, and
    # unlike the eligibility cut-offs they are recoverable from nothing the release contains, so they are
    # forbidden in the staged tree. The values are read from the pre-registration record and never written
    # here: a sweep that names what it excludes ships it, and this file is inside the bundle it sweeps.
    rule = json.load(open(f"{REJ}/sample_preregistered.json"))["rule"]
    tgt = [rf"(?<![\w.-]){re.escape(str(rule[k]))}(?![\d])" for k in ("low_target", "high_target")]
    NAMED = re.compile(r"(?i)\b\w*(?:target|tgt)\w*\b")
    leak = {}
    for p in staged:
        t = open(p, encoding="utf-8", errors="ignore").read()
        hit = ["the tie-break, verbatim"] if str(rule["tie_break"]) in t else []
        # By value and in code only. A rating is unremarkable in prose and in a review, and the high target
        # reads exactly like the model name every slot table in this bundle carries.
        if os.path.splitext(p)[1] in (".py", ".sh"):
            for ln in t.splitlines():
                v = [x for x in tgt if re.search(x, ln)]
                if v and NAMED.search(ln):
                    hit.append("a target value bound to a name")
                elif len(v) == 2 and "=" in ln:
                    hit.append("both target values on one line")
        if hit:
            leak[os.path.relpath(p, STAGE)] = sorted(set(hit))
    check(not leak, "no draw parameter that the released ratings do not already imply",
          "; ".join(f"{k} {v}" for k, v in list(leak.items())[:3]))

    # Credentials: matched by shape and reported by count only. Printing the match would put the secret in the
    # terminal, in the scrollback, and in whatever log is capturing this run.
    cred = {}
    for p in staged:
        b = open(p, "rb").read()
        c = sum(len(re.findall(pat, b)) for pat in CRED_PATTERNS)
        if c:
            cred[os.path.relpath(p, STAGE)] = c
    check(not cred, "no credential-shaped values", f"{sum(cred.values())} in {list(cred)[:3]}")

    frame = json.load(open(f"{STAGE}/{FRAME}"))
    rows = frame if isinstance(frame, list) else next((v for v in frame.values() if isinstance(v, list)), [])
    fields = sorted({k for r in rows[:200] if isinstance(r, dict) for k in r})
    check(not [k for k in fields if re.search(r"(?i)sampl|in_study|selected|our_|label|panel|composite", k)],
          "the frame flags no sampled row", fields)
    check(not any(isinstance(r, dict) and re.fullmatch(r"R\d\d", str(r.get("label", ""))) for r in rows),
          "the frame carries no released label")
    check(not [p for p in staged if p.endswith(".pdf")], "no PDFs redistributed")
    check(not [p for p in staged if os.path.basename(p) in ("manuscript.txt", "deid_index.json")],
          "no de-identified manuscript text")
    # By CONTENT, not by filename. The transform arm now has a second variant tree built from the declined
    # submissions, and its files are named baseline.txt and T1_endmatter.txt -- names the check above does not
    # match and never will. Those are full de-identified manuscripts of third-party submissions that were not
    # accepted anywhere, so shipping one is the worst thing this script could do, and the filename rule that
    # protects the published arm gives them no protection at all. Hashing every staged file against every
    # withheld text costs nothing here and does not depend on remembering which glob was safe.
    withheld = {}
    for f in glob.glob(f"{AN}/pia_variants_reject/*/*.txt"):
        withheld[hashlib.sha256(open(f, "rb").read()).hexdigest()] = os.path.relpath(f, AN)
    leaked = [(os.path.relpath(p, STAGE), withheld[h]) for p in staged
              if (h := hashlib.sha256(open(p, "rb").read()).hexdigest()) in withheld]
    check(not leaked, f"none of the {len(withheld)} declined-submission variant texts is in the bundle", leaked)

    # A review the schema refused leaves its parse candidate on disk next to the reviews, as
    # `<slot>.json.extracted.txt`, and that file is the model's whole reply -- summary, concerns and
    # justifications, none of it redacted. Every arm has some: a slot is retried until the schema accepts it,
    # and the residue of the attempt stays. Nothing stages them today, because the review globs name `R?.json`
    # and `C?.json`. This says so as an assertion rather than as a property of two globs, because the file that
    # would leak is a full free-text review of a submission that was not accepted anywhere.
    residue = [os.path.relpath(p, STAGE) for p in staged if p.endswith(".extracted.txt")]
    check(not residue, "no rejected parse candidate is in the bundle", residue)
    # And the redaction actually happened, checked on the files rather than trusted from the code path.
    sample = json.load(open(sorted(glob.glob(f"{STAGE}/reviews/rejected/*/*/R?.json"))[0]))
    check(all(k not in sample for k in FREE_TEXT), "declined-submission reviews carry no free text")
    # Every one of them, not a sample: this arm was added after the checks were written, and a spot check on
    # the first file cannot tell a redacted arm from an arm whose first file happened to be redacted.
    unredacted = [os.path.relpath(f, STAGE) for f in glob.glob(f"{STAGE}/reviews/transform_rejected/**/R?.json",
                                                               recursive=True)
                  if any(k in json.load(open(f)) for k in FREE_TEXT)]
    check(not unredacted, "every declined-submission transform review carries scores only", unredacted[:5])
    check("score" in next(iter(sample["metrics"].values())), "declined-submission reviews carry every score")
    full = json.load(open(sorted(glob.glob(f"{STAGE}/reviews/accepted/*/*/R?.json"))[0]))
    check(all(k in full for k in FREE_TEXT), "published-paper reviews are complete")

    n_named, bad_paths = unresolved_paper_paths()
    check(not bad_paths, f"every one of the {n_named} paths the paper names is in the bundle", bad_paths)

    # The bundle's central claim, run rather than asserted: the staged tree must recompute the paper. This is
    # the check that catches what a file-by-file audit cannot -- that the analysis scripts read paths the
    # bundle does not contain, so a reader who trusts the release and tries to use it gets nothing.
    print("\nthe bundle recomputing the paper")
    r = subprocess.run([sys.executable, f"{STAGE}/reproduce.py", "--bundle", STAGE],
                       capture_output=True, text=True)
    lines = [ln.strip() for ln in r.stdout.splitlines() if "reproduce" in ln or "FAIL" in ln]
    check(r.returncode == 0, "reproduce.py recomputes every printed number from the staged tree",
          "; ".join(lines[-3:]) or r.stderr.strip()[-300:])
    for ln in lines:
        print(f"  ..   {ln}")

    man = []
    for p in sorted(staged):
        man.append(f"{hashlib.sha256(open(p, 'rb').read()).hexdigest()}  {os.path.relpath(p, STAGE)}")
    open(f"{STAGE}/MANIFEST.sha256", "w").write("\n".join(man) + "\n")
    size = sum(os.path.getsize(p) for p in staged)
    print(f"\n{len(staged) + 1} files, {size / 1e6:.1f} MB staged at {os.path.relpath(STAGE, AN)}")

    if a.tar and not fails:
        tar = f"{AN}/release/aina2026_agent_reviewers.tar.gz"
        subprocess.run(["tar", "-czf", tar, "-C", f"{AN}/release", "aina2026_agent_reviewers"], check=True)
        print(f"wrote {os.path.relpath(tar, AN)}  ({os.path.getsize(tar) / 1e6:.1f} MB)")

    print(f"\n{len(fails)} failing check(s)" + ("" if not fails else ": " + ", ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
