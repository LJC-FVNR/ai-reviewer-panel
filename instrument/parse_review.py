#!/usr/bin/env python3
"""Parse a reviewer .out file into a schema-validated JSON record.

The reviewer prompt (`reviewer_prompt_template.md`) requires reviewers to emit a
single fenced JSON block as their *only* output. Real model outputs in practice
sometimes prepend a brief preamble, occasionally wrap the JSON in a generic
```` ``` ```` fence instead of ```` ```json ```` , or include trailing
commentary. This parser:

  1. Locates the JSON object in the .out file (preferring a ```json fenced
     block, falling back to a generic fence, then to a balanced-brace scan).
  2. Strips trailing commas a model may have emitted by accident, but
     otherwise does NOT mutate or synthesize content.
  3. Validates the resulting object against `metrics_schema.json`.
  4. Writes the validated object as pretty-printed JSON to the requested path.

Designed for use from `run_reviewer.sh` outputs: each reviewer R1..R5 produces
a `<DIR>/R{N}.out`, this script consumes it and writes `<DIR>/R{N}.json`.

Usage:
    parse_review.py --in R1.out --out R1.json
    parse_review.py --selftest
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover
    print("ERROR: python jsonschema is required (pip install jsonschema).", file=sys.stderr)
    raise

SCHEMA_PATH = Path(__file__).resolve().parent / "metrics_schema.json"


@dataclasses.dataclass
class ParseResult:
    ok: bool
    error: str | None
    extracted_text: str | None
    parsed: dict[str, Any] | None
    schema_errors: list[str]


def _load_schema() -> dict[str, Any]:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _strip_trailing_commas(s: str) -> str:
    # Remove trailing commas inside objects/arrays: ,}  ,]  with possible whitespace.
    return re.sub(r",(\s*[}\]])", r"\1", s)


def _try_json_loads(s: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(s), None
    except json.JSONDecodeError as e:
        # Try with trailing commas stripped.
        try:
            cleaned = _strip_trailing_commas(s)
            return json.loads(cleaned), None
        except json.JSONDecodeError as e2:
            return None, f"{e2.msg} at line {e2.lineno} col {e2.colno}"


def extract_json_block(raw: str) -> tuple[str | None, str | None]:
    """Extract the JSON object text from a reviewer .out file.

    Strategy, in order:
      1. ```json ... ``` fenced block (preferred per prompt template).
      2. ``` ... ``` generic fenced block whose content looks like JSON
         (first non-whitespace char is `{`).
      3. Balanced-brace scan: the first `{`..matching `}` substring that
         json.loads successfully on its own.

    Returns (extracted_text, error). Exactly one of the two is non-None.
    """
    # 1) ```json fenced
    m = re.search(r"```json\s*\n(.*?)\n```", raw, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip(), None

    # 2) any ``` ... ``` whose content starts with `{`
    for m in re.finditer(r"```[a-zA-Z0-9_-]*\s*\n(.*?)\n```", raw, flags=re.DOTALL):
        inner = m.group(1).strip()
        if inner.startswith("{"):
            return inner, None

    # 3) balanced-brace scan, greedy from each `{` to the matching `}`.
    starts = [i for i, c in enumerate(raw) if c == "{"]
    for start in starts:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(raw)):
            c = raw[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = raw[start : i + 1]
                        parsed, err = _try_json_loads(candidate)
                        if parsed is not None and isinstance(parsed, dict):
                            return candidate, None
                        break  # try the next `{` start
    return None, "no parseable JSON object found in input"


def parse_review(raw: str) -> ParseResult:
    schema = _load_schema()
    extracted, err = extract_json_block(raw)
    if extracted is None:
        return ParseResult(False, err, None, None, [])

    parsed, jerr = _try_json_loads(extracted)
    if parsed is None:
        return ParseResult(False, f"JSON decode failed: {jerr}", extracted, None, [])

    validator = jsonschema.Draft202012Validator(schema)
    schema_errors = [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(parsed), key=lambda e: list(e.absolute_path))
    ]
    if schema_errors:
        return ParseResult(False, "schema validation failed", extracted, parsed, schema_errors)
    return ParseResult(True, None, extracted, parsed, [])


# ----------------------------- self-test ----------------------------------- #

_SELFTEST_GOOD = """\
Some reviewer preamble that should be ignored.

```json
{
  "grade": "Major Revision",
  "summary": "Two sentence overall assessment that is plausible.",
  "strengths": ["broad model panel", "explicit nulls"],
  "key_concerns": [
    {"severity": "blocking", "issue": "by-construction headline", "suggested_fix": "expand target-independent test"}
  ],
  "questions_for_authors": ["how were endpoints fixed?"],
  "calibration_check": "Abstract slightly overclaims relative to deconfounded support.",
  "recommended_for_publication_after_minor_fixes": false,
  "metrics": {
    "significance":          {"score": 8, "justification": "relevant to RAG and interpretability"},
    "novelty":               {"score": 7, "justification": "mechanistic angle is new"},
    "rigor":                 {"score": 6, "justification": "controls present but uneven across families"},
    "statistical_soundness": {"score": 6, "justification": "clustered SEs reported; multiplicity partial"},
    "calibration_honesty":   {"score": 6, "justification": "candid in body, broader in abstract"},
    "clarity":               {"score": 6, "justification": "dense; many forward references"},
    "structure_compliance":  {"score": 7, "justification": "follows Article structure"},
    "reproducibility":       {"score": 6, "justification": "code planned; some pipelines underspecified"},
    "related_work":          {"score": 7, "justification": "fair coverage of context-vs-memory literature"},
    "figure_quality":        {"score": 6, "justification": "informative but cluttered panels"},
    "breadth_generality":    {"score": 5, "justification": "deconfounded support narrower than claim"},
    "overall_recommendation":{"score": 5, "justification": "promising but partly by-construction"}
  },
  "publishability_probability": 0.42
}
```

Trailing model commentary that should be ignored.
"""

_SELFTEST_BAD_MISSING_FIELD = """\
```json
{
  "grade": "Major Revision",
  "summary": "Two sentence overall assessment.",
  "strengths": ["something"],
  "key_concerns": [],
  "questions_for_authors": [],
  "calibration_check": "ok",
  "recommended_for_publication_after_minor_fixes": false,
  "metrics": {
    "significance":          {"score": 8, "justification": "ok"}
  },
  "publishability_probability": 0.2
}
```
"""

_SELFTEST_BAD_OUT_OF_RANGE = """\
```json
{
  "grade": "Accept",
  "summary": "ok",
  "strengths": ["x"],
  "key_concerns": [],
  "questions_for_authors": [],
  "calibration_check": "ok",
  "recommended_for_publication_after_minor_fixes": true,
  "metrics": {
    "significance":          {"score": 11, "justification": "ok"},
    "novelty":               {"score": 8, "justification": "ok"},
    "rigor":                 {"score": 8, "justification": "ok"},
    "statistical_soundness": {"score": 8, "justification": "ok"},
    "calibration_honesty":   {"score": 8, "justification": "ok"},
    "clarity":               {"score": 8, "justification": "ok"},
    "structure_compliance":  {"score": 8, "justification": "ok"},
    "reproducibility":       {"score": 8, "justification": "ok"},
    "related_work":          {"score": 8, "justification": "ok"},
    "figure_quality":        {"score": 8, "justification": "ok"},
    "breadth_generality":    {"score": 8, "justification": "ok"},
    "overall_recommendation":{"score": 8, "justification": "ok"}
  },
  "publishability_probability": 0.9
}
```
"""

_SELFTEST_GENERIC_FENCE_WITH_PREAMBLE = """\
Here's my review:

```
{
  "grade": "Minor Revision",
  "summary": "ok summary",
  "strengths": ["x"],
  "key_concerns": [{"severity": "minor", "issue": "x", "suggested_fix": "y"}],
  "questions_for_authors": ["a?"],
  "calibration_check": "ok",
  "recommended_for_publication_after_minor_fixes": true,
  "metrics": {
    "significance":          {"score": 8, "justification": "ok"},
    "novelty":               {"score": 7, "justification": "ok"},
    "rigor":                 {"score": 8, "justification": "ok"},
    "statistical_soundness": {"score": 7, "justification": "ok"},
    "calibration_honesty":   {"score": 8, "justification": "ok"},
    "clarity":               {"score": 8, "justification": "ok"},
    "structure_compliance":  {"score": 8, "justification": "ok"},
    "reproducibility":       {"score": 7, "justification": "ok"},
    "related_work":          {"score": 7, "justification": "ok"},
    "figure_quality":        {"score": 7, "justification": "ok"},
    "breadth_generality":    {"score": 7, "justification": "ok"},
    "overall_recommendation":{"score": 8, "justification": "ok"}
  },
  "publishability_probability": 0.6
}
```
"""


def _selftest() -> int:
    failures: list[str] = []

    # 1) Good input parses + validates.
    r = parse_review(_SELFTEST_GOOD)
    if not r.ok:
        failures.append(f"GOOD did not validate: {r.error}; schema_errors={r.schema_errors}")
    else:
        if r.parsed is None or r.parsed.get("grade") != "Major Revision":
            failures.append("GOOD parsed but field mismatch")

    # 2) Missing fields => schema validation must fail.
    r = parse_review(_SELFTEST_BAD_MISSING_FIELD)
    if r.ok:
        failures.append("BAD_MISSING_FIELD should not validate")

    # 3) Out-of-range score => schema validation must fail.
    r = parse_review(_SELFTEST_BAD_OUT_OF_RANGE)
    if r.ok:
        failures.append("BAD_OUT_OF_RANGE should not validate")

    # 4) Generic ``` ... ``` fence with preamble parses.
    r = parse_review(_SELFTEST_GENERIC_FENCE_WITH_PREAMBLE)
    if not r.ok:
        failures.append(f"GENERIC_FENCE did not validate: {r.error}; schema_errors={r.schema_errors}")

    # 5) Round-trip through file IO via the CLI args path.
    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "R1.out"
        out_path = Path(td) / "R1.json"
        in_path.write_text(_SELFTEST_GOOD, encoding="utf-8")
        rc = _cli_run(in_path=str(in_path), out_path=str(out_path))
        if rc != 0:
            failures.append(f"CLI round-trip returned rc={rc}")
        elif not out_path.exists():
            failures.append("CLI round-trip did not write output file")
        else:
            written = json.loads(out_path.read_text(encoding="utf-8"))
            if written.get("grade") != "Major Revision":
                failures.append("CLI round-trip produced wrong content")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        print("FAILED", file=sys.stderr)
        return 1
    print("OK")
    return 0


def _cli_run(in_path: str, out_path: str) -> int:
    raw = Path(in_path).read_text(encoding="utf-8", errors="replace")
    result = parse_review(raw)
    if not result.ok:
        sys.stderr.write(f"parse failed for {in_path}: {result.error}\n")
        for se in result.schema_errors:
            sys.stderr.write(f"  schema: {se}\n")
        if result.extracted_text is not None:
            err_path = out_path + ".extracted.txt"
            Path(err_path).write_text(result.extracted_text, encoding="utf-8")
            sys.stderr.write(f"  extracted JSON candidate written to {err_path}\n")
        return 1
    assert result.parsed is not None
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(result.parsed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "parse_review")
    ap.add_argument("--in", dest="in_path", help="path to reviewer .out file")
    ap.add_argument("--out", dest="out_path", help="path to write parsed .json file")
    ap.add_argument("--selftest", action="store_true", help="run built-in selftest and print OK on success")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.in_path or not args.out_path:
        ap.error("--in and --out are required unless --selftest is given")
    return _cli_run(args.in_path, args.out_path)


if __name__ == "__main__":
    raise SystemExit(main())
