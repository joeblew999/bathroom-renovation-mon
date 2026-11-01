"""The drawings' data: site.toml and layout.toml, read and checked, every wall built with
its items, and the design rules. svg.py draws what this holds.

    d = load(Path("."))     # the folder holding site.toml and layout.toml
    d.render()              # {file name: svg text} — the floor plan, then the three walls
    d.warnings()            # [(wall id, warning)] — every design rule broken
    d.tiles                 # {name: Tile} — every tile in site.toml
    d.tiles_needed()        # [TilesNeeded] — tiles per tile, worked out from the room

The site (room, door, lintel, window, tiles, walls) and the layout (every position) are the
inputs, with the product catalogue (products.toml) for every product's size. Items that follow from the site — the column, the door
opening, the lintel, the window, the door on the floor plan — are worked out here, never
typed twice. A drawing note stands on its own: it can't refer to a phase, step or rule.

Two kinds of problem:
  - bad data (it doesn't fit together)  -> DataError at load; nothing is built
  - a design rule broken (a hole too near a joint, a clash, a fixing outside its item)
                                         -> a warning, shown red under the drawing
"""
import math
from dataclasses import dataclass
from pathlib import Path

from common import DataError, Labels, need, number, only, read_toml

from .svg import draw_plan, draw_wall

SITE, LAYOUT = "site.toml", "layout.toml"
SITE_KEYS = {
    "room": {"length", "width", "ceiling"},
    "new_wall": {"length"},
    "lintel": {"height", "bearing"},
    "old_wall": {"step"},
    "window": {"from_main_wall", "width", "sill", "height"},
    "rules": {"min_clear"},
}
WALL_IDS = ("main_wall", "new_wall", "window_wall", "opposite_wall")
WALL_KEYS = {"th", "en", "view_th", "view_en", "tile"}
TILE_KEYS = {"product", "th", "top", "fill"}
LABELS = {"floor_plan": (), "elevation_title": ("wall", "view"), "viewed_inside": (), "seen_above": (),
          "mm": (), "generated": (), "tile_top": ("top",), "floor_higher": ("h",), "higher": (), "lower": (),
          "floor": (), "items": (), "x_from": ("wall",), "centre_height": (), "see_notes": (), "dashed": (),
          "all_clear": ("min_clear",), "tag_main": (), "tag_floor": (), "tag_window": (),
          "tile_count": ("tile", "need", "parts", "boxes", "planned", "spare")}
ELEVATIONS = {"main_wall": "main-wall.svg", "new_wall": "new-wall.svg", "window_wall": "window-wall.svg"}
DRAWN = ("main_wall", "new_wall", "window_wall")            # walls with items in layout.toml
SITE_ITEMS = ("column", "door_opening", "lintel", "window", "door")
NAME_KEYS = {"th", "en", "note_th", "note_en"}
LAYOUT_KEYS = {"no", "th", "en", "product", "shape", "x", "y", "w", "h", "d", "part", "note_th", "note_en"}
# What each shape needs to be drawn (after the product's size is filled in).
SHAPE_NEEDS = {"rect": ("x", "y", "w", "h"), "circle": ("x", "y", "w"), "point": ("x", "y"),
               "vline": ("x",), "zone": ("x", "w"), "step": ("x",)}
FLOOR_SHAPE_NEEDS = {"rect": ("x", "y", "w", "d"), "step": ("x",)}   # floor items are seen from above


# ---------- the model ----------
@dataclass(frozen=True)
class Tile:
    name: str            # what the floor and walls call it: "grey"
    product: str         # its id in products.toml
    th: str
    size: int            # square, mm (from the product)
    per_box: int         # (from the product)
    top: int             # tiled up to this height on a wall
    fill: str            # its colour on the drawings


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
    tile: str            # the name of its tile in site.toml
    tiled_run: float     # the length that is actually tiled (the new wall: not the door opening)
    along_room: bool     # runs along the room's length (so the floor step meets it)
    right: str           # the wall at x = 0, seen from inside facing this wall
    left: str            # the wall at x = length
    items: tuple


@dataclass(frozen=True)
class TilesNeeded:
    colour: str          # the tile's name
    product: str         # its id in products.toml
    th: str
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
    tiles: dict          # {name: Tile}
    floor_tile: str      # the name of the floor's tile
    walls: dict
    floor: tuple
    labels: Labels
    products_used: frozenset   # every product id the drawings take a size from

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

    def tiles_needed(self):
        """Tiles needed per tile: the floor and each wall's tiled run, by the tile each one has."""
        out = []
        for t in self.tiles.values():
            parts = []
            if self.floor_tile == t.name:
                parts.append(("floor", math.ceil(self.room_l / t.size) * math.ceil(self.room_w / t.size)))
            for w in self.walls.values():
                if w.tile == t.name:
                    parts.append((w.id, t.top // t.size * math.ceil(w.tiled_run / t.size)))
            out.append(TilesNeeded(t.name, t.product, t.th, t.size, t.per_box, tuple(parts)))
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
        for wid, name_ in ELEVATIONS.items():
            out[name_] = draw_wall(self, self.walls[wid])
        return out


# ---------- loading ----------
def load(folder, catalogue):
    """Read and check site.toml and layout.toml in `folder`, and build every wall. Every
    product's size comes from the catalogue (products.load)."""
    folder = Path(folder)
    site = read_toml(folder / SITE, "the room, walls and tiles")
    layout = read_toml(folder / LAYOUT, "all the positions")
    tiles = _tiles(site, catalogue)
    door = _door(site, catalogue)
    _check_site(site, tiles, door)
    labels = Labels(SITE, site.get("labels", {}), LABELS)
    only(LAYOUT, "the file", layout, set(DRAWN) | {"floor", "site_items"})
    walls, floor = _walls(site, layout, door, catalogue)
    used = ({e["product"] for k in DRAWN + ("floor",) for e in layout.get(k, []) if "product" in e}
            | {t.product for t in tiles.values()} | {door.id})
    return Drawings(site, tiles, site["floor"]["tile"], walls, floor, labels, frozenset(used))


def _value(site, key, name):
    try:
        return site[key][name]
    except KeyError:
        raise DataError(f"{SITE}: [{key}] needs '{name}'") from None


def _product(catalogue, where, pid, needs):
    """A product from the catalogue that has the sizes `needs`."""
    if pid not in catalogue:
        raise DataError(f"{where} names product '{pid}', which is not in products.toml")
    p = catalogue[pid]
    for k in needs:
        if getattr(p, k) is None:
            raise DataError(f"products.toml: product '{pid}' needs a {k} — {where} uses it")
    return p


def _door(site, catalogue):
    e = site.get("door", {})
    only(SITE, "[door]", e, {"product"})
    need(SITE, "[door]", e, ("product",))
    return _product(catalogue, f"{SITE}: [door]", e["product"], ("w", "h"))


def _tiles(site, catalogue):
    """Every [tiles.NAME] table in site.toml, with its size and box from its product."""
    raw = site.get("tiles", {})
    if not raw:
        raise DataError(f"{SITE}: no [tiles.…] — the floor and walls need at least one tile")
    out = {}
    for name_, e in raw.items():
        where = f"[tiles.{name_}]"
        only(SITE, where, e, TILE_KEYS)
        need(SITE, where, e, ("product", "th", "top", "fill"))
        number(SITE, where, "top", e["top"])
        p = _product(catalogue, f"{SITE}: {where}", e["product"], ("w", "h", "per_box"))
        if p.w != p.h:
            raise DataError(f"products.toml: tile '{p.id}' is {p.w:g} × {p.h:g} — the tile count needs square tiles")
        out[name_] = Tile(name_, p.id, e["th"], int(p.w), p.per_box, e["top"], e["fill"])
    return out


def _tile_name(where, v, tiles):
    if v not in tiles:
        raise DataError(f"{SITE}: {where} has tile = {v!r} (must be one of: {', '.join(tiles)})")


def _note(e, key, where):
    """A note as written. It stands on its own, so a {phase:…}-style reference is refused."""
    t = e.get(key, "")
    if "{" in t:
        raise DataError(f"{LAYOUT}: {where} '{key}' has a reference in braces — a drawing note "
                        f"can't refer to a phase, step or rule; write it out")
    return t


def _check_site(site, tiles, door):
    only(SITE, "the file", site, set(SITE_KEYS) | {"walls", "tiles", "floor", "door", "labels"})
    only(SITE, "[floor]", site.get("floor", {}), {"tile"})
    need(SITE, "[floor]", site.get("floor", {}), ("tile",))
    _tile_name("[floor]", site["floor"]["tile"], tiles)
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
        _tile_name(f"[walls.{w}]", e["tile"], tiles)
    if _value(site, "new_wall", "length") - door.w <= 0:
        raise DataError(f"{SITE}: the door ({door.w:g}) does not fit "
                        f"in the new wall ({_value(site, 'new_wall', 'length')})")


def _walls(site, layout, door, catalogue):
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
    new_wall_l, door_w, door_h = v("new_wall", "length"), door.w, door.h
    column, solid = room_w - new_wall_l, new_wall_l - door_w
    items = {k: _layout_items(layout, k, catalogue, room_w) for k in DRAWN + ("floor",)}

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


def _layout_items(layout, key, catalogue, room_w):
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
            dims.update(_product(catalogue, f"{LAYOUT}: {where}", e["product"], ()).size())
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
