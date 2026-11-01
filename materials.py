#!/usr/bin/env python3
"""The material list: materials.toml, read, checked, ordered and rendered. It knows nothing
about the phases or the drawings.

    m = load(Path("materials.toml"), catalogue)      # catalogue = products.load(...)
    m.render()          # the material list as Markdown table rows — the PDF prints exactly this
    m.still_to_buy()    # (total, whether any of it is approximate)
    m.on_site()         # how many lines are already on site (bought or reused)
    m.boxes_of(id)      # how many of one product are on the list (bought + to buy)

What a product is (its names, its size) is in products.toml; this file says how it is bought
(unit, price, shop, code) and, under it, a use for every line it takes on the list.
The shops, suppliers, units and groups are defined in the file too; the only fixed list here
is the four statuses, because each one has its own rules (what needs a price, a shop…).

Ordered by exactly two things written in the file: the group (in the order the groups are
listed), then the status (buy, bought, reused, supplied); lines with the same group and status
keep the order of their products in the file.

Usage:  python3 materials.py [materials.toml]    (prints the material list; reads products.toml beside it)
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import products as catalogue_file
from common import DataError, Labels, both, cli, flag, md_cell, need, number, one_of, only, read_toml

FILE = "materials.toml"
GROUP_KEYS = {"id", "th", "en"}
SHOP_KEYS = {"id", "name", "sku", "link"}
SUPPLIER_KEYS = {"id", "th", "en"}
UNIT_KEYS = {"id", "th", "en_one", "en_many"}
ENTRY_KEYS = {"id", "unit", "price", "approx", "shop", "sku", "use"}
USE_KEYS = {"group", "status", "n", "note_th", "note_en", "by"}
@dataclass(frozen=True)
class Rule:
    price: str           # "needed", "allowed" (what it cost) or "none"
    shop: bool           # True: needs a shop and SKU (its boxes count); False: has none
    on_site: bool        # already in the bathroom
    by: bool             # needs `by`: who brings it


# Each status's rules, stated once — and the order within a group.
STATUS = {
    "buy": Rule(price="needed", shop=True, on_site=False, by=False),
    "bought": Rule(price="allowed", shop=True, on_site=True, by=False),
    "reused": Rule(price="none", shop=False, on_site=True, by=False),
    "supplied": Rule(price="none", shop=False, on_site=False, by=True),
}
STATUSES = tuple(STATUS)
LABELS = {k: () for k in ("item", "qty", "price", "on_site", "still_to_buy", "buy", "approx", "about")}


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
class Unit:
    id: str
    th: str              # Thai has one form: 1 ถุง, 7 ถุง
    en_one: str          # 1 bag
    en_many: str         # 7 bags

    def of(self, n):
        return both(self.th, self.en_one if n == 1 else self.en_many)


@dataclass(frozen=True)
class Entry:
    """How one product is bought. What it is comes from the catalogue."""
    product: catalogue_file.Product
    unit: Unit = None
    price: float = None  # unit price in baht
    approx: bool = False
    shop: Shop = None    # where it is bought
    sku: str = None      # the shop's product code

    @property
    def link(self):
        """The product page, built from the shop and the SKU."""
        return self.shop.url(self.sku) if self.shop else None


@dataclass(frozen=True)
class Material:
    """One line on the list: a product (as bought), where it goes, and how many."""
    entry: Entry
    group: str           # the id of its group
    status: str          # "buy" (still to buy), "bought" (on site, paid for), "reused" (old fitting),
                         # "supplied" (the trade brings it)
    n: float             # how many
    note_th: str = ""
    note_en: str = ""
    by: Supplier = None  # who brings a supplied product

    @property
    def total(self):
        """What is still to pay for it."""
        return self.n * self.entry.price if self.status == "buy" else 0

    @property
    def paid(self):
        """What was paid for it, if it is on site and the price is known."""
        return self.n * self.entry.price if self.status == "bought" and self.entry.price is not None else 0


@dataclass(frozen=True)
class Materials:
    groups: tuple
    items: tuple         # every line on the list, in file order
    labels: Labels

    def in_order(self, group):
        """The lines of one group as the list shows them: by status, then file order."""
        return sorted((m for m in self.items if m.group == group.id), key=lambda m: STATUSES.index(m.status))

    def on_site(self):
        """How many lines are already on site."""
        return sum(1 for m in self.items if STATUS[m.status].on_site)

    def still_to_buy(self):
        """(total, whether any of it is approximate)."""
        buy = [m for m in self.items if m.status == "buy"]
        return sum(m.total for m in buy), any(m.entry.approx for m in buy)

    def products_used(self):
        return {m.entry.product.id for m in self.items}

    def boxes_of(self, product_id):
        """How many of one product the list has, bought or still to buy."""
        return sum(m.n for m in self.items if m.entry.product.id == product_id and STATUS[m.status].shop)

    def render(self):
        """The material list as Markdown table rows: a heading row per group, then its lines."""
        L = self.labels
        rows = [f"| {L.both('item')} | {L.both('qty')} | {L.both('price')} | {L.both('on_site')} |", "|---|---|---|---|"]
        for g in self.groups:
            items = self.in_order(g)
            if items:
                rows.append(f"| **{both(g.th, g.en)}** | | | |")
            rows += [f"| {name_cell(m)} | {qty(m)} | {money_cell(m, L)} | {site_cell(m, L)} |" for m in items]
        rows.append(f"| **{L.both('still_to_buy')}** | | {self.total_cell()} | |")
        return rows

    def total_cell(self, bold=True):
        """The still-to-buy total: rounded, and marked "about", if any of it is approximate."""
        total, approx = self.still_to_buy()
        v = f"{self.labels.both('about')} {baht(round(total, -2))}" if approx else baht(total)
        return f"**{v}**" if bold else v


# ---------- reading ----------
def load(path, catalogue):
    """Read and check materials.toml; each entry names a product in the catalogue."""
    raw = read_toml(Path(path), "all the materials and prices")
    only(FILE, "the file", raw, {"labels", "shop", "supplier", "unit", "group", "product"})
    labels = Labels(FILE, raw.get("labels", {}), LABELS)
    shops = {e["id"]: Shop(**e) for e in _defined(raw, "shop", SHOP_KEYS)}
    for s in shops.values():
        try:
            re.compile(s.sku)
            s.url("0")
        except (re.error, KeyError, IndexError, ValueError) as e:
            raise DataError(f"{FILE}: shop '{s.id}' has a bad sku pattern or link ({e})") from None
    suppliers = {e["id"]: Supplier(**e) for e in _defined(raw, "supplier", SUPPLIER_KEYS)}
    units = {e["id"]: Unit(**e) for e in _defined(raw, "unit", UNIT_KEYS)}
    groups = tuple(Group(**e) for e in _defined(raw, "group", GROUP_KEYS))
    ids = {g.id for g in groups}
    items, seen = [], set()
    for e in raw.get("product", []):
        entry = _entry(e, catalogue, shops, units)
        if entry.product.id in seen:
            raise DataError(f"{FILE}: product '{entry.product.id}' is listed twice — give it two uses instead")
        seen.add(entry.product.id)
        uses = e.get("use", [])
        if not uses:
            raise DataError(f"{FILE}: product '{entry.product.id}' has no [[product.use]] — it isn't on the list")
        items += [_use(u, entry, ids, suppliers) for u in uses]
    return Materials(groups, tuple(items), labels)


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


def _entry(e, catalogue, shops, units):
    where = f"product '{e.get('id', '?')}'"
    only(FILE, where, e, ENTRY_KEYS)
    need(FILE, where, e, ("id",))
    if e["id"] not in catalogue:
        raise DataError(f"{FILE}: {where} is not in {catalogue_file.FILE}")
    if "price" in e:
        number(FILE, where, "price", e["price"])
        if e["price"] < 0:
            raise DataError(f"{FILE}: {where} 'price' can't be negative")
    if "approx" in e:
        flag(FILE, where, "approx", e["approx"])
    shop = None
    if "shop" in e or "sku" in e:
        need(FILE, where, e, ("shop", "sku"))
        shop = one_of(FILE, where, "shop", e["shop"], shops)
        if not isinstance(e["sku"], str) or not re.fullmatch(shop.sku, e["sku"]):
            raise DataError(f"{FILE}: {where} has sku {e['sku']!r}, which isn't a {shop.name} code")
    unit = one_of(FILE, where, "unit", e["unit"], units) if "unit" in e else None
    return Entry(catalogue[e["id"]], unit, e.get("price"), e.get("approx", False), shop, e.get("sku"))


def _use(u, p, group_ids, suppliers):
    """One line on the list, checked against its product by the rules of its status (STATUS)."""
    where = f"product '{p.product.id}'"
    only(FILE, where, u, USE_KEYS)
    need(FILE, where, u, ("group", "status", "n"))
    if u["group"] not in group_ids:
        raise DataError(f"{FILE}: {where} names group '{u['group']}', which is not one of its groups")
    s = one_of(FILE, where, "status", u["status"], STATUSES)
    rule = STATUS[s]
    number(FILE, where, "n", u["n"])
    if u["n"] <= 0:
        raise DataError(f"{FILE}: {where} 'n' must be more than 0")
    if rule.price == "needed" and p.price is None:
        raise DataError(f"{FILE}: {where} is {s}, so it needs a price")
    if rule.price == "none" and p.price is not None:
        raise DataError(f"{FILE}: {where} is {s}, so it has no price")
    if rule.shop and not p.shop:
        raise DataError(f"{FILE}: {where} is {s}, so it needs a shop and sku")
    if not rule.shop and p.shop:
        raise DataError(f"{FILE}: {where} is {s}, so it has no shop or sku")
    by = None
    if rule.by:
        need(FILE, where, u, ("by",))
        by = one_of(FILE, where, "by", u["by"], suppliers)
    elif "by" in u:
        raise DataError(f"{FILE}: {where} is {s}, so it has no 'by'")
    return Material(p, u["group"], s, u["n"], u.get("note_th", ""), u.get("note_en", ""), by)


# ---------- the cells of the list ----------
def baht(v):
    return f"฿{v:,.0f}"


def qty(m):
    """How many (with the unit, singular or plural), and for what is to buy, × the unit price."""
    p = m.entry
    n = f"{m.n:g} {p.unit.of(m.n)}" if p.unit else f"{m.n:g}"
    return f"{n} × {baht(p.price)}" if m.status == "buy" else n


def money_cell(m, L):
    """What is still to pay, or what was paid for what is on site."""
    if m.status == "buy":
        return (f"{L.both('approx')} " if m.entry.approx else "") + baht(m.total)
    return baht(m.paid) if m.paid else "—"


def site_cell(m, L):
    if m.status == "supplied":
        return both(m.by.th, m.by.en)
    return L.both("buy") if m.status == "buy" else "✓"


def name_cell(m):
    """The name (linked to the shop's page), then its shop and SKU, then the note for this line."""
    p = m.entry
    name = md_cell(both(p.product.name_th, p.product.name_en))
    if p.link:
        name = f"[{name}]({p.link})<br>{p.shop.name} {p.sku}"
    if m.note_th or m.note_en:
        name += f"<br>*{md_cell(both(m.note_th, m.note_en))}*"
    return name


def main(argv):
    path = Path(argv[1] if len(argv) > 1 else FILE)
    m = load(path, catalogue_file.load(path.with_name(catalogue_file.FILE)))
    print("\n".join(m.render()))


if __name__ == "__main__":
    cli(lambda: main(sys.argv))
