#!/usr/bin/env python3
"""Draw the floor plan and the wall elevations, as SVG text.

Everything drawn comes from the Project (project.py): each wall's name, length, tile,
items and design-rule warnings, and the floor items. This module only decides how they
look: each wall seen from inside the bathroom, x from the corner on your right; the
floor plan from above. Warnings are shown in red under each elevation.

    drawings = draw_all(p)      # p = project.load(...)   ->  {file name: svg text}

Pure: it reads and writes nothing; build_pdf.py (or main() here) writes the files.

Usage:  python3 draw_walls.py [quote.md]
Writes: floor-plan.svg, main-wall.svg, new-wall.svg, window-wall.svg
"""
import sys
from html import escape

from project import ProjectError, load

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
def draw_wall(p, wall):
    """One elevation, with its design-rule warnings shown in red: returns svg text."""
    items = wall.items
    tile, top, _ = p.tile(wall.tile)
    L, CEIL = wall.length, p.ceiling
    right, left = p.walls[wall.right], p.walls[wall.left]
    view_th = f" ({wall.view_th})" if wall.view_th else ""
    view_en = f" ({wall.view_en})" if wall.view_en else ""
    warnings = p.wall_warnings(wall.id)

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
        step = next((f for f in p.floor if f.shape == "step"), None)
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
        a(f'<text x="{ML}" y="{yy}" font-size="12" fill="#1e8449">✓ ทุกจุดห่างแนวยาแนวอย่างน้อย {p.min_clear} มม. '
          f'หรืออยู่กึ่งกลางแนวพอดี และไม่มีชิ้นใดทับกัน</text>')
        a(f'<text x="{ML}" y="{yy + 18}" font-size="12" fill="#1e8449">✓ Every centre is at least {p.min_clear} mm '
          f'off a joint (or exactly centred on one), and nothing overlaps</text>')
    a('</svg>')
    return "\n".join(out)


# ---------- floor plan ----------
def draw_plan(p):
    """The floor plan seen from above: returns svg text."""
    main, win, floor = p.walls["main_wall"].items, p.walls["window_wall"].items, p.floor
    names = {k: name(w) for k, w in p.walls.items()}
    L, Wd, NEW_WALL_L = p.room_l, p.room_w, p.new_wall_l
    GREY = p.tile("grey")[0]
    col = p.column                              # column width at the end of the new wall
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
    mw, ww = p.walls["main_wall"], p.walls["window_wall"]
    a(f'<text x="{ML}" y="{ly0}" font-size="13" font-weight="bold">รายการ / Items — M = {mw.th} / {mw.en.lower()} · '
      f'F = พื้น / floor · W = {ww.th} / {ww.en.lower()}</text>')
    a(f'<text x="{ML}" y="{ly0 + 16}" font-size="11" fill="#555">เส้นประ = ติดผนังด้านบน (มองจากบน) / '
      f'dashed = mounted higher on the wall, seen from above</text>')
    ly0 += 16
    draw_legend(a, rows, ML, ly0, tag_w=26)
    a('</svg>')
    return "\n".join(out)


# ---------- all drawings ----------
def draw_all(p):
    """Every drawing: returns {file name: svg text}."""
    drawings = {"floor-plan.svg": draw_plan(p)}
    for wid, out in ELEVATIONS.items():
        drawings[out] = draw_wall(p, p.walls[wid])
    return drawings


def main(argv):
    try:
        p = load(argv[1] if len(argv) > 1 else "bathroom-renovation-quote.md")
        drawings = draw_all(p)
    except ProjectError as e:
        sys.exit(f"ERROR: {e}")
    warnings = p.warnings()
    for name, svg in drawings.items():
        (p.md_path.parent / name).write_text(svg, encoding="utf-8")
    for wall, w in warnings:
        print(f"WARNING ({wall}): {w}")
    print(f"Wrote {', '.join(drawings)} · {len(warnings)} warnings")


if __name__ == "__main__":
    main(sys.argv)
