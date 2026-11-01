"""The room: room.toml, read, checked, worked out and drawn. It knows nothing about the phases;
the products on the material list are handed to it (for their names and sizes).

    r = load(Path("room.toml"), products)   # products = {id: Product}, from materials.load()
    r.render()          # [svg text] — the floor plan, then each drawn wall
    r.warnings()        # [(wall id, (th, en))] — every design rule broken
    r.tiles_needed()    # [TilesNeeded] — tiles per tile, worked out from the room

  1. read       room.toml against the fields declared below (common.check)
  2. work out   each wall's place from the order of the walls; each item's name and size from
                its product; the column, door and lintel from how the room is built; tile counts
  3. rules      a hole too near a tile joint, items that clash or run off the wall, a part
                outside the item it belongs to — warnings, shown under the drawing
  4. draw       the floor plan and each drawn wall, as SVG; their look is in style.css

How this room is built is the one thing written here rather than in room.toml (README rule 1):
the existing column stands at the x = 0 end of its wall, the door opening beside it and the
lintel over the opening.

The tiles needed and any warnings print with `mise run check`; the drawings are in the PDF.
"""
import math
from dataclasses import dataclass
from html import escape
from pathlib import Path

from common import NAME, NAMED, DataError, Labels, both, check, check_each, placeholders, read_toml

FILE = "room.toml"

# ======================================== 1. read ========================================
# Every kind of entry in room.toml, declared once (common.check: "!" = required, "@x" = one of
# the x ids).
NUM = "count!"            # a size: more than 0
FILE_FIELDS = {"room": "table!", "column": "table!", "door": "table!", "lintel": "table!", "tile": "list!",
               "floor": "table!", "wall": "list!", "labels": "table!", "symbols": "table!"}
ROOM = {"length": NUM, "width": NUM, "ceiling": NUM, "min_clear": NUM}
COLUMN = {**NAMED, "width": NUM, "wall": "@wall!"}
DOOR = {"product": "text!", "note_th": "text", "note_en": "text"}
LINTEL = {"product": "text!", "bearing": NUM}
TILE = {"id": "text!", "product": "text!", **NAME, "top": NUM, "fill": "text!"}
FLOOR = {"tag": "text!", "tile": "@tile!", "item": "list"}
WALL = {"id": "text!", **NAME, "tag": "text!", "tile": "@tile!",
        "drawn": "flag!", "item": "list"}
# An item names a product (and takes its name from it) or has its own name (th, en) — checked in _items.
ITEM = {"id": "text!", "product": "text", "th": "text", "en": "text", "shape": "@shape!",
        "x": "amount", "y": "amount", "w": "count", "h": "count", "d": "count", "high": "@end", "part": "text",
        "note_th": "text", "note_en": "text"}
ENDS = ("start", "end")   # the ends of a wall or the floor: x = 0, and x = its length
BUILT = ("column", "door", "lintel")      # the items room.py works out — no item in room.toml takes these ids
SYMBOLS = {k: "text!" for k in ("axis_x", "axis_y", "width", "height", "none", "times", "warning", "ok", "up", "down")}
LABELS = {"floor_plan": (), "elevation_title": ("wall",), "viewed_inside": (), "seen_above": (),
          "mm": (), "generated": (), "tile_top": ("top",), "floor_higher": ("h",), "higher": (), "lower": (),
          "floor": (), "items": (), "x_from": ("wall", "axis"), "centre_height": (), "see_notes": (), "dashed": (),
          "all_clear": ("min_clear",), "tile_count": ("tile", "need", "parts", "boxes", "planned", "spare"),
          "warn_joint": ("item", "axis", "v", "d"), "warn_past_end": ("item",), "warn_overlap": ("a", "b"),
          "warn_outside": ("item", "axis", "v", "parent", "low", "high"), "warn_above": ("item", "axis", "v", "parent"),
          "tile_short": ("tile", "planned", "boxes")}
# What each shape needs to be drawn (after its product's size is filled in).
WALL_SHAPES = {"rect": ("x", "y", "w", "h"), "circle": ("x", "y", "w"), "point": ("x", "y"),
               "zone": ("x", "w"), "opening": ("x", "y", "w", "h")}
FLOOR_SHAPES = {"rect": ("x", "y", "w", "d"), "step": ("x", "h", "high")}   # the floor is seen from above; a
                                                                              # step's high side is one end
PLAN_SIDES = ("top", "right", "bottom", "left")                      # the walls' order round the plan


def _check(raw):
    check(FILE, "the file", raw, FILE_FIELDS, ordered=False)
    tiles = check_each(FILE, "tile", raw["tile"], TILE)
    walls = check_each(FILE, "wall", raw["wall"], WALL, {"tile": [t["id"] for t in tiles]})
    if len(walls) != len(PLAN_SIDES):
        raise DataError(f"{FILE}: {len(walls)} walls — the room has {len(PLAN_SIDES)}, in order round the plan")
    known = {"tile": [t["id"] for t in tiles], "wall": [w["id"] for w in walls]}
    for key, fields in (("room", ROOM), ("column", COLUMN), ("door", DOOR), ("lintel", LINTEL), ("floor", FLOOR),
                        ("symbols", SYMBOLS)):
        check(FILE, f"[{key}]", raw[key], fields, known)
    for w in walls:
        if w.get("item") and not w["drawn"]:
            raise DataError(f"{FILE}: wall '{w['id']}' has items but isn't drawn")
        check_each(FILE, f"wall '{w['id']}' item", w.get("item", []), ITEM, {"shape": WALL_SHAPES, "end": ENDS})
    check_each(FILE, "floor item", raw["floor"].get("item", []), ITEM, {"shape": FLOOR_SHAPES, "end": ENDS})


# ======================================== the model ========================================
@dataclass(frozen=True)
class Tile:
    id: str              # what the floor and walls call it
    product: str         # its id on the material list
    th: str
    en: str
    size: int            # square, mm (from the product)
    per_box: int         # (from the product)
    top: int             # tiled up to this height on a wall
    fill: str            # its colour on the drawings


@dataclass(frozen=True)
class Item:
    no: str              # its number on the drawing: its order on its wall or the floor
    id: str              # what a part names it by
    th: str
    en: str
    shape: str
    x: float = None
    y: float = None
    w: float = None
    h: float = None
    d: float = None
    high: str = None     # a step: which end is higher (start: x = 0, end: x = the length)
    part: str = None     # the id of the item it belongs to
    note_th: str = ""
    note_en: str = ""

    def label(self):
        """'3 ท่อน้ำทิ้งอ่าง', '3 Basin waste': how a warning names it."""
        return f"{self.no} {self.th}", f"{self.no} {self.en}"


@dataclass(frozen=True)
class Wall:
    id: str
    th: str
    en: str
    tag: str             # its letter on the floor plan
    side: str            # top, right, bottom or left on the floor plan (from its order)
    right: str           # the wall at x = 0, facing this one from inside (the next one round)
    left: str            # the wall at its far end (the one before)
    length: float
    along_room: bool     # runs along the room's length (so the floor step meets it)
    tile: str
    tiled_run: float     # the length actually tiled (the door's wall: not the door opening)
    drawn: bool
    items: tuple


@dataclass(frozen=True)
class TilesNeeded:
    tile: Tile
    parts: tuple         # ((surface, tiles), …) — surface is "floor" or a wall id

    @property
    def need(self):
        return sum(n for _, n in self.parts)

    @property
    def boxes(self):
        return math.ceil(self.need / self.tile.per_box)


@dataclass(frozen=True)
class Room:
    length: float
    width: float
    ceiling: float
    min_clear: float     # the design rule: every hole at least this far from a tile joint
    tiles: dict          # {id: Tile}
    floor_tag: str
    floor_tile: str
    floor: tuple         # the floor's items
    walls: dict          # {id: Wall}, in order round the plan
    labels: Labels
    symbols: dict        # the marks on the drawings: x, y, W, H, —, ×, ⚠

    def tiles_needed(self):
        """Tiles needed per tile: the floor, and each wall's tiled run up to its tile's top (a cut
        row counts as a row)."""
        out = []
        for t in self.tiles.values():
            parts = [("floor", math.ceil(self.length / t.size) * math.ceil(self.width / t.size))] \
                if self.floor_tile == t.id else []
            parts += [(w.id, math.ceil(t.top / t.size) * math.ceil(w.tiled_run / t.size))
                      for w in self.walls.values() if w.tile == t.id]
            out.append(TilesNeeded(t, tuple(parts)))
        return out

    def wall_warnings(self, wall):
        """Every design rule broken on one wall, as (th, en)."""
        t = self.tiles[wall.tile]
        return (_joint_warnings(self, wall.items, wall.length, t.size, t.top)
                + _clash_warnings(self, wall.items, wall.length) + _part_warnings(self, wall.items))

    def warnings(self):
        return [(w.id, x) for w in self.walls.values() for x in self.wall_warnings(w)]

    def render(self):
        """Every drawing as svg text: the floor plan, then each drawn wall."""
        return [draw_plan(self)] + [draw_wall(self, w) for w in self.walls.values() if w.drawn]


# ======================================== 2. work out ========================================
def load(path, products):
    """Read and check room.toml, and work out every wall and item. `products` = {id: Product}."""
    raw = read_toml(Path(path), "the room, its walls and tiles, and every item on them")
    _check(raw)
    r = raw["room"]
    tiles = {t["id"]: _tile(t, products) for t in raw["tile"]}
    floor = _items(raw["floor"].get("item", []), "floor item", FLOOR_SHAPES, products, r["width"])  # a step runs
                                                                                    # from the first wall
    walls = _walls(raw, products)
    return Room(r["length"], r["width"], r["ceiling"], r["min_clear"], tiles, raw["floor"]["tag"],
                raw["floor"]["tile"], tuple(floor), walls, Labels(FILE, raw["labels"], LABELS), raw["symbols"])


def _product(products, where, pid, needs=()):
    """A product on the material list that has the sizes `needs`."""
    if pid not in products:
        raise DataError(f"{FILE}: {where} names product '{pid}', which is not on the material list")
    p = products[pid]
    for k in needs:
        if getattr(p, k) is None:
            raise DataError(f"{FILE}: {where} needs a {k} in the size of product '{pid}' on the material list")
    return p


def _tile(e, products):
    p = _product(products, f"tile '{e['id']}'", e["product"], ("w", "h", "per_box"))
    if p.w != p.h:
        raise DataError(f"{FILE}: tile '{e['id']}' is {p.w:g} × {p.h:g} — the tile count needs square tiles")
    return Tile(e["id"], p.id, e["th"], e["en"], int(p.w), p.per_box, e["top"], e["fill"])


def _note(e, key, where):
    """A note as written: it stands on its own, so it fills in nothing."""
    placeholders(FILE, f"{where} {key}", e.get(key, ""), ())
    return e.get(key, "")


def _items(entries, kind, shapes, products, across):
    """The items of one wall or the floor, numbered by their order, each with its product's name and
    size. A zone or a step with no depth runs `across` the room, out from its wall."""
    out = []
    for i, e in enumerate(entries, 1):
        where = f"{kind} '{e['id']}'"
        if e["id"] in BUILT:
            raise DataError(f"{FILE}: {where} — '{e['id']}' is worked out from how the room is built, "
                            f"so no item takes that id ({', '.join(BUILT)})")
        if ("product" in e) == ("th" in e):
            raise DataError(f"{FILE}: {where} needs a product or a name (th, en) — one, not both")
        p = _product(products, where, e["product"]) if "product" in e else None
        have = {**(p.size() if p else {}), **{k: e[k] for k in ("x", "y", "w", "h", "d", "high") if k in e}}
        if e["shape"] in ("zone", "step"):
            have.setdefault("d", across)
        missing = [k for k in shapes[e["shape"]] if k not in have]
        if missing:
            raise DataError(f"{FILE}: {where} ({e['shape']}) needs '{missing[0]}' (give it here, or through its product)")
        out.append(Item(str(i), e["id"], p.th if p else e["th"], p.en if p else e["en"], e["shape"],
                        **{k: float(have[k]) for k in ("x", "y", "w", "h", "d") if k in have}, high=e.get("high"),
                        part=e.get("part"), note_th=_note(e, "note_th", where), note_en=_note(e, "note_en", where)))
    ids = {it.id for it in out}
    for it in out:
        if it.part and it.part not in ids:
            raise DataError(f"{FILE}: {kind} '{it.id}' belongs to '{it.part}', which isn't on the same wall")
    return out


def _walls(raw, products):
    """Every wall, its place from the walls' order, with its items — and the column, the door and the
    lintel on the column's wall, worked out from how the room is built."""
    r, col, order = raw["room"], raw["column"], raw["wall"]
    door = _product(products, "[door]", raw["door"]["product"], ("w", "h"))
    lintel = _product(products, "[lintel]", raw["lintel"]["product"], ("h",))
    bearing = raw["lintel"]["bearing"]
    walls = {}
    for i, e in enumerate(order):
        along = i % 2 == 0                                            # the first and third run along the room
        length, across = (r["length"], r["width"]) if along else (r["width"], r["length"])
        items = _items(e.get("item", []), f"wall '{e['id']}' item", WALL_SHAPES, products, across)
        run = length
        if e["id"] == col["wall"]:
            # How this room is built: the column at x = 0, the door opening beside it, the lintel over it.
            if col["width"] + door.w >= length:
                raise DataError(f"{FILE}: the door ({door.w:g}) doesn't fit beside the column ({col['width']:g}) "
                                f"in wall '{e['id']}' ({length:g})")
            n = len(items)
            notes = lambda e, where: {k: _note(e, k, where) for k in ("note_th", "note_en")}  # noqa: E731
            items += [
                Item(str(n + 1), "column", col["th"], col["en"], "column", x=col["width"] / 2, y=r["ceiling"] / 2,
                     w=col["width"], h=r["ceiling"], **notes(col, "[column]")),
                Item(str(n + 2), "door", door.th, door.en, "door", x=col["width"] + door.w / 2, y=door.h / 2,
                     w=door.w, h=door.h, **notes(raw["door"], "[door]")),
                Item(str(n + 3), "lintel", lintel.th, lintel.en, "rect", x=col["width"] + (door.w + bearing) / 2,
                     y=door.h + lintel.h / 2, w=door.w + bearing, h=lintel.h),
            ]
            run = length - door.w                                       # the door opening isn't tiled
        walls[e["id"]] = Wall(e["id"], e["th"], e["en"], e["tag"],
                              PLAN_SIDES[i], order[(i + 1) % len(order)]["id"], order[i - 1]["id"], length, along,
                              e["tile"], run, e["drawn"], tuple(items))
    return walls


# ======================================== 3. rules ========================================
# Warnings, not errors: each is (th, en), worded by its label.
def _warn(room, key, **values):
    return room.labels.th(key, **values), room.labels.en(key, **values)


def _joint_warnings(room, items, length, tile, top):
    """A hole (fixing, outlet, an item's centre) too near a tile joint: closer than min_clear
    but not exactly on it."""
    jx = list(range(tile, int(length), tile))
    jy = sorted(set(range(tile, top, tile)) | {top})   # the tile top edge counts as a joint
    out = []
    for it in items:
        if it.shape not in ("point", "rect", "circle"):
            continue
        checks = [("axis_x", it.x, jx)] if jx else []
        if jy and it.y is not None and it.y < top:
            checks.append(("axis_y", it.y, jy))
        for axis, v, joints in checks:
            d = min(abs(v - j) for j in joints)
            if 0 < d < room.min_clear:
                out.append(_warn(room, "warn_joint", item=it.label(), axis=room.symbols[axis], v=f"{v:g}", d=f"{d:g}"))
    return out


def _box(it):
    """(x0, x1, y0, y1) of a solid item, or None."""
    if it.shape not in ("rect", "circle", "opening", "door") or None in (it.x, it.w, it.y, it.h):
        return None
    return it.x - it.w / 2, it.x + it.w / 2, it.y - it.h / 2, it.y + it.h / 2


def _clash_warnings(room, items, length):
    solids = [(it, _box(it)) for it in items if _box(it)]
    out = [_warn(room, "warn_past_end", item=it.label()) for it, b in solids if b[0] < 0 or b[1] > length]
    for i, (a, ba) in enumerate(solids):
        for b, bb in solids[i + 1:]:
            if ba[0] < bb[1] and bb[0] < ba[1] and ba[2] < bb[3] and bb[2] < ba[3]:
                out.append(_warn(room, "warn_overlap", a=a.label(), b=b.label()))
    return out


def _part_warnings(room, items):
    """A part (a fixing, an outlet) must sit within the item it belongs to: inside its width and
    not above its top — catches an item moved without its parts."""
    by_id = {it.id: it for it in items}
    out = []
    for it in items:
        parent = by_id.get(it.part)
        if not parent or None in (it.x, parent.x, parent.w):
            continue
        if abs(it.x - parent.x) > parent.w / 2:
            out.append(_warn(room, "warn_outside", item=it.label(), axis=room.symbols["axis_x"], v=f"{it.x:g}",
                             parent=(parent.th, parent.en), low=f"{parent.x - parent.w / 2:g}",
                             high=f"{parent.x + parent.w / 2:g}"))
        if None not in (it.y, parent.y, parent.h) and it.y > parent.y + parent.h / 2:
            out.append(_warn(room, "warn_above", item=it.label(), axis=room.symbols["axis_y"], v=f"{it.y:g}",
                             parent=(parent.th, parent.en)))
    return out


# ======================================== 4. draw ========================================
# How the drawings are laid out. Their look (colours, line styles, text sizes) is in style.css.
WALL_SCALE = 0.3          # px per mm on a wall drawing
PLAN_SCALE = 0.25         # px per mm on the floor plan
MIN_WIDTH = 900           # every drawing at least this wide, so they line up on the page
TITLE_Y, SUBTITLE_Y = 28, 48
WALL_MARGINS = (70, 40, 70, 90)          # px round the wall: left, right, top, bottom
PLAN_MARGINS = (90, 90, 90, 80)          # px round the floor
BOTTOM_SPACE = {"wall": 90, "plan": 120}  # px below the legend
HEIGHT_STEP = 500         # mm between the height marks up a wall drawing
# Where things sit, in mm.
ZONE_TAG_HEIGHT = 200     # a zone's number on a wall drawing
ZONE_TAG_IN = 120         # a zone's tag, this far in from its edge on the floor plan
OVERHEAD = 1000           # a fitting whose bottom is higher than this is dashed on the floor plan
# Sizes and offsets, in px.
PLAN_WALL = 12            # a wall's thickness on the floor plan
COLUMN_THICK = 1.6        # the column, this many times a wall's thickness
NUMBER_R = 8              # the round number on a wall drawing
POINT_ARM = 6             # half a point's cross
NUMBER_BESIDE = 10        # a point's number, this far to its right
TAG_H = 16                # a tag's height (its width: TAG_W)
TAG_W = {"wall": 16, "plan": 24, "plan_legend": 26}
TAG_TEXT_DOWN = 11.5      # a tag's text baseline below its top
NUMBER_TEXT_DOWN = 3.5    # a number's text baseline below its centre
TEXT_DOWN = 4             # a small text's baseline below the point it marks
GAP = 8                   # text clear of what it labels
SIDE_NAME_OUT = (14, 44)  # a wall drawing's side names, out from the right and left edges
TICKS_DOWN, TICK_ARM, TICK_TEXT_DOWN = 18, 5, 18                     # the x marks under a wall
TILE_TEXT_UP, TILE_TOP_TEXT_DOWN, TILE_TOP_TEXT_IN = 5, 14, 4
STEP_TEXT_UP = 4
PLAN_GRID_TEXT = (34, 20)  # the plan's joint numbers: below the bottom wall, right of the floor
PLAN_TAG_OUT = 16          # an opening's tag, out from the wall
FLOOR_TAG = (-18, 4)       # a floor item's tag, from its centre
DOOR_TAG_UP = 12           # the door's tag, above its leaf
WALL_NAME_OUT = {"top": 8, "bottom": 16, "left": 40, "right": 40}    # the wall names round the plan
STEP_MARK = 6              # "higher" / "lower" either side of the floor step
KEY_DOWN = 16              # the plan's dashed-line key, under its heading
WARNINGS_DOWN = 16         # the warnings, below a wall drawing's legend
LEGEND_ROW, LEGEND_LINE, LEGEND_GAP, LEGEND_TAG_UP = 20, 14, 4, 12
WARNING_LINE = 18
WRAP = 125                # characters per legend note line


def start(a, width, height, ml, title, subtitle):
    """Open a drawing: its frame, background, title and subtitle."""
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
      f'viewBox="0 0 {width:.0f} {height:.0f}">')
    a('<rect class="paper" width="100%" height="100%"/>')
    a(f'<text class="title" x="{ml}" y="{TITLE_Y}">{title}</text>')
    a(f'<text class="subtitle" x="{ml}" y="{SUBTITLE_Y}">{subtitle}</text>')


def tag(a, cx, top, width, text):
    """A rounded tag with its text, centred on cx."""
    a(f'<rect class="tag" x="{cx - width / 2}" y="{top}" width="{width}" height="{TAG_H}" rx="{TAG_H / 2}"/>')
    a(f'<text class="tag-text" x="{cx}" y="{top + TAG_TEXT_DOWN}" text-anchor="middle">{text}</text>')


def wrap(text):
    """Split text into lines of about WRAP characters, breaking at spaces."""
    lines, cur = [], ""
    for word in text.split(" "):
        if cur and len(cur) + 1 + len(word) > WRAP:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    return lines + ([cur] if cur else [])


def legend_row(room, it, number, with_size=True, with_notes=True):
    """(number, headline, [note lines]) for one item."""
    lab, s = room.labels, room.symbols

    def f(v):
        return f"{v:g}" if v is not None else s["none"] if it.shape == "zone" else lab.both("see_notes")
    head = both(it.th, it.en)
    if with_size:
        size = "" if it.w is None else f"  {s['width']} {f(it.w)}" + \
            ("" if it.h is None else f" {s['times']} {s['height']} {f(it.h)}")
        head += f" — {s['axis_x']} {f(it.x)}  {s['axis_y']} {f(it.y)}{size}"
    notes = [ln for n in (it.note_th, it.note_en) if n and with_notes for ln in wrap(n)]
    return number, head, notes


def legend_height(rows):
    return sum(LEGEND_ROW + LEGEND_LINE * len(n) + LEGEND_GAP for _, _, n in rows)


def draw_legend(a, rows, x0, y0, tag_w):
    """The legend rows (tag, headline, note lines); returns the y below the last row."""
    yy, tx = y0, x0 + GAP + tag_w / 2 + GAP
    for number, head, notes in rows:
        yy += LEGEND_ROW
        tag(a, x0 + GAP, yy - LEGEND_TAG_UP, tag_w, number)
        a(f'<text class="legend" x="{tx}" y="{yy}">{escape(head)}</text>')
        for line in notes:
            yy += LEGEND_LINE
            a(f'<text class="legend-note" x="{tx}" y="{yy}">{escape(line)}</text>')
        yy += LEGEND_GAP
    return yy


def draw_warnings(a, room, warnings, x, y):
    """Each warning in Thai, then English — or the all-clear, in Thai then English."""
    lines = [("warning", f"{room.symbols['warning']} {escape(t)}") for w in warnings for t in w] or \
        [("ok", f"{room.symbols['ok']} {room.labels.th('all_clear', min_clear=room.min_clear)}"),
         ("ok", f"{room.symbols['ok']} {room.labels.en('all_clear', min_clear=room.min_clear)}")]
    for k, (cls, text) in enumerate(lines):
        a(f'<text class="{cls}" x="{x}" y="{y + WARNING_LINE * k}">{text}</text>')


# ---------- a wall drawing ----------
def draw_wall(room, wall):
    """One wall, seen from inside the bathroom, x from the corner on your right: svg text."""
    t, lab, s = room.tiles[wall.tile], room.labels, room.symbols
    L, CEIL = wall.length, room.ceiling
    ML, MR, MT, MB = WALL_MARGINS
    W, H = L * WALL_SCALE, CEIL * WALL_SCALE
    rows = [legend_row(room, it, it.no) for it in wall.items]

    def X(mm):                                      # x is measured from the right-hand corner
        return ML + (L - mm) * WALL_SCALE

    def Y(mm):
        return MT + (CEIL - mm) * WALL_SCALE

    out = []
    a = out.append
    start(a, max(ML + W + MR, MIN_WIDTH), MT + H + MB + legend_height(rows) + BOTTOM_SPACE["wall"], ML,
          lab.both("elevation_title", wall=(wall.th, wall.en)),
          f'{lab.both("viewed_inside", sep=" · ")} · {lab.both("mm")} · {lab.both("generated")}')
    _wall_face(a, room, wall, t, X, Y, W)
    _wall_sides(a, room, wall, ML, MT, W, H)
    _wall_ticks(a, _wall_items(a, wall, t, X, Y), X, Y(0), ML, W)
    ly0 = MT + H + MB
    right = room.walls[wall.right]
    a(f'<text class="heading" x="{ML}" y="{ly0}">{lab.both("items")} '
      f'({lab.both("x_from", wall=(right.th, right.en), axis=s["axis_x"])} · '
      f'{s["axis_y"]} = {lab.both("centre_height")})</text>')
    draw_warnings(a, room, room.wall_warnings(wall), ML,
                  draw_legend(a, rows, ML, ly0, TAG_W["wall"]) + WARNINGS_DOWN)
    a("</svg>")
    return "\n".join(out)


def _wall_face(a, room, wall, t, X, Y, W):
    """The wall, its tiled part and tile joints, the height marks, and the floor step where it meets it."""
    ML, lab, top = X(wall.length), room.labels, t.top
    a(f'<rect class="wall-face" x="{ML}" y="{Y(room.ceiling)}" width="{W}" height="{room.ceiling * WALL_SCALE}"/>')
    a(f'<rect x="{ML}" y="{Y(top)}" width="{W}" height="{top * WALL_SCALE}" fill="{t.fill}"/>')
    for k in range(t.size, int(wall.length), t.size):
        a(f'<line class="joint" x1="{X(k)}" y1="{Y(top)}" x2="{X(k)}" y2="{Y(0)}"/>')
        a(f'<text class="joint-text" x="{X(k)}" y="{Y(top) - TILE_TEXT_UP}" text-anchor="middle">{k}</text>')
    for k in range(t.size, top, t.size):
        a(f'<line class="joint" x1="{ML}" y1="{Y(k)}" x2="{ML + W}" y2="{Y(k)}"/>')
    for k in range(0, int(room.ceiling) + 1, HEIGHT_STEP):
        a(f'<text class="joint-text" x="{ML - GAP}" y="{Y(k) + TEXT_DOWN}" text-anchor="end">{k}</text>')
    a(f'<line class="tile-top" x1="{ML}" y1="{Y(top)}" x2="{ML + W}" y2="{Y(top)}"/>')
    a(f'<text class="tile-top-text" x="{ML + W - TILE_TOP_TEXT_IN}" y="{Y(top) + TILE_TOP_TEXT_DOWN}" '
      f'text-anchor="end">{lab.both("tile_top", top=top)}</text>')
    for step in (f for f in room.floor if f.shape == "step" and wall.along_room):
        # the raised floor, from the step to its high end; floor x is this wall's x on the first wall,
        # and runs the other way on the third
        ends = (0, step.x) if step.high == "start" else (step.x, room.length)
        x0, x1 = sorted(f if wall.side == "top" else wall.length - f for f in ends)
        a(f'<rect class="step-face" x="{X(x1)}" y="{Y(step.h)}" width="{(x1 - x0) * WALL_SCALE}" '
          f'height="{step.h * WALL_SCALE}"/>')
        a(f'<text class="step-text" x="{X((x0 + x1) / 2)}" y="{Y(step.h) - STEP_TEXT_UP}" text-anchor="middle">'
          f'{lab.both("floor_higher", h=f"{step.h:g}")}</text>')


def _wall_sides(a, room, wall, ML, MT, W, H):
    """The walls at either end, named up the sides."""
    cy, x_ = MT + H / 2, room.symbols["axis_x"]
    for x, rot, w, at in ((ML + W + SIDE_NAME_OUT[0], 90, room.walls[wall.right], 0),
                          (ML - SIDE_NAME_OUT[1], -90, room.walls[wall.left], wall.length)):
        a(f'<text class="side-name" x="{x}" y="{cy}" text-anchor="middle" transform="rotate({rot} {x} {cy})">'
          f'{both(w.th, w.en)} ({x_} = {at:g})</text>')


def _wall_items(a, wall, t, X, Y):
    """Every item on the wall, with its number; returns the x of each, for the ticks."""
    xs = set()
    for it in wall.items:
        x, w, y, h = it.x, it.w, it.y, it.h
        xs.add(int(x))
        lx, ly = X(x), Y(ZONE_TAG_HEIGHT if it.shape == "zone" else y)
        if it.shape == "zone":
            a(f'<rect class="zone" x="{X(x + w / 2)}" y="{Y(t.top)}" width="{w * WALL_SCALE}" '
              f'height="{t.top * WALL_SCALE}"/>')
        elif it.shape in BOXES:
            a(f'<rect class="{BOXES[it.shape]}" x="{X(x + w / 2)}" y="{Y(y + h / 2)}" '
              f'width="{w * WALL_SCALE}" height="{h * WALL_SCALE}"/>')
        elif it.shape == "circle":
            a(f'<circle class="round" cx="{lx}" cy="{ly}" r="{w / 2 * WALL_SCALE}"/>')
        elif it.shape == "point":
            for s in (1, -1):
                a(f'<line class="point" x1="{lx - POINT_ARM}" y1="{ly - POINT_ARM * s}" '
                  f'x2="{lx + POINT_ARM}" y2="{ly + POINT_ARM * s}"/>')
        nx = lx + (NUMBER_BESIDE if it.shape == "point" else 0)
        a(f'<circle class="number" cx="{nx}" cy="{ly}" r="{NUMBER_R}"/>')
        a(f'<text class="number-text" x="{nx}" y="{ly + NUMBER_TEXT_DOWN}" text-anchor="middle">{it.no}</text>')
    return xs


BOXES = {"rect": "item", "column": "column", "opening": "opening", "door": "opening"}   # shape → its look


def _wall_ticks(a, xs, X, floor_y, ML, W):
    """Each item's x, marked along the floor."""
    base = floor_y + TICKS_DOWN
    a(f'<line class="axis" x1="{ML}" y1="{base}" x2="{ML + W}" y2="{base}"/>')
    for x in sorted(xs):
        ty = base + TICK_TEXT_DOWN
        a(f'<line class="axis" x1="{X(x)}" y1="{base - TICK_ARM}" x2="{X(x)}" y2="{base + TICK_ARM}"/>')
        a(f'<text class="tick-text" x="{X(x)}" y="{ty}" text-anchor="end" transform="rotate(-45 {X(x)} {ty})">{x}</text>')


# ---------- the floor plan ----------
# Seen from above, the first wall at the top and the rest clockwise. A floor position is x from the
# right-hand wall (leftwards) and y from the top wall (downwards), in mm — the same way the first
# wall's drawing measures x.
OUT = {"top": (0, -1), "right": (1, 0), "bottom": (0, 1), "left": (-1, 0)}       # outwards, in px


def draw_plan(room):
    """The floor plan: svg text."""
    lab, L, D = room.labels, room.length, room.width
    ML, MR, MT, MB = PLAN_MARGINS
    PW, PH = L * PLAN_SCALE, D * PLAN_SCALE
    shown = {w.id: [it for it in w.items if _on_plan(it)] for w in room.walls.values()}
    rows = [legend_row(room, it, w.tag + it.no, with_size=False, with_notes=False)
            for w in room.walls.values() for it in shown[w.id]]
    rows += [legend_row(room, it, room.floor_tag + it.no, with_size=False) for it in room.floor]

    def P(fx, fy):                                  # a floor position → px
        return ML + (L - fx) * PLAN_SCALE, MT + fy * PLAN_SCALE

    out, tags = [], []
    a = out.append
    start(a, max(ML + PW + MR, MIN_WIDTH), MT + PH + MB + legend_height(rows) + BOTTOM_SPACE["plan"], ML,
          lab.both("floor_plan"), f'{lab.both("seen_above", sep=" · ")} · {lab.both("mm")} · {lab.both("generated")}')
    _plan_floor(a, room, P, ML, MT, PW, PH)
    walls = room.walls.values()
    for w in walls:                                 # the walls first, then what's in and on them
        _plan_wall(a, room, w, P)
    for w in walls:
        _plan_openings(a, room, w, P, shown[w.id], tags)
    for w in walls:
        _plan_footprints(a, room, w, P, shown[w.id], tags)
    _plan_floor_items(a, room, P, tags)
    for text, tx, ty in tags:
        tag(a, tx, ty - TAG_H / 2, TAG_W["plan"], text)
    _plan_wall_names(a, room, ML, MT, PW, PH)
    ly0 = MT + PH + MB
    keys = [f"{w.tag} = {both(w.th, w.en)}" for w in room.walls.values() if shown[w.id]]
    keys.append(f"{room.floor_tag} = {lab.both('floor')}")
    a(f'<text class="heading" x="{ML}" y="{ly0}">{lab.both("items")} — {" · ".join(keys)}</text>')
    a(f'<text class="key" x="{ML}" y="{ly0 + KEY_DOWN}">{lab.both("dashed")}</text>')
    draw_legend(a, rows, ML, ly0 + KEY_DOWN, TAG_W["plan_legend"])
    a("</svg>")
    return "\n".join(out)


def _on_plan(it):
    """A wall item is listed on the plan when it is a window or the door, or stands out from the wall
    (it has a depth). The column is drawn with the wall."""
    return it.shape in ("opening", "door") or (bool(it.d) and it.shape != "column")


def _to_floor(room, wall, x, d=0):
    """A point on a wall — x along it from its right-hand corner, d out from it — as a floor position."""
    L, D = room.length, room.width
    return {"top": (x, d), "right": (d, D - x), "bottom": (L - x, D - d), "left": (L - d, x)}[wall.side]


def _px_box(P, a_, b_):
    """px (x, y, width, height) of the box between two floor positions."""
    (x0, y0), (x1, y1) = P(*a_), P(*b_)
    return min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)


def _rect(a, cls, box):
    a('<rect class="{}" x="{}" y="{}" width="{}" height="{}"/>'.format(cls, *box))


def _plan_floor(a, room, P, ML, MT, PW, PH):
    """The floor in its tile's colour, its tile joints set out from the right and top walls."""
    t, L, D = room.tiles[room.floor_tile], room.length, room.width
    a(f'<rect x="{ML}" y="{MT}" width="{PW}" height="{PH}" fill="{t.fill}"/>')
    for k in range(t.size, int(L), t.size):
        (x, y0), (_, y1) = P(k, 0), P(k, D)
        a(f'<line class="joint" x1="{x}" y1="{y0}" x2="{x}" y2="{y1}"/>')
        a(f'<text class="joint-text" x="{x}" y="{y1 + PLAN_WALL + PLAN_GRID_TEXT[0]}" text-anchor="middle">{k}</text>')
    for k in range(t.size, int(D), t.size):
        y = P(0, k)[1]
        a(f'<line class="joint" x1="{ML}" y1="{y}" x2="{ML + PW}" y2="{y}"/>')
        a(f'<text class="joint-text" x="{ML + PW + PLAN_GRID_TEXT[1]}" y="{y + TEXT_DOWN}">{k}</text>')


def _band(room, wall, P, x0, x1, thick=PLAN_WALL):
    """px box of a wall's thickness, outside the floor, from x0 to x1 along it."""
    ox, oy = OUT[wall.side]
    x, y, w, h = _px_box(P, _to_floor(room, wall, x0), _to_floor(room, wall, x1))
    return (x, y + min(oy, 0) * thick, w, thick) if oy else (x + min(ox, 0) * thick, y, thick, h)


def _cuts(wall):
    """Where a wall isn't solid: the door and the column, as (x0, x1, item)."""
    return sorted((it.x - it.w / 2, it.x + it.w / 2, it) for it in wall.items if it.shape in ("column", "door"))


def _plan_wall(a, room, wall, P):
    """A wall on the plan: solid except at the door and the column, the column drawn thicker. The top
    and bottom walls run on over the corners."""
    over = PLAN_WALL / PLAN_SCALE if wall.side in ("top", "bottom") else 0
    edges = [-over] + [e for c0, c1, _ in _cuts(wall) for e in (c0, c1)] + [wall.length + over]
    for x0, x1 in zip(edges[::2], edges[1::2]):
        if x1 > x0:
            _rect(a, "plan-wall", _band(room, wall, P, x0, x1))
    for c0, c1, it in _cuts(wall):
        if it.shape == "column":
            _rect(a, "plan-column", _band(room, wall, P, c0, c1, PLAN_WALL * COLUMN_THICK))


def _plan_openings(a, room, wall, P, shown, tags):
    """The door, with its tag over its leaf, and the windows, drawn over the wall with their tags outside."""
    ox, oy = OUT[wall.side]
    for it in shown:
        if it.shape == "door":
            tags.append((wall.tag + it.no, *_plan_door(a, room, wall, P, it.x - it.w / 2, it.x + it.w / 2)))
        elif it.shape == "opening":
            _rect(a, "plan-opening", _band(room, wall, P, it.x - it.w / 2, it.x + it.w / 2))
            px, py = P(*_to_floor(room, wall, it.x))
            tags.append((wall.tag + it.no, px + ox * (PLAN_WALL + PLAN_TAG_OUT), py + oy * (PLAN_WALL + PLAN_TAG_OUT)))


def _plan_footprints(a, room, wall, P, shown, tags):
    """The footprint of each item that stands out from the wall: dashed when it's mounted high."""
    for it in (i for i in shown if i.shape not in ("opening", "door")):
        w = it.w or 0
        box = _px_box(P, _to_floor(room, wall, it.x - w / 2), _to_floor(room, wall, it.x + w / 2, it.d))
        if it.shape == "zone":
            _rect(a, "zone", box)
            tags.append((wall.tag + it.no, *P(*_to_floor(room, wall, it.x, it.d - ZONE_TAG_IN))))
            continue
        overhead = it.y is not None and it.y - (it.h or 0) / 2 > OVERHEAD
        _rect(a, "footprint overhead" if overhead else "footprint", box)
        tags.append((wall.tag + it.no, *P(*_to_floor(room, wall, it.x, it.d / 2))))


def _plan_door(a, room, wall, P, x0, x1):
    """The door leaf, hinged at the column side of the opening (x0) and opening in, and its swing.
    Returns where its tag goes: over the middle of the leaf."""
    r = (x1 - x0) * PLAN_SCALE
    hx, hy = P(*_to_floor(room, wall, x0))
    jx, jy = P(*_to_floor(room, wall, x1))
    ix, iy = -OUT[wall.side][0], -OUT[wall.side][1]                  # inwards
    ex, ey = hx + ix * r, hy + iy * r
    sweep = 1 if (ex - hx) * (jy - hy) - (ey - hy) * (jx - hx) > 0 else 0
    a(f'<line class="door-leaf" x1="{hx}" y1="{hy}" x2="{ex}" y2="{ey}"/>')
    a(f'<path class="door-swing" d="M {ex} {ey} A {r} {r} 0 0 {sweep} {jx} {jy}"/>')
    return hx + ix * r / 2, hy + iy * r / 2 - DOOR_TAG_UP


def _plan_floor_items(a, room, P, tags):
    """The floor's items: a rectangle with its centre line, and the step with its high and low sides."""
    lab = room.labels
    for it in room.floor:
        number = room.floor_tag + it.no
        if it.shape == "rect":
            _rect(a, "floor-item", _px_box(P, (it.x - it.w / 2, it.y - it.d / 2), (it.x + it.w / 2, it.y + it.d / 2)))
            (x0, y), (x1, _) = P(it.x + it.w / 2, it.y), P(it.x - it.w / 2, it.y)
            a(f'<line class="floor-item-line" x1="{x0}" y1="{y}" x2="{x1}" y2="{y}"/>')
            cx, cy = P(it.x, it.y)
            tags.append((number, cx + FLOOR_TAG[0], cy + FLOOR_TAG[1]))
        elif it.shape == "step":
            (x, y0), (_, y1) = P(it.x, 0), P(it.x, it.d)
            a(f'<line class="step-line" x1="{x}" y1="{y0}" x2="{x}" y2="{y1}"/>')
            s, right = room.symbols, it.high == "start"          # x = 0 is the plan's right-hand side
            for text, on_right in ((f'{s["up"]} {lab.both("higher")}', right), (f'{lab.both("lower")} {s["down"]}', not right)):
                anchor = "" if on_right else ' text-anchor="end"'
                a(f'<text class="step-mark" x="{x + (STEP_MARK if on_right else -STEP_MARK)}" y="{y1 - STEP_MARK}"{anchor}>'
                  f'{text}</text>')
            tags.append((number, *P(it.x, it.d / 2)))


def _plan_wall_names(a, room, ML, MT, PW, PH):
    """Each wall's name, outside its side of the plan."""
    T, cx, cy = PLAN_WALL, ML + PW / 2, MT + PH / 2
    for w in room.walls.values():
        g = WALL_NAME_OUT[w.side]
        x, y, rot = {"top": (cx, MT - T - g, 0), "bottom": (cx, MT + PH + T + g, 0),
                     "left": (ML - T - g, cy, -90), "right": (ML + PW + T + g, cy, 90)}[w.side]
        turn = f' transform="rotate({rot} {x} {y})"' if rot else ""
        a(f'<text class="wall-name" x="{x}" y="{y}" text-anchor="middle"{turn}>{both(w.th, w.en)}</text>')
