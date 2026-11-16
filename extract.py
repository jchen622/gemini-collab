#!/usr/bin/env python3
"""Deliverable -> plain text, written to disk so what left the machine is auditable.

The .docx path keeps superscript runs wrapped in <sup>...</sup> deliberately: a plain
text dump turns a superscript citation marker "17,18" into bare digits, after which a
citation sweep matches nothing and still reports zero defects. A silent zero is worse
than an error.

The .pdf path strips Private Use Area codepoints. pdftotext puts Symbol-font glyphs
(>=, =) in the PUA, where they render blank and silently corrupt any verbatim quote
taken from the extract.
"""
import re
import subprocess
import sys
import zipfile
from pathlib import Path

RUN = re.compile(r"<w:r[ >].*?</w:r>", re.S)
TXT = re.compile(r"<w:t[^>]*>(.*?)</w:t>", re.S)
SUP = re.compile(r'<w:vertAlign w:val="superscript"\s*/>')
PARA = re.compile(r"<w:p[ >].*?</w:p>", re.S)
PUA = re.compile("[\uE000-\uF8FF]")


def _unescape(s):
    return (s.replace("&amp;", "&").replace("&lt;", "<")
             .replace("&gt;", ">").replace("&apos;", "'").replace("&quot;", '"'))


def from_docx(path):
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    out = []
    for p in PARA.findall(xml):
        parts = []
        for r in RUN.findall(p):
            t = _unescape("".join(TXT.findall(r)))
            if not t:
                continue
            parts.append(f"<sup>{t}</sup>" if SUP.search(r) else t)
        line = "".join(parts).strip()
        if line:
            out.append(line)
    return "\n\n".join(out)


def from_pptx(path):
    from pptx import Presentation
    prs = Presentation(str(path))
    out = []
    for i, slide in enumerate(prs.slides, 1):
        out.append(f"=== Slide {i} ===")
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                out.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    out.append(" | ".join(cells))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                out.append(f"[Speaker notes] {notes}")
    return "\n\n".join(out)


def from_pdf(path):
    r = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                       capture_output=True, text=True, check=True)
    return PUA.sub("", r.stdout)


def extract(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    ext = path.suffix.lower()
    if ext == ".docx":
        text = from_docx(path)
    elif ext == ".pptx":
        text = from_pptx(path)
    elif ext == ".pdf":
        text = from_pdf(path)
    elif ext in (".md", ".txt", ".csv", ".tsv"):
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ValueError(f"unsupported file type: {ext}")
    if not text.strip():
        raise ValueError(f"extraction produced no text from {path.name}")
    return text


def extract_to_file(path, outdir):
    text = extract(path)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    # Suffix is part of the name: a .docx and its .pdf render share a stem and would
    # otherwise silently overwrite each other's audit copy.
    src = Path(path)
    dest = outdir / f"{src.stem}.{src.suffix.lstrip('.').lower()}.txt"
    dest.write_text(text, encoding="utf-8")
    return text, dest


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    t, d = extract_to_file(sys.argv[1], here / "extracted")
    print(f"{len(t)} chars -> {d}")
    print(f"superscript markers: {t.count('<sup>')}")
