#!/usr/bin/env python3
"""Tests for the bathroom pipeline — proves every check really fires.

Each test copies the template and the three data files into a temporary folder, breaks one
thing on purpose, then puts the quote together in this process:

    q = assemble(md)      phases + materials + room, the tile check, the filled document

and looks for the expected text in what comes back: the error message, the warnings, the
filled-in document or the drawings. No PDF is printed and the real files are never touched.

No test depends on today's numbers. A test picks what it breaks by what it is — "an item that
belongs to another item", "the floor tile's product", "a line still to buy" — edits it in the
loaded data, and works out the message it expects from the real data. So changing a price, a
position or a quantity in the data never breaks a test; only a broken check does. If the data
has nothing of the kind a test needs (no point on the wall, say), that test fails and says so.

Usage:  python3 test_pipeline.py
"""
import datetime
import sys
import tempfile
import tomllib
from pathlib import Path

import tomli_w

from common import DataError
from materials import STATUS, baht, name_cell
from build import assemble

HERE = Path(__file__).resolve().parent
MD = "bathroom-renovation-quote.md"
MATERIALS, ROOM, PHASES = "materials.toml", "room.toml", "phases.toml"
DATA = (MATERIALS, ROOM, PHASES)
RAW = {f: tomllib.loads((HERE / f).read_text(encoding="utf-8")) for f in DATA}
REAL = assemble(HERE / MD)
WALL = "main_wall"                 # the wall the layout tests use (a wall the code always draws)
CLEAN = None                       # expect: no error and no warnings


# ---------- finding things in the real data ----------
def find(items, what, cond=lambda e: True):
    for e in items:
        if cond(e):
            return e
    raise LookupError(f"the data has no {what}, so this test has nothing to break")


def wall():
    return REAL.room.walls[WALL]


def raw_item(d, no):
    return find(d["positions"][WALL], f"item {no} on the {WALL}", lambda e: str(e["no"]) == str(no))


def solids():
    """Items on the wall from layout.toml with a full box (they can clash or run off the end)."""
    nos = {str(e["no"]) for e in RAW[ROOM]["positions"][WALL]}
    out = [it for it in wall().items if it.no in nos and it.shape in ("rect", "circle")
           and None not in (it.x, it.w, it.y, it.h)]
    if len(out) < 2:
        raise LookupError(f"the {WALL} has fewer than two solid items, so nothing can clash")
    return out


def a_part():
    """An item that belongs to another item, and that item."""
    by_no = {it.no: it for it in wall().items}
    it = find(wall().items, f"item on the {WALL} that belongs to another", lambda i: i.part and i.x is not None)
    return it, by_no[it.part]


def an_entry(what, cond):
    return find(RAW[MATERIALS]["entry"], what, cond)


def has_status(status):
    return lambda e: any(ln["status"] == status for ln in e["line"])


# ---------- editing a copy ----------
def data(change):
    """An edit made on the loaded data: `change(d)` alters the dict, which is written back."""
    def edit(text):
        d = tomllib.loads(text)
        change(d)
        return tomli_w.dumps(d)
    return edit


def entry_by_id(d, pid):
    return find(d["entry"], f"entry '{pid}'", lambda e: e["id"] == pid)


def item_where(key, cond, change):
    """An edit of the first item on the wall whose `key` matches `cond`."""
    no = find(RAW[ROOM]["positions"][WALL], f"item on the {WALL} with a matching '{key}'",
              lambda e: key in e and cond(e[key]))["no"]
    return {ROOM: data(lambda d: change(raw_item(d, no)))}


def make(status, by=None, price=None):
    """An edit turning the first entry into one line of `status` (no shop; a price only if given;
    `by` = (Thai, English) for who brings it)."""
    def change(d):
        e = d["entry"][0]
        for k in ("price", "shop", "sku", "approx"):
            e.pop(k, None)
        if price is not None:
            e["price"] = price
        line = {k: v for k, v in e["line"][0].items() if k not in ("by_th", "by_en")}
        line["status"] = status
        if by:
            line["by_th"], line["by_en"] = by
        e["line"] = [line]
    return {MATERIALS: data(change)}


def run(edits):
    """Assemble the quote from copies, with `edits` = {file: edit(text) -> text}.
    Returns (warnings, text to search, quote) — the ERROR line if the data was refused."""
    with tempfile.TemporaryDirectory() as tmp:
        for name in (MD, *DATA):
            text = (HERE / name).read_text(encoding="utf-8")
            (Path(tmp) / name).write_text(edits[name](text) if name in edits else text, encoding="utf-8")
        try:
            q = assemble(Path(tmp) / MD)
        except DataError as e:
            return [], f"ERROR: {e}", None
    warnings = [w for _, w in q.warnings]
    return warnings, "\n".join([*warnings, q.doc, *q.svgs.values()]), q


# ---------- tests that need working out: each returns (edits, expected) ----------
def joint_test():
    it = find(wall().items, f"point on the {WALL}", lambda i: i.shape == "point")
    off = REAL.room.min_clear / 2
    x = REAL.room.tiles[wall().tile].size + off            # just past the first vertical joint
    return ({ROOM: data(lambda d: raw_item(d, it.no).update(x=x))},
            f"{it.no} {it.en}: x {x:g} is only {off:g} mm from a joint")


def clash_test():
    a, b = solids()[:2]
    return {ROOM: data(lambda d: raw_item(d, b.no).update(x=a.x, y=a.y))}, f"{a.no} {a.en} overlaps {b.no} {b.en}"


def wall_end_test():
    a = solids()[0]
    return ({ROOM: data(lambda d: raw_item(d, a.no).update(x=wall().length))},
            f"{a.no} {a.en}: runs past the end of the wall")


def part_test():
    it, parent = a_part()
    return ({ROOM: data(lambda d: raw_item(d, parent.no).update(x=parent.x + parent.w))},
            f"{it.no} {it.en}: x {it.x:g} is outside {parent.en}")


def missing_parent_test():
    it, _ = a_part()
    gone = max(int(i.no) for i in wall().items) + 99
    return ({ROOM: data(lambda d: raw_item(d, it.no).update(part=gone))},
            f"belongs to item {gone}, which is not in [[positions.{WALL}]]")


def duplicate_number_test():
    first = RAW[ROOM]["positions"][WALL][0]["no"]
    return {ROOM: data(lambda d: d["positions"][WALL][1].update(no=first))}, f"number {first} is used twice"


def tile_top_test():
    name = find(list(RAW[ROOM]["tiles"]), "tile in room.toml")
    return {ROOM: data(lambda d: d["tiles"][name].pop("top"))}, f"[tiles.{name}] has no 'top'"


def door_test():
    door = RAW[ROOM]["door"]["product"]
    return ({MATERIALS: data(lambda d: find(d["entry"], "door product", lambda p: p["id"] == door)["size"]
                            .update(w=REAL.room.new_wall_length + 100))},
            "does not fit in the new wall")


def size_in_name_test():
    pid = find(RAW[MATERIALS]["entry"], "product whose name shows {w}", lambda p: "{w}" in p["name_en"])["id"]

    def change(d):
        size = find(d["entry"], "-", lambda p: p["id"] == pid)["size"]
        size.update({k: 4321 for k in ("w", "h") if k in size})       # a tile stays square
    return {MATERIALS: data(change)}, "4321"


def price_test():
    e = an_entry("entry still to buy", lambda e: "price" in e and has_status("buy")(e))
    n = sum(ln["n"] for ln in e["line"] if ln["status"] == "buy")
    total, approx = REAL.materials.still_to_buy()
    new = total + 1000 * n
    want = f"{REAL.materials.labels.both('about')} {baht(round(new, -2))}" if approx else baht(new)
    return {MATERIALS: data(lambda d: entry_by_id(d, e["id"]).update(price=e["price"] + 1000))}, want


def tile_boxes_test():
    t = find(REAL.tiles, "tile with boxes on the list", lambda tp: tp[1] > 0)[0]
    e = an_entry(f"entry for '{t.product}'", lambda e: e["id"] == t.product)
    planned = sum(1 for ln in e["line"] if STATUS[ln["status"]].shop)       # one box per line

    def change(d):
        for ln in entry_by_id(d, t.product)["line"]:
            ln["n"] = 1
    return {MATERIALS: data(change)}, f"{t.name} tile: {planned:g} boxes planned but {t.boxes} needed"


def sku_test():
    e = an_entry("entry with a shop", lambda e: "shop" in e)
    shop = find(RAW[MATERIALS]["shop"], f"shop '{e['shop']}'", lambda s: s["id"] == e["shop"])
    return ({MATERIALS: data(lambda d: entry_by_id(d, e["id"]).update(sku="BAD-" + e["sku"]))},
            f"which isn't a {shop['name']} code")


def no_price_test():
    e = an_entry("entry still to buy", lambda e: "price" in e and has_status("buy")(e))
    return {MATERIALS: data(lambda d: entry_by_id(d, e["id"]).pop("price"))}, "is buy, so it needs a price"


def unit_test(n, form):
    """A line still to buy, with a unit, set to `n`: the unit's `form` shows (marked, so the
    test can't pass on text that happens to be in the data already)."""
    e = an_entry("entry with a unit and a line still to buy", lambda e: "unit" in e and has_status("buy")(e))
    th = find(RAW[MATERIALS]["unit"], f"unit '{e['unit']}'", lambda u: u["id"] == e["unit"])["th"]
    marker = f"{form.upper()}-UNIT"

    def change(d):
        find(d["unit"], "unit", lambda u: u["id"] == e["unit"])[form] = marker
        find(entry_by_id(d, e["id"])["line"], "line", lambda ln: ln["status"] == "buy")["n"] = n
    return {MATERIALS: data(change)}, f"| {n} {th} / {marker} × "


def buy_before_on_site(p):
    m = p.materials
    g = find(m.groups, "group with lines both to buy and on site",
             lambda g: {ln.status for ln in m.lines if ln.group == g.id} >= {"buy", "bought"})
    return f"| **{g.th} / {g.en}** | | | |\n| {name_cell(m.in_order(g)[0])} |"


def ref_test(insert):
    """A reference to the first step, added to the last phase — and, if `insert`, a new step
    put in front of it: the reference must follow it to its new number."""
    target = RAW[PHASES]["phase"][0]["step"][0]["id"]

    def change(d):
        last = d["phase"][-1].setdefault("step", [{"id": "ref_test", "th": "-", "en": "-"}])[0]
        last["en"] += f" · see step {{step:{target}}}"
        if insert:
            d["phase"][0]["step"].insert(0, {"id": "inserted_test", "th": "ใหม่", "en": "New step"})
    phase, step = REAL.work.numbers[("step", target)].split(".")
    return {PHASES: data(change)}, f"see step {phase}.{int(step) + insert}"


def duplicate_step_test():
    steps = RAW[PHASES]["phase"][0]["step"]
    return {PHASES: data(lambda d: d["phase"][0]["step"][1].update(id=steps[0]["id"]))}, f"step id '{steps[0]['id']}' is used twice"


def first_step(change):
    return {PHASES: data(lambda d: change(d["phase"][0]["step"][0]))}


def first_line(change):
    return {MATERIALS: data(lambda d: change(d["entry"][0]["line"][0]))}


def first_with(key, change):
    """An edit of the first entry that has `key`."""
    return lambda: ({MATERIALS: data(lambda d: change(find(d["entry"], f"entry with '{key}'", lambda e: key in e)))},)


def built(f):
    """An expectation read off the built quote."""
    return lambda p: f(p) if p else "(the data was refused, so there was no quote to look at)"


# ---------- the tests ----------
# (name, edits, expected) — expected is a text, CLEAN, or built(…) — or (name, make) where
# make() works out (edits, expected) from the real data when the test runs.
TESTS = [
    ("real data is clean", {}, CLEAN),
    # ---- the room and the layout: design rules (warnings) ----
    ("joint: a point moved just off a joint", joint_test),
    ("clash: an item moved onto another", clash_test),
    ("wall end: an item pushed past the end of the wall", wall_end_test),
    ("part: an item moved without the part that belongs to it", part_test),
    ("rules: the clearance from room.toml is printed on the drawings", {},
     built(lambda p: f"at least {p.room.min_clear} mm off a joint")),
    # ---- the room and the layout: bad data (errors) ----
    ("part: a part belonging to an item that isn't there", missing_parent_test),
    ("product: a drawn item naming a product that isn't on the material list",
     lambda: (item_where("product", lambda v: True, lambda e: e.update(product="no_such_product")),
              "names product 'no_such_product', which is not on the material list")),
    ("data: an item without an English name", {ROOM: data(lambda d: d["positions"][WALL][0].pop("en"))}, "has no 'en'"),
    ("keys: a typo in a positioned item", {ROOM: data(lambda d: d["positions"][WALL][0].update(xx=1))}, "unknown key 'xx'"),
    ("keys: a typo in room.toml", {ROOM: data(lambda d: d["window"].update(widht=1))}, "[window] has unknown key 'widht'"),
    ("links: two items with the same number", duplicate_number_test),
    ("links: a misspelt shape", {ROOM: data(lambda d: d["positions"][WALL][0].update(shape="rectangle"))}, "has shape 'rectangle'"),
    ("links: a point with no x",
     lambda: (item_where("shape", lambda v: v == "point", lambda e: e.pop("x")), "(point) needs 'x'")),
    ("links: a zone with no width",
     lambda: (item_where("shape", lambda v: v == "zone", lambda e: e.pop("w")), "(zone) needs 'w'")),
    ("types: a number typed as text",
     lambda: (item_where("x", lambda v: True, lambda e: e.update(x=str(e["x"]))), "'x' must be a number")),
    ("data: broken TOML", {ROOM: lambda t: t + "\n[[positions.main_wall\n"}, "is not valid TOML"),
    ("room: a tile with no tiling height", tile_top_test),
    ("notes: a drawing note that refers to a phase",
     lambda: (item_where("note_en", lambda v: True, lambda e: e.update(note_en="see {phase:x} " + e["note_en"])),
              "has a reference in braces")),
    ("labels: a label filling in a name it doesn't have",
     {ROOM: data(lambda d: d["labels"]["tile_top"].update(en=d["labels"]["tile_top"]["en"] + " {topp}"))},
     "tile_top en uses {topp} (it can use: top)"),
    # ---- products: on the material list, sizes used by the drawings ----
    ("products: a product's size reaches the drawings (door wider than the new wall)", door_test),
    ("products: a product's size reaches its name on the list", size_in_name_test),
    ("products: a name showing a size the product doesn't have",
     {MATERIALS: data(lambda d: find(d["entry"], "product without a size", lambda p: "size" not in p)
                      .update(name_en="sized {w}"))},
     "shows {w}, but its size has no w"),
    # ---- materials.toml ----
    ("materials: the still-to-buy total is shown", {}, built(lambda p: p.materials.total_cell())),
    ("materials: a price change flows into the total", price_test),
    ("materials: too few tile boxes for the room", tile_boxes_test),
    ("materials: a status that isn't buy, bought, reused or supplied",
     first_line(lambda ln: ln.update(status="bough")), "has status = 'bough'"),
    ("materials: a line with no quantity", first_line(lambda ln: ln.pop("n")), "has no 'n'"),
    ("materials: a line naming a group that doesn't exist",
     first_line(lambda ln: ln.update(group="kitchen")), "names group 'kitchen', which is not one of its groups"),
    ("materials: a reused item with a price", make("reused", price=10), "is reused, so it has no price"),
    ("materials: still to buy with no price", no_price_test),
    ("materials: the list is in sections by group", {},
     built(lambda p: f"| **{p.materials.groups[0].th} / {p.materials.groups[0].en}** |")),
    ("materials: in a group, what is still to buy comes before what is on site", {}, built(buy_before_on_site)),
    ("keys: a typo in an entry (sku written as skuu)",
     lambda: (*first_with("sku", lambda e: e.update(skuu=e.pop("sku")))(), "unknown key 'skuu'")),
    ("materials: a shop the file doesn't define",
     lambda: (*first_with("shop", lambda e: e.update(shop="lazada"))(), "has shop = 'lazada'")),
    ("materials: an SKU that isn't the shop's kind of code", sku_test),
    ("materials: the link is built from shop and SKU", {},
     built(lambda p: next(f"]({ln.entry.link})<br>{ln.entry.shop.name} {ln.entry.sku}"
                          for ln in p.materials.lines if ln.entry.sku))),
    ("materials: one takes the singular unit (en_one)", lambda: unit_test(1, "en_one")),
    ("materials: more than one takes the plural (en_many)", lambda: unit_test(3, "en_many")),
    ("materials: a unit that isn't defined",
     lambda: (*first_with("unit", lambda e: e.update(unit="sack"))(), "has unit = 'sack'")),
    ("types: approx written as text", {MATERIALS: data(lambda d: d["entry"][0].update(approx="yes"))},
     "'approx' must be true or false"),
    ("materials: a supplied item shows who brings it",
     make("supplied", by=("ช่าง-TEST", "BRINGER-TEST")), "| ช่าง-TEST / BRINGER-TEST |"),
    ("materials: a supplied item with a price", make("supplied", by=("ช่าง", "trade"), price=10),
     "is supplied, so it has no price"),
    ("materials: a supplied item with nobody to bring it", make("supplied"), "has no 'by_th'"),
    # ---- phases.toml ----
    ("phases: the steps are numbered", {}, built(lambda p: f"| {p.work.phases[0].steps[0].number} |")),
    ("phases: a reference resolves to its number", lambda: ref_test(insert=False)),
    ("phases: inserting a step renumbers it and its references", lambda: ref_test(insert=True)),
    ("phases: a reference of a kind phases.toml doesn't have",
     first_step(lambda s: s.update(en=s["en"] + " {rule:min_clear}")), "{rule:min_clear} doesn't match"),
    ("phases: a reference to an id that doesn't exist",
     first_step(lambda s: s.update(en=s["en"] + " {step:no_such_step}")), "{step:no_such_step} doesn't match"),
    ("keys: a typo in a step", first_step(lambda s: s.update(eng=s.pop("en"))), "unknown key 'eng'"),
    ("phases: the same step id twice", duplicate_step_test),
    # ---- the template ----
    ("document: each part's section goes where its marker is", {}, built(lambda p: p.work.render()[0])),
    ("document: a section marker missing from the template",
     {MD: lambda t: t.replace("<!-- section:materials -->", "", 1)}, "marker <!-- section:materials --> not found"),
    ("notes: a note in one language only",
     {PHASES: data(lambda d: d["section"].pop("note_en"))}, "has a note in one language only"),
    ("materials: the prices date reaches the section note",
     {MATERIALS: data(lambda d: d.update(prices_date=datetime.date(2030, 1, 2)))}, "02/01/2030"),
    ("materials: a group's note shows under its heading",
     {MATERIALS: data(lambda d: d["group"][0].update(note_th="GROUP-NOTE-TH", note_en="GROUP-NOTE-EN"))},
     "*GROUP-NOTE-TH*<br>*GROUP-NOTE-EN*"),
]


def main():
    failed = 0
    for test in TESTS:
        name = test[0]
        try:
            edits, expect = test[1:] if len(test) == 3 else test[1]()
            warnings, out, p = run(edits)
            if callable(expect):
                expect = expect(p)
            ok = (not warnings and not out.startswith("ERROR")) if expect is CLEAN else expect in out
        except LookupError as e:
            ok, expect, out = False, "(the test couldn't run)", str(e)
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print("      expected:", "no errors or warnings" if expect is CLEAN else expect)
            print("      got:", out.strip()[:800].replace("\n", "\n           "))
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
