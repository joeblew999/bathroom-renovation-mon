#!/usr/bin/env python3
"""The drawings: site.toml and layout.toml, read, checked, and drawn as the floor plan and
the wall elevations. It knows nothing about the phases or the materials.

    d = load(Path("."))     # the folder holding site.toml and layout.toml
    d.render()              # {file name: svg text} — the floor plan, then the three walls
    d.warnings()            # [(wall id, warning)] — every design rule broken
    d.tiles_needed()        # [TilesNeeded] — tiles per colour, worked out from the room

The site (room, door, lintel, window, tiles, product sizes, walls) and the layout (every
position) are the only inputs. Items that follow from the site — the column, the door
opening, the lintel, the window, the door on the floor plan — are worked out here, never
typed twice. A drawing note stands on its own: it can't refer to a phase, step or rule.

Two kinds of problem:
  - bad data (it doesn't fit together)  -> DataError at load; nothing is built
  - a design rule broken (a hole too near a joint, a clash, a fixing outside its item)
                                         -> a warning, shown red under the drawing

Usage:  python3 drawings.py [folder]    (prints the tiles needed and any warnings)
"""
import math
import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path

from common import DataError, need, number, only, read_toml

SITE, LAYOUT = "site.toml", "layout.toml"
SITE_KEYS = {
    "room": {"length", "width", "ceiling"},
    "new_wall": {"length"},
    "door": {"width", "height"},
    "lintel": {"height", "bearing"},
    "old_wall": {"step"},
    "window": {"from_main_wall", "width", "sill", "height"},
    "grey_tile": {"size", "per_box", "top"},
    "white_tile": {"size", "per_box", "top"},
    "rules": {"min_clear"},
}
WALL_IDS = ("main_wall", "new_wall", "window_wall", "opposite_wall")
WALL_KEYS = {"th", "en", "view_th", "view_en", "tile"}
PRODUCT_KEYS = {"w", "h", "d"}
DRAWN = ("main_wall", "new_wall", "window_wall")            # walls with items in layout.toml
SITE_ITEMS = ("column", "door_opening", "lintel", "window", "door")
NAME_KEYS = {"th", "en", "note_th", "note_en"}
LAYOUT_KEYS = {"no", "th", "en", "product", "shape", "x", "y", "w", "h", "d", "part", "note_th", "note_en"}
TILE_COLOURS = ("grey", "white")
# What each shape needs to be drawn (after the product's size is filled in).
SHAPE_NEEDS = {"rect": ("x", "y", "w", "h"), "circle": ("x", "y", "w"), "point": ("x", "y"),
               "vline": ("x",), "zone": ("x", "w"), "step": ("x",)}
FLOOR_SHAPE_NEEDS = {"rect": ("x", "y", "w", "d"), "step": ("x",)}   # floor items are seen from above


# ---------- the model ----------
@dataclass(frozen=True)
class Item:
    no: str
    th: str
    en: str
    shape: str
    x: float = None
    w: float = None
    y: float = None
    h: float = None
    d: float = None
    part: str = None
    note_th: str = ""
    note_en: str = ""


@dataclass(frozen=True)
class Wall:
    id: str
    th: str
    en: str
    view_th: str
    view_en: str
    length: float        # along the wall
    tile: str            # "grey" / "white"
    tiled_run: float     # the length that is actually tiled (the new wall: not the door opening)
    along_room: bool     # runs along the room's length (so the floor step meets it)
    right: str           # the wall at x = 0, seen from inside facing this wall
    left: str            # the wall at x = length
    items: tuple


@dataclass(frozen=True)
class TilesNeeded:
    colour: str
    size: int
    per_box: int
    parts: tuple         # ((surface, tiles), …) — surface is "floor" or a wall id

    @property
    def need(self):
        return sum(n for _, n in self.parts)

    @property
    def boxes(self):
        return math.ceil(self.need / self.per_box)


@dataclass(frozen=True)
class Drawings:
    site: dict
    walls: dict
    floor: tuple

    def value(self, key, name):
        return _value(self.site, key, name)

    @property
    def room_l(self): return self.value("room", "length")
    @property
    def room_w(self): return self.value("room", "width")
    @property
    def ceiling(self): return self.value("room", "ceiling")
    @property
    def new_wall_l(self): return self.value("new_wall", "length")
    @property
    def column(self): return self.room_w - self.new_wall_l          # column face at the end of the new wall
    @property
    def min_clear(self): return self.value("rules", "min_clear")

    def tile(self, colour):
        """(size, top, per_box) of the grey or white tile."""
        return _tile(self.site, colour)

    def tiles_needed(self):
        """Tiles needed per colour: the floor (grey) and each wall's tiled run."""
        out = []
        for colour in TILE_COLOURS:
            size, top, per_box = self.tile(colour)
            parts = []
            if colour == "grey":
                parts.append(("floor", math.ceil(self.room_l / size) * math.ceil(self.room_w / size)))
            for w in self.walls.values():
                if w.tile == colour:
                    parts.append((w.id, top // size * math.ceil(w.tiled_run / size)))
            out.append(TilesNeeded(colour, size, per_box, tuple(parts)))
        return out

    def wall_warnings(self, wall_id):
        """Every design rule broken on one wall."""
        w = self.walls[wall_id]
        size, top, _ = self.tile(w.tile)
        return (_joint_warnings(w.items, w.length, size, top, self.min_clear)
                + _clash_warnings(w.items, w.length) + _part_warnings(w.items))

    def warnings(self):
        """[(wall id, warning)] for every wall with items."""
        return [(wid, x) for wid, w in self.walls.items() if w.items for x in self.wall_warnings(wid)]

    def render(self):
        """Every drawing: {file name: svg text}, the floor plan first."""
        out = {"floor-plan.svg": draw_plan(self)}
        for wid, name_ in ELEVATIONS.items():
            out[name_] = draw_wall(self, self.walls[wid])
        return out


# ---------- loading ----------
def load(folder):
    """Read and check site.toml and layout.toml in `folder`, and build every wall."""
    folder = Path(folder)
    site = read_toml(folder / SITE, "the room, walls, tiles and product sizes")
    layout = read_toml(folder / LAYOUT, "all the positions")
    _check_site(site)
    only(LAYOUT, "the file", layout, set(DRAWN) | {"floor", "site_items"})
    walls, floor = _walls(site, layout)
    return Drawings(site, walls, floor)


def _value(site, key, name):
    try:
        return site[key][name]
    except KeyError:
        raise DataError(f"{SITE}: [{key}] needs '{name}'") from None


def _tile(site, colour):
    k = f"{colour}_tile"
    return _value(site, k, "size"), _value(site, k, "top"), _value(site, k, "per_box")


def _note(e, key, where):
    """A note as written. It stands on its own, so a {phase:…}-style reference is refused."""
    t = e.get(key, "")
    if "{" in t:
        raise DataError(f"{LAYOUT}: {where} '{key}' has a reference in braces — a drawing note "
                        f"can't refer to a phase, step or rule; write it out")
    return t


def _check_site(site):
    only(SITE, "the file", site, set(SITE_KEYS) | {"walls", "products"})
    for k, allowed in SITE_KEYS.items():
        only(SITE, f"[{k}]", site.get(k, {}), allowed)
        for n, v in site.get(k, {}).items():
            number(SITE, f"[{k}]", n, v)
    walls = site.get("walls", {})
    only(SITE, "[walls]", walls, WALL_IDS)
    for w in WALL_IDS:
        e = walls.get(w)
        if e is None:
            raise DataError(f"{SITE}: [walls.{w}] is missing")
        only(SITE, f"[walls.{w}]", e, WALL_KEYS)
        need(SITE, f"[walls.{w}]", e, ("th", "en", "tile"))
        if e["tile"] not in TILE_COLOURS:
            raise DataError(f"{SITE}: [walls.{w}] has tile = {e['tile']!r} "
                            f"(must be one of: {', '.join(TILE_COLOURS)})")
    for name_, e in site.get("products", {}).items():
        only(SITE, f"[products.{name_}]", e, PRODUCT_KEYS)
        for n, v in e.items():
            number(SITE, f"[products.{name_}]", n, v)
    if _value(site, "new_wall", "length") - _value(site, "door", "width") <= 0:
        raise DataError(f"{SITE}: the door ({_value(site, 'door', 'width')}) does not fit "
                        f"in the new wall ({_value(site, 'new_wall', 'length')})")


def _walls(site, layout):
    """Every wall with its items (from layout.toml, plus those that follow from the site)."""
    names = layout.get("site_items", {})
    only(LAYOUT, "[site_items]", names, SITE_ITEMS)
    for k in SITE_ITEMS:
        if k not in names:
            raise DataError(f"{LAYOUT}: [site_items.{k}] is missing")
        only(LAYOUT, f"[site_items.{k}]", names[k], NAME_KEYS)
        need(LAYOUT, f"[site_items.{k}]", names[k], ("th", "en"))

    def named(k, no, shape, **dims):
        e, where = names[k], f"[site_items.{k}]"
        return Item(str(no), e["th"], e["en"], shape, note_th=_note(e, "note_th", where),
                    note_en=_note(e, "note_en", where), **{a: float(v) for a, v in dims.items()})

    v = lambda key, name_: _value(site, key, name_)             # noqa: E731
    room_l, room_w, ceiling = v("room", "length"), v("room", "width"), v("room", "ceiling")
    new_wall_l, door_w, door_h = v("new_wall", "length"), v("door", "width"), v("door", "height")
    column, solid = room_w - new_wall_l, new_wall_l - door_w
    products = site.get("products", {})
    items = {k: _layout_items(layout, k, products, room_w) for k in DRAWN + ("floor",)}

    # new wall, seen from inside facing it: x from the opposite long wall (the column side)
    n = _next(items["new_wall"])
    lt, lb = v("lintel", "height"), v("lintel", "bearing")
    items["new_wall"] += [
        named("column", n, "column", x=column / 2, w=column, y=ceiling / 2, h=ceiling),
        named("door_opening", n + 1, "opening", x=column + door_w / 2, w=door_w, y=door_h / 2, h=door_h),
        named("lintel", n + 2, "rect", x=column + (door_w + lb) / 2, w=door_w + lb, y=door_h + lt / 2, h=lt),
    ]
    # window wall: the window
    win = {k: v("window", k) for k in ("from_main_wall", "width", "sill", "height")}
    items["window_wall"].append(named("window", _next(items["window_wall"]), "opening",
                                      x=win["from_main_wall"] + win["width"] / 2, w=win["width"],
                                      y=win["sill"] + win["height"] / 2, h=win["height"]))
    # floor: the door (x along the new wall, y from the main wall), and the step's height
    items["floor"].append(named("door", _next(items["floor"]), "door", x=0, w=door_w, y=solid + door_w / 2))
    step_h = float(v("old_wall", "step"))
    items["floor"] = [Item(**{**it.__dict__, "h": step_h}) if it.shape == "step" and it.h is None else it
                      for it in items["floor"]]

    # Each wall seen from inside facing it, x from the corner on your right.
    geometry = {   # id: (length, tiled run, runs along the room, wall at x = 0, wall at x = length)
        "main_wall": (room_l, room_l, True, "new_wall", "window_wall"),
        "new_wall": (room_w, solid + column, False, "opposite_wall", "main_wall"),
        "window_wall": (room_w, room_w, False, "main_wall", "opposite_wall"),
        "opposite_wall": (room_l, room_l, True, "window_wall", "new_wall"),
    }
    walls = {}
    for wid in WALL_IDS:
        e = site["walls"][wid]
        length, run, along, right, left = geometry[wid]
        walls[wid] = Wall(wid, e["th"], e["en"], e.get("view_th", ""), e.get("view_en", ""), length,
                          e["tile"], run, along, right, left, tuple(items.get(wid, ())))
    return walls, tuple(items["floor"])


def _layout_items(layout, key, products, room_w):
    out = []
    needs = FLOOR_SHAPE_NEEDS if key == "floor" else SHAPE_NEEDS
    for e in layout.get(key, []):
        where = f"[[{key}]] entry {e.get('no', '?')}"
        only(LAYOUT, where, e, LAYOUT_KEYS)
        need(LAYOUT, where, e, ("no", "th", "en", "shape"))
        for k in ("no", "x", "y", "w", "h", "d", "part"):
            if k in e:
                number(LAYOUT, where, k, e[k])
        if e["shape"] not in needs:
            raise DataError(f"{LAYOUT}: {where} has shape {e['shape']!r} "
                            f"(on this {'floor' if key == 'floor' else 'wall'}: {', '.join(needs)})")
        dims = {}
        if "product" in e:
            if e["product"] not in products:
                raise DataError(f"{LAYOUT}: product '{e['product']}' is not in {SITE}")
            dims.update(products[e["product"]])
        dims.update({k: e[k] for k in ("w", "h", "d") if k in e})
        if e["shape"] in ("zone", "step") and "d" not in dims:
            dims["d"] = room_w                           # zones and the floor step run across the room
        have = {**{k: e[k] for k in ("x", "y") if k in e}, **dims}
        missing = [k for k in needs[e["shape"]] if k not in have]
        if missing:
            raise DataError(f"{LAYOUT}: {where} ({e['shape']}) needs '{missing[0]}' "
                            f"(give it here, or through its product)")
        f = lambda k: None if k not in have else float(have[k])     # noqa: E731
        out.append(Item(str(e["no"]), e["th"], e["en"], e["shape"], f("x"), f("w"), f("y"), f("h"), f("d"),
                        None if "part" not in e else str(e["part"]),
                        _note(e, "note_th", where), _note(e, "note_en", where)))
    nos = [it.no for it in out]
    for no in nos:
        if nos.count(no) > 1:
            raise DataError(f"{LAYOUT}: [[{key}]] number {no} is used twice")
    for it in out:
        if it.part and it.part not in nos:
            raise DataError(f"{LAYOUT}: [[{key}]] entry {it.no} belongs to item {it.part}, "
                            f"which is not in [[{key}]]")
    return out


def _next(items):
    return max([int(i.no) for i in items] + [0]) + 1


# ---------- design rules (warnings, not errors) ----------
# a hole too near a tile joint · items overlapping or off the end of the wall · a part
# (fixing, outlet) outside the item it belongs to
def _joint_warnings(items, length, tile, tile_top, min_clear):
    jx = list(range(tile, length, tile))
    jy = list(range(tile, tile_top + 1, tile))      # includes the tile top edge
    out = []
    for it in items:
        if it.shape not in ("point", "rect", "vline", "circle"):
            continue
        checks = [("x", it.x, jx)] if jx else []
        if it.y is not None and it.y < tile_top:
            checks.append(("y", it.y, jy))
        for axis, v, joints in checks:
            d = min(abs(v - j) for j in joints)
            if 0 < d < min_clear:
                out.append(f'{it.no} {it.en}: {axis} {v:g} is only {d:g} mm from a joint')
    return out


def _box(it):
    """Bounding box (x0, x1, y0, y1) of a solid item, or None."""
    if it.shape not in ("rect", "circle", "opening") or None in (it.x, it.w, it.y, it.h):
        return None
    return (it.x - it.w / 2, it.x + it.w / 2, it.y - it.h / 2, it.y + it.h / 2)


def _clash_warnings(items, length):
    out = []
    solids = [(it, _box(it)) for it in items if _box(it)]
    for it, (x0, x1, y0, y1) in solids:
        if x0 < 0 or x1 > length:
            out.append(f'{it.no} {it.en}: runs past the end of the wall')
    for i, (a_, ba) in enumerate(solids):
        for b_, bb in solids[i + 1:]:
            if ba[0] < bb[1] and bb[0] < ba[1] and ba[2] < bb[3] and bb[2] < ba[3]:
                out.append(f'{a_.no} {a_.en} overlaps {b_.no} {b_.en}')
    return out


def _part_warnings(items):
    """A part (e.g. a screw fixing, a pipe outlet) must still sit within the item it
    belongs to: inside its width, and not above its top. Catches an item that was
    moved without its parts."""
    by_no = {it.no: it for it in items}
    out = []
    for it in items:
        if not it.part:
            continue
        parent = by_no[it.part]                 # checked at load: it exists
        if None in (it.x, parent.x, parent.w):
            continue
        if abs(it.x - parent.x) > parent.w / 2:
            out.append(f'{it.no} {it.en}: x {it.x:g} is outside {parent.en} '
                       f'({parent.x - parent.w / 2:g}–{parent.x + parent.w / 2:g})')
        if None not in (it.y, parent.y, parent.h) and it.y > parent.y + parent.h / 2:
            out.append(f'{it.no} {it.en}: y {it.y:g} is above the top of {parent.en}')
    return out


# ---------- drawing ----------
S = 0.3                      # px per mm
ACC = "#c0392b"


TILE_FILL = {"grey": "#d9d9d6", "white": "#f1f1ee"}
ELEVATIONS = {"main_wall": "main-wall.svg", "new_wall": "new-wall.svg", "window_wall": "window-wall.svg"}


def name(w):
    """'ไทย / English' of a wall."""
    return f"{w.th} / {w.en}"


# ---------- legend text ----------
def wrap(text, width=125):
    """Split text into lines of about `width` characters, breaking at spaces."""
    lines, cur = [], ""
    for word in text.split(" "):
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    return lines + ([cur] if cur else [])


def legend_rows(items, with_dims=True):
    """(item, headline, [note lines]) for each item."""
    def f(v, it):
        if v is None:
            return "—" if it.shape == "zone" else "ดูหมายเหตุ / see notes"
        return f"{v:g}"
    rows = []
    for it in items:
        head = f'{it.th} / {it.en}'
        if with_dims:
            size = "" if it.w is None else f"  W {f(it.w, it)}" + \
                ("" if it.h is None else f" × H {f(it.h, it)}")
            head += f' — x {f(it.x, it)}  y {f(it.y, it)}{size}'
        notes = (wrap(it.note_th) if it.note_th else []) + (wrap(it.note_en) if it.note_en else [])
        rows.append((it, head, notes))
    return rows


def legend_height(rows):
    return sum(20 + 14 * len(n) + 4 for _, _, n in rows)


def draw_legend(a, rows, x0, y0, tag_w=16):
    """Draw the legend rows (tag, headline, note lines); returns the y below the last row."""
    yy = y0
    for tag, head, notes in rows:
        yy += 20
        a(f'<rect x="{x0 + 8 - tag_w / 2}" y="{yy - 12}" width="{tag_w}" height="16" rx="8" fill="{ACC}"/>')
        a(f'<text x="{x0 + 8}" y="{yy - 0.5}" font-size="9.5" fill="#fff" text-anchor="middle" '
          f'font-weight="bold">{tag}</text>')
        a(f'<text x="{x0 + 8 + tag_w / 2 + 8}" y="{yy}" font-size="12">{escape(head)}</text>')
        for line in notes:
            yy += 14
            a(f'<text x="{x0 + 8 + tag_w / 2 + 8}" y="{yy}" font-size="10" fill="#666">{escape(line)}</text>')
        yy += 4
    return yy


# ---------- drawing ----------
def draw_wall(d, wall):
    """One elevation, with its design-rule warnings shown in red: returns svg text."""
    items = wall.items
    tile, top, _ = d.tile(wall.tile)
    L, CEIL = wall.length, d.ceiling
    right, left = d.walls[wall.right], d.walls[wall.left]
    view_th = f" ({wall.view_th})" if wall.view_th else ""
    view_en = f" ({wall.view_en})" if wall.view_en else ""
    warnings = d.wall_warnings(wall.id)

    ML, MR, MT, MB = 70, 40, 70, 90
    W, H = L * S, CEIL * S
    svg_w = max(ML + W + MR, 900)
    rows = [(it.no, head, notes) for it, head, notes in legend_rows(items)]
    svg_h = MT + H + MB + legend_height(rows) + 90

    def X(mm):                      # x is measured from the right-hand corner
        return ML + (L - mm) * S

    def Y(mm):
        return MT + (CEIL - mm) * S

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w:.0f}" height="{svg_h:.0f}" '
      f'viewBox="0 0 {svg_w:.0f} {svg_h:.0f}" font-family="Helvetica, Arial, sans-serif">')
    a('<rect width="100%" height="100%" fill="#ffffff"/>')
    a(f'<text x="{ML}" y="28" font-size="18" font-weight="bold">{wall.th}{view_th} / {wall.en}{view_en} — elevation</text>')
    a(f'<text x="{ML}" y="48" font-size="12" fill="#555">มองจากในห้องน้ำ · Viewed from inside the bathroom · '
      f'มม. / mm · generated from site.toml + layout.toml</text>')

    # wall, tiled area, grid
    a(f'<rect x="{ML}" y="{MT}" width="{W}" height="{H}" fill="#fbfbf8" stroke="#222" stroke-width="2"/>')
    a(f'<rect x="{ML}" y="{Y(top)}" width="{W}" height="{top * S}" fill="{TILE_FILL[wall.tile]}"/>')
    for k in range(tile, L, tile):
        a(f'<line x1="{X(k)}" y1="{Y(top)}" x2="{X(k)}" y2="{Y(0)}" stroke="#9a9a96"/>')
        a(f'<text x="{X(k)}" y="{Y(top) - 5}" font-size="10" fill="#777" text-anchor="middle">{k}</text>')
    for k in range(tile, top, tile):
        a(f'<line x1="{ML}" y1="{Y(k)}" x2="{ML + W}" y2="{Y(k)}" stroke="#9a9a96"/>')
    for k in range(0, CEIL + 1, 500):
        a(f'<text x="{ML - 8}" y="{Y(k) + 4}" font-size="10" fill="#777" text-anchor="end">{k}</text>')
    a(f'<line x1="{ML}" y1="{Y(top)}" x2="{ML + W}" y2="{Y(top)}" stroke="#555" stroke-width="1.5"/>')
    a(f'<text x="{ML + W - 4}" y="{Y(top) + 14}" font-size="10" fill="#444" text-anchor="end">'
      f'ขอบกระเบื้อง / tile top {top}</text>')

    # raised floor at the basin end: the floor step meets the walls that run along the room
    if wall.along_room:
        step = next((f for f in d.floor if f.shape == "step"), None)
        if step and step.h:
            a(f'<rect x="{X(step.x)}" y="{Y(step.h)}" width="{step.x * S}" height="{step.h * S}" '
              f'fill="#f5cba7" stroke="#e67e22" stroke-width="1.5"/>')
            a(f'<text x="{X(step.x / 2)}" y="{Y(step.h) - 4}" font-size="10" fill="#e67e22" '
              f'text-anchor="middle">พื้นยกสูง {step.h:g} / floor {step.h:g} higher</text>')

    # side labels
    cy = MT + H / 2
    a(f'<text x="{ML + W + 14}" y="{cy}" font-size="12" text-anchor="middle" '
      f'transform="rotate(90 {ML + W + 14} {cy})">{name(right)} (x = 0)</text>')
    a(f'<text x="{ML - 44}" y="{cy}" font-size="12" text-anchor="middle" '
      f'transform="rotate(-90 {ML - 44} {cy})">{name(left)} (x = {L})</text>')

    # items
    xs = set()
    vline_xs = {it.x for it in items if it.shape == "vline"}
    for it in items:
        sh = it.shape
        x, w, y, h = it.x, it.w, it.y, it.h
        xs.add(int(x))
        lx, ly = X(x), (Y(y) if y is not None else Y(1000))
        if sh == "zone":
            a(f'<rect x="{X(x + w / 2)}" y="{Y(top)}" width="{w * S}" height="{top * S}" '
              f'fill="#5dade2" fill-opacity="0.15" stroke="#2e86c1" stroke-dasharray="6 4"/>')
            ly = Y(200)
        elif sh == "column":
            a(f'<rect x="{X(x + w / 2)}" y="{Y(y + h / 2)}" width="{w * S}" height="{h * S}" '
              f'fill="#7f8c8d" fill-opacity="0.6" stroke="#2c3e50" stroke-width="1.5"/>')
        elif sh == "opening":
            a(f'<rect x="{X(x + w / 2)}" y="{Y(y + h / 2)}" width="{w * S}" height="{h * S}" '
              f'fill="#d6eaf8" stroke="#2e86c1" stroke-width="2"/>')
        elif sh == "rect":
            a(f'<rect x="{X(x + w / 2)}" y="{Y(y + h / 2)}" width="{w * S}" height="{h * S}" '
              f'fill="#ffffff" fill-opacity="0.85" stroke="{ACC}" stroke-width="1.5"/>')
        elif sh == "circle":
            a(f'<circle cx="{lx}" cy="{ly}" r="{w / 2 * S}" fill="#eaf2f8" fill-opacity="0.8" '
              f'stroke="{ACC}" stroke-width="1.5"/>')
        elif sh == "point":
            a(f'<line x1="{lx - 6}" y1="{ly - 6}" x2="{lx + 6}" y2="{ly + 6}" stroke="{ACC}" stroke-width="2"/>')
            a(f'<line x1="{lx - 6}" y1="{ly + 6}" x2="{lx + 6}" y2="{ly - 6}" stroke="{ACC}" stroke-width="2"/>')
        elif sh == "vline":
            a(f'<line x1="{lx}" y1="{Y(0)}" x2="{lx}" y2="{Y(1000)}" stroke="#2e86c1" '
              f'stroke-width="1.5" stroke-dasharray="4 3"/>')
            ly = Y(1000) - 2
        tx = lx + (10 if sh in ("point", "vline") else 0)
        if sh == "rect" and x in vline_xs:
            tx = lx - 14
        a(f'<circle cx="{tx}" cy="{ly}" r="8" fill="{ACC}"/>')
        a(f'<text x="{tx}" y="{ly + 3.5}" font-size="10" fill="#fff" text-anchor="middle" '
          f'font-weight="bold">{it.no}</text>')

    # x ticks along the floor
    base = Y(0) + 18
    a(f'<line x1="{ML}" y1="{base}" x2="{ML + W}" y2="{base}" stroke="#444"/>')
    for x in sorted(xs):
        a(f'<line x1="{X(x)}" y1="{base - 5}" x2="{X(x)}" y2="{base + 5}" stroke="#444"/>')
        a(f'<text x="{X(x)}" y="{base + 18}" font-size="10" text-anchor="end" '
          f'transform="rotate(-45 {X(x)} {base + 18})">{x}</text>')

    # legend
    ly0 = MT + H + MB
    a(f'<text x="{ML}" y="{ly0}" font-size="13" font-weight="bold">รายการ / Items '
      f'(x จาก{right.th} / from the {right.en.lower()} · '
      f'y = ความสูงกึ่งกลาง / centre height)</text>')
    yy = draw_legend(a, rows, ML, ly0) + 16
    if warnings:
        for k, w_ in enumerate(warnings):
            a(f'<text x="{ML}" y="{yy + 18 * k}" font-size="12" fill="{ACC}">⚠ {escape(w_)}</text>')
    else:
        a(f'<text x="{ML}" y="{yy}" font-size="12" fill="#1e8449">✓ ทุกจุดห่างแนวยาแนวอย่างน้อย {d.min_clear} มม. '
          f'หรืออยู่กึ่งกลางแนวพอดี และไม่มีชิ้นใดทับกัน</text>')
        a(f'<text x="{ML}" y="{yy + 18}" font-size="12" fill="#1e8449">✓ Every centre is at least {d.min_clear} mm '
          f'off a joint (or exactly centred on one), and nothing overlaps</text>')
    a('</svg>')
    return "\n".join(out)


# ---------- floor plan ----------
def draw_plan(d):
    """The floor plan seen from above: returns svg text."""
    main, win, floor = d.walls["main_wall"].items, d.walls["window_wall"].items, d.floor
    names = {k: name(w) for k, w in d.walls.items()}
    L, Wd, NEW_WALL_L = d.room_l, d.room_w, d.new_wall_l
    GREY = d.tile("grey")[0]
    col = d.column                              # column width at the end of the new wall
    SP = 0.25
    ML, MR, MT, MB = 90, 90, 90, 80
    PW, PH = L * SP, Wd * SP
    svg_w = max(ML + PW + MR, 900)
    legend = [("M", it) for it in main if it.d] + [("F", it) for it in floor] + [("W", it) for it in win]
    # Wall items list names only (their notes are on the elevations); floor items carry their notes.
    rows = []
    for pre, it in legend:
        (r,) = legend_rows([it], with_dims=False)
        rows.append((pre + it.no, r[1], r[2] if pre == "F" else []))
    svg_h = MT + PH + MB + legend_height(rows) + 120
    T = 12                                      # drawn wall thickness, px

    # Seen from above with the main wall at the top: the new wall is on the right,
    # so x (from the new wall) runs right-to-left, matching the elevations.
    def X(mm):
        return ML + (L - mm) * SP

    def Y(mm):                                  # y measured from the main wall
        return MT + mm * SP

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w:.0f}" height="{svg_h:.0f}" '
      f'viewBox="0 0 {svg_w:.0f} {svg_h:.0f}" font-family="Helvetica, Arial, sans-serif">')
    a('<rect width="100%" height="100%" fill="#ffffff"/>')
    a(f'<text x="{ML}" y="28" font-size="18" font-weight="bold">ผังพื้น / Floor plan</text>')
    a(f'<text x="{ML}" y="48" font-size="12" fill="#555">มองจากด้านบน · Seen from above · มม. / mm · '
      f'generated from site.toml + layout.toml</text>')

    # floor + floor tile grid (full tiles set out from the new wall and the main wall)
    a(f'<rect x="{ML}" y="{MT}" width="{PW}" height="{PH}" fill="#d9d9d6"/>')
    for k in range(GREY, L, GREY):
        a(f'<line x1="{X(k)}" y1="{Y(0)}" x2="{X(k)}" y2="{Y(Wd)}" stroke="#9a9a96"/>')
        a(f'<text x="{X(k)}" y="{Y(Wd) + T + 34}" font-size="10" fill="#777" text-anchor="middle">{k}</text>')
    for k in range(GREY, Wd, GREY):
        a(f'<line x1="{ML}" y1="{Y(k)}" x2="{ML + PW}" y2="{Y(k)}" stroke="#9a9a96"/>')
        a(f'<text x="{ML + PW + 20}" y="{Y(k) + 4}" font-size="10" fill="#777">{k}</text>')

    # walls
    wall = 'fill="#444"'
    a(f'<rect x="{ML - T}" y="{MT - T}" width="{PW + 2 * T}" height="{T}" {wall}/>')          # main wall
    a(f'<rect x="{ML - T}" y="{MT + PH}" width="{PW + 2 * T}" height="{T}" {wall}/>')         # opposite long wall
    a(f'<rect x="{ML - T}" y="{MT}" width="{T}" height="{PH}" {wall}/>')                       # window wall
    # new wall: solid from the main wall to the door opening, then the column
    door = next((f for f in floor if f.shape == "door"), None)
    d0 = door.y - door.w / 2 if door else NEW_WALL_L
    d1 = door.y + door.w / 2 if door else NEW_WALL_L
    a(f'<rect x="{ML + PW}" y="{Y(0)}" width="{T}" height="{d0 * SP}" {wall}/>')
    a(f'<rect x="{ML + PW}" y="{Y(NEW_WALL_L)}" width="{T * 1.6}" height="{col * SP}" fill="#222"/>')
    # window opening in the window wall (window-wall x = plan y)
    for it in win:
        if it.shape == "opening":
            a(f'<rect x="{ML - T}" y="{Y(it.x - it.w / 2)}" width="{T}" height="{it.w * SP}" '
              f'fill="#d6eaf8" stroke="#2e86c1"/>')

    # door leaf and swing (hinge on the column side)
    if door:
        hx, hy, r = ML + PW, Y(d1), door.w * SP
        a(f'<line x1="{hx}" y1="{hy}" x2="{hx - r}" y2="{hy}" stroke="#222" stroke-width="2"/>')
        a(f'<path d="M {hx - r} {hy} A {r} {r} 0 0 1 {hx} {Y(d0)}" fill="none" stroke="#222" '
          f'stroke-dasharray="4 3"/>')

    tags = []
    # main-wall items: footprint from the wall out to D
    for it in main:
        if not it.d:
            continue
        w = it.w or 0
        if it.shape == "zone":
            a(f'<rect x="{X(it.x + w / 2)}" y="{Y(0)}" width="{w * SP}" height="{it.d * SP}" '
              f'fill="#5dade2" fill-opacity="0.15" stroke="#2e86c1" stroke-dasharray="6 4"/>')
            tags.append(("M" + it.no, X(it.x), Y(it.d - 120)))
            continue
        overhead = it.y is not None and it.y - (it.h or 0) / 2 > 1000   # above head-height fittings
        dash = ' stroke-dasharray="5 3"' if overhead else ""
        fill = "none" if overhead else "#ffffff"
        a(f'<rect x="{X(it.x + w / 2)}" y="{Y(0)}" width="{w * SP}" height="{it.d * SP}" '
          f'fill="{fill}" stroke="{ACC}" stroke-width="1.5"{dash}/>')
        tags.append(("M" + it.no, X(it.x), Y(it.d / 2)))
    # floor items
    for it in floor:
        if it.shape == "rect":
            a(f'<rect x="{X(it.x + it.w / 2)}" y="{Y(it.y - it.d / 2)}" width="{it.w * SP}" '
              f'height="{it.d * SP}" fill="#ffffff" stroke="#2e86c1" stroke-width="1.5"/>')
            a(f'<line x1="{X(it.x + it.w / 2)}" y1="{Y(it.y)}" x2="{X(it.x - it.w / 2)}" '
              f'y2="{Y(it.y)}" stroke="#2e86c1"/>')
            tags.append(("F" + it.no, X(it.x) - 18, Y(it.y) + 4))
        elif it.shape == "step":
            a(f'<line x1="{X(it.x)}" y1="{Y(0)}" x2="{X(it.x)}" y2="{Y(it.d)}" stroke="#e67e22" '
              f'stroke-width="4" stroke-dasharray="10 5"/>')
            a(f'<text x="{X(it.x) + 6}" y="{Y(it.d) - 6}" font-size="11" fill="#e67e22" '
              f'font-weight="bold">▲ สูง / higher</text>')
            a(f'<text x="{X(it.x) - 6}" y="{Y(it.d) - 6}" font-size="11" fill="#e67e22" '
              f'font-weight="bold" text-anchor="end">ต่ำ / lower ▼</text>')
            tags.append(("F" + it.no, X(it.x), Y(it.d / 2)))
        elif it.shape == "door":
            tags.append(("F" + it.no, ML + PW - door.w * SP / 2, Y(d1) - 12))
    # window-wall items: footprint out from the window wall where a depth is given
    for it in win:
        if it.d and it.w:
            a(f'<rect x="{ML}" y="{Y(it.x - it.w / 2)}" width="{it.d * SP}" height="{it.w * SP}" '
              f'fill="none" stroke="{ACC}" stroke-width="1.5" stroke-dasharray="5 3"/>')
        tags.append(("W" + it.no, ML - T - 16, Y(it.x)))

    for t, tx, ty in tags:
        a(f'<rect x="{tx - 12}" y="{ty - 8}" width="24" height="16" rx="8" fill="{ACC}"/>')
        a(f'<text x="{tx}" y="{ty + 3.5}" font-size="9.5" fill="#fff" text-anchor="middle" font-weight="bold">{t}</text>')

    # wall names
    a(f'<text x="{ML + PW / 2}" y="{MT - T - 8}" font-size="12" text-anchor="middle">{names["main_wall"]}</text>')
    a(f'<text x="{ML + PW / 2}" y="{MT + PH + T + 16}" font-size="12" text-anchor="middle">{names["opposite_wall"]}</text>')
    a(f'<text x="{ML - T - 40}" y="{MT + PH / 2}" font-size="12" text-anchor="middle" '
      f'transform="rotate(-90 {ML - T - 40} {MT + PH / 2})">{names["window_wall"]}</text>')
    a(f'<text x="{ML + PW + T + 40}" y="{MT + PH / 2}" font-size="12" text-anchor="middle" '
      f'transform="rotate(90 {ML + PW + T + 40} {MT + PH / 2})">{names["new_wall"]}</text>')

    # legend
    ly0 = MT + PH + MB
    mw, ww = d.walls["main_wall"], d.walls["window_wall"]
    a(f'<text x="{ML}" y="{ly0}" font-size="13" font-weight="bold">รายการ / Items — M = {mw.th} / {mw.en.lower()} · '
      f'F = พื้น / floor · W = {ww.th} / {ww.en.lower()}</text>')
    a(f'<text x="{ML}" y="{ly0 + 16}" font-size="11" fill="#555">เส้นประ = ติดผนังด้านบน (มองจากบน) / '
      f'dashed = mounted higher on the wall, seen from above</text>')
    ly0 += 16
    draw_legend(a, rows, ML, ly0, tag_w=26)
    a('</svg>')
    return "\n".join(out)


def main(argv):
    try:
        d = load(argv[1] if len(argv) > 1 else ".")
    except DataError as e:
        sys.exit(f"ERROR: {e}")
    for t in d.tiles_needed():
        print(f"{t.colour}: {t.need} tiles → {t.boxes} boxes")
    for where, w in d.warnings():
        print(f"WARNING ({where}): {w}")
    print(f"{len(d.render())} drawings · {len(d.warnings())} warnings")


if __name__ == "__main__":
    main(sys.argv)
