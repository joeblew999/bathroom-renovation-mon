"""The room's design checks — setting out and clashes: problems found in a room that is otherwise well
written (room.py has read and checked room.toml, and worked out every wall and item).

    room_design_checks.warnings(room)          # [(wall id or "floor", (th, en))] — every setting-out or clash problem
    room_design_checks.wall_warnings(room, w)  # one wall's, (th, en) each — shown under its drawing
    room_design_checks.floor_warnings(room)    # the floor's — shown under the floor plan
    room_design_checks.joints_x(wall, size)    # where the vertical tile joints fall (room.py draws them)

The checks, each worded by its label in room.toml:
  - a hole (a fixing, an outlet, an item's centre) set out too near a tile joint   warn_joint
  - an item set out off its wall: past an end, below the floor, above the ceiling  warn_set_out_off_wall (edge_…)
  - two items clashing                                                            warn_clash
  - a fixing or outlet set out in an opening (a window, the door)                warn_in_opening
  - a part set out outside the width of the fitting it belongs to                warn_outside
  - a part set out above the top of the fitting it belongs to                    warn_above
  - a floor item set out off the floor                                           warn_set_out_off_floor
  - the door too wide to fit beside the column                               warn_door_fit
  - the lintel shorter than the door and its bearing                         warn_lintel_short

Each problem is shown in red under its drawing in the PDF, and printed by the build. It knows nothing about the other parts; it reads the room it is handed.
"""


def _warn(room, key, **values):
    """A problem as (th, en), worded by its label."""
    return room.labels.th(key, **values), room.labels.en(key, **values)


def warnings(room):
    return [(w.id, x) for w in room.walls.values() for x in wall_warnings(room, w)] + \
        [("floor", x) for x in floor_warnings(room)]


def wall_warnings(room, wall):
    """Every setting-out or clash problem on one wall, as (th, en)."""
    t = room.tiles[wall.tile]
    return (_construction_warnings(room, wall) + _joint_warnings(room, wall, t.size, t.top)
            + _clash_warnings(room, wall) + _part_warnings(room, wall))


def _name(wall):
    return wall.th, wall.en


def floor_warnings(room):
    """An item off the floor (a step's face is its x)."""
    out = []
    for it in room.floor:
        half_w, half_d = (it.w or 0) / 2, (it.d or 0) / 2 if it.shape == "rect" else 0
        y = it.y if it.y is not None else 0
        if it.x - half_w < 0 or it.x + half_w > room.length or y - half_d < 0 or y + half_d > room.width:
            out.append(_warn(room, "warn_set_out_off_floor", item=it.label(), length=f"{room.length:g}",
                             width=f"{room.width:g}"))
    return out


def _construction_warnings(room, wall):
    """On the column's wall: the door opening fits beside the column, and the lintel spans the
    opening and its bearing (when its product gives a length)."""
    construction = {it.shape: it for it in wall.items if it.shape in ("column", "door")}
    if len(construction) < 2:
        return []
    column, door = construction["column"], construction["door"]
    out = []
    if column.w + door.w >= wall.length:
        out.append(_warn(room, "warn_door_fit", wall=_name(wall), door=f"{door.w:g}", column=f"{column.w:g}",
                         length=f"{wall.length:g}"))
    if room.lintel_length is not None and room.lintel_length < door.w + room.bearing:
        out.append(_warn(room, "warn_lintel_short", wall=_name(wall), lintel=f"{room.lintel_length:g}", door=f"{door.w:g}",
                         bearing=f"{room.bearing:g}"))
    return out


def joints_x(wall, tile):
    """The vertical tile joints on a wall: set out from x = 0, and again from the far side of the door
    opening — none inside it."""
    door = next((it for it in wall.items if it.shape == "door"), None)
    runs = [(0, wall.length)] if not door else [(0, door.x - door.w / 2), (door.x + door.w / 2, wall.length)]
    return [s + k * tile for s, e in runs for k in range(1, int((e - s) // tile) + 1) if s + k * tile < e]


def _joint_warnings(room, wall, tile, top):
    """A hole (a fixing, an outlet, an item's centre) too near a tile joint: closer than min_clear
    but not exactly on it, below the tile top."""
    jx = joints_x(wall, tile)
    jy = sorted(set(range(tile, top, tile)) | {top})   # the tile top edge counts as a joint
    out = []
    for it in wall.items:
        if it.shape not in ("point", "rect", "circle") or it.y >= top:      # no joints above the tiling
            continue
        checks = [("axis_x", it.x, jx)] if jx else []
        if jy:
            checks.append(("axis_y", it.y, jy))
        for axis, v, joints in checks:
            d = min(abs(v - j) for j in joints)
            if 0 < d < room.min_clear:
                out.append(_warn(room, "warn_joint", wall=_name(wall), item=it.label(), axis=room.symbols[axis],
                                 v=f"{v:g}", d=f"{d:g}", min=f"{room.min_clear:g}"))
    return out


def _box(it):
    """(x0, x1, y0, y1) of a solid item (a circle: its diameter both ways), or None."""
    h = it.w if it.shape == "circle" else it.h
    if it.shape not in ("rect", "circle", "opening", "door", "column", "lintel") or None in (it.x, it.w, it.y, h):
        return None
    return it.x - it.w / 2, it.x + it.w / 2, it.y - h / 2, it.y + h / 2


def _span(it):
    """(x0, x1, y0, y1) of an item on its wall: its box; a zone its width, a point itself (a missing
    height counts as the floor)."""
    b = _box(it)
    if b:
        return b
    half = (it.w or 0) / 2
    return it.x - half, it.x + half, it.y or 0, it.y or 0


def _edge(room, wall, it):
    """Which edge an item runs off, as (th, en) — the first it crosses: start, end, floor, ceiling — or None."""
    x0, x1, y0, y1 = _span(it)
    lab = room.labels
    for off, key, values in ((x0 < 0, "edge_start", {}), (x1 > wall.length, "edge_end", {"length": f"{wall.length:g}"}),
                             (y0 < 0, "edge_floor", {}), (y1 > room.ceiling, "edge_ceiling", {"ceiling": f"{room.ceiling:g}"})):
        if off:
            return lab.th(key, **values), lab.en(key, **values)
    return None


def _clash_warnings(room, wall):
    items = wall.items
    solids = [(it, _box(it)) for it in items if _box(it)]
    out = [_warn(room, "warn_set_out_off_wall", wall=_name(wall), item=it.label(), edge=_edge(room, wall, it))
           for it in items if _edge(room, wall, it)]
    # a fixing or outlet in a window or the door opening has no wall to go in
    for p in (it for it in items if it.shape == "point"):
        for o, b in solids:
            if o.shape in ("opening", "door") and b[0] < p.x < b[1] and b[2] < p.y < b[3]:
                out.append(_warn(room, "warn_in_opening", wall=_name(wall), a=p.label(), b=o.label()))
    for i, (a, ba) in enumerate(solids):
        for b, bb in solids[i + 1:]:
            if ba[0] < bb[1] and bb[0] < ba[1] and ba[2] < bb[3] and bb[2] < ba[3]:
                out.append(_warn(room, "warn_clash", wall=_name(wall), a=a.label(), b=b.label()))
    return out


def _part_warnings(room, wall):
    """A part (a fixing, an outlet) must sit within the item it belongs to: inside its width and
    not above its top — catches an item moved without its parts."""
    items = wall.items
    by_id = {it.id: it for it in items}
    out = []
    for it in items:
        parent = by_id.get(it.part)
        if not parent or None in (it.x, parent.x, parent.w):
            continue
        if abs(it.x - parent.x) > parent.w / 2:
            out.append(_warn(room, "warn_outside", wall=_name(wall), item=it.label(), axis=room.symbols["axis_x"], v=f"{it.x:g}",
                             parent=(parent.th, parent.en), low=f"{parent.x - parent.w / 2:g}",
                             high=f"{parent.x + parent.w / 2:g}"))
        if None not in (it.y, parent.y, parent.h) and it.y > parent.y + parent.h / 2:
            out.append(_warn(room, "warn_above", wall=_name(wall), item=it.label(), axis=room.symbols["axis_y"],
                             v=f"{it.y:g}", parent=(parent.th, parent.en), top=f"{parent.y + parent.h / 2:g}"))
    return out
