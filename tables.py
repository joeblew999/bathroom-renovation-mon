#!/usr/bin/env python3
"""The document: the phases and the material list, formatted from the model.

    doc = fill(p)        # p = project.load(...)

returns the document with each <!-- generated:NAME --> … <!-- /generated --> block
filled in and every {phase:id} / {step:id} turned into its number. Pure: it reads
nothing, writes nothing, and decides nothing about the data — numbers, totals and
tile counts all come from the Project.

  generated:phases     the work by phase       p.phases
  generated:list       the material list       p.materials, grouped by phase

Usage:  python3 tables.py [quote.md]    (prints the tile counts, the still-to-buy total, warnings)
"""
import re
import sys

from project import ProjectError, load

APPROX = "ประมาณ / approx."
ABOUT = "ประมาณ / about"
COLOUR_TH = {"grey": "เทา", "white": "ขาว"}


# ---------- money ----------
def baht(v):
    return f"฿{v:,.0f}"


def qty(m):
    if m.n is not None and m.price is not None:
        unit = f" {m.unit}" if m.unit else ""
        return f"{m.n}{unit} × {baht(m.price)}"
    return m.qty


def money_cell(m):
    if m.fallback or not m.priced:
        return "—"
    return (f"{APPROX} " if m.approx else "") + baht(m.total)


def sum_cell(total, approx, bold=True):
    v = f"{ABOUT} {baht(round(total, -2))}" if approx else baht(total)
    return f"**{v}**" if bold else v


# ---------- the phases ----------
def _cell(v):
    return v.replace("|", "\\|").replace("\n", " ")


def phase_heading(ph):
    return f"ขั้น {ph.number} — {ph.th} / Phase {ph.number} — {ph.en}"


def phases_section(p):
    out = []
    for ph in p.phases:
        out += [f"### {phase_heading(ph)}", ""]
        if ph.note_th or ph.note_en:
            out += [f"> {ph.note_th}", f"> {ph.note_en}", ""]
        if ph.steps:
            out += ["| # | ภาษาไทย | English |", "|---|---------|---------|"]
            out += [f"| {st.number} | {_cell(st.th)} | {_cell(st.en)} |" for st in ph.steps]
            out.append("")
    return out[:-1]


# ---------- the material list ----------
def material_list(p):
    """One table, grouped by phase in working order; the product name links to the shop."""
    rows = ["| สินค้า / Item | จำนวน / Qty | ราคา / Price | ที่หน้างาน / On site |", "|---|---|---|---|"]
    for ph in p.phases:
        items = [m for m in p.materials if m.phase == ph.id]
        if items:
            rows.append(f"| **{phase_heading(ph)}** | | | |")
        for m in items:
            name = f"[{m.name}]({m.link})" if m.link else m.name
            site = "✓" if m.on_site else "ซื้อ / buy"
            rows.append(f"| {name} | {qty(m)} | {money_cell(m)} | {site} |")
    rows.append(f"| **ยังต้องซื้อ / Still to buy** | | {sum_cell(*p.still_to_buy())} | |")
    return rows


# ---------- tile counts (command line only) ----------
def tile_lines(p):
    names = {"floor": ("พื้น", "floor"), **{k: (w.th, w.en.lower()) for k, w in p.walls.items()}}
    out = []
    for t in p.tile_counts():
        d_th = " + ".join(f"{names[s][0]} {n}" for s, n in t.parts)
        d_en = " + ".join(f"{names[s][1]} {n}" for s, n in t.parts)
        out.append(f"กระเบื้อง{COLOUR_TH[t.colour]} {t.need} แผ่น ({d_th}) → ต้องใช้ {t.boxes} กล่อง "
                   f"วางแผนไว้ {t.planned:g} กล่อง (เหลือ {t.spare:g} แผ่น) / {t.colour} {t.need} tiles ({d_en}) "
                   f"→ {t.boxes} boxes needed, {t.planned:g} planned ({t.spare:g} spare tiles)")
    return out


# ---------- the document ----------
def fill(p):
    """The document with every generated block filled in and every reference resolved."""
    content = {"phases": phases_section(p), "list": material_list(p)}
    doc = p.text
    for name, lines in content.items():
        pat = re.compile(rf"(<!-- generated:{name} -->\n).*?(\n<!-- /generated -->)", re.S)
        if not pat.search(doc):
            raise ProjectError(f"{p.md_path.name}: marker <!-- generated:{name} --> … <!-- /generated --> not found")
        doc = pat.sub(lambda m: m.group(1) + "\n".join(lines) + m.group(2), doc)
    return p.resolve(doc)


def main(argv):
    try:
        p = load(argv[1] if len(argv) > 1 else "bathroom-renovation-quote.md")
        fill(p)
    except ProjectError as e:
        sys.exit(f"ERROR: {e}")
    warnings = p.tile_warnings()
    print("\n".join(tile_lines(p)))
    print("Still to buy:", sum_cell(*p.still_to_buy(), bold=False))
    for w in warnings:
        print("WARNING (materials):", w)
    print(f"Materials: {len(p.materials)} items, {sum(1 for m in p.materials if m.on_site)} on site, "
          f"{len(warnings)} warnings")


if __name__ == "__main__":
    main(sys.argv)
