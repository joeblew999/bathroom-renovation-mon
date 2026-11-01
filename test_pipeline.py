#!/usr/bin/env python3
"""Tests for the bathroom pipeline — proves every check really fires.

Each test copies the template and the three data files into a temporary folder, breaks one
thing on purpose, then puts the quote together in this process:

    q = assemble(md)      phases + materials + room, the design checks, the filled document

and looks for the expected text in what comes back: the error message, the design problems, the
tile counts, the filled-in document or the drawings. The real files are never touched. One test goes
further: it measures the design problems' lines in Chromium to see they fit their drawing.

No test depends on today's numbers or wording. A test picks what it breaks by what it is — "an
item that belongs to another item", "a product still to buy with a shop" — edits it in the loaded
data, and works out the message it expects from the real data and its labels. So changing a
price, a position, a quantity or a label never breaks a test; only a broken check does. If the
data has nothing of the kind a test needs, that test fails and says so.

There is a test for every check in the code: every DataError (bad data, a data check) and every
design check (room_design_checks.py, materials_design_checks.py).

Usage:  python3 test_pipeline.py
"""
import contextlib
import datetime
import html
import io
import json
import math
import re
import sys
import tempfile
import tomllib
from pathlib import Path


import labour
import materials
import phases
import room
import room_design_checks
import room_drawings
import drawing_design_checks
import build
from build import assemble, tile_lines
import common
from common import DataError

HERE = Path(__file__).resolve().parent
MD = "bathroom-renovation-quote.md"
MATERIALS, ROOM, PHASES, LABOUR = materials.FILE, room.FILE, phases.FILE, labour.FILE
DATA = (MATERIALS, ROOM, PHASES, LABOUR)
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
    wid = find(RAW[ROOM]["wall"], "drawn wall with items", lambda w: w["elevation"] and w.get("item"))["id"]
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
    it = find(wall().items, "item that belongs to another", lambda i: i.fitting and i.x is not None)
    return it, items[it.fitting]


def an_entry(what, cond):
    return find(RAW[MATERIALS]["entry"], what, cond)


def has_status(status):
    return lambda e: any(ln["status"] == status for ln in e["line"])


def to_buy_with_shop(e):
    return "price" in e and "shop" in e and has_status("procure")(e)


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


def copy_to(folder, edits):
    """The template and the data files, copied into `folder` with `edits` made."""
    for name in (MD, *DATA):
        if name in edits and edits[name] is None:
            continue
        text = (HERE / name).read_text(encoding="utf-8")
        (folder / name).write_text(edits[name](text) if name in edits else text, encoding="utf-8")


def run(edits):
    """Assemble the quote from copies, with `edits` = {file: edit(text) -> text, or None to leave
    the file out}. Returns (warnings, text to search, quote) — the ERROR line if the data was refused."""
    with tempfile.TemporaryDirectory() as tmp:
        copy_to(Path(tmp), edits)
        try:
            q = assemble(Path(tmp) / MD)
        except DataError as e:
            return [], f"ERROR: {e}", None
    warnings = [x for _, w in q.warnings for x in w]
    return warnings, "\n".join([*warnings, *tile_lines(q.room, q.tiles), q.doc, *q.svgs]), q


def construction_item(shape):
    """The column, door or lintel — the room's construction — as room.py worked it out on the column's wall."""
    return find(column_wall()[1].items, shape, lambda i: i.shape == shape)


def built(f):
    """An expectation read off the quote, as the build made it."""
    return lambda p: f(p) if p else "(the data was refused, so there was no quote to look at)"


# ---------- tests that need working out: each returns (edits, expected) ----------
def wall_name(w=None):
    """A wall's name as a design problem gives it: (th, en)."""
    w = w or wall()
    return w.th, w.en


def edge(key, **values):
    """Which edge an item runs off, as the room's labels word it: (th, en)."""
    lab = real().room.labels
    return lab.th(key, **values), lab.en(key, **values)


def length_end():
    return edge("edge_end", length=f"{wall().length:g}")


def joint_test(lang="en"):
    it = find(wall().items, "point on the wall", lambda i: i.shape == "point")
    off = real().room.joint_clearance / 2
    x = real().room.tiles[wall().tile].size + off            # just past the first vertical joint
    lab = real().room.labels
    want = getattr(lab, lang)("warn_joint", wall=wall_name(), item=it.label(), axis=real().room.symbols["axis_x"],
                              v=f"{x:g}", d=f"{off:g}", min=f"{real().room.joint_clearance:g}")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(x=x))}, want


def joint_y_test():
    it = find(wall().items, "point below the tile top", lambda i: i.shape == "point" and i.y < real().room.tiles[wall().tile].tiling_height)
    t = real().room.tiles[wall().tile]
    off = real().room.joint_clearance / 2
    y = t.size + off                                         # just above the first horizontal joint
    return ({ROOM: data(lambda d: raw_item(d, it.id).update(y=y))},
            warn("warn_joint", wall=wall_name(), item=it.label(), axis=real().room.symbols["axis_y"], v=f"{y:g}",
                 d=f"{off:g}", min=f"{real().room.joint_clearance:g}"))


def tile_top_joint_test():
    """The tile top edge counts as a joint: a point just below it is warned about."""
    it = find(wall().items, "point on the wall", lambda i: i.shape == "point")
    top, off = real().room.tiles[wall().tile].tiling_height, real().room.joint_clearance / 2
    return ({ROOM: data(lambda d: raw_item(d, it.id).update(y=top - off))},
            warn("warn_joint", wall=wall_name(), item=it.label(), axis=real().room.symbols["axis_y"], v=f"{top - off:g}",
                 d=f"{off:g}", min=f"{real().room.joint_clearance:g}"))


def on_joint_test():
    """A hole exactly on a joint is allowed (the screws go either side): no warning."""
    it = find(wall().items, "point on the wall", lambda i: i.shape == "point")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(x=real().room.tiles[wall().tile].size))}, CLEAN


def above_tiles_test():
    """No joints above the tiling: a point well above the tile top, near where a vertical joint would be,
    gets no warning."""
    it = find(wall().items, "point that belongs to nothing", lambda i: i.shape == "point" and not i.fitting)
    t = real().room.tiles[wall().tile]
    return {ROOM: data(lambda d: raw_item(d, it.id).update(x=t.size + real().room.joint_clearance / 2,
                                                            y=t.tiling_height + t.size))}, CLEAN


def point_off_wall_test():
    it = find(wall().items, "point on the wall", lambda i: i.shape == "point")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(x=wall().length + 100))}, \
        warn("warn_set_out_off_wall", wall=wall_name(), item=it.label(), edge=length_end())


def zone_off_wall_test():
    z = find(wall().items, "zone on the wall", lambda i: i.shape == "zone")
    return {ROOM: data(lambda d: raw_item(d, z.id).update(x=wall().length - z.w / 4))}, \
        warn("warn_set_out_off_wall", wall=wall_name(), item=z.label(), edge=length_end())


def ceiling_test():
    it = find(solids(), "box on the wall", lambda i: i.shape == "rect")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(y=real().room.ceiling))}, \
        warn("warn_set_out_off_wall", wall=wall_name(), item=it.label(), edge=edge("edge_ceiling", ceiling=f"{real().room.ceiling:g}"))


def off_floor_test():
    it = find(real().room.floor, "floor item", lambda i: i.shape == "rect")
    return ({ROOM: data(lambda d: find(d["floor"]["item"], it.id, lambda e: e["id"] == it.id).update(x=real().room.length))},
            warn("warn_set_out_off_floor", item=it.label(), length=f"{real().room.length:g}", width=f"{real().room.width:g}"))


def problem_text(svg):
    """The design problems under a drawing, as one text: its wrapped lines joined back up."""
    lines = re.findall(r'<text class="warning"[^>]*>([^<]*)</text>', svg)
    return " ".join(html.unescape(line).strip() for line in lines)


def take_off_short_on_plan_test():
    """The tile-box shortage shows red on the floor plan, not only in the terminal."""
    edits, want = tile_boxes_test()
    plan = real().room.labels.en("floor_plan")

    def expect(p):
        svg = find(p.svgs, "the floor plan", lambda s: plan in s)
        mark = f"{RAW[ROOM]['symbols']['warning']} {want}"
        return want if mark in problem_text(svg) else f"(the floor plan's problems: {problem_text(svg)[:200]})"
    return edits, expect


def clash_test():
    a, b = solids()[:2]
    return {ROOM: data(lambda d: raw_item(d, b.id).update(x=a.x, y=a.y))}, \
        warn("warn_clash", wall=wall_name(), a=a.label(), b=b.label())


def round_clash_test():
    """A round item (its size is just a width) moved onto another item: warned about."""
    c = find(solids(), "round item on the wall", lambda i: i.shape == "circle")
    b = find(solids(), "other solid item", lambda i: i is not c)
    return {ROOM: data(lambda d: raw_item(d, c.id).update(x=b.x, y=b.y))}, \
        warn("warn_clash", wall=wall_name(), **dict(zip("ab", (x.label() for x in sorted((c, b), key=wall().items.index)))))


def wall_end_test():
    a = solids()[0]
    return {ROOM: data(lambda d: raw_item(d, a.id).update(x=wall().length))}, \
        warn("warn_set_out_off_wall", wall=wall_name(), item=a.label(), edge=length_end())


def part_outside_test():
    it, parent = a_part()
    moved = parent.x + parent.w
    return ({ROOM: data(lambda d: raw_item(d, parent.id).update(x=moved))},
            warn("warn_outside", wall=wall_name(), item=it.label(), axis=real().room.symbols["axis_x"], v=f"{it.x:g}",
                 parent=(parent.th, parent.en), low=f"{moved - parent.w / 2:g}", high=f"{moved + parent.w / 2:g}"))


def part_above_test():
    it, parent = a_part()
    y = parent.y + parent.h                                  # above its parent's top edge
    return ({ROOM: data(lambda d: raw_item(d, it.id).update(y=y))},
            warn("warn_above", wall=wall_name(), item=it.label(), axis=real().room.symbols["axis_y"], v=f"{y:g}",
                 parent=(parent.th, parent.en), top=f"{parent.y + parent.h / 2:g}"))


def column_wall():
    """The column's wall, as written, and as worked out."""
    wid = RAW[ROOM]["column"]["wall"]
    return wid, real().room.walls[wid]


def add_item(wid, item, first=False):
    """An edit adding an item to a wall (drawn, so it can have items), last or first."""
    def change(d):
        w = by_id(d["wall"], wid)
        w["elevation"] = True
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
    return add_item(wid, box, first=True), warn("warn_clash", wall=wall_name(w), a=(f"{n} กล่องทดสอบ", f"{n} Test box"),
                                      b=(f"{int(col.no) + 1} {col.th}", f"{int(col.no) + 1} {col.en}"))


def door_joint_test():
    """No tile joint is drawn inside the door opening: where one tile from the wall's start would end,
    inside the opening, the column's wall drawing has no joint line (px from room_drawings.py's own layout)."""
    wid, w = column_wall()
    door = find(w.items, "the door", lambda i: i.shape == "door")
    k = real().room.tiles[w.tile].size
    if not door.x - door.w / 2 < k < door.x + door.w / 2:
        raise LookupError("one tile from the wall's start isn't inside the door opening, so there is nothing to test")
    x = room_drawings.WALL_MARGINS[0] + (w.length - k) * room_drawings.WALL_SCALE
    title = real().room.labels.en("elevation_title", wall=(w.th, w.en))

    def expect(p):                                   # the column's wall drawing, and only it
        svg = find(p.svgs, "the column's wall drawing", lambda s: title in s)
        return title if f'<line class="joint" x1="{x}"' not in svg else f"(no joint line at x {k:g} on {w.en})"
    return {ROOM: data(lambda d: by_id(d["wall"], wid).update(elevation=True))}, built(expect)


def lintel_short_test():
    lid, door = RAW[ROOM]["lintel"]["product"], construction_item("door")
    return {MATERIALS: data(lambda d: by_id(d["entry"], lid)["size"].update(w=1))}, \
        warn("warn_lintel_short", wall=wall_name(column_wall()[1]), lintel="1", door=f"{door.w:g}", bearing=f"{RAW[ROOM]['lintel']['bearing']:g}")


def point_in_opening_test():
    w = find(real().room.walls.values(), "wall with a window and a point",
             lambda w: w.elevation and any(i.shape == "opening" for i in w.items) and any(i.shape == "point" for i in w.items))
    win = find(w.items, "window", lambda i: i.shape == "opening")
    pt = find(w.items, "point", lambda i: i.shape == "point")
    edit = {ROOM: data(lambda d: find(by_id(d["wall"], w.id)["item"], pt.id, lambda e: e["id"] == pt.id).update(x=win.x, y=win.y))}
    return edit, warn("warn_in_opening", wall=wall_name(w), a=pt.label(), b=win.label())


def below_floor_test():
    it = find(solids(), "box on the wall", lambda i: i.shape == "rect")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(y=it.h / 4))}, \
        warn("warn_set_out_off_wall", wall=wall_name(), item=it.label(), edge=edge("edge_floor"))


def off_wall_start_test():
    """A box poking out past the wall's start (x = 0)."""
    it = find(solids(), "box on the wall", lambda i: i.shape == "rect")
    return {ROOM: data(lambda d: raw_item(d, it.id).update(x=it.w / 4))}, \
        warn("warn_set_out_off_wall", wall=wall_name(), item=it.label(), edge=edge("edge_start"))


def off_floor_y_test():
    it = find(real().room.floor, "floor item", lambda i: i.shape == "rect")
    return ({ROOM: data(lambda d: find(d["floor"]["item"], it.id, lambda e: e["id"] == it.id).update(y=real().room.width))},
            warn("warn_set_out_off_floor", item=it.label(), length=f"{real().room.length:g}", width=f"{real().room.width:g}"))


def money_test():
    """A price that isn't whole baht shows to the satang, so the line adds up as shown."""
    e = an_entry("product still to buy", lambda e: "price" in e and has_status("procure")(e))
    m = real().materials
    return ({MATERIALS: data(lambda d: by_id(d["entry"], e["id"]).update(price=e["price"] + 0.4))},
            f"{m.symbols['times']} {m.symbols['currency']}{e['price'] + 0.4:,.2f}")


def missing_parent_test():
    it, _ = a_part()
    return {ROOM: data(lambda d: raw_item(d, it.id).update(fitting="no_such_item"))}, \
        "serves fitting 'no_such_item', which isn't on the same wall"


def tile_boxes_test():
    t = find(real().tiles, "tile with boxes on the list", lambda tp: tp[1] > 0)[0]
    e = an_entry(f"entry for '{t.tile.product}'", lambda e: e["id"] == t.tile.product)
    planned = sum(1 for ln in e["line"] if materials.STATUS[ln["status"]].shop)       # one box per line

    def change(d):
        for ln in by_id(d["entry"], t.tile.product)["line"]:
            ln["n"] = 1
    return {MATERIALS: data(change)}, \
        real().materials.labels.en("warn_take_off_short", tile=(t.tile.th, t.tile.en), planned=f"{planned:g}", boxes=t.boxes)


def cut_row_test():
    """A tiling height that isn't a whole number of tiles: the cut row is counted."""
    w = wall()
    t = real().room.tiles[w.tile]
    top = t.tiling_height // t.size * t.size + 1                         # one mm into a row: a cut row
    n = (t.tiling_height // t.size + 1) * math.ceil(w.tiled_run / t.size)
    return {ROOM: data(lambda d: by_id(d["tile"], t.id).update(tiling_height=top))}, f"{w.en} {n}"


def door_test():
    door = RAW[ROOM]["door"]["product"]
    length = real().room.walls[RAW[ROOM]["column"]["wall"]].length
    return {MATERIALS: data(lambda d: by_id(d["entry"], door)["size"].update(w=length))}, \
        warn("warn_door_fit", wall=wall_name(column_wall()[1]), door=f"{length:g}", column=f"{construction_item("column").w:g}", length=f"{length:g}")


def frame_column_test():
    """The door frame made deeper than the column its hinge side is fixed to."""
    door, depth = RAW[ROOM]["door"]["product"], RAW[ROOM]["column"]["depth"]
    return {MATERIALS: data(lambda d: by_id(d["entry"], door)["size"].update(d=depth + 1))}, \
        warn("warn_frame_column", wall=wall_name(column_wall()[1]), frame=f"{depth + 1:g}", column=f"{depth:g}")


def size_in_name_test():
    pid = an_entry("product whose detail shows {w_cm} × {h_cm}",
                   lambda p: "{w_cm} × {h_cm}" in p["detail_en"])["id"]
    return ({MATERIALS: data(lambda d: by_id(d["entry"], pid)["size"].update(w=4321, h=4321))},
            f"{4321 / 10:g} × {4321 / 10:g}")


def price_test():
    e = an_entry("entry still to buy", lambda e: "price" in e and has_status("procure")(e))
    n = sum(ln["n"] for ln in e["line"] if ln["status"] == "procure")
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
    e = an_entry("entry still to buy", lambda e: "price" in e and has_status("procure")(e))
    return {MATERIALS: data(lambda d: by_id(d["entry"], e["id"]).pop("price"))}, "has status procure, so it needs a price"


def reused_with_shop_test():
    def change(e):
        e.pop("price")
        e["line"] = [{**e["line"][0], "status": "existing"}]
    return edit_entry(to_buy_with_shop, "product still to buy with a shop", change), "has status existing, so it has no shop and sku"


def make_approx_no_price():
    """A product bought (its price allowed, not needed) with approx but no price."""
    def change(e):
        e.pop("price", None)
        put(e, "approx", True, materials.ENTRY)
        e["line"] = [{**e["line"][0], "status": "procured"}]
    return edit_entry(to_buy_with_shop, "product still to buy with a shop", change)


def unit_test(n, form):
    """A line still to buy, set to `n`: its unit's `form` shows (marked, so the test can't pass on
    text that happens to be in the data already)."""
    e = an_entry("entry with a line still to buy", lambda e: "price" in e and has_status("procure")(e))
    th = by_id(RAW[MATERIALS]["unit"], e["unit"])["th"]
    marker = f"{form.upper()}-UNIT"

    def change(d):
        by_id(d["unit"], e["unit"])[form] = marker
        find(by_id(d["entry"], e["id"])["line"], "line", lambda ln: ln["status"] == "procure")["n"] = n
    m = real().materials
    return {MATERIALS: data(change)}, f"| {n} {th} / {marker} {m.symbols['times']} {m.money(e['price'])} |"


def buy_before_on_site(p):
    """In a group with lines both to buy and on site (found in the data), the first line on the list is
    one to buy — read off the page, not from the code that orders it."""
    lines = [ln for e in RAW[MATERIALS]["entry"] for ln in e["line"]]
    g = find(RAW[MATERIALS]["work_section"], "work section with lines both to procure and on site",
             lambda g: {ln["status"] for ln in lines if ln["work_section"] == g["id"]} >= {"procure", "procured"})
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
    """A product's page link, made here from its shop's link and its code."""
    e = an_entry("product with a shop", lambda e: "shop" in e)
    shop = by_id(RAW[MATERIALS]["shop"], e["shop"])
    url = shop["link"].replace("{sku}", e["sku"]).replace("{sku_digits}", re.sub(r"\D", "", e["sku"]))
    return {}, f"]({url})"


def group_heading(p):
    g = find(p.materials.work_sections, "work section with lines", lambda g: p.materials.in_order(g))
    return f"| **{g.th} / {g.en}** |"


def ref_test(insert):
    """A reference to a step, added to the last phase — and, if `insert`, a new step put in front
    of it: the reference must follow it to its new number."""
    target = a_step()["id"]

    def change(d):
        last = d["phase"][-1].setdefault("step", [{"id": "ref_test", "th": "-", "en": "-"}])[0]
        last["th"] += f" · ดูขั้นตอน {{step:{target}}}"
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


def facts_message(where, th_key, en_key, th, en):
    """The checker's own message for a Thai/English pair, worked out from the texts."""
    try:
        common.same_facts("", where, th_key, en_key, th, en)
    except DataError as e:
        return str(e).removeprefix(": ")
    raise LookupError(f"{where} would not differ, so this test has nothing to break")


def step_where(sid):
    ph = find(RAW[PHASES]["phase"], "phase with this step", lambda p: any(s["id"] == sid for s in p.get("step", [])))
    return f"phase '{ph['id']}' step '{sid}'"


def different_numbers_test():
    """One more number in the English than in the Thai."""
    s = a_step()
    return (edit_step(lambda x: x.update(en=x["en"] + " 7"), s["id"]),
            facts_message(step_where(s["id"]), "th", "en", s["th"], s["en"] + " 7"))


def different_placeholders_test():
    """A placeholder in the English that the Thai doesn't fill in."""
    key, lab = next(iter(RAW[ROOM]["labels"].items()))
    return ({ROOM: data(lambda d: d["labels"][key].update(en=d["labels"][key]["en"] + " {x}"))},
            facts_message(f"[labels] {key}", "th", "en", lab["th"], lab["en"] + " {x}"))


def same_numbers_reordered_test():
    """The same numbers in the other order is fine: word order differs between the languages."""
    return edit_step(lambda x: x.update(th="1 ก 22", en="22 a 1")), CLEAN


def publishable_test():
    """mise run ci builds with --publishable: with a design problem it still writes the page and the PDF
    (to look at), then refuses — so mise run publish never pushes, and GitHub never publishes."""
    edits, want = clash_test()

    def expect(p):
        with tempfile.TemporaryDirectory() as tmp:
            copy_to(Path(tmp), edits)
            out = Path(tmp) / "out"
            try:
                with contextlib.redirect_stdout(io.StringIO()):          # its own output isn't the test's
                    build.main(["build.py", "--publishable", str(Path(tmp) / MD), str(out)])
                refused = False
            except DataError:
                refused = True
            written = (out / build.PDF_NAME).exists()
        return want if refused and written else f"(refused: {refused}; PDF written: {written})"
    return edits, expect


def problems_fit_test():
    """Every design problem's lines (Thai and English, long ones wrapped) fit inside its drawing, across and
    down, however many there are — measured in Chromium, the browser that prints the PDF."""
    edits_a, _ = clash_test()
    edits_b, _ = joint_test()
    a, b = edits_a[ROOM], edits_b[ROOM]
    title = real().room.labels.en("elevation_title", wall=(wall().th, wall().en))

    def expect(p):
        svg = find(p.svgs, "the wall's drawing", lambda s: title in s)
        page = common.chromium().new_page()
        page.set_content(f"<style>{build.STYLE.read_text(encoding='utf-8')}</style><section class=drawing>{svg}</section>")
        size, boxes = page.evaluate("""() => { const s = document.querySelector('svg');
            return [[s.viewBox.baseVal.width, s.viewBox.baseVal.height],
                    [...s.querySelectorAll('text.warning')].map(t => { const b = t.getBBox();
                        return [b.x + b.width, b.y + b.height]; })]; }""")
        page.close()
        if len(boxes) < 4:
            return f"(only {len(boxes)} problem lines on the drawing, so nothing to test)"
        right, bottom = max(x for x, _ in boxes), max(y for _, y in boxes)
        return title if right <= size[0] and bottom <= size[1] else \
            f"(problem lines reach {right:.0f} × {bottom:.0f}, past the drawing's {size[0]:.0f} × {size[1]:.0f})"
    return {ROOM: lambda t: b(a(t))}, expect


def norm_edit(nid, **values):
    """An edit of one norm in room.toml."""
    return {ROOM: data(lambda d: by_id(d["norm"], nid).update(**values))}


def clearance_test():
    """Too little clear space in front of the toilet: its norm raised just past what the room leaves."""
    n = real().room.norms["wc_clearance"]
    w, it = room_design_checks._find(real().room, n.item)
    clear = (real().room.width if w.along_room else real().room.length) - it.d
    return norm_edit(n.id, value=clear + 1), warn("warn_clearance", wall=wall_name(w), item=it.label(),
                                                  clear=f"{clear:g}", need=f"{clear + 1:g}")


def rim_test():
    """The basin rim below its lowest height: the norm raised just past the rim."""
    lo, hi = real().room.norms["basin_rim_min"], real().room.norms["basin_rim_max"]
    w, it = room_design_checks._find(real().room, lo.item)
    rim = it.y + it.h / 2
    return norm_edit(lo.id, value=rim + 1), warn("warn_rim_height", wall=wall_name(w), item=it.label(), rim=f"{rim:g}",
                                                 low=f"{rim + 1:g}", high=f"{hi.value:g}")


def zone_items():
    """[(wall, item, reach from the shower outlet)] for every electrical item, nearest first."""
    r = real().room
    ow, o = room_design_checks._find(r, r.norms["zone_1_reach"].item)
    ox, oy = room_design_checks.floor_point(r, ow, o.x)
    out = []
    for w in r.walls.values():
        for it in w.items:
            if it.electrical:
                x, y = room_design_checks.floor_point(r, w, it.x)
                out.append((w, it, ((x - ox) ** 2 + (y - oy) ** 2) ** 0.5))
    return sorted(out, key=lambda t: t[2])


def zone_ip_test():
    """An electrical item in a zone round the shower, its product rated too low for it."""
    r = real().room
    w, it, reach = find(zone_items(), "electrical item inside zone 2",
                        lambda t: t[2] <= r.norms["zone_1_reach"].value + r.norms["zone_2_reach"].value)
    pid = find(wall_raw()["item"] if w.id == wall_raw()["id"] else by_id(RAW[ROOM]["wall"], w.id)["item"],
               "the item as written", lambda e: e["id"] == it.id)["product"]
    zone = "1" if reach <= r.norms["zone_1_reach"].value else "2"
    return ({MATERIALS: data(lambda d: by_id(d["entry"], pid).update(ip="IP21"))},
            warn("warn_zone_ip", wall=wall_name(w), item=it.label(), zone=zone, ip="IP21",
                 need=f"{r.norms['zone_ip_water'].value:g}"))


def outside_zones_test():
    """An electrical item rated too low is fine outside the zones: the item beyond zone 2 gets no problem when
    its product's rating is dropped (the one inside still does, so the check is running)."""
    r = real().room
    far = r.norms["zone_1_reach"].value + r.norms["zone_2_reach"].value
    w, it, _ = find(zone_items(), "electrical item beyond zone 2", lambda t: t[2] > far)
    pid = find(by_id(RAW[ROOM]["wall"], w.id)["item"], "the item as written", lambda e: e["id"] == it.id)["product"]
    marker = r.labels.en("floor_plan")

    def expect(p):
        about_it = [en for _, (th, en) in p.warnings if it.label()[1] in en]
        return marker if not about_it else f"(a problem about {it.label()[1]}, outside the zones: {about_it[0]})"
    return {MATERIALS: data(lambda d: by_id(d["entry"], pid).update(ip="IP21"))}, built(expect)


def off_drawing_test():
    """A wall name too long for the line that names it under another wall's drawing: that drawing gets the
    problem that something runs off its edge (worded by its label), in red under it."""
    r = real().room
    w = find([x for x in r.walls.values() if x.elevation], "drawn wall")
    right = r.walls[w.right]
    long = "X" * 400
    off = r.labels.en("warn_off_drawing", what="\0").split("\0")          # the label's words either side of {what}

    def expect(p):
        mine = [en for d, (_, en) in p.warnings if d == w.id and en.startswith(off[0]) and en.endswith(off[1])]
        return off[1] if mine else f"(no problem under {w.en} that something runs off it: {p.warnings})"
    return {ROOM: data(lambda d: by_id(d["wall"], right.id).update(th=long, en=long))}, built(expect)


# ---------- labour ----------
def labour_line(what, cond):
    """The first labour line (as written) that `cond` picks, and its number (labour.py names a line by it)."""
    i, e = find(list(enumerate(RAW[LABOUR]["line"], 1)), what, lambda t: cond(t[1]))
    return i, e


def labour_rate(rid):
    return by_id(RAW[LABOUR]["rate"], rid)


def edit_labour_line(i, change):
    return {LABOUR: data(lambda d: change(d["line"][i - 1]))}


def money(v):
    """Baht as the labour section writes it — from its own [symbols]."""
    c = RAW[LABOUR]["symbols"]["currency"]
    return f"{c}{v:,.0f}" if v == round(v) else f"{c}{v:,.2f}"


def take_off_line_test():
    """A measured line is the room's take-off (to one decimal) times its rate: its rate set to 1000 for the test."""
    i, e = labour_line("measured, unassumed line", lambda e: "take_off" in e and "times" not in e and "assumed" not in e)
    qty = round(real().room.take_off()[e["take_off"]][0], labour.DECIMALS)
    return ({LABOUR: data(lambda d: by_id(d["rate"], e["rate"]).update(rate=1000))},
            money(qty * 1000))


def count_line_test():
    """A line that counts products takes how many the materials list has: the first one's line set to 7."""
    i, e = labour_line("line that counts one product", lambda e: "count" in e and len(e["count"]) == 1)
    rate = labour_rate(e["rate"])["rate"]

    def change(d):
        p = by_id(d["entry"], e["count"][0])
        p["line"] = [dict(p["line"][0], n=7)]
    return {MATERIALS: data(change)}, money(7 * rate)


def share_line_test():
    """A share of materials is its percent of what they still cost: the first product's price set to 1000."""
    i, e = labour_line("share line with one product", lambda e: "of_products" in e and len(e["of_products"]) == 1)
    pid, pct = e["of_products"][0], labour_rate(e["rate"])["rate"]
    n = sum(ln["n"] for ln in by_id(RAW[MATERIALS]["entry"], pid)["line"] if ln["status"] == "procure")
    lab = labour.Labels(LABOUR, RAW[LABOUR]["labels"], labour.LABELS)
    qty = lab.both("of_products", percent=f"{pct:g}{RAW[LABOUR]['symbols']['percent']}", cost=money(1000 * n))
    return ({MATERIALS: data(lambda d: by_id(d["entry"], pid).update(price=1000))},
            f"{qty} | {lab.both('approx')} {money(pct / 100 * 1000 * n)} |")


def labour_totals_test():
    """The labour total is every line added up, and the grand total adds what the materials still cost."""
    def expect(p):
        total, approx = p.labour.total()
        mt, ma = p.materials.still_to_buy()
        want = [p.labour.total_text(total, approx), p.labour.total_text(total + mt, approx or ma)]
        got = [ln for ln in p.doc.splitlines() if p.labour.labels.both("labour_total") in ln or
               p.labour.labels.both("grand_total") in ln]
        ok = len(got) == 2 and want[0] in got[0] and want[1] in got[1] and abs(total - sum(m.amount for m in p.labour.lines)) < 1e-9
        return want[1] if ok else f"(totals shown: {got}; expected {want})"
    return {}, built(expect)


def labour_data_test(change, message):
    """A labour line written wrongly: the first measured line, changed."""
    i, e = labour_line("measured line", lambda e: "take_off" in e)
    return edit_labour_line(i, lambda x: change(x, e)), message.format(i=i, rate=e["rate"])


def drawing(*parts):
    """A small drawing to measure: 400 × 200, white paper, with `parts` (svg)."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">'
            '<rect class="paper" width="100%" height="100%"/>' + "".join(parts) + "</svg>")


def measured(kind, *parts):
    """What the drawing checks find of `kind` on a small drawing: [(what, other)]."""
    style = build.STYLE.read_text(encoding="utf-8")
    return [(w, o) for _, k, w, o in drawing_design_checks.check([drawing(*parts)], style) if k == kind]


def drawing_check_test(kind, want, *parts):
    """The drawing checks, on a small drawing made for the test: they find `want` ([(what, other)]) of `kind`."""
    marker = real().room.labels.en("floor_plan")
    return {}, lambda p: marker if measured(kind, *parts) == want else f"(found {measured(kind, *parts)}, not {want})"


def item_raw(d, iid):
    """An item as written in room.toml, on whichever wall it is."""
    return find([i for w in d["wall"] for i in w.get("item", [])], f"item '{iid}'", lambda i: i["id"] == iid)


def waterproofing_test():
    """The shower zone waterproofed lower than its norm."""
    r = real().room
    n = r.norms["shower_wall_waterproofing"]
    _, zone = room_design_checks._find(r, n.item)
    return ({ROOM: data(lambda d: item_raw(d, zone.id).update(waterproofing=n.value - 1))},
            warn("warn_waterproofing", zone=zone.label(), height=f"{n.value - 1:g}", need=f"{n.value:g}"))


def fall_test():
    """The wet side of the floor falling less than its norm: 1 in twice the norm."""
    need = real().room.norms["floor_fall"].value
    return ({ROOM: data(lambda d: d["floor"].update(fall_wet=need * 2))},
            warn("warn_fall", fall=f"{need * 2:g}", need=f"{need:g}"))


def zone_no_ip_test():
    """Something electrical in a zone round the shower, with no IP rating recorded on its product."""
    r = real().room
    inside = r.norms["zone_1_reach"].value + r.norms["zone_2_reach"].value
    raw = {i["id"]: i for w in RAW[ROOM]["wall"] for i in w.get("item", [])}
    w, it, reach = find(zone_items(), "electrical item inside zone 2 whose detail doesn't show its rating",
                        lambda t: t[2] <= inside and "{ip}" not in by_id(RAW[MATERIALS]["entry"], raw[t[1].id]["product"])["detail_en"])
    pid = raw[it.id]["product"]

    def change(e):
        e.pop("ip")
        if "assumed" in e:
            e["assumed"] = [k for k in e["assumed"] if k != "ip"]
            if not e["assumed"]:
                e.pop("assumed")
    zone = "1" if reach <= r.norms["zone_1_reach"].value else "2"
    return ({MATERIALS: data(lambda d: change(by_id(d["entry"], pid)))},
            warn("warn_zone_no_ip", wall=wall_name(w), item=it.label(), zone=zone))


def door_swing_test():
    """The door swinging into a fitting's clear space: the basin's clear space made as deep as the room."""
    r = real().room
    n = r.norms["basin_clearance"]
    w, it = room_design_checks._find(r, n.item)
    deep = norm_edit(n.id, value=max(r.width, r.length))[ROOM]
    opens_in = data(lambda d: d["door"].update(swing="in"))
    return ({ROOM: lambda t: opens_in(deep(t))},
            warn("warn_clearance_door", wall=wall_name(w), item=it.label(), door=construction_item("door").label()))


def no_door_problem(edits):
    """`edits` leave no door-swing problem, even with the basin's clear space as deep as the room."""
    r = real().room
    deep, want = door_swing_test()
    marker = r.labels.en("floor_plan")

    def expect(p):
        return marker if want not in "\n".join(en for _, (_, en) in p.warnings) else f"(still: {want})"
    return {ROOM: lambda t: edits(deep[ROOM](t))}, built(expect)


def door_swing_out_test():
    """A door opening out of the room never swings into a clear space."""
    return no_door_problem(data(lambda d: d["door"].update(swing="out")))


def drain_side_test():
    """The drain moved to the high (dry) side of the floor step."""
    r = real().room
    drain = find(r.floor, "the floor drain", lambda i: i.id == r.floor_drain)
    step = find(r.floor, "floor step", lambda i: i.shape == "step")
    x = step.x / 2 if step.high == "start" else (step.x + r.length) / 2
    return ({ROOM: data(lambda d: find(d["floor"]["item"], "drain", lambda i: i["id"] == drain.id).update(x=x))},
            warn("warn_drain_side", drain=drain.label(), step=step.label()))


def assumed_missing_test():
    """An item listing as assumed a key it doesn't have."""
    e = find(wall_raw()["item"], "item without a y", lambda i: "y" not in i)
    return edit_item(lambda i: i["id"] == e["id"], "item", lambda i: put(i, "assumed", ["y"], room.ITEM)), \
        f"item '{e['id']}' lists 'y' as assumed, but has no 'y'"


def waterproofing_not_zone_test():
    """Waterproofing given to an item that isn't a zone."""
    e = find(wall_raw()["item"], "item that isn't a zone", lambda i: i.get("shape") != "zone")
    return edit_item(lambda i: i["id"] == e["id"], "item", lambda i: put(i, "waterproofing", 1000, room.ITEM)), \
        f"item '{e['id']}' has waterproofing, but only a zone has its own"


def assumed_listed_test():
    """A value marked as assumed is listed by the build, with its value."""
    e = find(wall_raw()["item"], "item with an x and nothing assumed", lambda i: "x" in i and "assumed" not in i)

    def expect(p):
        want = (e["id"], "x", e["x"])
        got = [(w, k, v) for w, k, v in build.assumed(p) if e["id"] in w and k == "x"]
        return p.room.labels.en("floor_plan") if got and got[0][2] == want[2] else f"(assumed values listed: {build.assumed(p)})"
    return edit_item(lambda i: i["id"] == e["id"], "item", lambda i: put(i, "assumed", ["x"], room.ITEM)), built(expect)


def ip_in_detail_test():
    """A product's IP rating reaches its detail on the list."""
    e = an_entry("product with an IP rating shown in its detail", lambda e: "ip" in e and "{ip}" in e["detail_en"])
    return {MATERIALS: data(lambda d: by_id(d["entry"], e["id"]).update(ip="IP65"))}, "IP65"


def out_of_order_test():
    e = an_entry("product", lambda e: True)
    second = next(k for k in materials.ENTRY if k in e and k != "id")

    def change(x):
        x["id"] = x.pop("id")                                # id moved to the end
    return edit_entry(lambda x: x["id"] == e["id"], "product", change), f"has '{second}' out of order"


def both_names(e):
    put(e, "th", "x", room.ITEM)
    put(e, "en", "x", room.ITEM)


def elevation_wall_test():
    w = find(RAW[ROOM]["wall"], "wall with no elevation", lambda w: not w["elevation"])
    lab = real().room.labels
    return ({ROOM: data(lambda d: by_id(d["wall"], w["id"]).update(elevation=True))},
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
    ("checker: a number where text goes", {MATERIALS: data(lambda d: find(d["work_section"], "work section").update(th=5))},
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
    ("checker: Thai and English giving different numbers", different_numbers_test),
    ("checker: Thai and English filling in different placeholders", different_placeholders_test),
    ("checker: Thai and English giving the same numbers in a different order", same_numbers_reordered_test),
    ("checker: an id used twice", duplicate_id_test),
    ("checker: a placeholder the text can't use",
     {ROOM: data(lambda d: d["labels"]["tile_top"].update({k: v + " {topp}" for k, v in d["labels"]["tile_top"].items()}))},
     "tile_top th uses {topp} (it can use: top)"),
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
    # ---- room design (room_design_checks.py): setting out, clashes, clearances, heights, wet areas; in Thai and English, in red under the drawing ----
    ("room design: a point moved just off a joint", joint_test),
    ("room design: the same problem, in Thai", lambda: joint_test("th")),
    ("room design: a point moved just off a horizontal joint", joint_y_test),
    ("room design: the tile top edge counts as a joint", tile_top_joint_test),
    ("room design: a hole exactly on a joint is allowed", on_joint_test),
    ("room design: no joint problems above the tiling", above_tiles_test),
    ("room design: a point moved off the end of the wall", point_off_wall_test),
    ("room design: a zone running off its wall", zone_off_wall_test),
    ("room design: a box poking out past the wall's start", off_wall_start_test),
    ("room design: an item running below the floor", below_floor_test),
    ("room design: a fixing in a window", point_in_opening_test),
    ("room design: a floor item off the floor, across the room", off_floor_y_test),
    ("room design: an item above the ceiling", ceiling_test),
    ("room design: a floor item off the floor", off_floor_test),
    ("room design: an item moved onto another", clash_test),
    ("room design: a round item moved onto another", round_clash_test),
    ("room design: an item pushed past the end of the wall", wall_end_test),
    ("room design: an item moved without the part that belongs to it", part_outside_test),
    ("room design: a part moved above the item it belongs to", part_above_test),
    ("room design: an item moved onto the column", column_clash_test),
    ("room design: no tile joint inside the door opening", door_joint_test),
    ("room design: the all-clear is printed on the drawings", {},
     built(lambda p: p.room.labels.en("all_clear", min_clear=p.room.joint_clearance))),
    ("room design: the door wider than its wall beside the column", door_test),
    ("room design: a lintel shorter than the door and its bearing", lintel_short_test),
    ("room design: a door frame deeper than the column it is fixed to", frame_column_test),
    ("room design: too little clear space in front of a fitting", clearance_test),
    ("room design: the basin rim set out outside its heights", rim_test),
    ("room design: something electrical in a zone round the shower, rated too low", zone_ip_test),
    ("room design: electrical items rated low are fine outside the zones", outside_zones_test),
    ("room design: a shower wall waterproofed too low", waterproofing_test),
    ("room design: the floor falling too little to the drain", fall_test),
    ("room design: something electrical in a zone round the shower, with no IP rating", zone_no_ip_test),
    ("room design: the door swinging into a fitting's clear space", door_swing_test),
    ("room design: a door opening out never swings into a clear space", door_swing_out_test),
    ("room design: the drain on the dry side of the floor step", drain_side_test),
    # ---- materials design (materials_design_checks.py): quantities, the take-off against the materials list ----
    ("materials design: a tile-box shortage shows on the floor plan", take_off_short_on_plan_test),
    ("materials design: too few tile boxes for the room", tile_boxes_test),
    # ---- design problems and the build ----
    ("design problems: every design problem's lines fit inside its drawing", problems_fit_test),
    ("design problems: publishing refuses a build with a design problem, after writing the PDF", publishable_test),
    ("assumed values: each is listed by the build, with its value", assumed_listed_test),
    # ---- drawing design (drawing_design_checks.py): how each drawing reads, measured as drawn ----
    ("drawing design: a name too long for its drawing shows as a problem under it", off_drawing_test),
    ("drawing design: a text running off the edge",
     lambda: drawing_check_test(drawing_design_checks.OFF, [("RUNS-OFF", "")],
                                '<text class="key" x="380" y="100">RUNS-OFF</text>')),
    ("drawing design: two words drawn over each other",
     lambda: drawing_check_test(drawing_design_checks.OVERLAP, [("AAAA", "BBBB")],
                                '<text class="key" x="100" y="100">AAAA</text>', '<text class="key" x="110" y="102">BBBB</text>')),
    ("drawing design: two words with a clear gap between them",
     lambda: drawing_check_test(drawing_design_checks.OVERLAP, [],
                                '<text class="key" x="100" y="100">AAAA</text>', '<text class="key" x="100" y="130">BBBB</text>')),
    ("drawing design: a tag drawn over a word",
     lambda: drawing_check_test(drawing_design_checks.OVERLAP, [("WORD", "T1")],
                                '<text class="key" x="100" y="100">WORD</text>',
                                '<rect class="tag" x="105" y="88" width="24" height="16"/><text class="tag-text" x="117" y="99">T1</text>')),
    ("drawing design: a line drawn through a label that needs clear ground",
     lambda: drawing_check_test(drawing_design_checks.COVERED, [("A WALL NAME", "")],
                                '<text class="wall-name" x="100" y="100">A WALL NAME</text>',
                                '<line class="axis" x1="90" y1="96" x2="200" y2="96"/>')),
    ("drawing design: a line clear of a label",
     lambda: drawing_check_test(drawing_design_checks.COVERED, [],
                                '<text class="wall-name" x="100" y="100">A WALL NAME</text>',
                                '<line class="axis" x1="90" y1="130" x2="200" y2="130"/>')),
    # ---- the room: bad data ----
    ("room: a value marked as assumed that isn't there", assumed_missing_test),
    ("room: waterproofing on an item that isn't a zone", waterproofing_not_zone_test),
    ("room: the floor's drain isn't a floor item",
     {ROOM: data(lambda d: d["floor"].update(drain="no_such_item"))}, "[floor] drain 'no_such_item' isn't a floor item"),
    ("room: a norm without its source", {ROOM: data(lambda d: find(d["norm"], "norm").pop("url"))}, "has no 'url'"),
    ("room: a norm a design check needs, missing",
     lambda: ({ROOM: data(lambda d: d.update(norm=[n for n in d["norm"] if n["id"] != room.NORMS[-1]]))},
              f"no norm '{room.NORMS[-1]}'")),
    ("room: a norm no design check uses",
     lambda: ({ROOM: data(lambda d: d["norm"].append({**d["norm"][0], "id": "no_such_norm"}))},
              "norm 'no_such_norm' isn't used by any design check")),
    ("room: a norm for an item that isn't in the room",
     lambda: ({ROOM: data(lambda d: find(d["norm"], "norm with an item", lambda n: "item" in n).update(item="no_such_item"))},
              "applies to item 'no_such_item', which isn't in the room")),
    ("products: a product's IP rating reaches its detail on the list", ip_in_detail_test),
    ("room: a wall missing", {ROOM: data(lambda d: d["wall"].pop())},
     f"{len(RAW[ROOM]['wall']) - 1} walls — the room has {len(room.PLAN_SIDES)}"),
    ("room: items on a wall with no elevation",
     lambda: ({ROOM: data(lambda d: wall_raw(d).update(elevation=False))}, f"wall '{wall_raw()['id']}' has items but no elevation")),
    ("room: an item naming a product that isn't on the materials list",
     lambda: (edit_item(lambda e: "product" in e, "item with a product", lambda e: e.update(product="no_such_product")),
              "names product 'no_such_product', which is not on the materials list")),
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
     lambda: (edit_item(lambda e: e["id"] not in room.CONSTRUCTION, "item", lambda e: e.update(id=room.CONSTRUCTION[0])),
              f"'{room.CONSTRUCTION[0]}' is worked out from how the room is constructed")),
    ("room: two tiles naming the same product",
     {ROOM: data(lambda d: d["tile"][1].update(product=d["tile"][0]["product"]))} if len(RAW[ROOM]["tile"]) > 1 else {},
     f"tile product '{RAW[ROOM]['tile'][0]['product']}' is used twice"),
    ("room: two walls with the same reference",
     {ROOM: data(lambda d: d["wall"][1].update(ref=d["wall"][0]["ref"]))}, f"ref '{RAW[ROOM]['wall'][0]['ref']}' is used twice"),
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
     {MATERIALS: data(lambda d: tile_product(d).pop("per_box"))}, "on the materials list to have a per_box"),
    ("room: a tiling height that isn't a whole number",
     {ROOM: data(lambda d: find(d["tile"], "tile").update(tiling_height=find(d["tile"], "tile")["tiling_height"] + 0.5))},
     "'tiling_height' must be a whole number more than 0"),
    ("room: a tile that isn't a whole number of mm",
     {MATERIALS: data(lambda d: tile_product(d)["size"].update(w=500.5, h=500.5))}, "a whole number of mm"),
    ("room: a tile that isn't square",
     {MATERIALS: data(lambda d: tile_product(d)["size"].update(h=1))}, "the tile count needs square tiles"),
    ("room: a step's high side on a floor item that isn't a step",
     lambda: ({ROOM: data(lambda d: put(find(d["floor"]["item"], "floor rect", lambda e: e["shape"] == "rect"),
                                        "high", "end", room.ITEM))}, "is a rect, so it has no 'high'")),
    ("room: a drawing note that fills in a value",
     lambda: (edit_item(lambda e: "note_en" in e, "item with a note", lambda e: e.update(note_th="ดู {phase:x}", note_en="see {phase:x}")),
              "note_th uses {phase} (it can use: nothing)")),
    ("room: a wall given an elevation gets its own drawing", elevation_wall_test),
    ("room: a tiling height that isn't whole tiles counts the cut row", cut_row_test),
    # ---- products: on the materials list; their names and sizes are used by the room ----
    ("products: a product's size reaches its detail on the list", size_in_name_test),
    ("products: a detail showing a size the product doesn't have",
     lambda: (edit_entry(lambda e: "size" not in e, "product without a size", lambda e: e.update(detail_th="ขนาด {w}", detail_en="sized {w}")),
              "detail_th uses {w} (it can use: nothing)")),
    ("products: an item on the drawings takes its product's name",
     lambda: ({MATERIALS: data(lambda d: by_id(d["entry"], find(wall_raw()["item"], "item with a product",
                                                               lambda e: "product" in e)["product"]).update(en="NAME-TEST"))},
              f"NAME-TEST{RAW[ROOM]['symbols']['dash']}")),
    # ---- materials.toml ----
    ("materials: the still-to-buy total is shown", {}, built(lambda p: p.materials.total_cell())),
    # ---- labour.toml ----
    ("labour: a measured line is the room's take-off times its rate", take_off_line_test),
    ("labour: a counted line is how many the materials list has, times its rate", count_line_test),
    ("labour: a share of materials is its percent of what they still cost", share_line_test),
    ("labour: the labour total, and the grand total with the materials", labour_totals_test),
    ("labour: a line with two quantities",
     lambda: labour_data_test(lambda x, e: put(x, "n", 1, labour.LINE),
                              "line {i} ({rate}) must take its quantity from exactly one of")),
    ("labour: a line with no quantity",
     lambda: labour_data_test(lambda x, e: x.pop("take_off"), "line {i} ({rate}) must take its quantity from exactly one of")),
    ("labour: a take-off the room doesn't work out",
     lambda: labour_data_test(lambda x, e: x.update(take_off="no_such_take_off"),
                              "line {i} ({rate}) takes off 'no_such_take_off', which the room doesn't work out")),
    ("labour: a take-off in a different unit from its rate",
     lambda: (lambda i, e: (edit_labour_line(i, lambda x: x.update(take_off="lintel_m")),
                            f"line {i} ({e['rate']}) measures in metre, but rate '{e['rate']}' is per m2"))(
         *labour_line("line measured in m2", lambda e: "take_off" in e and labour_rate(e["rate"])["unit"] == "m2"))),
    ("labour: a product that isn't on the materials list",
     lambda: (lambda i, e: (edit_labour_line(i, lambda x: x.update(count=["no_such_product"])),
                            f"line {i} ({e['rate']}) names product 'no_such_product', which is not on the materials list"))(
         *labour_line("counted line", lambda e: "count" in e))),
    ("labour: a rate with no book, not marked assumed",
     lambda: (lambda r: ({LABOUR: data(lambda d: [by_id(d["rate"], r["id"]).pop(k) for k in ("book", "item", "url")])},
                         f"rate '{r['id']}' has no book, so its rate must be marked assumed"))(
         find(RAW[LABOUR]["rate"], "rate from the book by item", lambda r: "item" in r))),
    ("labour: a rate giving both an item and a note in its book",
     lambda: (lambda r: ({LABOUR: data(lambda d: put(by_id(d["rate"], r["id"]), "book_note", 1, labour.RATE))},
                         f"rate '{r['id']}' must give its place in its book: an item or a book_note, not both"))(
         find(RAW[LABOUR]["rate"], "rate from the book by item", lambda r: "item" in r))),
    ("labour: a quantity written for a share of materials",
     lambda: (lambda i, e: (edit_labour_line(i, lambda x: (x.pop("of_products"), put(x, "n", 1, labour.LINE))),
                            f"line {i} ({e['rate']}) writes a quantity, but rate '{e['rate']}' is a share of materials"))(
         *labour_line("share line", lambda e: "of_products" in e))),
    ("materials: a price change flows into the total", price_test),
    ("materials: a price that isn't whole baht shows to the satang", money_test),
    ("materials: a shop with a bad code pattern", {MATERIALS: data(lambda d: find(d["shop"], "shop").update(sku="["))},
     "sku isn't a pattern"),
    ("materials: a shop with a bad link", {MATERIALS: data(lambda d: find(d["shop"], "shop").update(link="{nope}"))},
     "link uses {nope} (it can use: sku, sku_digits)"),
    ("materials: approximate with no price", lambda: (make_approx_no_price(), "has approx but no price")),
    ("materials: a code that isn't the shop's kind of code", sku_test),
    ("materials: to procure with no price", no_price_test),
    ("materials: to procure with no shop", make("procure", price=10), "has status procure, so it needs a shop and sku"),
    ("materials: existing with a price", make("existing", price=10), "has status existing, so it has no price"),
    ("materials: existing with a shop", reused_with_shop_test),
    ("materials: by the trade with nobody to bring it", make("by_trade"), "has status by_trade, so it needs by_th and by_en"),
    ("materials: who brings it, on a line the trade doesn't bring",
     lambda: (edit_line(to_buy_with_shop, "product still to buy with a shop",
                        lambda ln: ln.update(by_th="ช่าง", by_en="trade")), "has status procure, so it has no by_th and by_en")),
    ("materials: an item by the trade shows who brings it",
     make("by_trade", by=("ช่าง-TEST", "BRINGER-TEST")), "| ช่าง-TEST / BRINGER-TEST |"),
    ("materials: the list is in sections by work section", {}, built(group_heading)),
    ("materials: in a work section, what is still to procure comes before what is on site", {}, built(buy_before_on_site)),
    ("materials: the link is made from shop and code", link_test),
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
     {MATERIALS: data(lambda d: d["section"].update(note_th=d["section"]["note_th"] + " {nope}",
                                                    note_en=d["section"]["note_en"] + " {nope}"))},
     "[section] note_th uses {nope}"),
    ("materials: a group's note shows under its heading",
     {MATERIALS: data(lambda d: find(d["work_section"], "work section").update(note_th="GROUP-NOTE-TH", note_en="GROUP-NOTE-EN"))},
     "*GROUP-NOTE-TH*<br>*GROUP-NOTE-EN*"),
    # ---- phases.toml ----
    ("phases: the steps are numbered", lambda: ({}, step_number())),
    ("phases: a reference resolves to its number", lambda: ref_test(insert=False)),
    ("phases: inserting a step renumbers it and its references", lambda: ref_test(insert=True)),
    ("phases: a brace that isn't a reference",
     lambda: (edit_step(lambda s: s.update(th=s["th"] + " {phase:make-good}", en=s["en"] + " {phase:make-good}")), "that isn't a reference like {step:id}")),
    ("phases: a reference to an id that doesn't exist",
     lambda: (edit_step(lambda s: s.update(th=s["th"] + " {step:no_such_step}", en=s["en"] + " {step:no_such_step}")), "{step:no_such_step} doesn't match")),
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
