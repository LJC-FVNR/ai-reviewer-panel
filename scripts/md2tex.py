#!/usr/bin/env python3
"""DRAFT.md -> paper/body.tex, so page count becomes measurable instead of guessed.

The 9-page limit is a page limit, not a word limit, and the draft is written in markdown. Compressing
against a guessed words-per-page ratio would either overshoot or leave space on the table, so the order is:
convert faithfully, compile, measure, then cut to a known target.

Deliberately narrow. It handles exactly the constructs DRAFT.md uses -- ATX headings, bold/italic runs,
inline code, GFM pipe tables, blockquotes, ordered and unordered lists -- and escapes the LaTeX specials
that appear in prose. It is not a general markdown converter and should not become one; anything it cannot
handle should be simplified in the markdown rather than special-cased here.

Two conversions carry judgement rather than syntax:

  Unicode maths.  The draft writes rho/tau/mu/sigma and the minus sign as literal Unicode, which is right
  for a markdown draft read in a terminal and wrong for LaTeX, where a bare U+2212 is a missing glyph in
  the default encoding. Each maps to a math-mode command, and any Unicode left over after the pass is
  REPORTED rather than silently dropped -- a silently dropped minus sign turns a negative result positive.

  Tables.  Column count comes from the header row and alignment from the content: a column whose non-header
  cells are all numeric right-aligns, everything else left-aligns, and the first column always left-aligns.
  Widths are left to LaTeX. Every table is wrapped in \\small since these are dense and the body text is 10pt.

  Figures.  `![caption](figs/F1.pdf)` becomes a figure environment, whether the caption sits on one line or
  wraps over several, and the converter -- not the markdown -- chooses the width, by reading the PDF's own
  MediaBox. Every figure here was drawn at its final placed
  size, so any \\includegraphics width that disagrees with the natural width silently rescales the type:
  \\linewidth on a 4.6in figure enlarges it, and on a 5.8in one shrinks 6.4pt annotations below the 6pt
  floor. So: natural size whenever it fits the 5.5in text block, \\linewidth only when it does not, and the
  scale factor is printed for the one case where it is not 1.0.

Writes paper/body.tex, which main.tex includes. Idempotent; safe to re-run after editing DRAFT.md.
"""
from __future__ import annotations

import collections
import os
import re
import sys

AN = os.path.dirname(os.path.abspath(__file__))
FIGSCALE = {}
CITED = set()
SRC = f"{AN}/DRAFT.md"
OUT = f"{AN}/paper/body.tex"
# The body has a 9-page limit and the appendix does not, so they are separate markdown files converted by
# the same code. Anything that moves between them must keep its numbers: number_guard.py reads both.
PAIRS = [(SRC, OUT, False), (f"{AN}/APPENDIX.md", f"{AN}/paper/appendix.tex", True)]
# The third field is whether the file's front matter is paper text. It is, for the appendix: \appendix
# prints no heading of its own, so without the level-1 heading the appendices follow the references with
# nothing marking the division, and the roadmap that names the sections is the reader's only map of them.
# The body's front matter is a title block and drafting notes, and stays out.

# Unicode the draft uses, in the order it must be applied (longest first where prefixes overlap).
UNI = [
    ("\u2014", "---"), ("\u2013", "--"), ("\u2212", "$-$"),
    ("\u2018", "`"), ("\u2019", "'"), ("\u201c", "``"), ("\u201d", "''"),
    ("\u03c1", "$\\rho$"), ("\u03c4", "$\\tau$"), ("\u03bc", "$\\mu$"), ("\u03c3", "$\\sigma$"),
    ("\u0394", "$\\Delta$"), ("\u03b4", "$\\delta$"),
    ("\u00d7", "$\\times$"), ("\u2264", "$\\le$"), ("\u2265", "$\\ge$"),
    # The radical is mapped with its operand rather than on its own: \sqrt takes an argument, and a bare
    # U+221A would have to become \surd, which draws the sign without the bar over what it applies to. Any
    # other radical the draft acquires therefore trips the unconverted-glyph check instead of typesetting
    # wrongly, which is the direction that fails loudly.
    ("\u221a2", "$\\sqrt{2}$"),
    ("\u2208", "$\\in$"), ("\u2194", "$\\leftrightarrow$"), ("\u2192", "$\\to$"),
    ("\u2026", "\\dots"), ("\u231e", "\\quad"), ("\u00a0", " "),
    # The section sign is spelled out rather than typeset as a glyph, and that is not a style preference.
    # The corpus extractor keeps printable ASCII and drops everything else, so a "\S" reaches an agent
    # reviewer as a space: "the ranking result in \u00a75" arrives as "the ranking result in 5". Every one of this
    # draft's cross-references was being deleted from the text its own panel read, which is the artifact \u00a79
    # tells a venue to look for, found by running that recommendation on this manuscript. Fixed here rather
    # than in the extractor, because the extractor is the instrument the corpus went through and re-choosing
    # it would put this paper on a different axis from the 48 papers it is compared against.
    ("\u00a7", "Section~"),
]
SPECIALS = {"&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_", "$": r"\$"}


def esc(s):
    """Escape LaTeX specials. Runs FIRST, before any command is inserted, so there is nothing to
    double-escape -- the source prose contains no backslash, and this asserts it rather than assuming."""
    assert "\\" not in s, f"backslash in source prose, converter would mangle it: {s[:80]!r}"
    return "".join(SPECIALS.get(ch, ch) for ch in s)


def cites(s):
    """`[@key; @key2]` -> \\citep, `[@@key]` -> \\citet. Runs after esc(), which leaves brackets alone.

    The draft needs citations and esc() asserts the source prose contains no backslash, so the markdown
    carries keys rather than LaTeX. Keys are validated against paper/references.bib at the end of the run:
    a typo'd key otherwise compiles to a silent "[?]" that survives to the submitted PDF.
    """
    def one(m):
        keys = [k.strip().lstrip("@") for k in m.group(2).split(";")]
        CITED.update(keys)
        return ("\\citet{" if m.group(1) else "\\citep{") + ",".join(keys) + "}"
    return re.sub(r"\[@(@?)([^\]]+)\]", one, s)


def inline(s):
    """Inline markup -> LaTeX. Code spans are escaped differently, so they are pulled out first."""
    parts, i = [], 0
    for m in re.finditer(r"`([^`]+)`", s):
        parts.append(("t", s[i:m.start()]))
        parts.append(("c", m.group(1)))
        i = m.end()
    parts.append(("t", s[i:]))

    out = []
    for kind, txt in parts:
        if kind == "c":
            # An address is set with \url, which breaks at a slash or a dot; \texttt would run past
            # the text block, and a printed address is read back by the submission audit.
            if re.fullmatch(r"https?://\S+", txt):
                out.append("\\url{" + txt + "}")
                continue
            # \texttt content: escape specials, and let LaTeX break long ids at underscores.
            out.append("\\texttt{" + txt.replace("\\", "").replace("_", "\\_")
                       .replace("&", "\\&").replace("%", "\\%").replace("#", "\\#")
                       .replace("$", "\\$").replace("[", "{[}").replace("]", "{]}") + "}")
            continue
        txt = esc(txt)
        for a, b in UNI:
            txt = txt.replace(a, b)
        txt = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", txt)
        txt = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\\emph{\1}", txt)
        txt = cites(txt)
        # T1 puts a right-hand quotation mark at position 0x22, so a straight `"` in the markdown set the
        # opening mark of every quoted span as a closing one -- visible beside the curly apostrophes the UNI
        # table already produces. Pair them here rather than in the markdown, because quote_guard.py finds a
        # reviewer quotation by splitting a paragraph on the straight quote character.
        txt = re.sub(r'"([^"]*)"', r"``\1''", txt)
        assert '"' not in txt, f"unpaired quote mark, LaTeX would set it closing: {txt[:90]!r}"
        # A value and its unit must not break across lines: the wrapped appendix column split "+0.546" from
        # its "z" in three cells. A thin kern is the right typography and is not a legal break point.
        txt = re.sub(r"(\d)\s+(z\b|\\%|\$\\times\$)", r"\1\\,\2", txt)
        out.append(txt)
    return "".join(out)


TEXTWIDTH_PT = 5.5 * 72.27   # neurips_2026.sty: textwidth=5.5in


def figure(path, caption, label):
    """Figure environment, placed at the size it was drawn at unless that overflows the text block."""
    raw = open(f"{AN}/paper/{path}", "rb").read()
    box = re.search(rb"MediaBox\s*\[([^\]]*)\]", raw)
    assert box, f"no MediaBox in {path}, cannot tell what size it was drawn at"
    x0, y0, x1, y1 = (float(v) for v in box.group(1).split())
    nat = x1 - x0
    if nat <= TEXTWIDTH_PT:
        opt, scale = f"width={nat:.1f}pt", 1.0
    else:
        opt, scale = "width=\\linewidth", TEXTWIDTH_PT / nat
    FIGSCALE[path] = (nat / 72.27, scale)
    return ["\\begin{figure}[htb]", "\\centering",
            f"  \\includegraphics[{opt}]{{{path}}}",
            f"  \\caption{{{inline(caption)}}}", f"  \\label{{{label}}}",
            "\\end{figure}", ""]


def plain(cell):
    """-> the cell as it prints, for width estimation: markup and cite keys occupy no space on the page."""
    t = re.sub(r"\[@[^\]]*\]", "", cell)
    t = re.sub(r"[*`_$\\]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def numericish(cells):
    """True if every non-empty cell reads as a number, so the column should right-align."""
    pat = re.compile(r"^[\s$\\textbf{}*+\u2212<>=~-]*[\d.,]+\s*(%|z|\u00d7|pts?|points?)?[\s}*]*$")
    vals = [c for c in cells if c.strip()]
    return bool(vals) and all(pat.match(c.strip()) for c in vals)


# Text width of the neurips_2026 body, in points, and the empirical cost of one character of Times at
# \small. Both were measured, not assumed: a table that overflows by 106pt at 117 characters and 6 columns
# pins the per-character cost once tabcolsep is subtracted. A pipe table is written to be read as markdown,
# so nothing in the source says how wide it will set, and LaTeX's only complaint is one log line that a
# generated file makes easy to ignore -- two tables were printing 1.5in into the margins of the submission.
SAFETY_PT = 8.0                                   # the estimate ran 12pt light on the widest real table
CHAR_PT = {"small": 3.90, "footnotesize": 3.47}   # footnotesize is 8/9 of small
# Calibrated on the two tables that overflowed: 106.4pt over at 117 chars x 6 cols, and 3.9pt over at
# 100 chars x 5 cols, which put the per-character cost between 3.68 and 3.84pt. Take the high end -- a
# table set one tier tighter than it needed costs nothing, and one printed into the margin ships.


def natural_pt(widths, size, sep=6.0):
    """-> the width a tabular of these per-column character counts will set at this font size."""
    return CHAR_PT[size] * sum(widths) + sep * 2 * len(widths)


def table(rows):
    """GFM pipe table -> tabular, sized so it cannot print into the margin.

    Over budget, two remedies in order: drop to footnotesize, then wrap the widest left-aligned column in a
    p{} of whatever width is left. Wrapping beats \resizebox, which would shrink the type below the size the
    figures are held to, and beats hand-editing the generated file, which the next conversion overwrites.
    """
    hdr, body = rows[0], rows[1:]
    n = len(hdr)
    body = [r + [""] * (n - len(r)) for r in (row[:n] for row in body)]
    align = ["l"] + ["r" if numericish([r[j] for r in body]) else "l" for j in range(1, n)]
    widths = [max(len(plain(r[j])) for r in [hdr] + body) for j in range(n)]

    # Remedies in order of what they cost the reader: full size, then a tighter column gap, then a smaller
    # font, then wrapping. Font size comes before wrapping because the figures are held to a type floor and a
    # table should not undercut it; the gap comes before both because nobody can see 2pt of white space.
    budget = TEXTWIDTH_PT - SAFETY_PT
    for size, sep in (("small", 6.0), ("small", 4.0), ("footnotesize", 6.0), ("footnotesize", 4.0)):
        if natural_pt(widths, size, sep) <= budget:
            break
    over = natural_pt(widths, size, sep) - budget
    note = "" if sep == 6.0 else f", tabcolsep {sep:.0f}pt"
    if over > 0:
        # The widest l column absorbs it. Floor at 1.1in so a wrapped column stays readable rather than
        # setting one word per line; if the floor binds, the table is genuinely too wide and says so.
        j = max((j for j in range(n) if align[j] == "l"), key=lambda j: widths[j])
        keep_pt = CHAR_PT[size] * widths[j] - over
        inches = max(keep_pt / 72.27, 1.10)
        align[j] = ">{\\raggedright\\arraybackslash}p{%.2fin}" % inches
        note += f", col {j + 1} wrapped to {inches:.2f}in"
        if keep_pt / 72.27 < 1.10:
            note += " (AT THE FLOOR -- shorten a cell)"
    if size != "small" or note or over > 0:
        print(f"  table {n}x{len(body)}: {natural_pt(widths, 'small'):.0f}pt natural -> {size}{note}")

    pre = "" if sep == 6.0 else "\\setlength{\\tabcolsep}{%.0fpt}" % sep
    lines = ["\\begin{center}\\" + size + pre, "\\begin{tabular}{" + "".join(align) + "}", "\\toprule"]
    lines.append(" & ".join(inline(c) for c in hdr) + " \\\\")
    lines.append("\\midrule")
    for r in body:
        lines.append(" & ".join(inline(c) for c in r) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{center}"]
    return lines


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def convert(src_path, out_path, front_matter=False):
    raw = open(src_path, encoding="utf-8").read()
    # HTML comments mark the spans that generator scripts rewrite in place. They are addressed to whoever runs
    # those scripts, so they must not survive into the .tex: LaTeX has no reason to treat "<!--" as a comment,
    # and two of them reached a printed page before this line existed.
    raw = re.sub(r"(?s)<!--.*?-->", "", raw)
    src = raw.split("\n")
    out, i, n = [], 0, len(src)
    if front_matter:
        # The level-1 heading is set unnumbered, so it divides the document without taking a letter from the
        # sections under it, and everything down to the first "## " converts as ordinary prose.
        m = re.match(r"^# +(.+)$", src[0].strip())
        assert m, f"{src_path} does not open with a level-1 heading"
        out.append(f"\\section*{{{inline(m.group(1))}}}")
        out.append("")
        i = 1
    else:
        # The front matter above the first "## " heading is drafting scaffolding, not paper text.
        while i < n and not src[i].startswith("## "):
            i += 1

    para, quote, lst = [], [], None

    def flush_para():
        if para:
            out.append(inline(" ".join(para)))
            out.append("")
            para.clear()

    def flush_quote():
        if quote:
            out.append("\\begin{quote}\\small")
            out.append(inline(" ".join(quote)))
            out.append("\\end{quote}")
            out.append("")
            quote.clear()

    def flush_list():
        nonlocal lst
        if lst:
            env = "enumerate" if lst[0] else "itemize"
            out.append(f"\\begin{{{env}}}\\itemsep2pt")
            for item in lst[1]:
                out.append("  \\item " + inline(item))
            out.append(f"\\end{{{env}}}")
            out.append("")
            lst = None

    def flush_all():
        flush_para(); flush_quote(); flush_list()

    while i < n:
        line = src[i]
        s = line.strip()

        if s == "---":
            flush_all(); i += 1; continue

        m = re.match(r"^(#{2,4}) +(.+)$", s)
        if m:
            flush_all()
            depth, title = len(m.group(1)), m.group(2)
            title = re.sub(r"^\d+(\.\d+)* +", "", title)  # LaTeX numbers sections itself
            cmd = {2: "section", 3: "subsection", 4: "subsubsection"}[depth]
            out.append(f"\\{cmd}{{{inline(title)}}}")
            out.append("")
            i += 1
            continue

        if s.startswith("|"):
            flush_all()
            rows = []
            while i < n and src[i].strip().startswith("|"):
                r = split_row(src[i])
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c):
                    rows.append(r)
                i += 1
            out.extend(table(rows))
            out.append("")
            continue

        # A caption is one image, not necessarily one line. The opening figure's caption is long enough to
        # have wrapped in the markdown, and while this pattern demanded the whole image on a single line the
        # wrapped one fell through to the paragraph branch below: the figure was not typeset at all and its
        # caption set as body text beginning with an exclamation mark and a bracket. Lines are joined up to
        # the closer, stopping at a blank line so that an unclosed image cannot swallow the section after it.
        if s.startswith("!["):
            j, cap = i, s
            while j + 1 < n and not cap.endswith(".pdf)") and src[j + 1].strip():
                j += 1
                cap += " " + src[j].strip()
            mf = re.match(r"^!\[(.+)\]\((figs/(F\d)\.pdf)\)$", cap)
            if mf:
                flush_all()
                out.extend(figure(mf.group(2), mf.group(1), "fig:" + mf.group(3).lower()))
                i = j + 1
                continue

        if s.startswith(">"):
            flush_para(); flush_list()
            quote.append(s.lstrip("> ").rstrip())
            i += 1
            continue

        mi = re.match(r"^(\d+)\. +(.+)$", s) or re.match(r"^[-*] +(.+)$", s)
        if mi:
            flush_para(); flush_quote()
            ordered = bool(re.match(r"^\d+\. ", s))
            text = mi.group(2) if ordered else mi.group(1)
            if lst is None or lst[0] != ordered:
                flush_list()
                lst = (ordered, [])
            lst[1].append(text)
            i += 1
            continue

        if not s:
            flush_all(); i += 1; continue

        # continuation of a list item, a quote, or a paragraph -- indentation says which
        if lst is not None and line.startswith("   "):
            lst[1][-1] += " " + s
        elif quote:
            quote.append(s)
        else:
            para.append(s)
        i += 1

    flush_all()
    text = "\n".join(out) + "\n"

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(text)
    print(f"wrote {out_path}: {len(text.split())} words, {text.count(chr(10))} lines, "
          f"{text.count('begin{tabular}')} tables, {text.count('begin{figure}')} figures")
    return collections.Counter(c for c in text if ord(c) > 127)


def main():
    left = collections.Counter()
    for src_path, out_path, front_matter in PAIRS:
        if not os.path.exists(src_path):
            print(f"skipped {os.path.basename(src_path)} (does not exist yet)")
            continue
        left += convert(src_path, out_path, front_matter)
    for path, (natin, scale) in sorted(FIGSCALE.items()):
        note = "natural size" if scale == 1.0 else f"RESCALED x{scale:.3f} -- 6.4pt type lands at {6.4*scale:.1f}pt"
        print(f"  {path}: drawn {natin:.2f}in wide, {note}")

    bib = f"{AN}/paper/references.bib"
    if os.path.exists(bib):
        have = set(re.findall(r"@\w+\{([^,]+),", open(bib, encoding="utf-8").read()))
        bad, unused = sorted(CITED - have), sorted(have - CITED)
        print(f"\ncitations: {len(CITED)} keys cited, {len(have)} in references.bib")
        if unused:
            print("  uncited entries (harmless, but they will not print): " + " ".join(unused))
        if bad:
            print("  UNDEFINED KEYS -- these compile to '[?]' in the PDF: " + " ".join(bad))
            return 1
    if left:
        print("\nUNCONVERTED NON-ASCII -- each is a glyph pdflatex will drop or mangle. A dropped "
              "minus sign turns a negative result positive, so fix every one:")
        for ch, k in left.most_common():
            print(f"  U+{ord(ch):04X} {ch!r} x{k}")
        return 1
    print("no unconverted non-ASCII")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
