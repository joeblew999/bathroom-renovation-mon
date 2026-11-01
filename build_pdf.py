#!/usr/bin/env python3
"""Build the quote: one web page and the same page as a PDF, into out/.

The only place the three parts meet. Each part reads its own files and renders itself;
none of them knows the others exist:

  phases.py      phases.toml               → the phases section
  materials.py   materials.toml            → the material list
  drawings.py    site.toml + layout.toml   → the floor plan and the wall elevations

This file puts them into the document skeleton (bathroom-renovation-quote.md) and checks
the one fact two parts share: the tile boxes on the material list against the tiles the
room needs (tile_check). Then:

  html     Markdown → HTML, drawings appended one per page   → out/index.html
  pdf      that same page printed by Chromium (Playwright)   → out/bathroom-renovation-quote.pdf

Bad data stops the build with one ERROR line naming the file and the problem, before
anything is written. The Markdown skeleton is never rewritten.

Usage:  python3 build_pdf.py [quote.md] [out-folder]
        python3 build_pdf.py --check [quote.md]    (tile counts, total, warnings; no build)
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

import drawings
import materials
import phases
from common import DataError

PDF_NAME = "bathroom-renovation-quote.pdf"
TITLE = "รายละเอียดหน้างานห้องน้ำใหม่ / New Bathroom Work Details"
COLOUR_TH = {"grey": "เทา", "white": "ขาว"}
CSS = """
  @page { size: A4; margin: 14mm 12mm; }
  body { font-family: "Helvetica", "Arial", "Loma", "Sarabun", "Noto Sans Thai", sans-serif;
         font-size: 9.5pt; line-height: 1.45; color: #111; }
  h1 { font-size: 17pt; margin: 0 0 8pt; }
  h2 { font-size: 13pt; margin: 16pt 0 6pt; border-bottom: 1px solid #999; padding-bottom: 2pt; }
  h3 { font-size: 11pt; margin: 12pt 0 4pt; }
  table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt; page-break-inside: auto; }
  tr { page-break-inside: avoid; }
  th, td { border: 1px solid #bbb; padding: 2.5pt 4pt; vertical-align: top; text-align: left; font-size: 9pt; }
  th { background: #eee; }
  code { font-size: 8.5pt; }
  blockquote { margin: 6pt 0; padding: 4pt 8pt; border-left: 3px solid #999; background: #f6f6f6; }
  a { color: #1a5276; word-break: break-all; }
  .drawing { page-break-before: always; text-align: center; }
  .drawing svg { width: 100%; height: auto; max-height: 265mm; }
"""


@dataclass(frozen=True)
class Quote:
    doc: str             # the filled-in Markdown
    svgs: dict           # {file name: svg text}
    phases: phases.Phases
    materials: materials.Materials
    drawings: drawings.Drawings
    tiles: list          # [(TilesNeeded, boxes planned)]
    warnings: list       # [(where, warning)]


# ---------- the one fact two parts share ----------
def tile_check(m, d):
    """[(tiles needed, boxes on the list)] per colour, and a warning where there are too few.
    A tile colour on the list that the room doesn't have is bad data, and stops the build."""
    have = [t.colour for t in d.tiles_needed()]
    for colour in m.tile_colours():
        if colour not in have:
            raise DataError(f"{materials.FILE}: tile = {colour!r} is not a tile on the drawings "
                            f"(they have: {', '.join(have)})")
    tiles = [(t, m.tile_boxes(t.colour)) for t in d.tiles_needed()]
    return tiles, [("materials", f"{t.colour} tile: {planned:g} boxes planned but {t.boxes} needed")
                   for t, planned in tiles if planned < t.boxes]


def tile_lines(d, tiles):
    names = {"floor": ("พื้น", "floor"), **{k: (w.th, w.en.lower()) for k, w in d.walls.items()}}
    out = []
    for t, planned in tiles:
        spare = planned * t.per_box - t.need
        d_th = " + ".join(f"{names[s][0]} {n}" for s, n in t.parts)
        d_en = " + ".join(f"{names[s][1]} {n}" for s, n in t.parts)
        out.append(f"กระเบื้อง{COLOUR_TH[t.colour]} {t.need} แผ่น ({d_th}) → ต้องใช้ {t.boxes} กล่อง "
                   f"วางแผนไว้ {planned:g} กล่อง (เหลือ {spare:g} แผ่น) / {t.colour} {t.need} tiles ({d_en}) "
                   f"→ {t.boxes} boxes needed, {planned:g} planned ({spare:g} spare tiles)")
    return out


# ---------- putting it together ----------
def fill(skeleton, name, blocks):
    """The skeleton with each <!-- generated:NAME --> … <!-- /generated --> block filled in."""
    for key, lines in blocks.items():
        pat = re.compile(rf"(<!-- generated:{key} -->\n).*?(\n<!-- /generated -->)", re.S)
        if not pat.search(skeleton):
            raise DataError(f"{name}: marker <!-- generated:{key} --> … <!-- /generated --> not found")
        skeleton = pat.sub(lambda mt: mt.group(1) + "\n".join(lines) + mt.group(2), skeleton)
    return skeleton


def assemble(md):
    """Load the three parts next to `md`, check what they share, and fill the skeleton."""
    md = Path(md)
    if not md.exists():
        raise DataError(f"{md} not found")
    ph = phases.load(md.with_name(phases.FILE))
    m = materials.load(md.with_name(materials.FILE))
    d = drawings.load(md.parent)
    tiles, tile_warnings = tile_check(m, d)
    skeleton = ph.resolve(md.read_text(encoding="utf-8"))      # the skeleton may name a phase
    doc = fill(skeleton, md.name, {"phases": ph.render(), "list": m.render()})
    return Quote(doc, d.render(), ph, m, d, tiles, d.warnings() + tile_warnings)


def html(doc, svgs):
    """The filled document plus the drawings (in the order given), one per page, as one HTML page."""
    body = markdown.markdown(doc, extensions=["tables", "sane_lists"])
    pages = "".join(f'<section class="drawing">{svg}</section>' for svg in svgs)
    return (f'<!doctype html><html lang="th"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{TITLE}</title><style>{CSS}</style></head><body>{body}{pages}</body></html>')


def pdf(page_html, out):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content(page_html, wait_until="load")
        page.pdf(path=str(out), format="A4", print_background=True,
                 margin=dict(top="14mm", bottom="14mm", left="12mm", right="12mm"))
        browser.close()


def build(md, out_dir):
    """Run the whole pipeline. Returns the warnings. Raises DataError on bad data
    (before anything is written)."""
    q = assemble(md)
    page = html(q.doc, q.svgs.values())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    pdf(page, out_dir / PDF_NAME)
    return q.warnings


def check(md):
    """Print the tile counts, the still-to-buy total and every warning, without building."""
    q = assemble(md)
    print("\n".join(tile_lines(q.drawings, q.tiles)))
    print("Still to buy:", materials.sum_cell(*q.materials.still_to_buy(), bold=False))
    for where, w in q.warnings:
        print(f"WARNING ({where}): {w}")
    items = q.materials.items
    print(f"Materials: {len(items)} items, {sum(1 for x in items if x.status in ('bought', 'reused'))} on site · "
          f"{len(q.warnings)} warnings")


def main(argv):
    args = argv[1:]
    try:
        if args[:1] == ["--check"]:
            check(Path(args[1] if len(args) > 1 else "bathroom-renovation-quote.md"))
            return
        md = Path(args[0] if args else "bathroom-renovation-quote.md")
        out = Path(args[1] if len(args) > 1 else "out")
        warnings = build(md, out)
    except DataError as e:
        sys.exit(f"ERROR: {e}")
    for where, w in warnings:
        print(f"WARNING ({where}): {w}")
    print(f"Wrote {out / 'index.html'} and {out / PDF_NAME} · {len(warnings)} warnings")


if __name__ == "__main__":
    main(sys.argv)
