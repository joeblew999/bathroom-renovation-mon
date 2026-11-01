#!/usr/bin/env python3
"""Tests for the bathroom pipeline — proves every check really fires.

Each test copies the document and the four data files into a temporary folder, breaks
one thing on purpose, then runs the pipeline stages in this process:

    p = load(md)  →  draw_all(p)  →  fill(p)

and looks for the expected text in what comes back: the error message, the warnings,
or the filled-in document. No PDF is printed and the real files are never touched.

Usage:  python3 test_pipeline.py
"""
import re
import sys
import tempfile
from pathlib import Path

from draw_walls import draw_all
from project import ProjectError, load
from tables import baht, fill, in_list_order, name_cell, sum_cell

HERE = Path(__file__).resolve().parent
MD = "bathroom-renovation-quote.md"
LAYOUT = "layout.toml"
MATERIALS = "materials.toml"
SITE = "site.toml"
PHASES = "phases.toml"


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


def run(edit_layout=None, edit_md=None, edit_mat=None, edit_site=None, edit_phases=None):
    """Run the stages on edited copies. Returns (warnings, text to search, project):
    the ERROR line if the data was refused, else the warnings and the filled document."""
    edits = {MD: edit_md, LAYOUT: edit_layout, MATERIALS: edit_mat, SITE: edit_site, PHASES: edit_phases}
    with tempfile.TemporaryDirectory() as tmp:
        for name, edit in edits.items():
            text = (HERE / name).read_text(encoding="utf-8")
            (Path(tmp) / name).write_text(edit(text) if edit else text, encoding="utf-8")
        try:
            p = load(Path(tmp) / MD)
            draw_all(p)
            doc = fill(p)
            warnings = [w for _, w in p.warnings()]
        except ProjectError as e:
            return [], f"ERROR: {e}", None
    return warnings, "\n".join(warnings) + "\n" + doc, p


CLEAN = None                 # expect: no error and no warnings
# An expected text can also be a function of the project that was built, so a test checks the
# rule ("a reference shows its step's number") rather than today's data ("step 1.10").
REAL = load(HERE / MD)


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
    ("product: layout names a product that isn't in site.toml",
     lambda t: t.replace('product = "toilet"', 'product = "sink"'), None, "product 'sink' is not in site.toml"),
    ("data: entry without an English name",
     lambda t: drop_key(t, "main_wall", 2, "en"), None, "has no 'en'"),
    ("keys: a typo in a layout entry",
     lambda t: t.replace("x = 1500\n", "xx = 1500\n", 1), None, "unknown key 'xx'"),
    ("keys: a typo in site.toml", None, None, "[door] has unknown key 'widht'",
     lambda t: t.replace("width = 800", "widht = 800", 1)),
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
     None, None, "[grey_tile] needs 'size'", lambda t: t.replace("size = 500\n", "", 1)),
    ("site: door wider than the new wall",
     None, None, "does not fit in the new wall", lambda t: t.replace("width = 800", "width = 1400", 1)),
]

MAT_TESTS = [
    # (name, materials edit, text expected in the warnings or the filled document)
    ("materials: the still-to-buy total is shown", None, lambda p: sum_cell(*p.still_to_buy())),
    ("materials: a price change flows into the total",
     lambda t: re.sub(r"(?m)^price = 799$", "price = 899", t, count=1),
     lambda p: f"about {baht(round(REAL.still_to_buy()[0] + 100, -2))}"),
    ("materials: too few grey tile boxes",
     lambda t: re.sub(r"(?m)^n = 9$", "n = 5", t, count=1),
     lambda p: next(f"grey tile: {t.planned:g} boxes planned but {t.boxes} needed" for t in p.tile_counts() if t.colour == "grey")),
    ("materials: a status that isn't buy, bought or reused",
     lambda t: re.sub(r'(?m)^status = "bought"$', 'status = "bough"', t, count=1), "has status 'bough'"),
    ("materials: an item with no quantity",
     lambda t: re.sub(r"(?m)^n = 18$\n", "", t, count=1), "has no 'n'"),
    ("materials: a reused item with a price",
     lambda t: re.sub(r'(?m)^(status = "reused"\n(?:.*\n)*?n = 1\n)', r"\1price = 10\n", t, count=1),
     "is reused, so it has no price"),
    ("materials: the list is in sections by group", None, lambda p: f"| **{p.groups[0].th} / {p.groups[0].en}** |"),
    ("materials: in a group, what is still to buy comes before what is on site", None,
     lambda p: next(f"| **{g.th} / {g.en}** | | | |\n| {name_cell(in_list_order(p, g)[0])} |"
                    for g in p.groups if {m.status for m in p.materials if m.group == g.id} >= {"buy", "bought"}
                    and next(m for m in p.materials if m.group == g.id).status != "buy")),
    ("materials: an item naming a group that doesn't exist",
     lambda t: t.replace('group = "plumbing_basin"', 'group = "kitchen"', 1), "names group 'kitchen', which is not one of its groups"),
    ("keys: a typo in a material (link written as lnk)",
     lambda t: t.replace("link = ", "lnk = ", 1), "unknown key 'lnk'"),
    ("links: a tile colour that doesn't exist",
     lambda t: re.sub(r'(?m)^tile = "grey"$', 'tile = "gray"', t, count=1), "tile = 'gray'"),
    ("types: approx written as text",
     lambda t: re.sub(r"(?m)^approx = true$", 'approx = "yes"', t, count=1), "'approx' must be true or false"),
    ("materials: still to buy with no price",
     lambda t: re.sub(r"(?m)^price = 400$\n", "", t, count=1), "is to buy but has no price"),
]

PHASE_TESTS = [
    # (name, phases edit, expected) — section 3 and every {step:id} reference
    ("phases: the steps are numbered", None, lambda p: f"| {p.phases[0].steps[0].number} |"),
    ("phases: a reference resolves to its number", None,
     lambda p: f"marked in step {p.numbers[('step', 'clear_mark')]}"),
    ("phases: inserting a step renumbers it and its references",
     lambda t: t.replace('[[phase.step]]\nid = "isolate"',
                         '[[phase.step]]\nid = "photos"\nth = "ถ่ายรูป"\nen = "Take photos"\n\n[[phase.step]]\nid = "isolate"', 1),
     lambda p: f"marked in step {next_step(REAL.numbers[('step', 'clear_mark')])}"),
    ("rules: the tiling note quotes the clearance from site.toml", None,
     lambda p: f"at least {p.min_clear:g} mm off a joint"),
    ("rules: a reference to a rule that doesn't exist",
     lambda t: t.replace("{rule:min_clear} mm", "{rule:min_gap} mm", 1), "{rule:min_gap} doesn't match site.toml [rules]"),
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
     lambda p: f"plastered after first fix, in phase {p.numbers[('phase', 'make_good')]}"),
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
            [(n, dict(edit_mat=e), x) for n, e, x in MAT_TESTS]
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
