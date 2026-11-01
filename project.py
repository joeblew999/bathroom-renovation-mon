#!/usr/bin/env python3
"""The project: every source read once, checked once, and built into one model.

    p = load("bathroom-renovation-quote.md")

reads the five sources (they sit next to each other):

  - bathroom-renovation-quote.md : the document skeleton (title, headings, short prose,
                                   <!-- generated:… --> markers)
  - site.toml                    : the room, the walls, tiles and product sizes
  - layout.toml                  : every position (walls and floor), and the names of
                                   the items that follow from the site
  - phases.toml                  : the work, phase by phase
  - materials.toml               : every material and price

and returns a Project:

  p.phases      [Phase]     each with its number and its [Step]s, each step with "1.8"
  p.materials   [Material]  one list, in file order: quantities to buy and on site, and what
                            still has to be paid — materials and phases don't refer to each other
  p.walls       {id: Wall}  main_wall, new_wall, window_wall, opposite_wall: name, length,
                            tile, tiled run, and every item on it (layout + worked out)
  p.floor       [Item]      the floor-plan items (drain, step, door)
  p.resolve(t)  text with every {phase:id} / {step:id} / {rule:name} filled in
  p.tile_counts()  tiles needed per colour against the boxes on the material list
  p.warnings()  every design-rule warning: holes near joints, clashes, items off the
                end of a wall, fixings outside their item, too few tile boxes

This is the only module that reads files or knows a rule about the data: numbering,
prices, which wall gets which tile, where each wall's x is measured from, and the design
rules. Everything downstream (tables.py, draw_walls.py, build_pdf.py) formats what the
model holds.

Two kinds of problem:
  - bad data (it doesn't fit together)  -> ProjectError at load; nothing is built
  - a design rule broken (a hole too near a joint, a clash, too few boxes)
                                         -> a warning; built, and shown red on the drawing

Bad data raises ProjectError naming the file and the problem. Nothing is half-built:
load() either returns a complete, checked Project or raises.
"""
import math
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ProjectError(Exception):
    """Bad or missing data in the sources. The message says where and what."""


# ---------- what each file may contain ----------
# Any other key is a typo (`lnk` for `link`, `widht` for `w`) that would otherwise be
# silently ignored, so it stops the build.
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
PHASE_KEYS = {"id", "th", "en", "note_th", "note_en", "step"}
STEP_KEYS = {"id", "th", "en"}
MATERIAL_KEYS = {"name", "note", "buy", "have", "reused", "price", "unit", "approx",
                 "tile", "fallback", "link"}
TILE_COLOURS = ("grey", "white")

# What each shape needs to be drawn (after the product's size is filled in).
SHAPE_NEEDS = {"rect": ("x", "y", "w", "h"), "circle": ("x", "y", "w"), "point": ("x", "y"),
               "vline": ("x",), "zone": ("x", "w"), "step": ("x",)}
FLOOR_SHAPE_NEEDS = {"rect": ("x", "y", "w", "d"), "step": ("x",)}   # floor items are seen from above


# ---------- the model ----------
@dataclass(frozen=True)
class Step:
    id: str
    number: str          # "1.8"
    th: str
    en: str


@dataclass(frozen=True)
class Phase:
    id: str
    number: int
    th: str
    en: str
    note_th: str
    note_en: str
    steps: tuple


@dataclass(frozen=True)
class Material:
    name: str
    note: str
    buy: float = 0       # how many still to buy
    have: float = 0      # how many already on site
    reused: bool = False # what is on site is an old fitting, reused
    price: float = None  # unit price in baht
    unit: str = ""
    approx: bool = False
    tile: str = None
    fallback: bool = False
    link: str = None

    @property
    def to_buy(self):
        """Still to buy and counted in the total (a fallback is listed but never counted)."""
        return self.buy > 0 and not self.fallback

    @property
    def total(self):
        """What is still to pay for it."""
        return self.buy * self.price if self.to_buy else 0

    @property
    def paid(self):
        """What was paid for what is on site (nothing for a reused fitting)."""
        return self.have * self.price if self.have and self.price is not None and not self.reused else 0

    @property
    def tile_boxes(self):
        return self.have + self.buy


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
class TileCount:
    colour: str
    size: int
    per_box: int
    parts: tuple         # ((surface, tiles), …) — surface is "floor" or a wall id
    planned: float       # boxes on the material list

    @property
    def need(self):
        return sum(n for _, n in self.parts)

    @property
    def boxes(self):
        return math.ceil(self.need / self.per_box)

    @property
    def spare(self):
        return self.planned * self.per_box - self.need


@dataclass(frozen=True)
class Project:
    md_path: Path
    text: str
    site: dict
    phases: tuple
    materials: tuple
    walls: dict
    floor: tuple
    numbers: dict = field(repr=False)

    # the room
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

    def resolve(self, t):
        return _resolve(self.numbers, t)

    def still_to_buy(self):
        """(total, whether any of it is approximate)."""
        items = [m for m in self.materials if m.to_buy]
        return sum(m.total for m in items), any(m.approx for m in items)

    def tile_counts(self):
        """Tiles needed per colour, from the room and tile sizes, against the boxes planned."""
        out = []
        for colour in TILE_COLOURS:
            size, top, per_box = self.tile(colour)
            rows = top // size
            parts = []
            if colour == "grey":                     # the floor is grey
                parts.append(("floor", math.ceil(self.room_l / size) * math.ceil(self.room_w / size)))
            for w in self.walls.values():
                if w.tile == colour:
                    parts.append((w.id, rows * math.ceil(w.tiled_run / size)))
            planned = sum(m.tile_boxes for m in self.materials if m.tile == colour)
            out.append(TileCount(colour, size, per_box, tuple(parts), planned))
        return out

    def tile_warnings(self):
        return [f"{t.colour} tile: {t.planned:g} boxes planned but {t.boxes} needed"
                for t in self.tile_counts() if t.planned < t.boxes]

    # ---------- design rules on a wall ----------
    def wall_warnings(self, wall_id):
        """Every design rule broken on one wall."""
        w = self.walls[wall_id]
        size, top, _ = self.tile(w.tile)
        return (_joint_warnings(w.items, w.length, size, top, self.min_clear)
                + _clash_warnings(w.items, w.length) + _part_warnings(w.items))

    def warnings(self):
        """[(where, warning)] for every wall with items, then the tile boxes."""
        out = [(wid, x) for wid, w in self.walls.items() if w.items for x in self.wall_warnings(wid)]
        return out + [("materials", x) for x in self.tile_warnings()]


# ---------- loading ----------
def load(md_path):
    """Read every source next to `md_path`, check it, and build the model."""
    md = Path(md_path)
    if not md.exists():
        raise ProjectError(f"{md} not found")
    site = _toml(md.with_name("site.toml"), "the room, walls, tiles and product sizes")
    layout = _toml(md.with_name("layout.toml"), "all the positions")
    phases_raw = _toml(md.with_name("phases.toml"), "the work, phase by phase")
    materials_raw = _toml(md.with_name("materials.toml"), "all the materials and prices")

    _check_site(site)
    _only("layout.toml", "the file", layout, set(DRAWN) | {"floor", "site_items"})
    _only("phases.toml", "the file", phases_raw, {"phase"})
    _only("materials.toml", "the file", materials_raw, {"item"})

    # Each part is built from its own file; only the references ({phase:…}, {step:…}, {rule:…})
    # in the text cross between them, and they are numbered first:
    phases, numbers = _phases(phases_raw.get("phase", []),           # 1. numbers, for references
                              {("rule", k): f"{v:g}" for k, v in site.get("rules", {}).items()})
    materials = _materials(materials_raw.get("item", []))            # 2. materials.toml on its own
    walls, floor = _walls(site, layout, numbers)                     # 3. notes need references
    return Project(md, md.read_text(encoding="utf-8"), site, phases, materials, walls, floor, numbers)


def _toml(path, what):
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProjectError(f"{path} not found — it holds {what}") from None
    except tomllib.TOMLDecodeError as e:
        raise ProjectError(f"{path} is not valid TOML: {e}") from None


# ---------- small checks ----------
def _only(file, where, entry, allowed):
    unknown = sorted(set(entry) - set(allowed))
    if unknown:
        raise ProjectError(f"{file}: {where} has unknown key '{unknown[0]}' "
                           f"(allowed: {', '.join(sorted(allowed))})")


def _need(file, where, entry, keys):
    for k in keys:
        if k not in entry:
            raise ProjectError(f"{file}: {where} has no '{k}'")


def _number(file, where, key, v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ProjectError(f"{file}: {where} '{key}' must be a number, not {v!r}")


def _flag(file, where, key, v):
    if not isinstance(v, bool):
        raise ProjectError(f"{file}: {where} '{key}' must be true or false, not {v!r}")


def _value(site, key, name):
    try:
        return site[key][name]
    except KeyError:
        raise ProjectError(f"site.toml: [{key}] needs '{name}'") from None


def _tile(site, colour):
    k = f"{colour}_tile"
    return _value(site, k, "size"), _value(site, k, "top"), _value(site, k, "per_box")


# ---------- site.toml ----------
def _check_site(site):
    _only("site.toml", "the file", site, set(SITE_KEYS) | {"walls", "products"})
    for k, allowed in SITE_KEYS.items():
        _only("site.toml", f"[{k}]", site.get(k, {}), allowed)
        for n, v in site.get(k, {}).items():
            _number("site.toml", f"[{k}]", n, v)
    walls = site.get("walls", {})
    _only("site.toml", "[walls]", walls, WALL_IDS)
    for w in WALL_IDS:
        e = walls.get(w)
        if e is None:
            raise ProjectError(f"site.toml: [walls.{w}] is missing")
        _only("site.toml", f"[walls.{w}]", e, WALL_KEYS)
        _need("site.toml", f"[walls.{w}]", e, ("th", "en", "tile"))
        if e["tile"] not in TILE_COLOURS:
            raise ProjectError(f"site.toml: [walls.{w}] has tile = {e['tile']!r} "
                               f"(must be one of: {', '.join(TILE_COLOURS)})")
    for name, e in site.get("products", {}).items():
        _only("site.toml", f"[products.{name}]", e, PRODUCT_KEYS)
        for n, v in e.items():
            _number("site.toml", f"[products.{name}]", n, v)
    if _value(site, "new_wall", "length") - _value(site, "door", "width") <= 0:
        raise ProjectError(f"site.toml: the door ({_value(site, 'door', 'width')}) does not fit "
                           f"in the new wall ({_value(site, 'new_wall', 'length')})")


# ---------- phases.toml ----------
def _phases(raw, rules):
    """The phases with their numbers, and {(kind, id): number} for references (rules included)."""
    phases, numbers = [], dict(rules)

    def add(kind, key, num):
        if (kind, key) in numbers:
            raise ProjectError(f"phases.toml: {kind} id '{key}' is used twice")
        numbers[(kind, key)] = num

    for p_no, ph in enumerate(raw, 1):
        _only("phases.toml", f"phase '{ph.get('id', p_no)}'", ph, PHASE_KEYS)
        _need("phases.toml", f"phase {p_no}", ph, ("id", "th", "en"))
        add("phase", ph["id"], str(p_no))
        steps = []
        for s_no, st in enumerate(ph.get("step", []), 1):
            _only("phases.toml", f"step '{st.get('id', '?')}'", st, STEP_KEYS)
            _need("phases.toml", f"step {p_no}.{s_no} in '{ph['id']}'", st, ("id", "th", "en"))
            add("step", st["id"], f"{p_no}.{s_no}")
            steps.append((st["id"], f"{p_no}.{s_no}", st["th"], st["en"]))
        phases.append((ph, p_no, steps))
    # resolve every reference only once all numbers are known (a step may refer forward)
    built = tuple(
        Phase(ph["id"], p_no, ph["th"], ph["en"],
              _resolve(numbers, ph.get("note_th", "")), _resolve(numbers, ph.get("note_en", "")),
              tuple(Step(i, n, _resolve(numbers, th), _resolve(numbers, en)) for i, n, th, en in steps))
        for ph, p_no, steps in phases)
    return built, numbers


def _resolve(numbers, t):
    """Replace {phase:id} and {step:id} with their numbers, {rule:name} with its value."""
    def sub(m):
        key = (m.group(1), m.group(2))
        if key not in numbers:
            where = "site.toml [rules]" if m.group(1) == "rule" else f"any {m.group(1)} id in phases.toml"
            raise ProjectError(f"Reference {{{m.group(1)}:{m.group(2)}}} doesn't match {where}")
        return numbers[key]
    return re.sub(r"\{(phase|step|rule):([a-z0-9_]+)\}", sub, t)


# ---------- materials.toml ----------
def _materials(raw):
    """The materials, from materials.toml alone, in file order."""
    out = []
    for it in raw:
        where = f"'{it.get('name', '?')[:40]}'"
        _only("materials.toml", where, it, MATERIAL_KEYS)
        _need("materials.toml", where, it, ("name",))
        for k in ("buy", "have", "price"):
            if k in it:
                _number("materials.toml", where, k, it[k])
                if it[k] < 0:
                    raise ProjectError(f"materials.toml: {where} '{k}' can't be negative")
        for k in ("reused", "approx", "fallback"):
            if k in it:
                _flag("materials.toml", where, k, it[k])
        if "tile" in it and it["tile"] not in TILE_COLOURS:
            raise ProjectError(f"materials.toml: {where} has tile = {it['tile']!r} "
                               f"(must be one of: {', '.join(TILE_COLOURS)})")
        if "link" in it and not str(it["link"]).startswith("https://"):
            raise ProjectError(f"materials.toml: {where} link must start with https://")
        m = Material(name=it["name"], note=it.get("note", ""),
                     buy=it.get("buy", 0), have=it.get("have", 0), reused=it.get("reused", False),
                     price=it.get("price"), unit=it.get("unit", ""), approx=it.get("approx", False),
                     tile=it.get("tile"), fallback=it.get("fallback", False), link=it.get("link"))
        if m.fallback:
            if m.price is None or m.buy:
                raise ProjectError(f"materials.toml: {where} is a fallback: give its price, and no 'buy'")
        elif m.buy == 0 and m.have == 0:
            raise ProjectError(f"materials.toml: {where} has nothing to buy and nothing on site (give buy or have)")
        if m.buy and m.price is None:
            raise ProjectError(f"materials.toml: {where} is still to buy but has no price")
        if m.reused and (m.buy or not m.have):
            raise ProjectError(f"materials.toml: {where} is reused: give 'have' and no 'buy'")
        out.append(m)
    return tuple(out)


# ---------- the walls and the floor ----------
def _walls(site, layout, numbers):
    """Every wall with its items (from layout.toml, plus those that follow from the site)."""
    names = layout.get("site_items", {})
    _only("layout.toml", "[site_items]", names, SITE_ITEMS)
    for k in SITE_ITEMS:
        if k not in names:
            raise ProjectError(f"layout.toml: [site_items.{k}] is missing")
        _only("layout.toml", f"[site_items.{k}]", names[k], NAME_KEYS)
        _need("layout.toml", f"[site_items.{k}]", names[k], ("th", "en"))

    def named(k, no, shape, **dims):
        e = names[k]
        return Item(str(no), e["th"], e["en"], shape, note_th=_resolve(numbers, e.get("note_th", "")),
                    note_en=_resolve(numbers, e.get("note_en", "")), **{a: float(v) for a, v in dims.items()})

    v = lambda key, name: _value(site, key, name)               # noqa: E731
    room_l, room_w, ceiling = v("room", "length"), v("room", "width"), v("room", "ceiling")
    new_wall_l, door_w, door_h = v("new_wall", "length"), v("door", "width"), v("door", "height")
    column, solid = room_w - new_wall_l, new_wall_l - door_w
    products = site.get("products", {})
    items = {k: _layout_items(layout, k, products, room_w, numbers) for k in DRAWN + ("floor",)}

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


def _layout_items(layout, key, products, room_w, numbers):
    out, file = [], "layout.toml"
    needs = FLOOR_SHAPE_NEEDS if key == "floor" else SHAPE_NEEDS
    for e in layout.get(key, []):
        where = f"[[{key}]] entry {e.get('no', '?')}"
        _only(file, where, e, LAYOUT_KEYS)
        _need(file, where, e, ("no", "th", "en", "shape"))
        for k in ("no", "x", "y", "w", "h", "d", "part"):
            if k in e:
                _number(file, where, k, e[k])
        if e["shape"] not in needs:
            raise ProjectError(f"{file}: {where} has shape {e['shape']!r} "
                               f"(on this {'floor' if key == 'floor' else 'wall'}: {', '.join(needs)})")
        dims = {}
        if "product" in e:
            if e["product"] not in products:
                raise ProjectError(f"{file}: product '{e['product']}' is not in site.toml")
            dims.update(products[e["product"]])
        dims.update({k: e[k] for k in ("w", "h", "d") if k in e})
        if e["shape"] in ("zone", "step") and "d" not in dims:
            dims["d"] = room_w                           # zones and the floor step run across the room
        have = {**{k: e[k] for k in ("x", "y") if k in e}, **dims}
        missing = [k for k in needs[e["shape"]] if k not in have]
        if missing:
            raise ProjectError(f"{file}: {where} ({e['shape']}) needs '{missing[0]}' "
                               f"(give it here, or through its product)")
        f = lambda k: None if k not in have else float(have[k])     # noqa: E731
        out.append(Item(str(e["no"]), e["th"], e["en"], e["shape"], f("x"), f("w"), f("y"), f("h"), f("d"),
                        None if "part" not in e else str(e["part"]),
                        _resolve(numbers, e.get("note_th", "")), _resolve(numbers, e.get("note_en", ""))))
    nos = [it.no for it in out]
    for no in nos:
        if nos.count(no) > 1:
            raise ProjectError(f"{file}: [[{key}]] number {no} is used twice")
    for it in out:
        if it.part and it.part not in nos:
            raise ProjectError(f"{file}: [[{key}]] entry {it.no} belongs to item {it.part}, "
                               f"which is not in [[{key}]]")
    return out


# ---------- design rules (warnings, not errors) ----------
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


# ---------- clash check ----------
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


# ---------- part-of check ----------
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



def _next(items):
    return max([int(i.no) for i in items] + [0]) + 1
