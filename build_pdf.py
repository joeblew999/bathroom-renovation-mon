#!/usr/bin/env python3
"""Build the quote: one web page and the same page as a PDF, into out/.

One process, one straight line:

  1. load      project.load      read the five sources once, check them
  2. draw      draw_walls.draw_all   floor plan + wall elevations (warnings in red), as SVG text
  3. fill      tables.fill       the phases and the material list, references resolved
  4. html      Markdown → HTML, drawings appended one per page   → out/index.html
  5. pdf       that same page printed by Chromium (Playwright)   → out/bathroom-renovation-quote.pdf

These two files are the only output, always written together from the same page.
out/ is not committed; the GitHub workflow builds it the same way and publishes it to
GitHub Pages. The Markdown source is never rewritten.

Bad data stops the build with one ERROR line naming the file and the problem.

Usage:  python3 build_pdf.py [quote.md] [out-folder]
"""
import sys
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

from draw_walls import draw_all
from project import ProjectError, load
from tables import fill

PDF_NAME = "bathroom-renovation-quote.pdf"
TITLE = "รายละเอียดหน้างานห้องน้ำใหม่ / New Bathroom Work Details"
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


def html(doc, drawings):
    """The filled document plus the drawings (in the order given), one per page, as one HTML page."""
    body = markdown.markdown(doc, extensions=["tables", "sane_lists"])
    pages = "".join(f'<section class="drawing">{svg}</section>' for svg in drawings)
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
    """Run the whole pipeline. Returns the warnings. Raises ProjectError on bad data
    (before anything is written)."""
    p = load(md)
    page = html(fill(p), draw_all(p).values())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    pdf(page, out_dir / PDF_NAME)
    return p.warnings()


def main(argv):
    md = Path(argv[1] if len(argv) > 1 else "bathroom-renovation-quote.md")
    out = Path(argv[2] if len(argv) > 2 else "out")
    try:
        warnings = build(md, out)
    except ProjectError as e:
        sys.exit(f"ERROR: {e}")
    for where, w in warnings:
        print(f"WARNING ({where}): {w}")
    print(f"Wrote {out / 'index.html'} and {out / PDF_NAME} · {len(warnings)} warnings")


if __name__ == "__main__":
    main(sys.argv)
