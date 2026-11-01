#!/usr/bin/env python3
"""The material list: materials.toml, read, checked, ordered and rendered. It knows nothing
about the phases or the drawings.

    m = load(Path("materials.toml"))
    m.render()          # the material list as Markdown table rows — the PDF prints exactly this
    m.still_to_buy()    # (total, whether any of it is approximate)
    m.on_site()         # how many items are already on site (bought or reused)
    m.tile_colours()    # the tile colours the list names
    m.tile_boxes(c)     # how many boxes of one tile colour are on the list

The groups, the shops and the suppliers are defined in materials.toml; the only fixed list
here is the four statuses, because each one has its own rules (what needs a price, a shop…).

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
SHOP_KEYS = {"id", "name", "sku", "link"}
SUPPLIER_KEYS = {"id", "th", "en"}
ITEM_KEYS = {"group", "status", "name", "note", "n", "price", "unit", "approx", "tile", "shop", "sku", "by"}
STATUSES = ("buy", "bought", "reused", "supplied")      # also the order within a group
APPROX = "ประมาณ / approx."
ABOUT = "ประมาณ / about"


@dataclass(frozen=True)
class Group:
    id: str
    th: str
    en: str


@dataclass(frozen=True)
class Shop:
    id: str
    name: str            # "HomePro"
    sku: str             # what its product codes look like (a regular expression)
    link: str            # the product page, with {sku} or {sku_digits} (the code without dots)

    def url(self, sku):
        return self.link.format(sku=sku, sku_digits=re.sub(r"\D", "", sku))


@dataclass(frozen=True)
class Supplier:
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
    shop: Shop = None    # where it is bought
    sku: str = None      # the shop's product code
    by: Supplier = None  # who brings a supplied item

    @property
    def shop_name(self):
        return self.shop.name if self.shop else ""

    @property
    def link(self):
        """The product page, built from the shop and the SKU."""
        return self.shop.url(self.sku) if self.shop else None

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

    def on_site(self):
        """How many items are already on site."""
        return sum(1 for m in self.items if m.status in ("bought", "reused"))

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
    only(FILE, "the file", raw, {"shop", "supplier", "group", "item"})
    shops = {e["id"]: Shop(**e) for e in _defined(raw, "shop", SHOP_KEYS)}
    for s in shops.values():
        try:
            re.compile(s.sku)
            s.url("0")
        except (re.error, KeyError, IndexError, ValueError) as e:
            raise DataError(f"{FILE}: shop '{s.id}' has a bad sku pattern or link ({e})") from None
    suppliers = {e["id"]: Supplier(**e) for e in _defined(raw, "supplier", SUPPLIER_KEYS)}
    groups = tuple(Group(**e) for e in _defined(raw, "group", GROUP_KEYS))
    ids = {g.id for g in groups}
    return Materials(groups, tuple(_item(it, ids, shops, suppliers) for it in raw.get("item", [])))


def _defined(raw, kind, keys):
    """The [[kind]] entries, each with exactly `keys` and a unique id."""
    seen = set()
    for e in raw.get(kind, []):
        where = f"{kind} '{e.get('id', '?')}'"
        only(FILE, where, e, keys)
        need(FILE, where, e, sorted(keys))
        if e["id"] in seen:
            raise DataError(f"{FILE}: {kind} id '{e['id']}' is used twice")
        seen.add(e["id"])
    return raw.get(kind, [])


def _item(it, group_ids, shops, suppliers):
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
        if it["by"] not in suppliers:
            raise DataError(f"{FILE}: {where} has by = {it['by']!r} (must be one of: {', '.join(suppliers)})")
    elif "by" in it:
        raise DataError(f"{FILE}: {where} is {it['status']}, so it has no 'by' (only supplied items do)")
    if "tile" in it and not isinstance(it["tile"], str):
        raise DataError(f"{FILE}: {where} 'tile' must be text (a tile colour), not {it['tile']!r}")
    if it["status"] in ("reused", "supplied"):
        if "shop" in it or "sku" in it:
            raise DataError(f"{FILE}: {where} is {it['status']}, so it has no shop or sku")
    else:
        need(FILE, where, it, ("shop", "sku"))
        if it["shop"] not in shops:
            raise DataError(f"{FILE}: {where} has shop {it['shop']!r} (must be one of: {', '.join(shops)})")
        shop = shops[it["shop"]]
        if not isinstance(it["sku"], str) or not re.fullmatch(shop.sku, it["sku"]):
            raise DataError(f"{FILE}: {where} has sku {it['sku']!r}, which isn't a {shop.name} code")
    return Material(name=it["name"], note=it.get("note", ""), group=it["group"], status=it["status"],
                    n=it["n"], price=it.get("price"), unit=it.get("unit", ""), approx=it.get("approx", False),
                    tile=it.get("tile"), shop=shops.get(it.get("shop")), sku=it.get("sku"),
                    by=suppliers.get(it.get("by")))


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
        return f"{m.by.th} / {m.by.en}"
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
