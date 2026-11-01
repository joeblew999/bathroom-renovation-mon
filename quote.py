#!/usr/bin/env python3
"""Build the quote: one web page and the same page as a PDF, into out/.

The only place the three parts meet. Each part reads its own files and renders itself;
none of them knows the others exist:

  phases.py      phases.toml               → the phases section
  materials.py   materials.toml            → the material list
  room/          room.toml + layout.toml   → the floor plan and the wall elevations

The material list and the drawings both take their products from products.toml (products.py),
which this file loads once and hands to both. It puts the parts into the document skeleton
(bathroom-renovation-quote.md) and runs the two checks that need more than one part: the tile
boxes on the list against the tiles the room needs, and every product used somewhere. Then:

  html     Markdown → HTML, drawings appended one per page   → out/index.html
  pdf      that same page printed by Chromium (Playwright)   → out/bathroom-renovation-quote.pdf

Bad data stops the build with one ERROR line naming the file and the problem, before
anything is written. The Markdown skeleton is never rewritten.

Usage:  python3 quote.py [quote.md] [out-folder]
        python3 quote.py --check [quote.md]    (tile counts, total, warnings; no build)
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

import materials
import phases
import products
import room
from common import DataError, cli

PDF_NAME = "bathroom-renovation-quote.pdf"
STYLE = Path(__file__).with_name("style.css")      # the page's look: fonts, tables, page breaks


@dataclass(frozen=True)
class Quote:
    doc: str             # the filled-in Markdown
    svgs: dict           # {file name: svg text}
    work: phases.Work
    materials: materials.Materials
    room: room.Room
    tiles: list          # [(TilesNeeded, boxes planned)]
    warnings: list       # [(where, warning)]


# ---------- the one fact two parts share ----------
def tile_check(m, r):
    """[(tiles needed, boxes on the list)] per tile, and a warning where there are too few. A
    tile and its boxes are matched by product: both name the same one in products.toml."""
    tiles = [(t, m.boxes_of(t.product)) for t in r.tiles_needed()]
    return tiles, [("materials", f"{t.name} tile: {planned:g} boxes planned but {t.boxes} needed")
                   for t, planned in tiles if planned < t.boxes]


def tile_lines(r, tiles):
    """One line per tile: what the room needs, surface by surface, against the boxes planned."""
    lab = r.labels
    names = {"floor": (lab.th("floor"), lab.en("floor")), **{k: (w.th, w.en.lower()) for k, w in r.walls.items()}}
    out = []
    for t, planned in tiles:
        parts = tuple(" + ".join(f"{names[s][i]} {n}" for s, n in t.parts) for i in (0, 1))
        out.append(lab.both("tile_count", tile=(t.th, t.name), need=t.need, parts=parts, boxes=t.boxes,
                            planned=f"{planned:g}", spare=f"{planned * t.per_box - t.need:g}"))
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
    work = phases.load(md.with_name(phases.FILE))
    catalogue = products.load(md.with_name(products.FILE))
    m = materials.load(md.with_name(materials.FILE), catalogue)
    r = room.load(md.parent, catalogue)
    unused = [pid for pid in catalogue if pid not in m.products_used() | r.products_used]
    if unused:
        raise DataError(f"{products.FILE}: product '{unused[0]}' isn't on the material list or the drawings")
    tiles, tile_warnings = tile_check(m, r)
    skeleton = work.resolve(md.read_text(encoding="utf-8"))    # the skeleton may name a phase
    doc = fill(skeleton, md.name, {"phases": work.render(), "list": m.render()})
    return Quote(doc, r.render(), work, m, r, tiles, r.warnings() + tile_warnings)


def html(doc, svgs):
    """The filled document plus the drawings (in the order given), one per page, as one HTML page.
    The page title is the document's own first heading."""
    body = markdown.markdown(doc, extensions=["tables", "sane_lists"])
    title = next((line[2:].strip() for line in doc.splitlines() if line.startswith("# ")), "")
    pages = "".join(f'<section class="drawing">{svg}</section>' for svg in svgs)
    return (f'<!doctype html><html lang="th"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title}</title><style>{STYLE.read_text(encoding="utf-8")}</style></head><body>{body}{pages}</body></html>')


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
    print("\n".join(tile_lines(q.room, q.tiles)))
    print("Still to buy:", q.materials.total_cell(bold=False))
    for where, w in q.warnings:
        print(f"WARNING ({where}): {w}")
    print(f"Materials: {len(q.materials.lines)} items, {q.materials.on_site()} on site · "
          f"{len(q.warnings)} warnings")


def main(argv):
    args = argv[1:]
    if args[:1] == ["--check"]:
        check(Path(args[1] if len(args) > 1 else "bathroom-renovation-quote.md"))
        return
    md = Path(args[0] if args else "bathroom-renovation-quote.md")
    out = Path(args[1] if len(args) > 1 else "out")
    warnings = build(md, out)
    for where, w in warnings:
        print(f"WARNING ({where}): {w}")
    print(f"Wrote {out / 'index.html'} and {out / PDF_NAME} · {len(warnings)} warnings")


if __name__ == "__main__":
    cli(lambda: main(sys.argv))
