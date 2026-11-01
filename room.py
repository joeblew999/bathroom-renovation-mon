"""The room: room.toml, read, checked and worked out. It knows nothing about the phases;
the products on the materials list are handed to it (for their names and sizes). It is drawn by
room_drawings.py.

    r = load(Path("room.toml"), products)   # products = {id: Product}, from materials.load()
    r.warnings()        # [(wall id or "floor", (th, en))] — every setting-out or clash problem (room_design_checks.py)
    r.tiles_needed()    # [TilesNeeded] — tiles per tile, worked out from the room

  1. read       room.toml against the fields declared below (common.check)
  2. work out   each wall's place from the order of the walls; each item's name and size from
                its product; the column, door and lintel from how the room is constructed; tile counts

The design checks (a hole too near a tile joint, items that clash or run off the wall, a part outside
the item it belongs to, the door and lintel) are in room_design_checks.py.

How this room is constructed is the one thing written here rather than in room.toml (README rule 1):
the existing column stands at the x = 0 end of its wall, the door opening beside it and the
lintel over the opening.

The tiles needed and any design problems print with `mise run summary`; the drawings are in the PDF.
"""
import math
from dataclasses import dataclass
from pathlib import Path

import room_design_checks
from common import NAME, NAMED, DataError, Labels, assumed, check, check_each, placeholders, read_toml

FILE = "room.toml"

# ======================================== 1. read ========================================
# Every kind of entry in room.toml, declared once (common.check: "!" = required, "@x" = one of
# the x ids).
NUM = "count!"            # a size: more than 0
FILE_FIELDS = {"room": "table!", "column": "table!", "door": "table!", "lintel": "table!", "tile": "list!",
               "floor": "table!", "wall": "list!", "norm": "list!", "labels": "table!", "symbols": "table!"}
ROOM = {"length": NUM, "width": NUM, "ceiling": NUM, "joint_clearance": NUM}
COLUMN = {**NAMED, "width": NUM, "depth": NUM, "into_room": "amount!", "wall": "@wall!"}
DOOR = {"product": "text!", "hinge": "@end!", "swing": "@swing!", "note_th": "text", "note_en": "text"}
LINTEL = {"product": "text!", "bearing": NUM, "note_th": "text", "note_en": "text"}
TILE = {"id": "text!", "product": "text!", **NAME, "tiling_height": "whole!", "fill": "text!"}
FLOOR = {"ref": "text!", "tile": "@tile!", "drain": "text!", "fall_wet": NUM, "fall_dry": NUM, "assumed": "list", "item": "list"}
WALL = {"id": "text!", **NAME, "ref": "text!", "tile": "@tile!", "waterproofing": NUM,
        "elevation": "flag!", "assumed": "list", "item": "list"}
# A norm a design check holds the room to: a value from outside, with where it came from and when it was
# checked (README rule 10). `item`: the item it applies to, by id.
NORM = {"id": "text!", **NAME, "item": "text", "value": NUM, "standard": "text!", "url": "text!", "checked": "date!"}
NORMS = ("wc_clearance", "basin_clearance", "basin_rim_min", "basin_rim_max", "zone_1_reach", "zone_2_reach",
         "zone_height", "zone_ip_water", "shower_wall_waterproofing", "floor_fall")      # the ones the checks use
# An item names a product (and takes its name from it) or has its own name (th, en) — checked in _items.
ITEM = {"id": "text!", "product": "text", "th": "text", "en": "text", "shape": "@shape!",
        "x": "amount", "y": "amount", "w": "count", "h": "count", "d": "count", "high": "@end", "fitting": "text",
        "note_th": "text", "note_en": "text", "waterproofing": "count", "assumed": "list"}
WALL_ITEM = {k: v for k, v in ITEM.items() if k != "high"}       # a high side is a floor step's
FLOOR_ITEM = {k: v for k, v in ITEM.items() if k != "fitting"}   # only wall items serve a fitting
ENDS = ("start", "end")   # the ends of a wall or the floor: x = 0, and x = its length
SWINGS = ("in", "out")    # which way the door leaf opens: into the room, or out of it
CONSTRUCTION = ("column", "door", "lintel")   # the items room.py works out — no item in room.toml takes these ids
SYMBOLS = {k: "text!" for k in ("axis_x", "axis_y", "width", "height", "none", "times", "warning", "ok", "up", "down",
                                 "dash", "dot", "eq", "plus", "more")}
LABELS = {"floor_plan": (), "elevation_title": ("wall",), "viewed_inside": (), "seen_above": (),
          "mm": (), "generated": (), "tile_top": ("top",), "floor_higher": ("h",), "higher": (), "lower": (),
          "floor": (), "items": (), "x_from": ("wall", "axis"), "centre_height": (), "dashed": (),
          "all_clear": ("min_clear",), "tile_count": ("tile", "need", "parts", "boxes", "planned", "spare"),
          # the design problems (room_design_checks.py), each a note for the architect: where, what, the rule, what to do
          "warn_joint": ("wall", "item", "axis", "v", "d", "min"),
          "warn_set_out_off_wall": ("wall", "item", "edge"),
          "edge_start": (), "edge_end": ("length",), "edge_floor": (), "edge_ceiling": ("ceiling",),
          "warn_set_out_off_floor": ("item", "length", "width"),
          "warn_clash": ("wall", "a", "b"), "warn_in_opening": ("wall", "a", "b"),
          "warn_outside": ("wall", "item", "axis", "v", "parent", "low", "high"),
          "warn_above": ("wall", "item", "axis", "v", "parent", "top"),
          "warn_door_fit": ("wall", "door", "column", "length"), "warn_lintel_short": ("wall", "lintel", "door", "bearing"),
          "warn_frame_column": ("wall", "frame", "column"),
          "warn_clearance": ("wall", "item", "clear", "need"), "warn_rim_height": ("wall", "item", "rim", "low", "high"),
          "warn_zone_ip": ("wall", "item", "zone", "ip", "need"), "warn_zone_no_ip": ("wall", "item", "zone"),
          "warn_clearance_door": ("wall", "item", "door"), "warn_waterproofing": ("zone", "height", "need"),
          "warn_fall": ("fall", "need"), "warn_off_drawing": ("what",),
          "warn_overlap": ("what", "other"), "warn_covered": ("what",), "drawing_line": (), "warn_drain_side": ("drain", "step"),
          "waterproofing_line": ("walls", "zone"), "fall_line": ("wet", "dry")}
# The position and size keys each shape may have; an item gives no others.
WALL_KEYS = {"rect": ("x", "y", "w", "h", "d"), "circle": ("x", "y", "w", "d"), "point": ("x", "y"),
             "zone": ("x", "w", "d"), "opening": ("x", "y", "w", "h")}
FLOOR_KEYS = {"rect": ("x", "y", "w", "d"), "step": ("x", "h", "d", "high")}
PLACE_KEYS = ("x", "y", "w", "h", "d", "high")
# What each shape needs to be drawn (after its product's size is filled in).
WALL_SHAPES = {"rect": ("x", "y", "w", "h"), "circle": ("x", "y", "w"), "point": ("x", "y"),
               "zone": ("x", "w"), "opening": ("x", "y", "w", "h")}
FLOOR_SHAPES = {"rect": ("x", "y", "w", "d"), "step": ("x", "h", "high")}   # the floor is seen from above; a
                                                                              # step's high side is one end
PLAN_SIDES = ("top", "right", "bottom", "left")                      # the walls' order round the plan


def _check(raw):
    check(FILE, "the file", raw, FILE_FIELDS, ordered=False)
    tiles = check_each(FILE, "tile", raw["tile"], TILE)
    known = {"tile": [t["id"] for t in tiles]}
    walls = check_each(FILE, "wall", raw["wall"], WALL, known)
    for kind, values in (("tile product", [t["product"] for t in tiles]),
                         ("ref", [w["ref"] for w in walls] + [raw["floor"]["ref"]])):
        twice = next((v for v in values if values.count(v) > 1), None)
        if twice:
            raise DataError(f"{FILE}: {kind} '{twice}' is used twice — each one names one thing")
    if len(walls) != len(PLAN_SIDES):
        raise DataError(f"{FILE}: {len(walls)} walls — the room has {len(PLAN_SIDES)}, in order round the plan")
    known.update(wall=[w["id"] for w in walls], end=ENDS, swing=SWINGS)
    for key, fields in (("room", ROOM), ("column", COLUMN), ("door", DOOR), ("lintel", LINTEL), ("floor", FLOOR),
                        ("symbols", SYMBOLS)):
        check(FILE, f"[{key}]", raw[key], fields, known)
    for w in walls:
        if w.get("item") and not w["elevation"]:
            raise DataError(f"{FILE}: wall '{w['id']}' has items but no elevation")
        check_each(FILE, f"wall '{w['id']}' item", w.get("item", []), WALL_ITEM, {"shape": WALL_SHAPES})
    check_each(FILE, "floor item", raw["floor"].get("item", []), FLOOR_ITEM, {"shape": FLOOR_SHAPES, "end": ENDS})
    norms = check_each(FILE, "norm", raw["norm"], NORM)
    ids = [n["id"] for n in norms]
    for need in NORMS:
        if need not in ids:
            raise DataError(f"{FILE}: no norm '{need}' — a design check needs it")
    for n in norms:
        if n["id"] not in NORMS:
            raise DataError(f"{FILE}: norm '{n['id']}' isn't used by any design check")
    items = {it["id"] for w in walls for it in w.get("item", [])} | {it["id"] for it in raw["floor"].get("item", [])}
    for it in [it for w in walls for it in w.get("item", [])] + raw["floor"].get("item", []):
        if "waterproofing" in it and it["shape"] != "zone":
            raise DataError(f"{FILE}: item '{it['id']}' has waterproofing, but only a zone has its own")
    if raw["floor"]["drain"] not in {it["id"] for it in raw["floor"].get("item", [])}:
        raise DataError(f"{FILE}: [floor] drain '{raw['floor']['drain']}' isn't a floor item")
    for n in norms:
        if "item" in n and n["item"] not in items:
            raise DataError(f"{FILE}: norm '{n['id']}' applies to item '{n['item']}', which isn't in the room")


# ======================================== the model ========================================
@dataclass(frozen=True)
class Tile:
    id: str              # what the floor and walls call it
    product: str         # its id on the materials list
    th: str
    en: str
    size: int            # square, mm (from the product)
    per_box: int         # (from the product)
    tiling_height: int   # tiled up to this height on a wall
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
    ip: str = None       # its product's ingress protection rating, if electrical ("IP44")
    electrical: bool = False  # its product is electrical
    waterproofing: float = None  # a zone: waterproofed up to this height within it
    fitting: str = None  # the id of the fitting it serves (a services point or fixing)
    note_th: str = ""
    note_en: str = ""

    def label(self):
        """'3 ท่อน้ำทิ้งอ่าง', '3 Basin waste': how a design problem names it."""
        return f"{self.no} {self.th}", f"{self.no} {self.en}"


@dataclass(frozen=True)
class Wall:
    id: str
    th: str
    en: str
    ref: str             # its wall reference: its letter on the floor plan
    side: str            # top, right, bottom or left on the floor plan (from its order)
    right: str           # the wall at x = 0, facing this one from inside (the next one round)
    left: str            # the wall at its far end (the one before)
    length: float
    along_room: bool     # runs along the room's length (so the floor step meets it)
    tile: str
    tiled_run: float     # the length actually tiled (the door's wall: not the door opening)
    waterproofing: float  # waterproofed up to this height
    elevation: bool      # it gets an elevation drawing
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
class Norm:
    id: str
    th: str
    en: str
    item: str            # the id of the item it applies to, or None
    value: float
    standard: str        # where the value comes from
    url: str
    checked: object      # the date the source was checked


@dataclass(frozen=True)
class Room:
    length: float
    width: float
    ceiling: float
    joint_clearance: float  # every hole at least this far from a tile joint (a design check)
    tiles: dict          # {id: Tile}
    floor_ref: str
    floor_tile: str
    floor: tuple         # the floor's items
    walls: dict          # {id: Wall}, in order round the plan
    labels: Labels
    symbols: dict        # the marks on the drawings (room.toml [symbols])
    lintel_length: float  # the lintel product's length, or None if the list gives none (a design check)
    bearing: float        # how far the lintel rests on the wall each side of the opening
    column_depth: float   # the existing column's depth through its wall
    frame_depth: float    # the door frame product's depth, or None if the list gives none (a design check)
    column_wall: str      # the wall the existing column, the door and the lintel are on
    door_hinge: str       # which end of the door opening its leaf is hinged at: start (the column side) or end
    door_swing: str       # in: the leaf opens into the room; out: out of it
    floor_drain: str      # the id of the floor item the floor falls to
    floor_fall_wet: float  # the wet (low) side of the step falls 1 in this to the drain
    floor_fall_dry: float  # the dry (high) side falls 1 in this towards the step
    norms: dict           # {id: Norm}: the values the design checks hold the room to, with their sources
    assumed: tuple = ()   # [(where, key, value)]: values not yet known for real (README rule 10)

    def tiles_needed(self):
        """Tiles needed per tile: the floor, and each wall's tiled run up to its tile's top (a cut
        row counts as a row)."""
        out = []
        for t in self.tiles.values():
            parts = [("floor", math.ceil(self.length / t.size) * math.ceil(self.width / t.size))] \
                if self.floor_tile == t.id else []
            parts += [(w.id, math.ceil(t.tiling_height / t.size) * math.ceil(w.tiled_run / t.size))
                      for w in self.walls.values() if w.tile == t.id]
            out.append(TilesNeeded(t, tuple(parts)))
        return out

    def take_off(self):
        """The quantities labour is priced by, measured from the room: {name: (value, unit)}, areas in m²
        (unit "m2"), lengths in m (unit "metre"). Each is worked out here from the room's sizes, never typed."""
        L, W, C = self.length, self.width, self.ceiling
        tiling = existing = above = 0
        for w in self.walls.values():
            top = self.tiles[w.tile].tiling_height
            windows = [it for it in w.items if it.shape == "opening"]
            below = w.tiled_run * top - sum(it.w * _overlap(it.y - it.h / 2, it.y + it.h / 2, 0, top) for it in windows)
            tiling += below
            existing += below if w.id != self.column_wall else 0
            above += w.tiled_run * (C - top) - sum(it.w * _overlap(it.y - it.h / 2, it.y + it.h / 2, top, C) for it in windows)
        wall = self.walls[self.column_wall]
        top = self.tiles[wall.tile].tiling_height
        col, door, lintel = (next(it for it in wall.items if it.shape == s) for s in ("column", "door", "lintel"))
        tiling += 2 * col.d * top                                   # the column's two sides in the room
        above += 2 * col.d * (C - top) + door.w * (C - door.h)      # and the wall over the door
        block = wall.length - col.w                                  # the new wall's length, beside the column
        living = block * C - door.w * door.h                         # its living-room face
        step = next((it for it in self.floor if it.shape == "step"), None)
        m2 = 1e6
        return {"ceiling_m2": (L * W / m2, "m2"),
                "floor_tiling_m2": ((L * W + (step.h * W if step else 0)) / m2, "m2"),     # with the step's face
                "wall_tiling_m2": (tiling / m2, "m2"),
                "existing_wall_tiling_m2": (existing / m2, "m2"),
                "new_wall_block_m2": ((living - lintel.w * lintel.h) / m2, "m2"),
                "lintel_m": (lintel.w / 1000, "metre"),
                "step_nosing_m": ((W if step else 0) / 1000, "metre"),       # the step runs across the room
                "new_wall_plaster_m2": ((living + (wall.tiled_run - col.w) * top) / m2, "m2"),   # both faces, below the tiles
                "build_out_m2": (((wall.tiled_run - col.w) * (C - top) + door.w * (C - door.h)) / m2, "m2"),  # the new
                                                                     # wall above the tile line, built out flush
                "paint_walls_m2": ((above + living) / m2, "m2"),
                "door_m2": (door.w * door.h / m2, "m2")}

    def warnings(self):
        """Every setting-out or clash problem: the design checks in room_design_checks.py."""
        return room_design_checks.warnings(self)


def _overlap(a0, a1, b0, b1):
    """How much of the span a0–a1 lies within b0–b1."""
    return max(0, min(a1, b1) - max(a0, b0))


# ======================================== 2. work out ========================================
def load(path, products):
    """Read and check room.toml, and work out every wall and item. `products` = {id: Product}."""
    raw = read_toml(Path(path), "the room, its walls and tiles, and every item on them")
    _check(raw)
    r = raw["room"]
    tiles = {t["id"]: _tile(t, products) for t in raw["tile"]}
    floor = _items(raw["floor"].get("item", []), "floor item", FLOOR_SHAPES, FLOOR_KEYS, products, r["width"])  # a step runs
                                                                                    # from the first wall
    walls = _walls(raw, products)
    return Room(r["length"], r["width"], r["ceiling"], r["joint_clearance"], tiles, raw["floor"]["ref"],
                raw["floor"]["tile"], tuple(floor), walls, Labels(FILE, raw["labels"], LABELS), raw["symbols"],
                products[raw["lintel"]["product"]].w, raw["lintel"]["bearing"], raw["column"]["depth"],
                products[raw["door"]["product"]].d, raw["column"]["wall"], raw["door"]["hinge"],
                raw["door"]["swing"], raw["floor"]["drain"],
                raw["floor"]["fall_wet"], raw["floor"]["fall_dry"],
                {n["id"]: Norm(n["id"], n["th"], n["en"], n.get("item"), n["value"], n["standard"], n["url"], n["checked"])
                 for n in raw["norm"]},
                tuple(assumed(raw["floor"], f"{FILE} [floor]")
                      + [g for w in raw["wall"] for g in assumed(w, f"{FILE} wall '{w['id']}'")]
                      + [g for w in raw["wall"] for it in w.get("item", []) for g in assumed(it, f"{FILE} item '{it['id']}'")]
                      + [g for it in raw["floor"].get("item", []) for g in assumed(it, f"{FILE} floor item '{it['id']}'")]))


def _product(products, where, pid, needs=()):
    """A product on the materials list that has the sizes `needs`."""
    if pid not in products:
        raise DataError(f"{FILE}: {where} names product '{pid}', which is not on the materials list")
    p = products[pid]
    for k in needs:
        if getattr(p, k) is None:
            raise DataError(f"{FILE}: {where} needs product '{pid}' on the materials list to have a {k}")
    return p


def _tile(e, products):
    p = _product(products, f"tile '{e['id']}'", e["product"], ("w", "h", "per_box"))
    if p.w != p.h or p.w != int(p.w):
        raise DataError(f"{FILE}: tile '{e['id']}' is {p.w:g} × {p.h:g} — the tile count needs square tiles, "
                        f"a whole number of mm")
    return Tile(e["id"], p.id, e["th"], e["en"], int(p.w), p.per_box, int(e["tiling_height"]), e["fill"])


def _note(e, key, where):
    """A note as written: it stands on its own, so it fills in nothing."""
    placeholders(FILE, f"{where} {key}", e.get(key, ""), ())
    return e.get(key, "")


def _notes(e, where):
    """Its note, as keyword values for an Item."""
    return {k: _note(e, k, where) for k in ("note_th", "note_en")}


def _items(entries, kind, shapes, keys, products, across):
    """The items of one wall or the floor, numbered by their order, each with its product's name and
    size. A zone or a step with no depth runs `across` the room, out from its wall."""
    out = []
    for i, e in enumerate(entries, 1):
        where = f"{kind} '{e['id']}'"
        if e["id"] in CONSTRUCTION:
            raise DataError(f"{FILE}: {where} — '{e['id']}' is worked out from how the room is constructed, "
                            f"so no item takes that id ({', '.join(CONSTRUCTION)})")
        if ("product" in e) == ("th" in e):
            raise DataError(f"{FILE}: {where} needs a product or a name (th, en) — one, not both")
        p = _product(products, where, e["product"]) if "product" in e else None
        extra = next((k for k in PLACE_KEYS if k in e and k not in keys[e["shape"]]), None)
        if extra:
            raise DataError(f"{FILE}: {where} is a {e['shape']}, so it has no '{extra}'")
        if p and any(k in e for k in ("w", "h", "d")):
            raise DataError(f"{FILE}: {where} takes its size from product '{p.id}' — give no w, h or d here")
        have = {**(p.size() if p else {}), **{k: e[k] for k in ("x", "y", "w", "h", "d", "high") if k in e}}
        if e["shape"] in ("zone", "step"):
            have.setdefault("d", across)
        missing = [k for k in shapes[e["shape"]] if k not in have]
        if missing:
            raise DataError(f"{FILE}: {where} ({e['shape']}) needs '{missing[0]}' (give it here, or through its product)")
        out.append(Item(str(i), e["id"], p.th if p else e["th"], p.en if p else e["en"], e["shape"],
                        **{k: float(have[k]) for k in ("x", "y", "w", "h", "d") if k in have}, high=e.get("high"), ip=p.ip if p else None,
                        electrical=p.electrical if p else False, waterproofing=e.get("waterproofing"),
                        fitting=e.get("fitting"), **_notes(e, where)))
    ids = {it.id for it in out}
    for it in out:
        if it.fitting and it.fitting not in ids:
            raise DataError(f"{FILE}: {kind} '{it.id}' serves fitting '{it.fitting}', which isn't on the same wall")
    return out


def _walls(raw, products):
    """Every wall, its place from the walls' order, with its items — and the column, the door and the
    lintel on the column's wall, worked out from how the room is constructed."""
    r, col, order = raw["room"], raw["column"], raw["wall"]
    door = _product(products, "[door]", raw["door"]["product"], ("w", "h"))
    lintel = _product(products, "[lintel]", raw["lintel"]["product"], ("h",))
    bearing = raw["lintel"]["bearing"]
    walls = {}
    for i, e in enumerate(order):
        along = i % 2 == 0                                            # the first and third run along the room
        length, across = (r["length"], r["width"]) if along else (r["width"], r["length"])
        items = _items(e.get("item", []), f"wall '{e['id']}' item", WALL_SHAPES, WALL_KEYS, products, across)
        run = length
        if e["id"] == col["wall"]:
            # How this room is constructed: the column at x = 0, the door opening beside it, the lintel over it.
            # Whether they fit is a design check (room_design_checks.py).
            n = len(items)
            items += [
                Item(str(n + 1), "column", col["th"], col["en"], "column", x=col["width"] / 2, y=r["ceiling"] / 2,
                     w=col["width"], h=r["ceiling"], d=col["into_room"], **_notes(col, "[column]")),
                Item(str(n + 2), "door", door.th, door.en, "door", x=col["width"] + door.w / 2, y=door.h / 2,
                     w=door.w, h=door.h, **_notes(raw["door"], "[door]")),
                Item(str(n + 3), "lintel", lintel.th, lintel.en, "lintel", x=col["width"] + (door.w + bearing) / 2,
                     y=door.h + lintel.h / 2, w=door.w + bearing, h=lintel.h, **_notes(raw["lintel"], "[lintel]")),
            ]
            run = length - door.w                                       # the door opening isn't tiled
        walls[e["id"]] = Wall(e["id"], e["th"], e["en"], e["ref"],
                              PLAN_SIDES[i], order[(i + 1) % len(order)]["id"], order[i - 1]["id"], length, along,
                              e["tile"], run, e["waterproofing"], e["elevation"], tuple(items))
    return walls
