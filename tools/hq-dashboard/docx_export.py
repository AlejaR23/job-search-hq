"""Markdown to a plain, ATS-friendly .docx: headings, bullets, paragraphs, **bold** runs."""
import re

import docx
from docx.shared import Pt
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE


def plain(s):
    return re.sub("[\ud800-\udfff]", "", ILLEGAL_CHARACTERS_RE.sub("", s.replace("\x0b", "\n").replace("\x0c", "\n")))


def md_to_docx(md, path):
    # Plain, ATS-friendly: headings, bullets, paragraphs, **bold** runs. Good enough for a draft to edit in Word or Pages.
    d = docx.Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(11)
    for line in plain(md).replace("\r\n", "\n").split("\n"):
        s = line.rstrip()
        if not s.strip():
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m:
            d.add_heading(m.group(2).strip(), level=len(m.group(1)))
            continue
        b = re.match(r"^\s*[-*•]\s+(.*)", s)
        p = d.add_paragraph(style="List Bullet" if b else None)
        text = b.group(1) if b else s
        for part in re.split(r"(\*\*[^*]+\*\*)", text):
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                p.add_run(part[2:-2]).bold = True
            elif part:
                p.add_run(part)
    d.save(path)
