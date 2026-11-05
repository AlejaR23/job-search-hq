"""Trim tailored CV markdown to one page by DELETING lines only, then build the .docx.


Nothing is reworded: every kept line or summary sentence is copied verbatim from the source CV, so no new claim
can appear. The check below fails loudly if that ever stops being true. Page fit is an estimate from real Arial
metrics (no Word needed); always glance at the file once on the phone.

Usage: python -I cv_onepage.py <source.md> <out.md> <out.docx>
"""
import re
import sys
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Emu, Pt, Twips
from PIL import ImageFont

FONT = Path(r'C:\Windows\Fonts\arial.ttf')
PAGE_W, MARGIN_X, MARGIN_Y = 12240, 1020, 850  # twips, same as the existing tailored CVs
TEXT_W = (PAGE_W - 2 * MARGIN_X) / 20  # points
PAGE_H = (15840 - 2 * MARGIN_Y) / 20
BUDGET = PAGE_H * 0.96  # keep a safety margin; Word wraps a little differently from this estimate
MIN_BULLETS = [3, 3, 2, 2, 1]  # newest role first; shrinks further only if the page still overflows
_fonts = {}


def width(text, size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        path = FONT.with_name('arialbd.ttf') if bold else FONT
        _fonts[key] = ImageFont.truetype(str(path), 200)
    return _fonts[key].getlength(text) * size / 200


def wrap_lines(text, size, avail, bold=False):
    lines, cur = 1, 0.0
    space = width(' ', size, bold)
    for word in text.split():
        w = width(word, size, bold)
        if cur and cur + space + w > avail:
            lines, cur = lines + 1, w
        else:
            cur = cur + (space if cur else 0) + w
    return lines


def parse(md):
    head, sections, name = [], [], None
    for raw in md.replace('\r\n', '\n').split('\n'):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith('## '):
            name = line[3:].strip()
            sections.append({'name': name, 'items': []})
        elif name is None:
            head.append(line)
        else:
            sections[-1]['items'].append(line)
    return head, sections


def entries(items):
    """Group a section's lines into [title, bullet, bullet...] entries; plain lines stay alone."""
    out = []
    for line in items:
        if line.startswith('**') or not out:
            out.append([line])
        else:
            out[-1].append(line)
    return out


def height(head, sections):
    h = 15 * 1.2 + 10 * 1.2 + 9 * 1.2 + 6  # name, tagline, contact
    for s in sections:
        h += 8 + 11 * 1.2 + 2  # section heading
        for line in s['items']:
            bullet = line.startswith('- ')
            text = re.sub(r'\*\*', '', line[2:] if bullet else line)
            bold = line.startswith('**') and not bullet
            avail = TEXT_W - (18 if bullet else 0)
            n = wrap_lines(text, 10, avail, bold)
            h += n * 10 * 1.15 + (1 if bullet else 5 if bold else 2)
    return h


def sentences(text):
    return re.findall(r'.+?(?:[.!?](?=\s|$)|$)', text)


def trim(md):
    head, sections = parse(md)
    by = {s['name']: s for s in sections}
    exp = by.get('Experience')
    roles = entries(exp['items']) if exp else []
    proj = entries(by['Projects']['items']) if 'Projects' in by else []

    def apply():
        if exp:
            exp['items'] = [l for r in roles for l in r]
        if 'Projects' in by:
            by['Projects']['items'] = [l for r in proj for l in r]

    apply()
    mins = list(MIN_BULLETS)
    summary = by.get('Summary')
    parts = sentences(summary['items'][0]) if summary else []

    def over():
        apply()
        if summary:
            summary['items'] = [' '.join(p.strip() for p in parts)]
        return height(head, sections) > BUDGET

    # 1: projects down to the first bullet each, 2: oldest-first bullet removal, 3: lower the minimums, 4: summary sentences
    for entry in proj:
        while over() and len(entry) > 2:
            entry.pop()
    for floor_drop in range(3):
        progress = True
        while over() and progress:
            progress = False
            for idx in range(len(roles) - 1, -1, -1):  # oldest role first
                floor = max(1, (mins[idx] if idx < len(mins) else 1) - floor_drop)
                if len(roles[idx]) - 1 > floor:
                    roles[idx].pop()
                    progress = True
                    if not over():
                        break
    while over() and len(parts) > 2:
        parts.pop()
    over()
    return head, sections


def render_md(head, sections):
    out = list(head) + ['']
    for s in sections:
        out += ['## ' + s['name']] + s['items'] + ['']
    return '\n'.join(out).rstrip() + '\n'


def contexts(text):
    """Yield (context, normalized line): context is the section plus the role/project title the line sits under."""
    section = title = ''
    for line in text.replace('\r\n', '\n').split('\n'):
        if not line.strip():
            continue
        if line.startswith('## '):
            section, title = line.strip(), ''
        elif line.startswith('**'):
            title = re.sub(r'\s+', ' ', line.strip())
        yield (section, title if not line.startswith('**') else ''), re.sub(r'\s+', ' ', line.strip())


def verify_subset(source, result):
    """Every kept line must be a whole source line under the same section and role; summary text must be whole
    source sentences in order. Nothing can be reworded, truncated, or moved under another role."""
    norm = lambda x: re.sub(r'\s+', ' ', x.strip())
    src_pairs = set(contexts(source))
    src_sentences = [norm(x) for l in source.replace('\r\n', '\n').split('\n') if l.strip() and not l.startswith(('#', '-', '**'))
                     for x in sentences(l)]
    pos = 0
    for pair in contexts(result):
        ctx, line = pair
        if pair in src_pairs:
            continue
        for x in (norm(y) for y in sentences(line)):
            if ctx[0] != '## Summary' or x not in src_sentences[pos:]:
                raise SystemExit('Not verbatim, refusing to write: ' + x[:80])
            pos = src_sentences.index(x, pos) + 1


def build_docx(head, sections, path):
    d = docx.Document()
    s = d.sections[0]
    s.page_width, s.page_height = Twips(PAGE_W), Twips(15840)
    s.left_margin = s.right_margin = Twips(MARGIN_X)
    s.top_margin = s.bottom_margin = Twips(MARGIN_Y)
    st = d.styles['Normal']
    st.font.name, st.font.size = 'Arial', Pt(10)

    def para(text, bold=False, size=None, center=False, before=0, after=2, style=None):
        p = d.add_paragraph(style=style)
        p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(before), Pt(after)
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return p

    sizes = [15, 10, 9]
    for i, line in enumerate(head):
        text = re.sub(r'^#\s+', '', line)
        p = para('', center=True)
        r = p.add_run(text)
        r.bold, r.font.size = i < 2, Pt(sizes[min(i, 2)])
    for sec in sections:
        p = para('', before=8, after=2)
        r = p.add_run(sec['name'].upper())
        r.bold, r.font.size = True, Pt(11)
        for line in sec['items']:
            bullet = line.startswith('- ')
            text = line[2:] if bullet else line
            p = para('', before=0 if (bullet or not line.startswith('**')) else 5, after=1 if bullet else 2,
                     style='List Bullet' if bullet else None)
            for piece in re.split(r'(\*\*[^*]+\*\*)', text):
                if piece.startswith('**') and piece.endswith('**') and len(piece) > 4:
                    p.add_run(piece[2:-2]).bold = True
                elif piece:
                    p.add_run(('  |  ' if piece.startswith(' | ') and line.startswith('**') else '') + piece.lstrip(' |').strip()
                              if piece.startswith(' | ') and line.startswith('**') else piece)
    d.save(path)


def main():
    src, out_md, out_docx = (Path(a) for a in sys.argv[1:4])
    if src.resolve() in (out_md.resolve(), out_docx.resolve()) or out_md.resolve() == out_docx.resolve():
        raise SystemExit('Outputs must be two new files and must not overwrite the source CV.')
    source = src.read_text(encoding='utf-8')
    head, sections = trim(source)
    result = render_md(head, sections)
    verify_subset(source, result)
    out_md.write_text(result, encoding='utf-8')
    build_docx(head, sections, out_docx)
    words = len(re.sub(r'[#*]', '', result).split())
    print(f'{src.stem}: {len(source.split())} -> {words} words, est {height(head, sections) / PAGE_H:.0%} of a page')


if __name__ == '__main__':
    main()
