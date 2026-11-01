#!/usr/bin/env python3
"""Tests for the bathroom pipeline — proves every check really fires.

Each test copies the template and the three data files into a temporary folder, breaks one
thing on purpose, then puts the quote together in this process:

    q = assemble(md)      phases + materials + room, the tile check, the filled document

and looks for the expected text in what comes back: the error message, the warnings, the tile
counts, the filled-in document or the drawings. No PDF is printed and the real files are never
touched.

No test depends on today's numbers or wording. A test picks what it breaks by what it is — "an
item that belongs to another item", "a product still to buy with a shop" — edits it in the loaded
data, and works out the message it expects from the real data and its labels. So changing a
price, a position, a quantity or a label never breaks a test; only a broken check does. If the
data has nothing of the kind a test needs, that test fails and says so.

There is a test for every check in the code: every DataError (bad data) and every design-rule
warning.

Usage:  python3 test_pipeline.py
"""
import datetime
import html
import json
import math
import re
import sys
import tempfile
import tomllib
from pathlib import Path

import materials
import phases
import room
from build import assemble, tile_lines
from common import DataError

HERE = Path(__file__).resolve().parent
MD = "bathroom-renovation-quote.md"
MATERIALS, ROOM, PHASES = materials.FILE, room.FILE, phases.FILE
DATA = (MATERIALS, ROOM, PHASES)
RAW = {f: tomllib.loads((HERE / f).read_text(encoding="utf-8")) for f in DATA}
CLEAN = None                       # expect: no error and no warnings


# ---------- finding things in the real data ----------
def find(items, what, cond=lambda e: True):
    for e in items:
        if cond(e):
            return e
    raise LookupError(f"the data has no {what}, so this test has nothing to break")


def real():
    """The real quote, put together once."""
    if not hasattr(real, "q"):
        real.q = assemble(HERE / MD)
    return real.q


def wall_raw(d=None):
    """A drawn wall with items, as written in room.toml (in `d`, an edited copy, if given)."""
    wid = find(RAW[ROOM]["wall"], "drawn wall with items", lambda w: w["drawn"] and w.get("item"))["id"]
    return find((d or RAW[ROOM])["wall"], wid, lambda w: w["id"] == wid)


def wall():
    return real().room.walls[wall_raw()["id"]]


def raw_item(d, id_):
    return find(wall_raw(d)["item"], f"item {id_}", lambda e: e["id"] == id_)


def solids():
    """Items on the wall from room.toml with a full box (they can clash or run off the end)."""
    ids = {e["id"] for e in wall_raw()["item"]}
    out = [it for it in wall().items if it.id in ids and it.shape in ("rect", "circle")
           and None not in (it.x, it.w, it.y) and (it.h is not None or it.shape == "circle")]
    if len(out) < 2:
        raise LookupError("the wall has fewer than two solid items, so nothing can clash")
    return out


def a_part():
    """An item that belongs to another item, and that item."""
    items = {it.id: it for it in wall().items}
    it = find(wall().items, "item that belongs to another", lambda i: i.part and i.x is not None)
    return it, items[it.part]


def an_entry(what, cond):
    return find(RAW[MATERIALS]["entry"], what, cond)


def has_status(status):
    return lambda e: any(ln["status"] == status for ln in e["line"])


def to_buy_with_shop(e):
    return "price" in e and "shop" in e and has_status("buy")(e)


def steps(d):
    return [s for ph in d["phase"] for s in ph.get("step", [])]


def a_step():
    return find(steps(RAW[PHASES]), "step")


def warn(key, **values):
    """A warning as the data words it (its English), from the room's labels."""
    return real().room.labels.en(key, **values)


# ---------- editing a copy ----------
def toml(v):
    """A value as TOML, every table and list inside it inline, so every key keeps its place."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float, datetime.date)):
        return v.isoformat() if isinstance(v, datetime.date) else repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ", ".join(toml(x) for x in v) + "]"
    return "{ " + ", ".join(f"{key(k)} = {toml(x)}" for k, x in v.items()) + " }"


def key(k):
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else json.dumps(k, ensure_ascii=False)


def dump(d):
    """A whole data file as TOML, keeping the order of every key (the file's own values first, then
    each table and list of tables, everything inside them inline)."""
    def tables(v):
        return isinstance(v, dict) or (isinstance(v, list) and v and all(isinstance(x, dict) for x in v))
    out = [f"{key(k)} = {toml(v)}" for k, v in d.items() if not tables(v)]
    for k, v in d.items():
        for head, entry in ([(f"[{key(k)}]", v)] if isinstance(v, dict) else
                            [(f"[[{key(k)}]]", e) for e in v] if tables(v) else []):
            out += ["", head] + [f"{key(a)} = {toml(b)}" for a, b in entry.items()]
    return "\n".join(out) + "\n"


def data(change):
    """An edit made on the loaded data: `change(d)` alters the dict, which is written back with
    every key in its place."""
    def edit(text):
        d = tomllib.loads(text)
        change(d)
        return dump(d)
    return edit


def by_id(items, id_):
    return find(items, f"entry '{id_}'", lambda e: e["id"] == id_)


def put(e, key, value, fields):
    """Set e[key] = value, keeping the keys in the declared order."""
    e[key] = value
    ordered = {k: e[k] for k in fields if k in e}
    e.clear()
    e.update(ordered)


def edit_step(change, sid=None):
    """An edit of a step (by its id, or any step)."""
    sid = sid or a_step()["id"]
    return {PHASES: data(lambda d: change(by_id(steps(d), sid)))}


def edit_entry(cond, what, change):
    """An edit of the first product that matches."""
    pid = an_entry(what, cond)["id"]
    return {MATERIALS: data(lambda d: change(by_id(d["entry"], pid)))}


def edit_line(cond, what, change):
    """An edit of the first line of the first product that matches."""
    return edit_entry(cond, what, lambda e: change(e["line"][0]))


def edit_item(cond, what, change):
    """An edit of an item on the wall."""
    iid = find(wall_raw()["item"], what, cond)["id"]
    return {ROOM: data(lambda d: change(raw_item(d, iid)))}


def make(status, by=None, price=None):
    """An edit turning a product with a shop into one line of `status`, with no shop; a price only if
    given; `by` = (Thai, English) for who brings it."""
    def change(e):
        for k in ("price", "shop", "sku", "approx"):
            e.pop(k, None)
        if price is not None:
            put(e, "price", price, materials.ENTRY)
        line = {k: v for k, v in e["line"][0].items() if k not in ("by_th", "by_en")}
        line["status"] = status
        if by:
            line["by_th"], line["by_en"] = by
        e["line"] = [line]
    return edit_entry(to_buy_with_shop, "product still to buy with a shop", change)


def run(edits):
    """Assemble the quote from copies, with `edits` = {file: edit(text) -> text, or None to leave
    the file out}. Returns (warnings, text to search, quote) — the ERROR line if the data was refused."""
    with tempfile.TemporaryDirectory() as tmp:
        for name in (MD, *DATA):
            if name in edits and edits[name] is None:
                continue
            text = (HERE / name).read_text(encoding="utf-8")
            (Path(tmp) / name).write_text(edits[name](text) if name in edits else text, encoding="utf-8")
        try:
            q = assemble(Path(tmp) / MD)
        except DataError as e:
            return [], f"ERROR: {e}", None
    warnings = [x for _, w in q.warnings for x in w]
    return warnings, "\n".join([*warnings, *tile_lines(q.room, q.tiles), q.doc, *q.svgs]), q


def built(f):
    """An expectation read off the built quote."""
    return lambda p: f(p) if p else "(the data was refused, so there was no quote to look at)"


# ---------- tests that need working out: each returns (edits, expected) ----------
def joint_test(lang="en"):
    it = find(wall().items, "point on the wall", lambda i: i.shape == "point")
    off = real().room.min_clear / 2
    x = real().room.tiles[wall().tile].size + off            # just past the first vertical joint
    lab = real().room.labels
    want = getattr(lab, lang)("warn_joint", item=it.label(), axis=real().room.symbols["axis_x"], v=f"{x:g}",
                              d=f"{off:g}")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(x=x))}, want


def joint_y_test():
    it = find(wall().items, "point below the tile top", lambda i: i.shape == "point" and i.y < real().room.tiles[wall().tile].top)
    t = real().room.tiles[wall().tile]
    off = real().room.min_clear / 2
    y = t.size + off                                         # just above the first horizontal joint
    return ({ROOM: data(lambda d: raw_item(d, it.id).update(y=y))},
            warn("warn_joint", item=it.label(), axis=real().room.symbols["axis_y"], v=f"{y:g}", d=f"{off:g}"))


def tile_top_joint_test():
    """The tile top edge counts as a joint: a point just below it is warned about."""
    it = find(wall().items, "point on the wall", lambda i: i.shape == "point")
    top, off = real().room.tiles[wall().tile].top, real().room.min_clear / 2
    return ({ROOM: data(lambda d: raw_item(d, it.id).update(y=top - off))},
            warn("warn_joint", item=it.label(), axis=real().room.symbols["axis_y"], v=f"{top - off:g}", d=f"{off:g}"))


def on_joint_test():
    """A hole exactly on a joint is allowed (the screws go either side): no warning."""
    it = find(wall().items, "point on the wall", lambda i: i.shape == "point")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(x=real().room.tiles[wall().tile].size))}, CLEAN


def above_tiles_test():
    """No joints above the tiling: a point well above the tile top, near where a vertical joint would be,
    gets no warning."""
    it = find(wall().items, "point that belongs to nothing", lambda i: i.shape == "point" and not i.part)
    t = real().room.tiles[wall().tile]
    return {ROOM: data(lambda d: raw_item(d, it.id).update(x=t.size + real().room.min_clear / 2,
                                                            y=t.top + t.size))}, CLEAN


def point_off_wall_test():
    it = find(wall().items, "point on the wall", lambda i: i.shape == "point")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(x=wall().length + 100))}, warn("warn_off_wall", item=it.label())


def zone_off_wall_test():
    z = find(wall().items, "zone on the wall", lambda i: i.shape == "zone")
    return {ROOM: data(lambda d: raw_item(d, z.id).update(x=wall().length - z.w / 4))}, warn("warn_off_wall", item=z.label())


def ceiling_test():
    it = find(solids(), "box on the wall", lambda i: i.shape == "rect")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(y=real().room.ceiling))}, warn("warn_off_wall", item=it.label())


def off_floor_test():
    it = find(real().room.floor, "floor item", lambda i: i.shape == "rect")
    return ({ROOM: data(lambda d: find(d["floor"]["item"], it.id, lambda e: e["id"] == it.id).update(x=real().room.length))},
            warn("warn_off_floor", item=it.label()))


def tile_short_on_plan_test():
    """The tile-box shortage shows red on the floor plan, not only in the terminal."""
    edits, want = tile_boxes_test()
    return edits, f"{RAW[ROOM]['symbols']['warning']} {html.escape(want)}</text>"


def clash_test():
    a, b = solids()[:2]
    return {ROOM: data(lambda d: raw_item(d, b.id).update(x=a.x, y=a.y))}, \
        warn("warn_overlap", a=a.label(), b=b.label())


def round_clash_test():
    """A round item (its size is just a width) moved onto another item: warned about."""
    c = find(solids(), "round item on the wall", lambda i: i.shape == "circle")
    b = find(solids(), "other solid item", lambda i: i is not c)
    return {ROOM: data(lambda d: raw_item(d, c.id).update(x=b.x, y=b.y))}, \
        warn("warn_overlap", **dict(zip("ab", (x.label() for x in sorted((c, b), key=wall().items.index)))))


def wall_end_test():
    a = solids()[0]
    return {ROOM: data(lambda d: raw_item(d, a.id).update(x=wall().length))}, warn("warn_off_wall", item=a.label())


def part_outside_test():
    it, parent = a_part()
    moved = parent.x + parent.w
    return ({ROOM: data(lambda d: raw_item(d, parent.id).update(x=moved))},
            warn("warn_outside", item=it.label(), axis=real().room.symbols["axis_x"], v=f"{it.x:g}",
                 parent=(parent.th, parent.en), low=f"{moved - parent.w / 2:g}", high=f"{moved + parent.w / 2:g}"))


def part_above_test():
    it, parent = a_part()
    y = parent.y + parent.h                                  # above its parent's top edge
    return ({ROOM: data(lambda d: raw_item(d, it.id).update(y=y))},
            warn("warn_above", item=it.label(), axis=real().room.symbols["axis_y"], v=f"{y:g}",
                 parent=(parent.th, parent.en)))


def column_wall():
    """The column's wall, as written, and as worked out."""
    wid = RAW[ROOM]["column"]["wall"]
    return wid, real().room.walls[wid]


def add_item(wid, item, first=False):
    """An edit adding an item to a wall (drawn, so it can have items), last or first."""
    def change(d):
        w = by_id(d["wall"], wid)
        w["drawn"] = True
        items = w.setdefault("item", [])
        items.insert(0 if first else len(items), item)
    return {ROOM: data(change)}


def a_point_on(wid, x, y):
    return add_item(wid, {"id": "test_point", "th": "จุดทดสอบ", "en": "Test point", "shape": "point", "x": x, "y": y})


def column_clash_test():
    wid, w = column_wall()
    col = find(w.items, "the column", lambda i: i.shape == "column")

    box = {"id": "test_box", "th": "กล่องทดสอบ", "en": "Test box", "shape": "rect",
           "x": col.x, "y": col.y, "w": col.w, "h": col.h / 4}
    n = 1                                                       # the test box comes first on its wall
    return add_item(wid, box, first=True), warn("warn_overlap", a=(f"{n} กล่องทดสอบ", f"{n} Test box"),
                                      b=(f"{int(col.no) + 1} {col.th}", f"{int(col.no) + 1} {col.en}"))


def door_joint_test():
    """No tile joint is drawn inside the door opening: where one tile from the wall's start would end,
    inside the opening, the column's wall drawing has no joint line (px from room.py's own layout)."""
    wid, w = column_wall()
    door = find(w.items, "the door", lambda i: i.shape == "door")
    k = real().room.tiles[w.tile].size
    if not door.x - door.w / 2 < k < door.x + door.w / 2:
        raise LookupError("one tile from the wall's start isn't inside the door opening, so there is nothing to test")
    x = room.WALL_MARGINS[0] + (w.length - k) * room.WALL_SCALE
    title = real().room.labels.en("elevation_title", wall=(w.th, w.en))

    def expect(p):                                   # the column's wall drawing, and only it
        svg = find(p.svgs, "the column's wall drawing", lambda s: title in s)
        return title if f'<line class="joint" x1="{x}"' not in svg else f"(no joint line at x {k:g} on {w.en})"
    return {ROOM: data(lambda d: by_id(d["wall"], wid).update(drawn=True))}, built(expect)


def lintel_short_test():
    lid = RAW[ROOM]["lintel"]["product"]
    return {MATERIALS: data(lambda d: by_id(d["entry"], lid)["size"].update(w=1))}, "is shorter than the door and its bearing"


def point_in_opening_test():
    w = find(real().room.walls.values(), "wall with a window and a point",
             lambda w: w.drawn and any(i.shape == "opening" for i in w.items) and any(i.shape == "point" for i in w.items))
    win = find(w.items, "window", lambda i: i.shape == "opening")
    pt = find(w.items, "point", lambda i: i.shape == "point")
    edit = {ROOM: data(lambda d: find(by_id(d["wall"], w.id)["item"], pt.id, lambda e: e["id"] == pt.id).update(x=win.x, y=win.y))}
    return edit, warn("warn_overlap", a=pt.label(), b=win.label())


def below_floor_test():
    it = find(solids(), "box on the wall", lambda i: i.shape == "rect")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(y=it.h / 4))}, warn("warn_off_wall", item=it.label())


def off_wall_start_test():
    """A box poking out past the wall's start (x = 0)."""
    it = find(solids(), "box on the wall", lambda i: i.shape == "rect")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(x=it.w / 4))}, warn("warn_off_wall", item=it.label())


def off_floor_y_test():
    it = find(real().room.floor, "floor item", lambda i: i.shape == "rect")
    return ({ROOM: data(lambda d: find(d["floor"]["item"], it.id, lambda e: e["id"] == it.id).update(y=real().room.width))},
            warn("warn_off_floor", item=it.label()))


def money_test():
    """A price that isn't whole baht shows to the satang, so the line adds up as shown."""
    e = an_entry("product still to buy", lambda e: "price" in e and has_status("buy")(e))
    m = real().materials
    return ({MATERIALS: data(lambda d: by_id(d["entry"], e["id"]).update(price=e["price"] + 0.4))},
            f"{m.symbols['times']} {m.symbols['currency']}{e['price'] + 0.4:,.2f}")


def missing_parent_test():
    it, _ = a_part()
    return {ROOM: data(lambda d: raw_item(d, it.id).update(part="no_such_item"))}, \
        "belongs to 'no_such_item', which isn't on the same wall"


def tile_boxes_test():
    t = find(real().tiles, "tile with boxes on the list", lambda tp: tp[1] > 0)[0]
    e = an_entry(f"entry for '{t.tile.product}'", lambda e: e["id"] == t.tile.product)
    planned = sum(1 for ln in e["line"] if materials.STATUS[ln["status"]].shop)       # one box per line

    def change(d):
        for ln in by_id(d["entry"], t.tile.product)["line"]:
            ln["n"] = 1
    return {MATERIALS: data(change)}, \
        real().room.labels.en("tile_short", tile=(t.tile.th, t.tile.en), planned=f"{planned:g}", boxes=t.boxes)


def cut_row_test():
    """A tiling height that isn't a whole number of tiles: the cut row is counted."""
    w = wall()
    t = real().room.tiles[w.tile]
    top = t.top // t.size * t.size + 1                         # one mm into a row: a cut row
    n = (t.top // t.size + 1) * math.ceil(w.tiled_run / t.size)
    return {ROOM: data(lambda d: by_id(d["tile"], t.id).update(top=top))}, f"{w.en} {n}"


def door_test():
    door = RAW[ROOM]["door"]["product"]
    length = real().room.walls[RAW[ROOM]["column"]["wall"]].length
    return {MATERIALS: data(lambda d: by_id(d["entry"], door)["size"].update(w=length))}, "doesn't fit beside the column"


def size_in_name_test():
    pid = an_entry("product whose detail shows {w_cm} × {h_cm}",
                   lambda p: "{w_cm} × {h_cm}" in p["detail_en"])["id"]
    return ({MATERIALS: data(lambda d: by_id(d["entry"], pid)["size"].update(w=4321, h=4321))},
            f"{4321 / 10:g} × {4321 / 10:g}")


def price_test():
    e = an_entry("entry still to buy", lambda e: "price" in e and has_status("buy")(e))
    n = sum(ln["n"] for ln in e["line"] if ln["status"] == "buy")
    m = real().materials
    total, approx = m.still_to_buy()
    new = total + 1000 * n
    want = f"{m.labels.both('about')} {m.money(round(new / m.round_approx) * m.round_approx)}" if approx else m.money(new)
    return {MATERIALS: data(lambda d: by_id(d["entry"], e["id"]).update(price=e["price"] + 1000))}, want


def sku_test():
    e = an_entry("entry with a shop", lambda e: "shop" in e)
    shop = by_id(RAW[MATERIALS]["shop"], e["shop"])
    return ({MATERIALS: data(lambda d: by_id(d["entry"], e["id"]).update(sku="BAD-" + e["sku"]))},
            f"which isn't a {shop['en']} code")


def no_price_test():
    e = an_entry("entry still to buy", lambda e: "price" in e and has_status("buy")(e))
    return {MATERIALS: data(lambda d: by_id(d["entry"], e["id"]).pop("price"))}, "is buy, so it needs a price"


def reused_with_shop_test():
    def change(e):
        e.pop("price")
        e["line"] = [{**e["line"][0], "status": "reused"}]
    return edit_entry(to_buy_with_shop, "product still to buy with a shop", change), "is reused, so it has no shop and sku"


def make_approx_no_price():
    """A product bought (its price allowed, not needed) with approx but no price."""
    def change(e):
        e.pop("price", None)
        put(e, "approx", True, materials.ENTRY)
        e["line"] = [{**e["line"][0], "status": "bought"}]
    return edit_entry(to_buy_with_shop, "product still to buy with a shop", change)


def unit_test(n, form):
    """A line still to buy, set to `n`: its unit's `form` shows (marked, so the test can't pass on
    text that happens to be in the data already)."""
    e = an_entry("entry with a line still to buy", lambda e: "price" in e and has_status("buy")(e))
    th = by_id(RAW[MATERIALS]["unit"], e["unit"])["th"]
    marker = f"{form.upper()}-UNIT"

    def change(d):
        by_id(d["unit"], e["unit"])[form] = marker
        find(by_id(d["entry"], e["id"])["line"], "line", lambda ln: ln["status"] == "buy")["n"] = n
    m = real().materials
    return {MATERIALS: data(change)}, f"| {n} {th} / {marker} {m.symbols['times']} {m.money(e['price'])} |"


def buy_before_on_site(p):
    """In a group with lines both to buy and on site (found in the data), the first line on the list is
    one to buy — read off the page, not from the code that orders it."""
    lines = [ln for e in RAW[MATERIALS]["entry"] for ln in e["line"]]
    g = find(RAW[MATERIALS]["group"], "group with lines both to buy and on site",
             lambda g: {ln["status"] for ln in lines if ln["group"] == g["id"]} >= {"buy", "bought"})
    page = p.doc.split("\n")
    first = page[page.index(f"| **{g['th']} / {g['en']}** | | | |") + 1]
    buy = p.materials.labels.both("buy")
    return first if first.endswith(f"| {buy} |") else f"(a line to buy first under {g['en']}; the first is: {first})"


def step_number():
    """A step's number, counted from the data: '| phase.step |'."""
    target = a_step()["id"]
    for p_no, ph in enumerate(RAW[PHASES]["phase"], 1):
        for s_no, st in enumerate(ph.get("step", []), 1):
            if st["id"] == target:
                return f"| {p_no}.{s_no} |"


def link_test():
    """A product's page link, built here from its shop's link and its code."""
    e = an_entry("product with a shop", lambda e: "shop" in e)
    shop = by_id(RAW[MATERIALS]["shop"], e["shop"])
    url = shop["link"].replace("{sku}", e["sku"]).replace("{sku_digits}", re.sub(r"\D", "", e["sku"]))
    return {}, f"]({url})"


def group_heading(p):
    g = find(p.materials.groups, "group with lines", lambda g: p.materials.in_order(g))
    return f"| **{g.th} / {g.en}** |"


def ref_test(insert):
    """A reference to a step, added to the last phase — and, if `insert`, a new step put in front
    of it: the reference must follow it to its new number."""
    target = a_step()["id"]

    def change(d):
        last = d["phase"][-1].setdefault("step", [{"id": "ref_test", "th": "-", "en": "-"}])[0]
        last["en"] += f" · see step {{step:{target}}}"
        if insert:
            ph = find(d["phase"], "phase with the step", lambda ph: any(s["id"] == target for s in ph.get("step", [])))
            ph["step"].insert(0, {"id": "inserted_test", "th": "ใหม่", "en": "New step"})
    phase, step = step_number().strip("| ").split(".")
    return {PHASES: data(change)}, f"see step {phase}.{int(step) + insert}"


def duplicate_id_test():
    all_steps = steps(RAW[PHASES])
    if len(all_steps) < 2:
        raise LookupError("the data has fewer than two steps, so no id can be used twice")
    first, second = all_steps[0]["id"], all_steps[1]["id"]
    return edit_step(lambda s: s.update(id=first), second), f"step id '{first}' is used twice"


def out_of_order_test():
    e = an_entry("product", lambda e: True)
    second = next(k for k in materials.ENTRY if k in e and k != "id")

    def change(x):
        x["id"] = x.pop("id")                                # id moved to the end
    return edit_entry(lambda x: x["id"] == e["id"], "product", change), f"has '{second}' out of order"


def both_names(e):
    put(e, "th", "x", room.ITEM)
    put(e, "en", "x", room.ITEM)


def drawn_wall_test():
    w = find(RAW[ROOM]["wall"], "wall that isn't drawn", lambda w: not w["drawn"])
    lab = real().room.labels
    return ({ROOM: data(lambda d: by_id(d["wall"], w["id"]).update(drawn=True))},
            lab.en("elevation_title", wall=(w["th"], w["en"])))


def tile_product(d):
    return by_id(d["entry"], RAW[ROOM]["tile"][0]["product"])


# ---------- the tests ----------
# (name, edits, expected) — expected is a text, CLEAN, or built(…) — or (name, make) where
# make() works out (edits, expected) from the real data when the test runs.
TESTS = [
    ("real data is clean", {}, CLEAN),
    # ---- the one checker (common.check): one test per kind of mistake ----
    ("checker: an unknown key (a typo)", lambda: (edit_item(lambda e: True, "item", lambda e: e.update(xx=1)),
                                                 "unknown key 'xx'")),
    ("checker: a required key missing", lambda: (edit_line(lambda e: True, "product", lambda ln: ln.pop("n")),
                                                 "has no 'n'")),
    ("checker: keys out of order", out_of_order_test),
    ("checker: text where a number goes",
     lambda: (edit_item(lambda e: "x" in e, "item with an x", lambda e: e.update(x=str(e["x"]))), "'x' must be a number")),
    ("checker: a number that isn't finite",
     {ROOM: data(lambda d: d["room"].update(ceiling=float("nan")))}, "'ceiling' must be a number, not nan"),
    ("checker: text where true / false goes",
     lambda: (edit_entry(lambda e: True, "product", lambda e: put(e, "approx", "yes", materials.ENTRY)),
              "'approx' must be true or false")),
    ("checker: a number where text goes", {MATERIALS: data(lambda d: find(d["group"], "group").update(th=5))},
     "'th' must be text"),
    ("checker: a value where a table goes",
     lambda: (edit_entry(lambda e: "size" in e, "product with a size", lambda e: e.update(size=5)), "'size' must be a table")),
    ("checker: a value where a list goes",
     lambda: (edit_entry(lambda e: True, "product", lambda e: e.update(line="x")), "'line' must be a list of tables")),
    ("checker: a value where a table in a list goes",
     {PHASES: data(lambda d: find(d["phase"], "phase with steps", lambda ph: ph.get("step")).update(step=["x"]))},
     "step 1 must be a table"),
    ("checker: text where a date goes", {MATERIALS: data(lambda d: d.update(prices_date="yesterday"))},
     "'prices_date' must be a date"),
    ("checker: a negative amount (a price)",
     lambda: (edit_entry(lambda e: "price" in e, "product with a price", lambda e: e.update(price=-1)),
              "'price' can't be negative")),
    ("checker: a count that isn't more than 0",
     lambda: (edit_line(lambda e: True, "product", lambda ln: ln.update(n=0)), "'n' must be more than 0")),
    ("checker: a name pointing at nothing (a shop the file doesn't define)",
     lambda: (edit_entry(lambda e: "shop" in e, "product with a shop", lambda e: e.update(shop="lazada")),
              "has shop = 'lazada'")),
    ("checker: keys that come together, one missing (a shop without its code)",
     lambda: (edit_entry(lambda e: "shop" in e, "product with a shop", lambda e: e.pop("sku")), "has shop but no sku")),
    ("checker: one language only", {PHASES: data(lambda d: d["section"].pop("note_en"))}, "has note_th but no note_en"),
    ("checker: an id used twice", duplicate_id_test),
    ("checker: a placeholder the text can't use",
     {ROOM: data(lambda d: d["labels"]["tile_top"].update(en=d["labels"]["tile_top"]["en"] + " {topp}"))},
     "tile_top en uses {topp} (it can use: top)"),
    ("checker: a stray brace", lambda: (edit_item(lambda e: "note_en" in e, "item with a note",
                                                  lambda e: e.update(note_en=e["note_en"] + " {")), "has a stray { or }")),
    ("checker: an empty list (a product with no lines)",
     lambda: (edit_entry(lambda e: True, "product", lambda e: e.update(line=[])), "'line' is empty")),
    ("checker: broken TOML", {ROOM: lambda t: t + "\n[[wall\n"}, "is not valid TOML"),
    ("checker: a data file missing", {PHASES: None}, f"{PHASES} not found"),
    # ---- the template ----
    ("document: the template missing", {MD: None}, f"{MD} not found"),
    ("document: each part's section goes where its marker is, in order", {},
     built(lambda p: "\n".join(p.work.render()) + "\n\n" + "\n".join(p.materials.render()))),
    ("document: a section marker missing from the template",
     {MD: lambda t: t.replace("<!-- section:materials -->", "", 1)}, "marker <!-- section:materials --> not found"),
    # ---- the room: design rules (warnings, in Thai and English) ----
    ("rules: a point moved just off a joint", joint_test),
    ("rules: the same warning, in Thai", lambda: joint_test("th")),
    ("rules: a point moved just off a horizontal joint", joint_y_test),
    ("rules: the tile top edge counts as a joint", tile_top_joint_test),
    ("rules: a hole exactly on a joint is allowed", on_joint_test),
    ("rules: no joint warnings above the tiling", above_tiles_test),
    ("rules: a point moved off the end of the wall", point_off_wall_test),
    ("rules: a zone running off its wall", zone_off_wall_test),
    ("rules: a box poking out past the wall's start", off_wall_start_test),
    ("rules: an item running below the floor", below_floor_test),
    ("rules: a fixing in a window", point_in_opening_test),
    ("rules: a floor item off the floor, across the room", off_floor_y_test),
    ("rules: an item above the ceiling", ceiling_test),
    ("rules: a floor item off the floor", off_floor_test),
    ("rules: a tile-box shortage shows on the floor plan", tile_short_on_plan_test),
    ("rules: an item moved onto another", clash_test),
    ("rules: a round item moved onto another", round_clash_test),
    ("rules: an item pushed past the end of the wall", wall_end_test),
    ("rules: an item moved without the part that belongs to it", part_outside_test),
    ("rules: a part moved above the item it belongs to", part_above_test),
    ("rules: an item moved onto the column", column_clash_test),
    ("rules: no tile joint inside the door opening", door_joint_test),
    ("rules: the all-clear is printed on the drawings", {},
     built(lambda p: p.room.labels.en("all_clear", min_clear=p.room.min_clear))),
    ("rules: too few tile boxes for the room", tile_boxes_test),
    # ---- the room: bad data ----
    ("room: a wall missing", {ROOM: data(lambda d: d["wall"].pop())},
     f"{len(RAW[ROOM]['wall']) - 1} walls — the room has {len(room.PLAN_SIDES)}"),
    ("room: items on a wall that isn't drawn",
     lambda: ({ROOM: data(lambda d: wall_raw(d).update(drawn=False))}, f"wall '{wall_raw()['id']}' has items but isn't drawn")),
    ("room: an item naming a product that isn't on the material list",
     lambda: (edit_item(lambda e: "product" in e, "item with a product", lambda e: e.update(product="no_such_product")),
              "names product 'no_such_product', which is not on the material list")),
    ("room: an item with both a product and a name",
     lambda: (edit_item(lambda e: "product" in e, "item with a product", both_names),
              "needs a product or a name (th, en) — one, not both")),
    ("room: an item with neither a product nor a name",
     lambda: (edit_item(lambda e: "th" in e, "item with its own name", lambda e: (e.pop("th"), e.pop("en"))),
              "needs a product or a name (th, en) — one, not both")),
    ("room: an item with a product giving its own size",
     lambda: (edit_item(lambda e: "product" in e, "item with a product", lambda e: put(e, "w", 900, room.ITEM)),
              "takes its size from product")),
    ("room: an item taking an id the room works out",
     lambda: (edit_item(lambda e: e["id"] not in room.BUILT, "item", lambda e: e.update(id=room.BUILT[0])),
              f"'{room.BUILT[0]}' is worked out from how the room is built")),
    ("room: two tiles naming the same product",
     {ROOM: data(lambda d: d["tile"][1].update(product=d["tile"][0]["product"]))} if len(RAW[ROOM]["tile"]) > 1 else {},
     f"tile product '{RAW[ROOM]['tile'][0]['product']}' is used twice"),
    ("room: two walls with the same tag",
     {ROOM: data(lambda d: d["wall"][1].update(tag=d["wall"][0]["tag"]))}, f"tag '{RAW[ROOM]['wall'][0]['tag']}' is used twice"),
    ("room: a size key the shape doesn't have (a point with a width)",
     lambda: (edit_item(lambda e: e["shape"] == "point", "point", lambda e: put(e, "w", 100, room.ITEM)),
              "is a point, so it has no 'w'")),
    ("room: a step with no high side",
     {ROOM: data(lambda d: find(d["floor"]["item"], "step", lambda e: e["shape"] == "step").pop("high"))},
     "(step) needs 'high'"),
    ("room: a point with no x", lambda: (edit_item(lambda e: e["shape"] == "point", "point", lambda e: e.pop("x")),
                                        "(point) needs 'x'")),
    ("room: a part belonging to an item that isn't there", missing_parent_test),
    ("room: a tile whose product has no tiles-per-box",
     {MATERIALS: data(lambda d: tile_product(d).pop("per_box"))}, "on the material list to have a per_box"),
    ("room: a tiling height that isn't a whole number",
     {ROOM: data(lambda d: find(d["tile"], "tile").update(top=find(d["tile"], "tile")["top"] + 0.5))},
     "'top' must be a whole number more than 0"),
    ("room: a tile that isn't a whole number of mm",
     {MATERIALS: data(lambda d: tile_product(d)["size"].update(w=500.5, h=500.5))}, "a whole number of mm"),
    ("room: a tile that isn't square",
     {MATERIALS: data(lambda d: tile_product(d)["size"].update(h=1))}, "the tile count needs square tiles"),
    ("room: the door wider than its wall beside the column", door_test),
    ("room: a lintel shorter than the door and its bearing", lintel_short_test),
    ("room: a step's high side on a floor item that isn't a step",
     lambda: ({ROOM: data(lambda d: put(find(d["floor"]["item"], "floor rect", lambda e: e["shape"] == "rect"),
                                        "high", "end", room.ITEM))}, "is a rect, so it has no 'high'")),
    ("room: a drawing note that fills in a value",
     lambda: (edit_item(lambda e: "note_en" in e, "item with a note", lambda e: e.update(note_en="see {phase:x}")),
              "note_en uses {phase} (it can use: nothing)")),
    ("room: a wall set to drawn gets its own drawing", drawn_wall_test),
    ("room: a tiling height that isn't whole tiles counts the cut row", cut_row_test),
    # ---- products: on the material list; their names and sizes are used by the room ----
    ("products: a product's size reaches its detail on the list", size_in_name_test),
    ("products: a detail showing a size the product doesn't have",
     lambda: (edit_entry(lambda e: "size" not in e, "product without a size", lambda e: e.update(detail_en="sized {w}")),
              "detail_en uses {w} (it can use: nothing)")),
    ("products: an item on the drawings takes its product's name",
     lambda: ({MATERIALS: data(lambda d: by_id(d["entry"], find(wall_raw()["item"], "item with a product",
                                                               lambda e: "product" in e)["product"]).update(en="NAME-TEST"))},
              f"NAME-TEST{RAW[ROOM]['symbols']['dash']}")),
    # ---- materials.toml ----
    ("materials: the still-to-buy total is shown", {}, built(lambda p: p.materials.total_cell())),
    ("materials: a price change flows into the total", price_test),
    ("materials: a price that isn't whole baht shows to the satang", money_test),
    ("materials: a shop with a bad code pattern", {MATERIALS: data(lambda d: find(d["shop"], "shop").update(sku="["))},
     "sku isn't a pattern"),
    ("materials: a shop with a bad link", {MATERIALS: data(lambda d: find(d["shop"], "shop").update(link="{nope}"))},
     "link uses {nope} (it can use: sku, sku_digits)"),
    ("materials: approximate with no price", lambda: (make_approx_no_price(), "has approx but no price")),
    ("materials: a code that isn't the shop's kind of code", sku_test),
    ("materials: still to buy with no price", no_price_test),
    ("materials: still to buy with no shop", make("buy", price=10), "is buy, so it needs a shop and sku"),
    ("materials: reused with a price", make("reused", price=10), "is reused, so it has no price"),
    ("materials: reused with a shop", reused_with_shop_test),
    ("materials: supplied with nobody to bring it", make("supplied"), "is supplied, so it needs by_th and by_en"),
    ("materials: who brings it, on a line the trade doesn't bring",
     lambda: (edit_line(to_buy_with_shop, "product still to buy with a shop",
                        lambda ln: ln.update(by_th="ช่าง", by_en="trade")), "is buy, so it has no by_th and by_en")),
    ("materials: a supplied item shows who brings it",
     make("supplied", by=("ช่าง-TEST", "BRINGER-TEST")), "| ช่าง-TEST / BRINGER-TEST |"),
    ("materials: the list is in sections by group", {}, built(group_heading)),
    ("materials: in a group, what is still to buy comes before what is on site", {}, built(buy_before_on_site)),
    ("materials: the link is built from shop and code", link_test),
    ("materials: one takes the singular unit (en)", lambda: unit_test(1, "en")),
    ("materials: more than one takes the plural (en_many)", lambda: unit_test(3, "en_many")),
    ("materials: the prices date reaches the section note, in its format",
     {MATERIALS: data(lambda d: d.update(prices_date=datetime.date(2030, 1, 2)))},
     datetime.date(2030, 1, 2).strftime(RAW[MATERIALS]["date_format"])),
    ("materials: the approx. label reaches the section note",
     {MATERIALS: data(lambda d: d["labels"]["approx"].update(en="APPROX-TEST"))},
     "> " + RAW[MATERIALS]["section"]["note_en"].format(
         prices_date=RAW[MATERIALS]["prices_date"].strftime(RAW[MATERIALS]["date_format"]), approx="APPROX-TEST")),
    ("materials: the section note filling in something it can't",
     {MATERIALS: data(lambda d: d["section"].update(note_en=d["section"]["note_en"] + " {nope}"))},
     "[section] note_en uses {nope}"),
    ("materials: a group's note shows under its heading",
     {MATERIALS: data(lambda d: find(d["group"], "group").update(note_th="GROUP-NOTE-TH", note_en="GROUP-NOTE-EN"))},
     "*GROUP-NOTE-TH*<br>*GROUP-NOTE-EN*"),
    # ---- phases.toml ----
    ("phases: the steps are numbered", lambda: ({}, step_number())),
    ("phases: a reference resolves to its number", lambda: ref_test(insert=False)),
    ("phases: inserting a step renumbers it and its references", lambda: ref_test(insert=True)),
    ("phases: a brace that isn't a reference",
     lambda: (edit_step(lambda s: s.update(en=s["en"] + " {phase:make-good}")), "that isn't a reference like {step:id}")),
    ("phases: a reference to an id that doesn't exist",
     lambda: (edit_step(lambda s: s.update(en=s["en"] + " {step:no_such_step}")), "{step:no_such_step} doesn't match")),
]


def main():
    try:
        real()
    except DataError as e:
        sys.exit(f"The real data is refused, so nothing can be tested:\nERROR: {e}")
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
