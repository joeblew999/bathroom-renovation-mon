#!/usr/bin/env python3
"""Tests for the bathroom pipeline — proves every check really fires.

Each test copies the document and the five data files into a temporary folder, breaks
one thing on purpose, then puts the quote together in this process:

    q = assemble(md)      phases + materials + drawings, the tile check, the filled document

and looks for the expected text in what comes back: the error message, the warnings, the
filled-in document or the drawings. No PDF is printed and the real files are never touched.

Usage:  python3 test_pipeline.py
"""
import re
import sys
import tempfile
from pathlib import Path

from build_pdf import assemble
from common import DataError
from materials import baht, name_cell

HERE = Path(__file__).resolve().parent
MD = "bathroom-renovation-quote.md"
LAYOUT = "layout.toml"
MATERIALS = "materials.toml"
SITE = "site.toml"
PHASES = "phases.toml"
PRODUCTS = "products.toml"


def set_key(toml, section, no, key, value):
    """Change `key` in the [[section]] entry with number `no` (adds it if missing)."""
    blocks = re.split(r"(?m)^(?=\[\[)", toml)
    for i, b in enumerate(blocks):
        if b.startswith(f"[[{section}]]") and re.search(rf"(?m)^no = {no}$", b):
            if re.search(rf"(?m)^{key} = ", b):
                blocks[i] = re.sub(rf"(?m)^{key} = .*$", f"{key} = {value}", b)
            else:
                blocks[i] = b.rstrip("\n") + f"\n{key} = {value}\n\n"
            return "".join(blocks)
    raise KeyError(f"[[{section}]] no = {no} not found")


def drop_key(toml, section, no, key):
    blocks = re.split(r"(?m)^(?=\[\[)", toml)
    for i, b in enumerate(blocks):
        if b.startswith(f"[[{section}]]") and re.search(rf"(?m)^no = {no}$", b):
            blocks[i] = re.sub(rf"(?m)^{key} = .*\n", "", b)
            return "".join(blocks)
    raise KeyError(f"[[{section}]] no = {no} not found")


def run(edit_layout=None, edit_md=None, edit_mat=None, edit_site=None, edit_phases=None, edit_products=None):
    """Assemble the quote from edited copies. Returns (warnings, text to search, quote): the
    ERROR line if the data was refused, else the warnings, the filled document and the drawings."""
    edits = {MD: edit_md, LAYOUT: edit_layout, MATERIALS: edit_mat, SITE: edit_site, PHASES: edit_phases,
             PRODUCTS: edit_products}
    with tempfile.TemporaryDirectory() as tmp:
        for name, edit in edits.items():
            text = (HERE / name).read_text(encoding="utf-8")
            (Path(tmp) / name).write_text(edit(text) if edit else text, encoding="utf-8")
        try:
            q = assemble(Path(tmp) / MD)
        except DataError as e:
            return [], f"ERROR: {e}", None
    warnings = [w for _, w in q.warnings]
    return warnings, "\n".join([*warnings, q.doc, *q.svgs.values()]), q


CLEAN = None                 # expect: no error and no warnings
# An expected text can also be a function of the quote that was built, so a test checks the
# rule ("a reference shows its step's number") rather than today's data ("step 1.10").
REAL = assemble(HERE / MD)


def next_step(number):
    """'1.10' -> '1.11'"""
    phase, step = number.split(".")
    return f"{phase}.{int(step) + 1}"


TESTS = [
    # (name, layout edit, md edit, text expected in the output[, site edit])
    ("real data is clean", None, None, CLEAN),
    ("joint: outlet 10 mm off a joint",
     lambda t: set_key(t, "main_wall", 4, "x", 490), None, "only 10 mm from a joint"),
    ("clash: toilet moved into the roll holder",
     lambda t: set_key(t, "main_wall", 9, "x", 1150), None, "Roll holder overlaps 9 Toilet"),
    ("wall end: heater pushed past the window wall",
     lambda t: set_key(t, "main_wall", 16, "x", 2950), None, "runs past the end of the wall"),
    ("part: shower unit moved without its fixings",
     lambda t: set_key(t, "main_wall", 13, "x", 2000), None, "is outside Shower unit with rain head"),
    ("part: fixing pointing at a missing item",
     lambda t: set_key(t, "main_wall", 14, "part", 99), None, "belongs to item 99, which is not in [[main_wall]]"),
    ("product: layout names a product that isn't in products.toml",
     lambda t: t.replace('product = "toilet"', 'product = "sink"'), None, "names product 'sink', which is not in products.toml"),
    ("data: entry without an English name",
     lambda t: drop_key(t, "main_wall", 2, "en"), None, "has no 'en'"),
    ("keys: a typo in a layout entry",
     lambda t: t.replace("x = 1500\n", "xx = 1500\n", 1), None, "unknown key 'xx'"),
    ("keys: a typo in site.toml", None, None, "[window] has unknown key 'widht'",
     lambda t: t.replace("width = 600", "widht = 600", 1)),
    ("links: two items with the same number",
     lambda t: set_key(t, "main_wall", 7, "no", 8), None, "number 8 is used twice"),
    ("links: a misspelt shape",
     lambda t: set_key(t, "main_wall", 8, "shape", '"rectangle"'), None, "has shape 'rectangle'"),
    ("links: an item with no x",
     lambda t: drop_key(t, "main_wall", 7, "x"), None, "(point) needs 'x'"),
    ("links: a rect with no height and no product",
     lambda t: drop_key(t, "main_wall", 12, "w"), None, "(zone) needs 'w'"),
    ("types: a number typed as text",
     lambda t: set_key(t, "main_wall", 9, "x", '"1500"'), None, "'x' must be a number"),
    ("data: broken TOML",
     lambda t: t + "\n[[main_wall\n", None, "is not valid TOML"),
    ("site: a number missing from site.toml",
     None, None, "[tiles.grey] has no 'top'", lambda t: t.replace("top = 2000\n", "", 1)),
    ("rules: the clearance from site.toml is printed on the drawings", None, None,
     lambda p: f"at least {p.drawings.min_clear} mm off a joint"),
    ("notes: a drawing note that refers to a phase is refused",
     lambda t: t.replace('note_en = "', 'note_en = "see phase {phase:tile} · ', 1), None, "has a reference in braces"),
    ("labels: a label filling in a name it doesn't have", None, None, "tile_top en uses {topp} (it can use: top)",
     lambda t: t.replace("tile top {top}", "tile top {topp}", 1)),

]

PRODUCT_TESTS = [
    # (name, products edit, expected) — the catalogue shared by the material list and the drawings
    ("products: a product's size reaches the drawings (door wider than the new wall)",
     lambda t: t.replace("size = { w = 800, h = 2000 }", "size = { w = 1400, h = 2000 }", 1), "does not fit in the new wall"),
    ("products: a product's size reaches its name on the list",
     lambda t: t.replace("size = { w = 500, h = 500 }", "size = { w = 450, h = 450 }", 1),
     "Grey tile TARA Stone Blast 450 × 450 mm"),
    ("products: a name showing a size the product doesn't have",
     lambda t: t.replace('name_en = "TPI AAC block"', 'name_en = "TPI AAC block {w} mm"', 1), "shows {w}, but its size has no w"),
    ("products: a product that isn't on the list or the drawings",
     lambda t: t + '\n[[product]]\nid = "spare"\nname_th = "x"\nname_en = "x"\n',
     "product 'spare' isn't on the material list or the drawings"),
]

MAT_TESTS = [
    # (name, materials edit, text expected in the warnings or the filled document)
    ("materials: the still-to-buy total is shown", None, lambda p: p.materials.total_cell()),
    ("materials: a price change flows into the total",
     lambda t: re.sub(r"(?m)^price = 799$", "price = 899", t, count=1),
     lambda p: f"about {baht(round(REAL.materials.still_to_buy()[0] + 100, -2))}"),
    ("materials: too few grey tile boxes",
     lambda t: re.sub(r"(?m)^  n = 9$", "  n = 5", t, count=1),
     lambda p: next(f"grey tile: {n:g} boxes planned but {t.boxes} needed" for t, n in p.tiles if t.colour == "grey")),
    ("materials: a status that isn't buy, bought, reused or supplied",
     lambda t: re.sub(r'(?m)^  status = "bought"$', '  status = "bough"', t, count=1), "has status 'bough'"),
    ("materials: an item with no quantity",
     lambda t: re.sub(r"(?m)^  n = 18$\n", "", t, count=1), "has no 'n'"),
    ("materials: a reused item with a price",
     lambda t: re.sub(r'(?m)^(id = .*\n)(\n  \[\[product\.use\]\]\n  group = .*\n  status = "reused")',
                      r"\1price = 10\n\2", t, count=1),
     "is reused, so it has no price"),
    ("materials: the list is in sections by group", None, lambda p: f"| **{p.materials.groups[0].th} / {p.materials.groups[0].en}** |"),
    ("materials: in a group, what is still to buy comes before what is on site", None,
     lambda p: next(f"| **{g.th} / {g.en}** | | | |\n| {name_cell(p.materials.in_order(g)[0])} |"
                    for g in p.materials.groups
                    if {m.status for m in p.materials.items if m.group == g.id} >= {"buy", "bought"}
                    and next(m for m in p.materials.items if m.group == g.id).status != "buy")),
    ("materials: an item naming a group that doesn't exist",
     lambda t: t.replace('group = "plumbing_basin"', 'group = "kitchen"', 1), "names group 'kitchen', which is not one of its groups"),
    ("keys: a typo in a material (sku written as skuu)",
     lambda t: t.replace("sku = ", "skuu = ", 1), "unknown key 'skuu'"),
    ("materials: a shop the code doesn't know",
     lambda t: t.replace('shop = "homepro"', 'shop = "lazada"', 1), "has shop = 'lazada'"),
    ("materials: an SKU that isn't the shop's kind of code",
     lambda t: re.sub(r'(?m)^sku = "(\d+)"$', 'sku = "HP-\\1"', t, count=1), "which isn't a HomePro code"),
    ("materials: the link is built from shop and SKU", None,
     lambda p: next(f"]({m.entry.link})<br>{m.entry.shop.name} {m.entry.sku}"
                    for m in p.materials.items if m.entry.sku)),
    ("materials: one takes the singular unit (en_one)",
     lambda t: t.replace('en_one = "bag"', 'en_one = "ONE-BAG"', 1), "| 1 ถุง / ONE-BAG × "),
    ("materials: more than one takes the plural (en_many)",
     lambda t: t.replace('en_many = "bags"', 'en_many = "MANY-BAGS"', 1), "| 2 ถุง / MANY-BAGS × "),
    ("materials: a unit that isn't defined",
     lambda t: t.replace('unit = "bag"', 'unit = "sack"', 1), "has unit = 'sack'"),
    ("products: the list names a product that isn't in products.toml",
     lambda t: t.replace('id = "aac_block"', 'id = "aac_blok"', 1), "product 'aac_blok' is not in products.toml"),
    ("types: approx written as text",
     lambda t: re.sub(r"(?m)^approx = true$", 'approx = "yes"', t, count=1), "'approx' must be true or false"),
    ("materials: a supplied item shows who brings it", None, "| ช่างไฟนำมา / electrician provides |"),
    ("materials: a supplied item with a price",
     lambda t: re.sub(r'(?m)^(id = .*\nunit = .*\n)(\n  \[\[product\.use\]\]\n  group = .*\n  status = "supplied")',
                      r"\1price = 10\n\2", t, count=1),
     "is supplied, so it has no price"),
    ("materials: a supplied item with nobody to bring it",
     lambda t: t.replace('by = "electrician"', 'by = "plumber"', 1), "has by = 'plumber'"),
    ("materials: still to buy with no price",
     lambda t: re.sub(r"(?m)^price = 400$\n", "", t, count=1), "is to buy but has no price"),
]

PHASE_TESTS = [
    # (name, phases edit, expected) — section 3 and every {step:id} reference
    ("phases: the steps are numbered", None, lambda p: f"| {p.phases.phases[0].steps[0].number} |"),
    ("phases: a reference resolves to its number", None,
     lambda p: f"marked in step {p.phases.numbers[('step', 'clear_mark')]}"),
    ("phases: inserting a step renumbers it and its references",
     lambda t: t.replace('[[phase.step]]\nid = "isolate"',
                         '[[phase.step]]\nid = "photos"\nth = "ถ่ายรูป"\nen = "Take photos"\n\n[[phase.step]]\nid = "isolate"', 1),
     lambda p: f"marked in step {next_step(REAL.phases.numbers[('step', 'clear_mark')])}"),
    ("phases: the tiling step points to the drawings for the clearance", None, "by the distance stated on the drawings"),
    ("phases: a reference of a kind phases.toml doesn't have",
     lambda t: t.replace("marked in step {step:clear_mark}", "marked in step {rule:min_clear}", 1), "{rule:min_clear} doesn't match"),
    ("phases: a reference to an id that doesn't exist",
     lambda t: t.replace("marked in step {step:clear_mark}", "marked in step {step:clean_up}", 1), "{step:clean_up} doesn't match"),
    ("keys: a typo in a step",
     lambda t: t.replace('en = "Take the debris', 'eng = "Take the debris', 1), "unknown key 'eng'"),
    ("phases: the same step id twice",
     lambda t: t.replace('id = "plate_off"', 'id = "isolate"', 1), "step id 'isolate' is used twice"),
]

DOC_TESTS = [
    # (name, md edit, expected) — the document skeleton
    ("document: a phase note resolves its phase reference", None,
     lambda p: f"plastered after first fix, in phase {p.phases.numbers[('phase', 'make_good')]}"),
    ("document: only phases and materials", None, "## 2. วัสดุทั้งหมด"),
    ("document: a generated block whose marker is missing",
     lambda t: t.replace("<!-- generated:list -->", "", 1), "marker <!-- generated:list -->"),
]


def main():
    failed = 0
    cases = [(t[0], dict(edit_layout=t[1], edit_md=t[2], edit_site=t[4] if len(t) > 4 else None), t[3])
             for t in TESTS] + \
            [(n, dict(edit_md=e), x) for n, e, x in DOC_TESTS] + \
            [(n, dict(edit_phases=e), x) for n, e, x in PHASE_TESTS] + \
            [(n, dict(edit_mat=e), x) for n, e, x in MAT_TESTS] + \
            [(n, dict(edit_products=e), x) for n, e, x in PRODUCT_TESTS]
    for name, kw, expect in cases:
        warnings, out, p = run(**kw)
        if callable(expect):
            expect = expect(p) if p else "(the data was refused, so there was no project to check)"
        ok = (not warnings and not out.startswith("ERROR")) if expect is CLEAN else expect in out
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print("      expected:", "no errors or warnings" if expect is CLEAN else expect)
            print("      got:", out.strip()[:800].replace("\n", "\n           "))
    print(f"\n{len(cases) - failed}/{len(cases)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
