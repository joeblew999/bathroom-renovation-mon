#!/usr/bin/env python3
"""The document: the phases and the material list, formatted from the model.

    doc = fill(p)        # p = project.load(...)

returns the document with each <!-- generated:NAME --> … <!-- /generated --> block
filled in and every {phase:id} / {step:id} turned into its number. Pure: it reads
nothing, writes nothing, and decides nothing about the data — numbers, totals and
tile counts all come from the Project.

  generated:phases     the work by phase       p.phases
  generated:list       the material list       p.materials, by area

Usage:  python3 tables.py [quote.md]    (prints the tile counts, the still-to-buy total, warnings)
"""
import re
import sys

from project import ProjectError, load

APPROX = "ประมาณ / approx."
ABOUT = "ประมาณ / about"
COLOUR_TH = {"grey": "เทา", "white": "ขาว"}


def baht(v):
    return f"฿{v:,.0f}"


def _cell(v):
    """Text safe inside a Markdown table cell."""
    return v.replace("|", "\\|").replace("\n", " ")


# ---------- the phases ----------
def phases_section(p):
    out = []
    for ph in p.phases:
        out += [f"### ขั้น {ph.number} — {ph.th} / Phase {ph.number} — {ph.en}", ""]
        if ph.note_th or ph.note_en:
            out += [f"> {ph.note_th}", f"> {ph.note_en}", ""]
        if ph.steps:
            out += ["| # | ภาษาไทย | English |", "|---|---------|---------|"]
            out += [f"| {st.number} | {_cell(st.th)} | {_cell(st.en)} |" for st in ph.steps]
            out.append("")
    return out[:-1]


# ---------- the material list ----------
STATUS_ORDER = ("buy", "bought", "reused", "fallback")


def _n(v, unit):
    return f"{v:g} {unit}" if unit else f"{v:g}"


def qty(m):
    """Quantity cell: what to buy (× unit price), or what is on site; a fallback shows its price."""
    if m.status == "fallback":
        return f"{baht(m.price)} / {m.unit}" if m.unit else baht(m.price)
    if m.status == "buy":
        return f"{_n(m.buy, m.unit)} × {baht(m.price)}"
    return _n(m.have, m.unit)


def money_cell(m):
    """Price cell: what is still to pay, or what was paid for what is on site."""
    if m.status == "buy":
        return (f"{APPROX} " if m.approx else "") + baht(m.total)
    return baht(m.paid) if m.paid else "—"


def site_cell(m):
    if m.status == "fallback":
        return "—"
    if m.status != "buy":
        return "✓"
    return f"✓ {m.have:g} · ซื้อ / buy {m.buy:g}" if m.have else "ซื้อ / buy"


def name_cell(m):
    name = f"[{_cell(m.name)}]({m.link})" if m.link else _cell(m.name)
    return f"{name}<br>*{_cell(m.note)}*" if m.note else name


def sum_cell(total, approx, bold=True):
    v = f"{ABOUT} {baht(round(total, -2))}" if approx else baht(total)
    return f"**{v}**" if bold else v


def in_list_order(p, area):
    """The materials of one area as the list shows them: to buy first, then on site (bought),
    then reused, then a fallback; items with the same status keep their order in the file."""
    return sorted((m for m in p.materials if m.area == area.id), key=lambda m: STATUS_ORDER.index(m.status))


def material_list(p):
    """One table: a section per area (in the order materials.toml defines them), and in each
    area the order of in_list_order. The product name links to the shop."""
    rows = ["| สินค้า / Item | จำนวน / Qty | ราคา / Price | ที่หน้างาน / On site |", "|---|---|---|---|"]
    for a in p.areas:
        items = in_list_order(p, a)
        if items:
            rows.append(f"| **{a.th} / {a.en}** | | | |")
        rows += [f"| {name_cell(m)} | {qty(m)} | {money_cell(m)} | {site_cell(m)} |" for m in items]
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
    print(f"Materials: {len(p.materials)} items, {sum(1 for m in p.materials if m.status in ("bought", "reused"))} fully on site, "
          f"{len(warnings)} warnings")


if __name__ == "__main__":
    main(sys.argv)
