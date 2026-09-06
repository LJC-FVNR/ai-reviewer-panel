#!/usr/bin/env python3
"""De-identify a single-column CONFERENCE (arXiv/ICLR/NeurIPS/ICML) PDF into a
blind, single-column, compilable review manuscript — the conference analogue of
deidentify_published_pdf.py (which is Nature two-column specific).

Differences from the Nature script:
  * SINGLE column: no page-midpoint left/right split (that garbles single-col text).
  * Conference leak patterns: arXiv stamp, "Published/Accepted ... at ICLR/NeurIPS/ICML",
    author block under the title, email footnotes, "Under review", "Preprint".
  * Truncate at References / Appendix / Acknathe like (keep main body + Methods-equivalent).
  * Captions "Figure N:" / "Table N:" (colon or period), emitted as full-caption placeholders.
  * Author full-name masking from arXiv metadata.

Usage: deid_conference.py <pdf> "Author One|Author Two|..." <outdir>
Then the operator MUST run the manual leakage/structure/completeness checks (see DEID_GUIDE §4).
"""
import fitz, re, sys, os, subprocess, statistics

# ---- leak patterns (conference) ----
VENUE_LEAK = re.compile(
    r'(published as a conference paper|accepted (as|at|to|by|for)|under review as|to appear'
    r'|ICLR\s*20\d\d|NeurIPS\s*20\d\d|ICML\s*20\d\d|International Conference on Learning Representations'
    r'|Conference on Neural Information Processing|preprint|under review|camera[- ]ready'
    r'|Proceedings of the)', re.I)
LINEMETA = re.compile(
    r'(arXiv:\s*\d{4}\.\d{4,5}|https?://|doi\.org|10\.48550|github\.com/|huggingface\.co/'
    r'|Equal contribution|Corresponding author|\bemail\b|@[A-Za-z0-9.\-]+\.(edu|com|org|gov|ac\.[a-z]{2}|cn|uk|ch|de)'
    r'|Work done (during|while)|\bintern(ship)?\b)', re.I)
AFF = re.compile(
    r'(University|Institute|Laborator|Department|School of|College|Research|Google|DeepMind|Microsoft'
    r'|Meta|OpenAI|Anthropic|Amazon|NVIDIA|Tsinghua|Peking|Stanford|MIT|Berkeley|Carnegie|Allen Institute'
    r'|EPFL|ETH|Oxford|Cambridge|Tencent|Alibaba|ByteDance|Huawei|Academy of Sciences)\b', re.I)
BACK = re.compile(
    r'^(References|Acknowledge?ments?|Appendix|Author Contributions?|Ethics Statement'
    r'|Reproducibility Statement|Broader Impact|Supplementary|Bibliography|Funding)\b', re.I)
REFLINE = re.compile(r'^\s*\[\d{1,3}\]\s|^\s*\d{1,3}\.\s+[A-Z][A-Za-z\-]+,?\s+[A-Z]\.')
CAP = re.compile(r'^(Figure|Fig\.|Table|Algorithm)\s*\d+\s*[:.]', re.I)

def title_of(doc):
    pg = doc[0]; spans = []
    for b in pg.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                if s["text"].strip():
                    spans.append((round(s["size"], 1), s["bbox"][1], s["text"].strip()))
    spans = [s for s in spans if s[1] < pg.rect.height * 0.4]
    if not spans:
        return "Submitted manuscript"
    mx = max(s[0] for s in spans)
    # title = largest-font spans near the top, in y order
    return ' '.join(t for sz, y, t in sorted([s for s in spans if s[0] >= mx - 0.6], key=lambda x: x[1]))

def _is_h(s):
    return "Bold" in s.get("font", "") or "bold" in s.get("font", "")

SEC_PAT = re.compile(
    r'^\d{0,2}\.?\d{0,2}\.?\s*(Introduction|Related Work|Related|Background|Preliminaries|Method|Methods'
    r'|Methodology|Approach|Experiment|Experiments|Experimental|Result|Results|Evaluation|Analysis'
    r'|Discussion|Conclusion|Conclusions|Setup|Notation|Theory|Model|Framework|Ablation|Ablations'
    r'|Limitations|Overview|Motivation|Problem|Preliminary)\b', re.I)

def _body_median_size(doc):
    sizes = []
    for pi in range(min(6, len(doc))):
        for b in doc[pi].get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if s["text"].strip():
                        sizes.append(round(s["size"], 1))
    return statistics.median(sizes) if sizes else 10.0

def extract(doc, title):
    """Single-column, reading order = block y then x. Emit (kind,text)."""
    items = []
    tlow = title[:40].lower()
    body_sz = _body_median_size(doc)
    for pi in range(len(doc)):
        pg = doc[pi]
        d = pg.get_text("dict")
        top_skip = (pg.rect.height * 0.28) if pi == 0 else -1  # title+author band on p1
        blocks = []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            by = b["bbox"][1]; bx = b["bbox"][0]
            if pi == 0 and by < top_skip:
                continue
            blocks.append((by, bx, b))
        blocks.sort(key=lambda t: (round(t[0] / 3), t[1]))  # y-band then x
        for by, bx, b in blocks:
            btext = re.sub(r'\s+', ' ', "".join(s["text"] for l in b.get("lines", [])
                                                for s in l.get("spans", []))).strip()
            if not btext:
                continue
            wc = len(btext.split())
            # block-level leak strip
            if LINEMETA.search(btext):
                continue
            if VENUE_LEAK.search(btext) and wc <= 30:
                continue
            if AFF.search(btext) and wc <= 30:
                continue
            if pi == 0 and by < pg.rect.height * 0.42 and wc <= 30 and not CAP.match(btext):
                # p1 author/affiliation zone under title
                continue
            if CAP.match(btext):
                items.append(("CAP", btext)); continue
            # figure-interior tiny text
            szs = [s['size'] for l in b.get("lines", []) for s in l.get("spans", []) if s['text'].strip()]
            msz = statistics.median(szs) if szs else 9.0
            if msz < 6.5 and not CAP.match(btext):
                continue
            # heading heuristic: short line that is (bold OR larger-than-body OR a known section word)
            first_spans = b["lines"][0]["spans"] if b.get("lines") and b["lines"][0].get("spans") else []
            fsz = round(first_spans[0]["size"], 1) if first_spans else body_sz
            # a real heading is at least body-size (rejects tiny bold figure-panel labels like "Backbone" 6.9pt)
            is_bold = bool(first_spans) and _is_h(first_spans[0]) and fsz >= body_sz - 0.5
            is_big = fsz >= body_sz + 0.8
            is_secword = bool(SEC_PAT.match(btext)) and fsz >= body_sz - 0.5
            # strip a leading section number ("1INTRODUCTION" / "3.2 Method") for the emitted heading
            if wc <= 12 and (is_bold or is_big or is_secword):
                htxt = re.sub(r'^\s*\d{1,2}(\.\d{1,2}){0,2}\.?\s*', '', btext).strip()
                # dedupe consecutive identical headings (repeated figure labels)
                if items and items[-1] == ("H", htxt or btext):
                    continue
                items.append(("H", htxt or btext)); continue
            items.append(("BODY", btext))
    return items

def build(pdf, authors, outdir, title_override=None):
    doc = fitz.open(pdf); title = title_override or title_of(doc)
    raw = extract(fitz.open(pdf), title)
    apat = re.compile('|'.join(re.escape(a) for a in authors if len(a) > 2)) if authors else None
    # also mask surname tokens
    surnames = [a.split()[-1] for a in authors if a.split()]
    spat = re.compile(r'\b(' + '|'.join(re.escape(s) for s in surnames if len(s) > 2) + r')\b') if surnames else None
    out = []
    tlow = title[:40].lower()
    for kind, txt in raw:
        flat = re.sub(r'\s+', ' ', txt).strip()
        if BACK.match(flat) and len(out) > 15:
            break
        wc = len(flat.split())
        if REFLINE.match(flat):
            continue
        if (LINEMETA.search(flat) and wc <= 30):
            continue
        if (VENUE_LEAK.search(flat) and wc <= 25):
            continue
        if kind == "BODY" and tlow and tlow in flat.lower() and wc <= 25:
            continue
        flat = re.sub(r'(\w)-\s+(\w)', r'\1\2', flat)  # de-hyphenate
        if apat:
            flat = apat.sub('[Author]', flat)
        if spat:
            flat = spat.sub('[Author]', flat)
        out.append((kind, flat))
    # latex
    UNI = {'τ': '$\\tau$', 'α': '$\\alpha$', 'β': '$\\beta$', 'ρ': '$\\rho$', 'σ': '$\\sigma$',
           'μ': '$\\mu$', 'λ': '$\\lambda$', 'θ': '$\\theta$', 'π': '$\\pi$', 'χ': '$\\chi$',
           'γ': '$\\gamma$', 'δ': '$\\delta$', 'ε': '$\\epsilon$', 'ω': '$\\omega$', 'Δ': '$\\Delta$',
           'Σ': '$\\Sigma$', '∑': '$\\sum$', '∈': '$\\in$', '∼': '$\\sim$', '×': '$\\times$',
           '≈': '$\\approx$', '≤': '$\\leq$', '≥': '$\\geq$', '≠': '$\\neq$', '→': '$\\to$',
           '↑': '$\\uparrow$', '↓': '$\\downarrow$', '∇': '$\\nabla$', '∞': '$\\infty$',
           '−': '-', '’': "'", '‘': "'", '“': '"', '”': '"', '—': '---', '–': '--', '…': '...', '·': '$\\cdot$'}
    GREEK = {'Θ': r'$\Theta$', 'Φ': r'$\Phi$', 'Ψ': r'$\Psi$', 'Ω': r'$\Omega$', 'Γ': r'$\Gamma$',
             'Λ': r'$\Lambda$', 'Ξ': r'$\Xi$', 'Π': r'$\Pi$', 'φ': r'$\phi$', 'ψ': r'$\psi$',
             'ξ': r'$\xi$', 'ζ': r'$\zeta$', 'η': r'$\eta$', 'κ': r'$\kappa$', 'ν': r'$\nu$',
             'ι': r'$\iota$', 'υ': r'$\upsilon$', 'ς': r'$\varsigma$'}
    SYM = {'∥': r'$\|$', '‖': r'$\|$', '⟨': r'$\langle$', '⟩': r'$\rangle$', '∀': r'$\forall$',
           '∃': r'$\exists$', '∂': r'$\partial$', '∫': r'$\int$', '∏': r'$\prod$', '√': r'$\sqrt{}$',
           '∝': r'$\propto$', '≡': r'$\equiv$', '≪': r'$\ll$', '≫': r'$\gg$', '⊗': r'$\otimes$',
           '⊕': r'$\oplus$', '∩': r'$\cap$', '∪': r'$\cup$', '⊂': r'$\subset$', '⊆': r'$\subseteq$',
           '∅': r'$\emptyset$', '±': r'$\pm$', '∓': r'$\mp$', '°': r'$^\circ$', '′': "'", '″': "''",
           '→': r'$\to$', '↦': r'$\mapsto$', 'ﬁ': 'fi', 'ﬂ': 'fl',
           ' ': ' ', ' ': ' ', ' ': ' ', ' ': ' ', ' ': ' ', ' ': ' '}
    def esc(s):
        # 1) escape LaTeX-special ASCII chars FIRST (on plain text, before inserting any commands)
        for a, b in [('\\', r'\textbackslash{}'), ('&', r'\&'), ('%', r'\%'), ('#', r'\#'),
                     ('_', r'\_'), ('$', r'\$'), ('{', r'\{'), ('}', r'\}'),
                     ('~', r'\textasciitilde{}'), ('^', r'\textasciicircum{}')]:
            s = s.replace(a, b)
        # 2) now map unicode -> LaTeX commands (these contain $, \, {} that must NOT be re-escaped)
        for u, r in UNI.items():
            s = s.replace(u, r)
        for u, r in GREEK.items():
            s = s.replace(u, r)
        for u, r in SYM.items():
            s = s.replace(u, r)
        # 3) keep only printable ASCII (drop control chars U+0000-001F and all non-ASCII)
        #    to keep pdflatex clean (blind review = text fidelity, not glyphs)
        s = ''.join(c if (32 <= ord(c) < 127 or c in '\n\t') else ' ' for c in s)
        return s
    parts = []
    for kind, txt in out:
        if kind == "H":
            parts.append(r'\section*{%s}' % esc(txt))
        elif kind == "CAP":
            num = re.match(r'(Figure|Fig\.|Table|Algorithm)\s*\d+', txt)
            num = num.group(0) if num else "Display item"
            parts.append(r'\begin{quote}\small\textbf{[%s about here]}\\ \textit{%s}\end{quote}' % (esc(num), esc(txt)))
        else:
            parts.append(esc(txt))
    body = '\n\n'.join(parts)
    tex = r'''\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}\usepackage{microtype}\usepackage[T1]{fontenc}
\setlength{\parskip}{0.5em}\setlength{\parindent}{0pt}
\title{\textbf{%s}}\author{}\date{}
\begin{document}\maketitle
\begin{center}\small[Double-blind manuscript for peer review: authors, affiliations, funding, acknowledgements, references and publication metadata removed. Figures/tables are given as full captions with placeholders; judge them from the captions.]\end{center}
\vspace{1em}
%s
\end{document}''' % (esc(title), body)
    os.makedirs(outdir, exist_ok=True)
    open(f"{outdir}/main.tex", "w").write(tex)
    subprocess.run(["pdflatex", "-interaction=nonstopmode", "main.tex"], cwd=outdir,
                   stdout=open(f"{outdir}/compile.log", "w"), stderr=subprocess.STDOUT)
    subprocess.run(["pdflatex", "-interaction=nonstopmode", "main.tex"], cwd=outdir,
                   stdout=open(f"{outdir}/compile.log", "w"), stderr=subprocess.STDOUT)
    return title, len(out)

if __name__ == '__main__':
    pdf = sys.argv[1]
    authors = sys.argv[2].split('|') if len(sys.argv) > 2 and sys.argv[2] else []
    outdir = sys.argv[3] if len(sys.argv) > 3 else "build_" + os.path.splitext(os.path.basename(pdf))[0]
    title_override = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None
    t, n = build(pdf, authors, outdir, title_override)
    print(f"TITLE: {t}\nUNITS: {n}")
