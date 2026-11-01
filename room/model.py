"""The room: room.toml, read and checked, every wall built with its items, and the design
rules. svg.py draws what this holds.

    r = load(Path("room.toml"), products)   # products = {id: Product}: sizes from the material list
    r.render()              # {file name: svg text} — the floor plan, then the three walls
    r.warnings()            # [(wall id, warning)] — every design rule broken
    r.tiles                 # {name: Tile} — every tile in room.toml
    r.tiles_needed()        # [TilesNeeded] — tiles per tile, worked out from the room

The room (its size, door, lintel, window, tiles, walls, every position) is the input, with the
products on the material list for every product's size — handed over by build.py. Items that
follow from the room — the column, the door opening, the lintel, the window, the door on the
floor plan — are worked out here, never typed twice. A drawing note stands on its own: it can't refer to a phase, step or rule.

Two kinds of problem:
  - bad data (it doesn't fit together)  -> DataError at load; nothing is built
  - a design rule broken (a hole too near a joint, a clash, a fixing outside its item)
                                         -> a warning, shown red under the drawing
"""
import math
from dataclasses import dataclass
from pathlib import Path

from common import NAMED, DataError, Labels, check, check_each, only, read_toml

from .svg import draw_plan, draw_wall

ROOM_FILE = "room.toml"
PLAN_SIDES = ("top", "right", "bottom", "left")
ROOM_ITEMS = ("column", "door_opening", "lintel", "window", "door")
RUNS = ("length", "width")
# Every kind of entry in room.toml, declared once (common.check: "!" = required, "@x" = one of
# the x ids). Every named thing has th and en. A product is named by its id on the material list.
FILE_FIELDS = {k: "table!" for k in ("room", "column", "door", "lintel", "old_wall", "window", "rules",
                                     "labels", "walls", "plan", "floor", "tiles", "room_items", "positions")}
NUM = "number!"
TABLES = {
    "room": {"length": NUM, "width": NUM, "ceiling": NUM},
    "column": {"width": NUM},
    "door": {"product": "text!", "wall": "@wall!"},
    "lintel": {"product": "text!", "bearing": NUM},
    "old_wall": {"step": NUM},
    "window": {"wall": "@wall!", "from_corner": NUM, "width": NUM, "sill": NUM, "height": NUM},
    "rules": {"min_clear": NUM},
    "floor": {"tile": "@tile!"},
    "plan": {side: "@wall!" for side in PLAN_SIDES},
    "room_items": {k: "table!" for k in ROOM_ITEMS},
}
WALL = {"th": "text!", "en": "text!", "view_th": "text", "view_en": "text", "tile": "@tile!",
        "runs": "@runs!", "right": "@wall!", "left": "@wall!", "drawn": "flag!"}
TILE = {"product": "text!", "th": "text!", "en": "text!", "top": NUM, "fill": "text!"}
POSITION = {"id": "text!", "th": "text!", "en": "text!", "product": "text", "shape": "@shape!",
            **{k: "number" for k in ("x", "y", "w", "h", "d")}, "part": "text",
            "note_th": "text", "note_en": "text"}
LABELS = {"floor_plan": (), "elevation_title": ("wall", "view"), "viewed_inside": (), "seen_above": (),
          "mm": (), "generated": (), "tile_top": ("top",), "floor_higher": ("h",), "higher": (), "lower": (),
          "floor": (), "items": (), "x_from": ("wall", "axis"), "centre_height": (), "see_notes": (), "dashed": (),
          "all_clear": ("min_clear",), "tag_main": (), "tag_floor": (), "tag_window": (),
          "axis_x": (), "axis_y": (), "width": (), "height": (),
          "tile_count": ("tile", "need", "parts", "boxes", "planned", "spare")}
# What each shape needs to be drawn (after the product's size is filled in).
SHAPE_NEEDS = {"rect": ("x", "y", "w", "h"), "circle": ("x", "y", "w"), "point": ("x", "y"),
               "vline": ("x",), "zone": ("x", "w"), "step": ("x",)}
FLOOR_SHAPE_NEEDS = {"rect": ("x", "y", "w", "d"), "step": ("x",)}   # floor items are seen from above


# ---------- the model ----------
@dataclass(frozen=True)
class Tile:
    id: str              # what the floor and walls call it: "grey"
    product: str         # its id on the material list
    th: str
    en: str
    size: int            # square, mm (from the product)
    per_box: int         # (from the product)
    top: int             # tiled up to this height on a wall
    fill: str            # its colour on the drawings


@dataclass(frozen=True)
class Item:
    no: str              # its number on the drawing: from its order in room.toml
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
    id: str = ""         # what a part names it by


@dataclass(frozen=True)
class Wall:
    id: str
    th: str
    en: str
    view_th: str
    view_en: str
    length: float        # along the wall
    tile: str            # the id of its tile in room.toml
    tiled_run: float     # the length that is actually tiled (the door's wall: not the door opening)
    along_room: bool     # runs along the room's length (so the floor step meets it)
    right: str           # the wall at x = 0, seen from inside facing this wall
    left: str            # the wall at x = length
    drawn: bool          # gets its own elevation
    items: tuple


@dataclass(frozen=True)
class TilesNeeded:
    id: str              # the tile's id
    product: str         # its id on the material list
    th: str
    en: str
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
class Room:
    length: float        # along the main wall
    width: float         # along the new wall and the window wall
    ceiling: float
    column: float        # the existing column's width, at the start of the door's wall
    min_clear: float     # the design rule: every hole at least this far from a tile joint
    tiles: dict          # {id: Tile}
    floor_tile: str      # the id of the floor's tile
    walls: dict
    floor: tuple
    labels: Labels
    plan: dict           # {"top" | "right" | "bottom" | "left": wall id} — the floor plan seen from above
    products_used: frozenset   # every product id the drawings take a size from

    @property
    def new_wall_length(self):
        """The new wall: the rest of the door's wall after the column."""
        return self.width - self.column

    def tiles_needed(self):
        """Tiles needed per tile: the floor and each wall's tiled run, by the tile each one has."""
        out = []
        for t in self.tiles.values():
            parts = []
            if self.floor_tile == t.id:
                parts.append(("floor", math.ceil(self.length / t.size) * math.ceil(self.width / t.size)))
            for w in self.walls.values():
                if w.tile == t.id:
                    parts.append((w.id, t.top // t.size * math.ceil(w.tiled_run / t.size)))
            out.append(TilesNeeded(t.id, t.product, t.th, t.en, t.size, t.per_box, tuple(parts)))
        return out

    def wall_warnings(self, wall_id):
        """Every design rule broken on one wall."""
        w = self.walls[wall_id]
        t = self.tiles[w.tile]
        return (_joint_warnings(w.items, w.length, t.size, t.top, self.min_clear)
                + _clash_warnings(w.items, w.length) + _part_warnings(w.items))

    def warnings(self):
        """[(wall id, warning)] for every wall with items."""
        return [(wid, x) for wid, w in self.walls.items() if w.items for x in self.wall_warnings(wid)]

    def render(self):
        """Every drawing: {file name: svg text}, the floor plan first."""
        out = {"floor-plan.svg": draw_plan(self)}
        for w in self.walls.values():
            if w.drawn:
                out[f"{w.id.replace('_', '-')}.svg"] = draw_wall(self, w)
        return out


# ---------- loading ----------
def load(path, catalogue):
    """Read and check room.toml and build every wall. Every product's size comes from
    `catalogue` = {id: Product}, the products on the material list."""
    room = read_toml(Path(path), "the room, its walls and tiles, and every position")
    _check(room)
    tiles = _tiles(room, catalogue)
    door = _product(catalogue, f"{ROOM_FILE}: [door]", room["door"]["product"], ("w", "h"))
    lintel = _product(catalogue, f"{ROOM_FILE}: [lintel]", room["lintel"]["product"], ("h",))
    new_wall = room["room"]["width"] - room["column"]["width"]
    if new_wall - door.w <= 0:
        raise DataError(f"{ROOM_FILE}: the door ({door.w:g}) does not fit in the new wall ({new_wall:g}: "
                        f"the room's width less the column)")
    drawn = tuple(wid for wid, e in room["walls"].items() if e["drawn"])
    layout = room["positions"]
    labels = Labels(ROOM_FILE, room["labels"], LABELS)
    walls, floor = _walls(room, layout, drawn, door, room["door"]["wall"], lintel.h, room["lintel"]["bearing"],
                          catalogue)
    used = ({e["product"] for k in drawn + ("floor",) for e in layout.get(k, []) if "product" in e}
            | {t.product for t in tiles.values()} | {door.id, lintel.id})
    r = room["room"]
    return Room(r["length"], r["width"], r["ceiling"], room["column"]["width"], room["rules"]["min_clear"],
                tiles, room["floor"]["tile"], walls, floor, labels, room["plan"], frozenset(used))


def _check(room):
    """Every table and entry in room.toml against its declared fields."""
    check(ROOM_FILE, "the file", room, FILE_FIELDS)
    known = {"wall": room["walls"], "tile": room["tiles"], "runs": RUNS}
    for k, fields in TABLES.items():
        check(ROOM_FILE, f"[{k}]", room[k], fields, known)
    for k, e in room["room_items"].items():
        check(ROOM_FILE, f"[room_items.{k}]", e, NAMED)
    for wid, e in room["walls"].items():
        check(ROOM_FILE, f"[walls.{wid}]", e, WALL, known)
    for tid, e in room["tiles"].items():
        check(ROOM_FILE, f"[tiles.{tid}]", e, TILE)
    drawn = [wid for wid, e in room["walls"].items() if e["drawn"]]
    only(ROOM_FILE, "[positions]", room["positions"], set(drawn) | {"floor"})
    for key, entries in room["positions"].items():
        check_each(ROOM_FILE, f"[[positions.{key}]] entry", entries, POSITION,
                   {"shape": FLOOR_SHAPE_NEEDS if key == "floor" else SHAPE_NEEDS})


def _product(catalogue, where, pid, needs):
    """A product from the catalogue that has the sizes `needs`."""
    if pid not in catalogue:
        raise DataError(f"{where} names product '{pid}', which is not on the material list (materials.toml)")
    p = catalogue[pid]
    for k in needs:
        if getattr(p, k) is None:
            raise DataError(f"materials.toml: product '{pid}' needs a {k} in its size — {where} uses it")
    return p


def _tiles(room, catalogue):
    """Every [tiles.ID] table in room.toml, with its size and box from its product."""
    out = {}
    for tid, e in room["tiles"].items():
        p = _product(catalogue, f"{ROOM_FILE}: [tiles.{tid}]", e["product"], ("w", "h", "per_box"))
        if p.w != p.h:
            raise DataError(f"materials.toml: tile '{p.id}' is {p.w:g} × {p.h:g} — the tile count needs square tiles")
        out[tid] = Tile(tid, p.id, e["th"], e["en"], int(p.w), p.per_box, e["top"], e["fill"])
    return out


def _note(e, key, where):
    """A note as written. It stands on its own, so a {phase:…}-style reference is refused."""
    t = e.get(key, "")
    if "{" in t:
        raise DataError(f"{ROOM_FILE}: {where} '{key}' has a reference in braces — a drawing note "
                        f"can't refer to a phase, step or rule; write it out")
    return t


def _walls(room, layout, drawn, door, door_wall, lt, lb, catalogue):
    """Every wall with its items (positioned in room.toml, plus those that follow from the room)."""
    names = room["room_items"]

    def named(k, no, shape, **dims):
        e, where = names[k], f"[room_items.{k}]"
        return Item(str(no), e["th"], e["en"], shape, note_th=_note(e, "note_th", where),
                    note_en=_note(e, "note_en", where), id=k, **{a: float(v) for a, v in dims.items()})

    v = lambda key, name_: room[key][name_]                     # noqa: E731
    room_l, room_w, ceiling = v("room", "length"), v("room", "width"), v("room", "ceiling")
    column, door_w, door_h = v("column", "width"), door.w, door.h
    solid = room_w - column - door_w                                  # the new wall beside the door
    items = {k: _layout_items(layout, k, catalogue, room_w) for k in drawn + ("floor",)}

    # This design's rules: the existing column is at the x = 0 end of the door's wall, with the
    # door opening beside it and the lintel over the opening; the window is in its own wall.
    items.setdefault(door_wall, [])
    n = _next(items[door_wall])
    items[door_wall] += [
        named("column", n, "column", x=column / 2, w=column, y=ceiling / 2, h=ceiling),
        named("door_opening", n + 1, "opening", x=column + door_w / 2, w=door_w, y=door_h / 2, h=door_h),
        named("lintel", n + 2, "rect", x=column + (door_w + lb) / 2, w=door_w + lb, y=door_h + lt / 2, h=lt),
    ]
    win = {k: v("window", k) for k in ("from_corner", "width", "sill", "height")}
    window_wall = room["window"]["wall"]
    items.setdefault(window_wall, [])
    items[window_wall].append(named("window", _next(items[window_wall]), "opening",
                                    x=win["from_corner"] + win["width"] / 2, w=win["width"],
                                    y=win["sill"] + win["height"] / 2, h=win["height"]))
    # floor: the door (x along the door's wall, y from the plan's top wall), and the step's height
    items["floor"].append(named("door", _next(items["floor"]), "door", x=0, w=door_w, y=solid + door_w / 2))
    step_h = float(v("old_wall", "step"))
    items["floor"] = [Item(**{**it.__dict__, "h": step_h}) if it.shape == "step" and it.h is None else it
                      for it in items["floor"]]

    # Each wall seen from inside facing it, x from the corner on your right (room.toml [walls]).
    walls = {}
    for wid, e in room["walls"].items():
        length = room_l if e["runs"] == "length" else room_w
        run = length - door_w if wid == door_wall else length        # the door opening isn't tiled
        walls[wid] = Wall(wid, e["th"], e["en"], e.get("view_th", ""), e.get("view_en", ""), length,
                          e["tile"], run, e["runs"] == "length", e["right"], e["left"], e["drawn"],
                          tuple(items.get(wid, ())))
    return walls, tuple(items["floor"])


def _layout_items(layout, key, catalogue, room_w):
    """The checked items of one [[positions.KEY]] list, each with its product's size filled in;
    its number on the drawing is its place in the list."""
    out = []
    needs = FLOOR_SHAPE_NEEDS if key == "floor" else SHAPE_NEEDS
    for i, e in enumerate(layout.get(key, []), 1):
        where = f"[[positions.{key}]] entry '{e['id']}'"
        dims = {}
        if "product" in e:
            dims.update(_product(catalogue, f"{ROOM_FILE}: {where}", e["product"], ()).size())
        dims.update({k: e[k] for k in ("w", "h", "d") if k in e})
        if e["shape"] in ("zone", "step") and "d" not in dims:
            dims["d"] = room_w                           # zones and the floor step run across the room
        have = {**{k: e[k] for k in ("x", "y") if k in e}, **dims}
        missing = [k for k in needs[e["shape"]] if k not in have]
        if missing:
            raise DataError(f"{ROOM_FILE}: {where} ({e['shape']}) needs '{missing[0]}' "
                            f"(give it here, or through its product)")
        f = lambda k: None if k not in have else float(have[k])     # noqa: E731
        out.append(Item(str(i), e["th"], e["en"], e["shape"], f("x"), f("w"), f("y"), f("h"), f("d"),
                        e.get("part"), _note(e, "note_th", where), _note(e, "note_en", where), id=e["id"]))
    ids = {it.id for it in out}
    for it in out:
        if it.part and it.part not in ids:
            raise DataError(f"{ROOM_FILE}: [[positions.{key}]] entry '{it.id}' belongs to {it.part}, "
                            f"which is not in [[positions.{key}]]")
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
        if jy and it.y is not None and it.y < tile_top:          # no joints when a tile is taller than the tiling
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
    by_id = {it.id: it for it in items}
    out = []
    for it in items:
        if not it.part:
            continue
        parent = by_id[it.part]                 # checked at load: it exists
        if None in (it.x, parent.x, parent.w):
            continue
        if abs(it.x - parent.x) > parent.w / 2:
            out.append(f'{it.no} {it.en}: x {it.x:g} is outside {parent.en} '
                       f'({parent.x - parent.w / 2:g}–{parent.x + parent.w / 2:g})')
        if None not in (it.y, parent.y, parent.h) and it.y > parent.y + parent.h / 2:
            out.append(f'{it.no} {it.en}: y {it.y:g} is above the top of {parent.en}')
    return out
