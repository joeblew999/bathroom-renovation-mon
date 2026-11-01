"""Draw the floor plan and the wall elevations, as SVG text, from the drawings' data
(model.py): each wall's name, length, tile, items and design-rule warnings, and the floor
items. This file only decides how they look: each wall seen from inside the bathroom,
x from the corner on your right; the floor plan from above. Warnings are shown in red
under each elevation. It reads and writes nothing.
"""
from html import escape

from common import both

S = 0.3                      # px per mm

# The drawing's colours, each named once. (Each tile's colour is in room.toml: it belongs to the tile.)
MARKER = "#c0392b"        # items, their number tags, warnings
OPENING = "#2e86c1"       # openings, zones, pipe lines, floor items
OPENING_FILL = "#d6eaf8"
ZONE_FILL = "#5dade2"
ROUND_FILL = "#eaf2f8"    # round items (the mirror)
STEP = "#e67e22"          # the floor step
STEP_FILL = "#f5cba7"
OK = "#1e8449"            # the all-clear lines
COLUMN = "#7f8c8d"
COLUMN_LINE = "#2c3e50"
WALL_FACE = "#fbfbf8"
GRID = "#9a9a96"          # tile joints
GRID_TEXT = "#777"
NOTE = "#666"
SUBTITLE = "#555"
DARK = "#444"             # walls on the plan, axis lines
OUTLINE = "#222"
WHITE = "#fff"

# The drawing's text sizes, each named once.
TITLE_SIZE = 18
HEADING_SIZE = 13
TEXT_SIZE = 12
SMALL_SIZE = 11
NOTE_SIZE = 10
TAG_SIZE = 9.5


def name(w):
    return both(w.th, w.en)


# ---------- pieces every drawing uses ----------
def start(a, width, height, ml, title, subtitle):
    """Open a drawing: its frame, white background, title and subtitle."""
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
      f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="Helvetica, Arial, sans-serif">')
    a(f'<rect width="100%" height="100%" fill="{WHITE}"/>')
    a(f'<text x="{ml}" y="28" font-size="{TITLE_SIZE}" font-weight="bold">{title}</text>')
    a(f'<text x="{ml}" y="48" font-size="{TEXT_SIZE}" fill="{SUBTITLE}">{subtitle}</text>')


def tag(a, cx, top, width, text):
    """A red rounded tag with white text, centred on cx."""
    a(f'<rect x="{cx - width / 2}" y="{top}" width="{width}" height="16" rx="8" fill="{MARKER}"/>')
    a(f'<text x="{cx}" y="{top + 11.5}" font-size="{TAG_SIZE}" fill="{WHITE}" text-anchor="middle" '
      f'font-weight="bold">{text}</text>')


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


def legend_rows(lab, items, with_dims=True):
    """(item, headline, [note lines]) for each item."""
    def f(v, it):
        if v is None:
            return "—" if it.shape == "zone" else lab.both("see_notes")
        return f"{v:g}"
    rows = []
    for it in items:
        head = both(it.th, it.en)
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
    for label, head, notes in rows:
        yy += 20
        tag(a, x0 + 8, yy - 12, tag_w, label)
        a(f'<text x="{x0 + 8 + tag_w / 2 + 8}" y="{yy}" font-size="{TEXT_SIZE}">{escape(head)}</text>')
        for line in notes:
            yy += 14
            a(f'<text x="{x0 + 8 + tag_w / 2 + 8}" y="{yy}" font-size="{NOTE_SIZE}" fill="{NOTE}">{escape(line)}</text>')
        yy += 4
    return yy


# ---------- drawing ----------
def draw_wall(room, wall):
    """One elevation, with its design-rule warnings shown in red: returns svg text."""
    items = wall.items
    t = room.tiles[wall.tile]
    tile, top = t.size, t.top
    L, CEIL = wall.length, room.ceiling
    right, left = room.walls[wall.right], room.walls[wall.left]
    view_th = f" ({wall.view_th})" if wall.view_th else ""
    view_en = f" ({wall.view_en})" if wall.view_en else ""
    warnings = room.wall_warnings(wall.id)

    ML, MR, MT, MB = 70, 40, 70, 90
    W, H = L * S, CEIL * S
    svg_w = max(ML + W + MR, 900)
    lab = room.labels
    rows = [(it.no, head, notes) for it, head, notes in legend_rows(lab, items)]
    svg_h = MT + H + MB + legend_height(rows) + 90

    def X(mm):                      # x is measured from the right-hand corner
        return ML + (L - mm) * S

    def Y(mm):
        return MT + (CEIL - mm) * S

    def box(x, y, w, h):            # a solid item's rectangle, from its centre and size
        return f'x="{X(x + w / 2)}" y="{Y(y + h / 2)}" width="{w * S}" height="{h * S}"'

    out = []
    a = out.append
    start(a, svg_w, svg_h, ML, lab.both("elevation_title", wall=(wall.th, wall.en), view=(view_th, view_en)),
          f'{lab.both("viewed_inside", sep=" · ")} · {lab.both("mm")} · {lab.both("generated")}')

    # wall, tiled area, grid
    a(f'<rect x="{ML}" y="{MT}" width="{W}" height="{H}" fill="{WALL_FACE}" stroke="{OUTLINE}" stroke-width="2"/>')
    a(f'<rect x="{ML}" y="{Y(top)}" width="{W}" height="{top * S}" fill="{t.fill}"/>')
    for k in range(tile, L, tile):
        a(f'<line x1="{X(k)}" y1="{Y(top)}" x2="{X(k)}" y2="{Y(0)}" stroke="{GRID}"/>')
        a(f'<text x="{X(k)}" y="{Y(top) - 5}" font-size="{NOTE_SIZE}" fill="{GRID_TEXT}" text-anchor="middle">{k}</text>')
    for k in range(tile, top, tile):
        a(f'<line x1="{ML}" y1="{Y(k)}" x2="{ML + W}" y2="{Y(k)}" stroke="{GRID}"/>')
    for k in range(0, CEIL + 1, 500):
        a(f'<text x="{ML - 8}" y="{Y(k) + 4}" font-size="{NOTE_SIZE}" fill="{GRID_TEXT}" text-anchor="end">{k}</text>')
    a(f'<line x1="{ML}" y1="{Y(top)}" x2="{ML + W}" y2="{Y(top)}" stroke="{SUBTITLE}" stroke-width="1.5"/>')
    a(f'<text x="{ML + W - 4}" y="{Y(top) + 14}" font-size="{NOTE_SIZE}" fill="{DARK}" text-anchor="end">'
      f'{lab.both("tile_top", top=top)}</text>')

    # raised floor at the basin end: the floor step meets the walls that run along the room
    if wall.along_room:
        step = next((f for f in room.floor if f.shape == "step"), None)
        if step and step.h:
            a(f'<rect x="{X(step.x)}" y="{Y(step.h)}" width="{step.x * S}" height="{step.h * S}" '
              f'fill="{STEP_FILL}" stroke="{STEP}" stroke-width="1.5"/>')
            a(f'<text x="{X(step.x / 2)}" y="{Y(step.h) - 4}" font-size="{NOTE_SIZE}" fill="{STEP}" '
              f'text-anchor="middle">{lab.both("floor_higher", h=f"{step.h:g}")}</text>')

    # side labels
    cy = MT + H / 2
    a(f'<text x="{ML + W + 14}" y="{cy}" font-size="{TEXT_SIZE}" text-anchor="middle" '
      f'transform="rotate(90 {ML + W + 14} {cy})">{name(right)} (x = 0)</text>')
    a(f'<text x="{ML - 44}" y="{cy}" font-size="{TEXT_SIZE}" text-anchor="middle" '
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
              f'fill="{ZONE_FILL}" fill-opacity="0.15" stroke="{OPENING}" stroke-dasharray="6 4"/>')
            ly = Y(200)
        elif sh == "column":
            a(f'<rect {box(x, y, w, h)} '
              f'fill="{COLUMN}" fill-opacity="0.6" stroke="{COLUMN_LINE}" stroke-width="1.5"/>')
        elif sh == "opening":
            a(f'<rect {box(x, y, w, h)} '
              f'fill="{OPENING_FILL}" stroke="{OPENING}" stroke-width="2"/>')
        elif sh == "rect":
            a(f'<rect {box(x, y, w, h)} '
              f'fill="{WHITE}" fill-opacity="0.85" stroke="{MARKER}" stroke-width="1.5"/>')
        elif sh == "circle":
            a(f'<circle cx="{lx}" cy="{ly}" r="{w / 2 * S}" fill="{ROUND_FILL}" fill-opacity="0.8" '
              f'stroke="{MARKER}" stroke-width="1.5"/>')
        elif sh == "point":
            a(f'<line x1="{lx - 6}" y1="{ly - 6}" x2="{lx + 6}" y2="{ly + 6}" stroke="{MARKER}" stroke-width="2"/>')
            a(f'<line x1="{lx - 6}" y1="{ly + 6}" x2="{lx + 6}" y2="{ly - 6}" stroke="{MARKER}" stroke-width="2"/>')
        elif sh == "vline":
            a(f'<line x1="{lx}" y1="{Y(0)}" x2="{lx}" y2="{Y(1000)}" stroke="{OPENING}" '
              f'stroke-width="1.5" stroke-dasharray="4 3"/>')
            ly = Y(1000) - 2
        tx = lx + (10 if sh in ("point", "vline") else 0)
        if sh == "rect" and x in vline_xs:
            tx = lx - 14
        a(f'<circle cx="{tx}" cy="{ly}" r="8" fill="{MARKER}"/>')
        a(f'<text x="{tx}" y="{ly + 3.5}" font-size="{NOTE_SIZE}" fill="{WHITE}" text-anchor="middle" '
          f'font-weight="bold">{it.no}</text>')

    # x ticks along the floor
    base = Y(0) + 18
    a(f'<line x1="{ML}" y1="{base}" x2="{ML + W}" y2="{base}" stroke="{DARK}"/>')
    for x in sorted(xs):
        a(f'<line x1="{X(x)}" y1="{base - 5}" x2="{X(x)}" y2="{base + 5}" stroke="{DARK}"/>')
        a(f'<text x="{X(x)}" y="{base + 18}" font-size="{NOTE_SIZE}" text-anchor="end" '
          f'transform="rotate(-45 {X(x)} {base + 18})">{x}</text>')

    # legend
    ly0 = MT + H + MB
    a(f'<text x="{ML}" y="{ly0}" font-size="{HEADING_SIZE}" font-weight="bold">{lab.both("items")} '
      f'({lab.both("x_from", wall=(right.th, right.en.lower()))} · '
      f'y = {lab.both("centre_height")})</text>')
    yy = draw_legend(a, rows, ML, ly0) + 16
    if warnings:
        for k, w_ in enumerate(warnings):
            a(f'<text x="{ML}" y="{yy + 18 * k}" font-size="{TEXT_SIZE}" fill="{MARKER}">⚠ {escape(w_)}</text>')
    else:
        a(f'<text x="{ML}" y="{yy}" font-size="{TEXT_SIZE}" fill="{OK}">{lab.th("all_clear", min_clear=room.min_clear)}</text>')
        a(f'<text x="{ML}" y="{yy + 18}" font-size="{TEXT_SIZE}" fill="{OK}">{lab.en("all_clear", min_clear=room.min_clear)}</text>')
    a('</svg>')
    return "\n".join(out)


# ---------- floor plan ----------
def draw_plan(room):
    """The floor plan seen from above: returns svg text."""
    main, win, floor = room.walls["main_wall"].items, room.walls["window_wall"].items, room.floor
    names = {k: name(w) for k, w in room.walls.items()}
    lab = room.labels
    L, Wd, NEW_WALL_L = room.length, room.width, room.new_wall_length
    FLOOR = room.tiles[room.floor_tile]
    col = room.column                           # column width at the end of the new wall
    SP = 0.25
    ML, MR, MT, MB = 90, 90, 90, 80
    PW, PH = L * SP, Wd * SP
    svg_w = max(ML + PW + MR, 900)
    M, F, W = lab.en("tag_main"), lab.en("tag_floor"), lab.en("tag_window")    # the tag letters
    legend = [(M, it) for it in main if it.d] + [(F, it) for it in floor] + [(W, it) for it in win]
    # Wall items list names only (their notes are on the elevations); floor items carry their notes.
    rows = []
    for pre, it in legend:
        (r,) = legend_rows(lab, [it], with_dims=False)
        rows.append((pre + it.no, r[1], r[2] if pre == F else []))
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
    start(a, svg_w, svg_h, ML, lab.both("floor_plan"),
          f'{lab.both("seen_above", sep=" · ")} · {lab.both("mm")} · {lab.both("generated")}')

    # floor + floor tile grid (full tiles set out from the new wall and the main wall)
    a(f'<rect x="{ML}" y="{MT}" width="{PW}" height="{PH}" fill="{FLOOR.fill}"/>')
    for k in range(FLOOR.size, L, FLOOR.size):
        a(f'<line x1="{X(k)}" y1="{Y(0)}" x2="{X(k)}" y2="{Y(Wd)}" stroke="{GRID}"/>')
        a(f'<text x="{X(k)}" y="{Y(Wd) + T + 34}" font-size="{NOTE_SIZE}" fill="{GRID_TEXT}" text-anchor="middle">{k}</text>')
    for k in range(FLOOR.size, Wd, FLOOR.size):
        a(f'<line x1="{ML}" y1="{Y(k)}" x2="{ML + PW}" y2="{Y(k)}" stroke="{GRID}"/>')
        a(f'<text x="{ML + PW + 20}" y="{Y(k) + 4}" font-size="{NOTE_SIZE}" fill="{GRID_TEXT}">{k}</text>')

    # walls
    wall = f'fill="{DARK}"'
    a(f'<rect x="{ML - T}" y="{MT - T}" width="{PW + 2 * T}" height="{T}" {wall}/>')          # main wall
    a(f'<rect x="{ML - T}" y="{MT + PH}" width="{PW + 2 * T}" height="{T}" {wall}/>')         # opposite long wall
    a(f'<rect x="{ML - T}" y="{MT}" width="{T}" height="{PH}" {wall}/>')                       # window wall
    # new wall: solid from the main wall to the door opening, then the column
    door = next((f for f in floor if f.shape == "door"), None)
    d0 = door.y - door.w / 2 if door else NEW_WALL_L
    d1 = door.y + door.w / 2 if door else NEW_WALL_L
    a(f'<rect x="{ML + PW}" y="{Y(0)}" width="{T}" height="{d0 * SP}" {wall}/>')
    a(f'<rect x="{ML + PW}" y="{Y(NEW_WALL_L)}" width="{T * 1.6}" height="{col * SP}" fill="{OUTLINE}"/>')
    # window opening in the window wall (window-wall x = plan y)
    for it in win:
        if it.shape == "opening":
            a(f'<rect x="{ML - T}" y="{Y(it.x - it.w / 2)}" width="{T}" height="{it.w * SP}" '
              f'fill="{OPENING_FILL}" stroke="{OPENING}"/>')

    # door leaf and swing (hinge on the column side)
    if door:
        hx, hy, r = ML + PW, Y(d1), door.w * SP
        a(f'<line x1="{hx}" y1="{hy}" x2="{hx - r}" y2="{hy}" stroke="{OUTLINE}" stroke-width="2"/>')
        a(f'<path d="M {hx - r} {hy} A {r} {r} 0 0 1 {hx} {Y(d0)}" fill="none" stroke="{OUTLINE}" '
          f'stroke-dasharray="4 3"/>')

    tags = []
    # main-wall items: footprint from the wall out to D
    for it in main:
        if not it.d:
            continue
        w = it.w or 0
        if it.shape == "zone":
            a(f'<rect x="{X(it.x + w / 2)}" y="{Y(0)}" width="{w * SP}" height="{it.d * SP}" '
              f'fill="{ZONE_FILL}" fill-opacity="0.15" stroke="{OPENING}" stroke-dasharray="6 4"/>')
            tags.append((M + it.no, X(it.x), Y(it.d - 120)))
            continue
        overhead = it.y is not None and it.y - (it.h or 0) / 2 > 1000   # above head-height fittings
        dash = ' stroke-dasharray="5 3"' if overhead else ""
        fill = "none" if overhead else WHITE
        a(f'<rect x="{X(it.x + w / 2)}" y="{Y(0)}" width="{w * SP}" height="{it.d * SP}" '
          f'fill="{fill}" stroke="{MARKER}" stroke-width="1.5"{dash}/>')
        tags.append((M + it.no, X(it.x), Y(it.d / 2)))
    # floor items
    for it in floor:
        if it.shape == "rect":
            a(f'<rect x="{X(it.x + it.w / 2)}" y="{Y(it.y - it.d / 2)}" width="{it.w * SP}" '
              f'height="{it.d * SP}" fill="{WHITE}" stroke="{OPENING}" stroke-width="1.5"/>')
            a(f'<line x1="{X(it.x + it.w / 2)}" y1="{Y(it.y)}" x2="{X(it.x - it.w / 2)}" '
              f'y2="{Y(it.y)}" stroke="{OPENING}"/>')
            tags.append((F + it.no, X(it.x) - 18, Y(it.y) + 4))
        elif it.shape == "step":
            a(f'<line x1="{X(it.x)}" y1="{Y(0)}" x2="{X(it.x)}" y2="{Y(it.d)}" stroke="{STEP}" '
              f'stroke-width="4" stroke-dasharray="10 5"/>')
            a(f'<text x="{X(it.x) + 6}" y="{Y(it.d) - 6}" font-size="{SMALL_SIZE}" fill="{STEP}" '
              f'font-weight="bold">{lab.both("higher")}</text>')
            a(f'<text x="{X(it.x) - 6}" y="{Y(it.d) - 6}" font-size="{SMALL_SIZE}" fill="{STEP}" '
              f'font-weight="bold" text-anchor="end">{lab.both("lower")}</text>')
            tags.append((F + it.no, X(it.x), Y(it.d / 2)))
        elif it.shape == "door":
            tags.append((F + it.no, ML + PW - door.w * SP / 2, Y(d1) - 12))
    # window-wall items: footprint out from the window wall where a depth is given
    for it in win:
        if it.d and it.w:
            a(f'<rect x="{ML}" y="{Y(it.x - it.w / 2)}" width="{it.d * SP}" height="{it.w * SP}" '
              f'fill="none" stroke="{MARKER}" stroke-width="1.5" stroke-dasharray="5 3"/>')
        tags.append((W + it.no, ML - T - 16, Y(it.x)))

    for t, tx, ty in tags:
        tag(a, tx, ty - 8, 24, t)

    # wall names
    a(f'<text x="{ML + PW / 2}" y="{MT - T - 8}" font-size="{TEXT_SIZE}" text-anchor="middle">{names["main_wall"]}</text>')
    a(f'<text x="{ML + PW / 2}" y="{MT + PH + T + 16}" font-size="{TEXT_SIZE}" text-anchor="middle">{names["opposite_wall"]}</text>')
    a(f'<text x="{ML - T - 40}" y="{MT + PH / 2}" font-size="{TEXT_SIZE}" text-anchor="middle" '
      f'transform="rotate(-90 {ML - T - 40} {MT + PH / 2})">{names["window_wall"]}</text>')
    a(f'<text x="{ML + PW + T + 40}" y="{MT + PH / 2}" font-size="{TEXT_SIZE}" text-anchor="middle" '
      f'transform="rotate(90 {ML + PW + T + 40} {MT + PH / 2})">{names["new_wall"]}</text>')

    # legend
    ly0 = MT + PH + MB
    mw, ww = room.walls["main_wall"], room.walls["window_wall"]
    a(f'<text x="{ML}" y="{ly0}" font-size="{HEADING_SIZE}" font-weight="bold">{lab.both("items")} — {M} = {both(mw.th, mw.en.lower())} · '
      f'{F} = {lab.both("floor")} · {W} = {both(ww.th, ww.en.lower())}</text>')
    a(f'<text x="{ML}" y="{ly0 + 16}" font-size="{SMALL_SIZE}" fill="{SUBTITLE}">{lab.both("dashed")}</text>')
    ly0 += 16
    draw_legend(a, rows, ML, ly0, tag_w=26)
    a('</svg>')
    return "\n".join(out)
