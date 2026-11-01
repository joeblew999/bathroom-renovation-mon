#!/usr/bin/env python3
"""Build the quote: one web page and the same page as a PDF, into out/.

The only place the three parts meet. Each part reads its own file and renders itself:

  phases.py      phases.toml      → the work, phase by phase
  materials.py   materials.toml   → the materials list (and every product's names and size)
  room.py        room.toml        → the floor plan and the wall drawings

This file hands the products on the materials list to the room (for their sizes), hands the tiles
the room needs to the materials list's design check (materials_design_checks.py), and puts each part's
section into the template (bathroom-renovation-quote.md). Then:

  html     Markdown → HTML, drawings appended one per page   → out/index.html
  pdf      that same page printed by Chromium (Playwright)   → out/bathroom-renovation-quote.pdf

Bad data stops the build with one ERROR line naming the file and the problem, before
anything is written. A design problem (room_design_checks.py, materials_design_checks.py,
drawing_design_checks.py) doesn't
stop it: the page and the PDF are written with each problem in red under its drawing, and the
problems and their count are printed. The template is
never rewritten.

Usage:  python3 build.py [template.md] [out-folder]
        python3 build.py --publishable [template.md] [out-folder]  (the same, then an ERROR if there is
                                                                    any design problem: mise run ci)
        python3 build.py --summary [template.md]  (tile counts, total, design problems; no build)
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import markdown

import drawing_design_checks
import materials
import materials_design_checks
import phases
import room
from common import DataError, chromium, cli

TEMPLATE = "bathroom-renovation-quote.md"
PDF_NAME = "bathroom-renovation-quote.pdf"
STYLE = Path(__file__).with_name("style.css")      # the page's look: fonts, tables, page breaks


@dataclass(frozen=True)
class Quote:
    doc: str             # the filled-in Markdown
    svgs: list           # [svg text], one per drawing
    work: phases.Work
    materials: materials.Materials
    room: room.Room
    tiles: list          # [(TilesNeeded, boxes planned)]
    warnings: list       # [(where, (th, en))]


def tile_lines(r, tiles):
    """One line per tile: what the room needs, surface by surface, against the boxes planned."""
    lab = r.labels
    names = {"floor": (lab.th("floor"), lab.en("floor")), **{k: (w.th, w.en) for k, w in r.walls.items()}}
    out = []
    for t, planned in tiles:
        parts = tuple(r.symbols["plus"].join(f"{names[s][i]} {n}" for s, n in t.parts) for i in (0, 1))
        out.append(lab.both("tile_count", tile=(t.tile.th, t.tile.en), need=t.need, parts=parts, boxes=t.boxes,
                            planned=f"{planned:g}", spare=f"{planned * t.tile.per_box - t.need:g}"))
    return out


# ---------- putting it together ----------
def fill(template, name, sections):
    """The template with each <!-- section:NAME --> filled in."""
    doc = template
    for key, lines in sections.items():
        marker = f"<!-- section:{key} -->"
        if marker not in doc:
            raise DataError(f"{name}: marker {marker} not found")
        doc = doc.replace(marker, "\n".join(lines))
    return doc


def assemble(md):
    """Load the parts next to the template `md`, check what connects them, and fill the template."""
    md = Path(md)
    if not md.exists():
        raise DataError(f"{md} not found")
    work = phases.load(md.with_name(phases.FILE))
    m = materials.load(md.with_name(materials.FILE))
    r = room.load(md.with_name(room.FILE), m.products)
    tiles, tile_warnings = materials_design_checks.tile_check(m, r.tiles_needed())
    doc = fill(md.read_text(encoding="utf-8"), md.name, {"phases": work.render(), "materials": m.render()})
    more = {"floor": [w for _, w in tile_warnings]}
    svgs = r.render(more)
    # How the drawings read, measured as drawn; any problem is drawn again in red under its drawing.
    drawing_warnings = r.drawing_warnings(drawing_design_checks.check(svgs, STYLE.read_text(encoding="utf-8")))
    if drawing_warnings:
        for d, w in drawing_warnings:
            more.setdefault(d, []).append(w)
        svgs = r.render(more)
    return Quote(doc, svgs, work, m, r, tiles, r.warnings() + tile_warnings + drawing_warnings)


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
    page = chromium().new_page()
    page.set_content(page_html, wait_until="load")
    page.pdf(path=str(out), print_background=True, prefer_css_page_size=True)   # size and margins: style.css
    page.close()


def build(md, out_dir):
    """Run the whole pipeline. Returns (the design problems, the assumed values). Raises DataError on bad data
    (before anything is written)."""
    q = assemble(md)
    page = html(q.doc, q.svgs)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    pdf(page, out_dir / PDF_NAME)
    return q.warnings, assumed(q)


def summary(md):
    """Print the tile counts, the still-to-buy total and every design problem, without building."""
    q = assemble(md)
    print("\n".join(tile_lines(q.room, q.tiles)))
    print(f"{q.materials.labels.both('still_to_buy')}:", q.materials.total_cell(bold=False))
    print_warnings(q.warnings)
    print_assumed(assumed(q))
    print(f"Materials: {len(q.materials.lines)} items, {q.materials.on_site()} on site · "
          f"{problems(q.warnings)} · {values(assumed(q))}")


def assumed(q):
    """Every value the data marks as assumed, across the parts: [(where, key, value)] (README rule 10)."""
    return list(q.room.assumed) + list(q.materials.assumed)


def problems(warnings):
    """'0 design problems', '1 design problem', '4 design problems'."""
    return f"{len(warnings)} design problem{'' if len(warnings) == 1 else 's'}"


def values(guesses):
    """'0 assumed values', '1 assumed value', '6 assumed values'."""
    return f"{len(guesses)} assumed value{'' if len(guesses) == 1 else 's'}"


def print_assumed(guesses):
    """A warning, not a design problem: each value the data marks as assumed, until it is measured on site."""
    for where, key, value in guesses:
        print(f"ASSUMED ({where}): {key} = {value!r} — a stand-in; measure or check it on site, then replace it")


def print_warnings(warnings):
    for where, (_, en) in warnings:
        print(f"DESIGN PROBLEM ({where}): {en}")


def main(argv):
    args = argv[1:]
    publishable = args[:1] == ["--publishable"]
    if publishable:
        args = args[1:]
    if args[:1] == ["--summary"]:
        summary(Path(args[1] if len(args) > 1 else TEMPLATE))
        return
    md = Path(args[0] if args else TEMPLATE)
    out = Path(args[1] if len(args) > 1 else "out")
    warnings, guesses = build(md, out)
    print_warnings(warnings)
    print_assumed(guesses)
    print(f"Wrote {out / 'index.html'} and {out / PDF_NAME} · {problems(warnings)} · {values(guesses)}")
    if publishable and warnings:
        raise DataError(f"{problems(warnings)}, in red on the drawings in {out / PDF_NAME} — not publishable; "
                        f"fix them first")


if __name__ == "__main__":
    cli(lambda: main(sys.argv))
