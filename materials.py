#!/usr/bin/env python3
"""The material list: materials.toml, read, checked, ordered and rendered. It knows nothing
about the phases or the drawings.

    m = load(Path("materials.toml"))
    m.render()          # the material list as Markdown table rows — the PDF prints exactly this
    m.still_to_buy()    # (total, whether any of it is approximate)
    m.tile_colours()    # the tile colours the list names
    m.tile_boxes(c)     # how many boxes of one tile colour are on the list

Ordered by exactly two things written in the file: the group (in the order the groups are
listed), then the status (buy, bought, reused, supplied); items with the same group and status keep
their order in the file.

Usage:  python3 materials.py [materials.toml]    (prints the material list)
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from common import DataError, flag, md_cell, need, number, only, read_toml

FILE = "materials.toml"
GROUP_KEYS = {"id", "th", "en"}
ITEM_KEYS = {"group", "status", "name", "note", "n", "price", "unit", "approx", "tile", "shop", "sku", "by"}
STATUSES = ("buy", "bought", "reused", "supplied")      # also the order within a group
# Who brings a supplied item: "ไทย / English" as shown in the list.
SUPPLIERS = {"electrician": "ช่างไฟนำมา / electrician provides"}
# Where things are bought: the shop's name, what its SKUs look like, and the product page.
SHOPS = {
    "homepro": ("HomePro", r"\d+", lambda sku: f"https://www.homepro.co.th/p/{sku}"),
    "ikea": ("IKEA", r"\d{3}\.\d{3}\.\d{2}", lambda sku: f"https://www.ikea.com/th/th/p/-{sku.replace('.', '')}/"),
}
APPROX = "ประมาณ / approx."
ABOUT = "ประมาณ / about"


@dataclass(frozen=True)
class Group:
    id: str
    th: str
    en: str


@dataclass(frozen=True)
class Material:
    name: str
    note: str
    group: str           # the id of its group
    status: str          # "buy" (still to buy), "bought" (on site, paid for), "reused" (old fitting),
                         # "supplied" (the trade brings it)
    n: float             # how many
    price: float = None  # unit price in baht
    unit: str = ""
    approx: bool = False
    tile: str = None
    shop: str = None     # an id in SHOPS
    sku: str = None      # the shop's product code
    by: str = None       # who brings a supplied item: an id in SUPPLIERS

    @property
    def shop_name(self):
        return SHOPS[self.shop][0] if self.shop else ""

    @property
    def link(self):
        """The product page, built from the shop and the SKU."""
        return SHOPS[self.shop][2](self.sku) if self.shop else None

    @property
    def total(self):
        """What is still to pay for it."""
        return self.n * self.price if self.status == "buy" else 0

    @property
    def paid(self):
        """What was paid for it, if it is on site and the price is known."""
        return self.n * self.price if self.status == "bought" and self.price is not None else 0


@dataclass(frozen=True)
class Materials:
    groups: tuple
    items: tuple

    def in_order(self, group):
        """The materials of one group as the list shows them: by status, then file order."""
        return sorted((m for m in self.items if m.group == group.id), key=lambda m: STATUSES.index(m.status))

    def still_to_buy(self):
        """(total, whether any of it is approximate)."""
        buy = [m for m in self.items if m.status == "buy"]
        return sum(m.total for m in buy), any(m.approx for m in buy)

    def tile_colours(self):
        """Every tile colour the list names, as written. Whether the room has that tile is
        not this file's business: build_pdf.py checks it against the drawings."""
        return sorted({m.tile for m in self.items if m.tile})

    def tile_boxes(self, colour):
        return sum(m.n for m in self.items if m.tile == colour)

    def render(self):
        """The material list as Markdown table rows: a heading row per group, then its items."""
        rows = ["| สินค้า / Item | จำนวน / Qty | ราคา / Price | ที่หน้างาน / On site |", "|---|---|---|---|"]
        for g in self.groups:
            items = self.in_order(g)
            if items:
                rows.append(f"| **{g.th} / {g.en}** | | | |")
            rows += [f"| {name_cell(m)} | {qty(m)} | {money_cell(m)} | {site_cell(m)} |" for m in items]
        rows.append(f"| **ยังต้องซื้อ / Still to buy** | | {sum_cell(*self.still_to_buy())} | |")
        return rows


# ---------- reading ----------
def load(path):
    """Read and check materials.toml."""
    raw = read_toml(Path(path), "all the materials and prices")
    only(FILE, "the file", raw, {"group", "item"})
    groups = []
    for g in raw.get("group", []):
        where = f"group '{g.get('id', '?')}'"
        only(FILE, where, g, GROUP_KEYS)
        need(FILE, where, g, ("id", "th", "en"))
        if any(x.id == g["id"] for x in groups):
            raise DataError(f"{FILE}: group id '{g['id']}' is used twice")
        groups.append(Group(g["id"], g["th"], g["en"]))
    ids = {g.id for g in groups}
    return Materials(tuple(groups), tuple(_item(it, ids) for it in raw.get("item", [])))


def _item(it, group_ids):
    where = f"'{it.get('name', '?')[:40]}'"
    only(FILE, where, it, ITEM_KEYS)
    need(FILE, where, it, ("name", "group", "status", "n"))
    if it["group"] not in group_ids:
        raise DataError(f"{FILE}: {where} names group '{it['group']}', which is not one of its groups")
    if it["status"] not in STATUSES:
        raise DataError(f"{FILE}: {where} has status {it['status']!r} (must be one of: {', '.join(STATUSES)})")
    for k in ("n", "price"):
        if k in it:
            number(FILE, where, k, it[k])
    if it["n"] <= 0:
        raise DataError(f"{FILE}: {where} 'n' must be more than 0")
    if "price" in it and it["price"] < 0:
        raise DataError(f"{FILE}: {where} 'price' can't be negative")
    if "approx" in it:
        flag(FILE, where, "approx", it["approx"])
    if it["status"] == "buy" and "price" not in it:
        raise DataError(f"{FILE}: {where} is to buy but has no price")
    if it["status"] in ("reused", "supplied") and "price" in it:
        raise DataError(f"{FILE}: {where} is {it['status']}, so it has no price")
    if it["status"] == "supplied":
        need(FILE, where, it, ("by",))
        if it["by"] not in SUPPLIERS:
            raise DataError(f"{FILE}: {where} has by = {it['by']!r} (must be one of: {', '.join(SUPPLIERS)})")
    elif "by" in it:
        raise DataError(f"{FILE}: {where} is {it['status']}, so it has no 'by' (only supplied items do)")
    if "tile" in it and not isinstance(it["tile"], str):
        raise DataError(f"{FILE}: {where} 'tile' must be text (a tile colour), not {it['tile']!r}")
    if it["status"] in ("reused", "supplied"):
        if "shop" in it or "sku" in it:
            raise DataError(f"{FILE}: {where} is {it['status']}, so it has no shop or sku")
    else:
        need(FILE, where, it, ("shop", "sku"))
        if it["shop"] not in SHOPS:
            raise DataError(f"{FILE}: {where} has shop {it['shop']!r} (must be one of: {', '.join(SHOPS)})")
        if not isinstance(it["sku"], str) or not re.fullmatch(SHOPS[it["shop"]][1], it["sku"]):
            raise DataError(f"{FILE}: {where} has sku {it['sku']!r}, which isn't a {SHOPS[it['shop']][0]} code")
    return Material(name=it["name"], note=it.get("note", ""), group=it["group"], status=it["status"],
                    n=it["n"], price=it.get("price"), unit=it.get("unit", ""), approx=it.get("approx", False),
                    tile=it.get("tile"), shop=it.get("shop"), sku=it.get("sku"), by=it.get("by"))


# ---------- the cells of the list ----------
def baht(v):
    return f"฿{v:,.0f}"


def qty(m):
    """How many, and for what is to buy, × the unit price."""
    n = f"{m.n:g} {m.unit}" if m.unit else f"{m.n:g}"
    return f"{n} × {baht(m.price)}" if m.status == "buy" else n


def money_cell(m):
    """What is still to pay, or what was paid for what is on site."""
    if m.status == "buy":
        return (f"{APPROX} " if m.approx else "") + baht(m.total)
    return baht(m.paid) if m.paid else "—"


def site_cell(m):
    if m.status == "supplied":
        return SUPPLIERS[m.by]
    return "ซื้อ / buy" if m.status == "buy" else "✓"


def name_cell(m):
    """The name (linked to the shop's page), then its shop and SKU, then its note."""
    name = f"[{md_cell(m.name)}]({m.link})" if m.link else md_cell(m.name)
    if m.sku:
        name += f"<br>{m.shop_name} {m.sku}"
    return f"{name}<br>*{md_cell(m.note)}*" if m.note else name


def sum_cell(total, approx, bold=True):
    v = f"{ABOUT} {baht(round(total, -2))}" if approx else baht(total)
    return f"**{v}**" if bold else v


def main(argv):
    try:
        m = load(argv[1] if len(argv) > 1 else FILE)
    except DataError as e:
        sys.exit(f"ERROR: {e}")
    print("\n".join(m.render()))


if __name__ == "__main__":
    main(sys.argv)
