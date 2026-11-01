#!/usr/bin/env python3
"""The material list: materials.toml, read, checked, ordered and rendered. It knows nothing
about the phases or the drawings.

    m = load(Path("materials.toml"))
    m.render()          # the material list as Markdown table rows — the PDF prints exactly this
    m.products          # {id: Product} — every product's names and size (the drawings use the sizes)
    m.still_to_buy()    # (total, whether any of it is approximate)
    m.on_site()         # how many lines are already on site (bought or reused)
    m.boxes_of(id)      # how many of one product are on the list (bought + to buy)

Each [[entry]] is one product: what it is (names, size), how it is bought (unit, price, shop,
code) and, under it, an [[entry.line]] for every line it takes on the list.
The shops, units and groups are defined in the file too; the only fixed list here
is the four statuses, because each one has its own rules (what needs a price, a shop…).

Ordered by exactly two things written in the file: the group (in the order the groups are
listed), then the status (buy, bought, reused, supplied); lines with the same group and status
keep the order of their products in the file.

Usage:  python3 materials.py [materials.toml]    (prints the material list)
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import string

from common import (NAMED, DataError, Labels, both, check, check_each, cli, heading, md_cell, named,
                    note, note_cell, read_toml)

FILE = "materials.toml"
# Every kind of entry in materials.toml, declared once (common.check: "!" = required, "@x" = one
# of the x ids). Every named thing has th and en.
FILE_FIELDS = {"prices_date": "date", "section": "table!", "labels": "table!", "shop": "list!",
               "unit": "list!", "group": "list!", "entry": "list!"}
SHOP = {"id": "text!", "th": "text!", "en": "text!", "sku": "text!", "link": "text!"}
UNIT = {"id": "text!", "th": "text!", "en": "text!", "en_many": "text!"}
GROUP = {"id": "text!", **NAMED}
TEXT_KEYS = ("th", "detail_th", "en", "detail_en")      # a product's name and detail, sizes filled in
ENTRY = {"id": "text!", **{k: "text!" for k in TEXT_KEYS}, "size": "table", "per_box": "number",
         "unit": "@unit", "price": "number", "approx": "flag", "shop": "@shop", "sku": "text", "line": "list!"}
LINE = {"group": "@group!", "status": "@status!", "n": "number!", "note_th": "text", "note_en": "text",
        "by_th": "text", "by_en": "text"}
SIZE_KEYS = ("w", "h", "d")
SIZE = {k: "number" for k in SIZE_KEYS}
SIZE_UNITS = {"": 1, "_cm": 10, "_m": 1000}          # {w} in mm, {w_cm} in cm, {w_m} in m
@dataclass(frozen=True)
class Rule:
    price: str           # "needed", "allowed" (what it cost) or "none"
    shop: bool           # True: needs a shop and SKU (its boxes count); False: has none
    on_site: bool        # already in the bathroom
    by: bool             # needs by_th / by_en: who brings it


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
    note_th: str = ""
    note_en: str = ""


@dataclass(frozen=True)
class Shop:
    id: str
    th: str              # "โฮมโปร"
    en: str              # "HomePro"
    sku: str             # what its product codes look like (a regular expression)
    link: str            # the product page, with {sku} or {sku_digits} (the code without dots)

    def url(self, sku):
        return self.link.format(sku=sku, sku_digits=re.sub(r"\D", "", sku))


@dataclass(frozen=True)
class Product:
    """What a product is: what it's called and its detail (model, size, pack, colour — any size
    filled in), in Thai and English, and its size in mm."""
    id: str
    th: str
    detail_th: str
    en: str
    detail_en: str
    w: float = None
    h: float = None
    d: float = None
    per_box: int = None  # tiles in a box (tiles only)

    def size(self):
        """{w, h, d} that are given."""
        return {k: getattr(self, k) for k in SIZE_KEYS if getattr(self, k) is not None}


@dataclass(frozen=True)
class Unit:
    id: str
    th: str              # Thai has one form: 1 ถุง, 7 ถุง
    en: str              # 1 bag
    en_many: str         # 7 bags

    def of(self, n):
        return both(self.th, self.en if n == 1 else self.en_many)


@dataclass(frozen=True)
class Entry:
    """One product on the list: what it is, and how it is bought."""
    product: Product
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
class Line:
    """One line on the list: an entry (a product, as bought), where it goes, and how many."""
    entry: Entry
    group: str           # the id of its group
    status: str          # "buy" (still to buy), "bought" (on site, paid for), "reused" (old fitting),
                         # "supplied" (the trade brings it)
    n: float             # how many
    note_th: str = ""
    note_en: str = ""
    by_th: str = ""      # who brings a supplied product
    by_en: str = ""

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
    section: tuple       # (th, en, note_th, note_en): this part's heading and note, date filled in
    groups: tuple
    lines: tuple         # every line on the list, in file order
    labels: Labels

    def in_order(self, group):
        """The lines of one group as the list shows them: by status, then file order."""
        return sorted((m for m in self.lines if m.group == group.id), key=lambda m: STATUSES.index(m.status))

    def on_site(self):
        """How many lines are already on site."""
        return sum(1 for m in self.lines if STATUS[m.status].on_site)

    def still_to_buy(self):
        """(total, whether any of it is approximate)."""
        buy = [m for m in self.lines if m.status == "buy"]
        return sum(m.total for m in buy), any(m.entry.approx for m in buy)

    @property
    def products(self):
        """{id: Product} — every product on the list, with its names and size."""
        return {m.entry.product.id: m.entry.product for m in self.lines}

    def boxes_of(self, product_id):
        """How many of one product the list has, bought or still to buy."""
        return sum(m.n for m in self.lines if m.entry.product.id == product_id and STATUS[m.status].shop)

    def render(self):
        """The section as Markdown lines: its heading and note, then the table — a heading row
        (and its note) per group, then its lines."""
        L = self.labels
        th, en, nth, nen = self.section
        rows = [heading(2, th, en), ""] + ([*note(nth, nen), ""] if nth else [])
        rows += [f"| {L.both('item')} | {L.both('qty')} | {L.both('price')} | {L.both('on_site')} |", "|---|---|---|---|"]
        for g in self.groups:
            lines = self.in_order(g)
            if lines:
                rows.append(f"| **{both(g.th, g.en)}** | | | |")
                if g.note_th:
                    rows.append(f"| {note_cell(g.note_th, g.note_en)} | | | |")
            rows += [f"| {name_cell(m)} | {qty(m)} | {money_cell(m, L)} | {site_cell(m, L)} |" for m in lines]
        rows.append(f"| **{L.both('still_to_buy')}** | | {self.total_cell()} | |")
        return rows

    def total_cell(self, bold=True):
        """The still-to-buy total: rounded, and marked "about", if any of it is approximate."""
        total, approx = self.still_to_buy()
        v = f"{self.labels.both('about')} {baht(round(total, -2))}" if approx else baht(total)
        return f"**{v}**" if bold else v


# ---------- reading ----------
def load(path):
    """Read and check materials.toml."""
    raw = read_toml(Path(path), "all the materials and prices")
    check(FILE, "the file", raw, FILE_FIELDS)
    section = _section(raw)
    labels = Labels(FILE, raw["labels"], LABELS)
    shops = {e["id"]: Shop(**e) for e in check_each(FILE, "shop", raw["shop"], SHOP)}
    for s in shops.values():
        try:
            re.compile(s.sku)
            s.url("0")
        except (re.error, KeyError, IndexError, ValueError) as e:
            raise DataError(f"{FILE}: shop '{s.id}' has a bad sku pattern or link ({e})") from None
    units = {e["id"]: Unit(**e) for e in check_each(FILE, "unit", raw["unit"], UNIT)}
    groups = tuple(Group(e["id"], *named(e)) for e in check_each(FILE, "group", raw["group"], GROUP))
    known = {"shop": shops, "unit": units, "group": [g.id for g in groups], "status": STATUSES}
    lines = []
    for e in check_each(FILE, "product", raw["entry"], ENTRY, known):
        entry = _entry(e, shops, units)
        where = f"product '{e['id']}'"
        lines += [_line(u, entry, where) for u in check_each(FILE, f"{where} line", e["line"], LINE, known)]
    return Materials(section, groups, tuple(lines), labels)


def _section(raw):
    """This part's heading and note; the note's {prices_date} filled in."""
    th, en, nth, nen = named(check(FILE, "[section]", raw["section"], NAMED))
    date = raw.get("prices_date")
    for lang, text in (("note_th", nth), ("note_en", nen)):
        for _, f, _, _ in string.Formatter().parse(text):
            if f is not None and f != "prices_date":
                raise DataError(f"{FILE}: [section] {lang} has {{{f}}} (it can show: prices_date)")
            if f == "prices_date" and date is None:
                raise DataError(f"{FILE}: [section] {lang} shows {{prices_date}}, but the file has no prices_date")
    shown = date.strftime("%d/%m/%Y") if date else ""
    return th, en, nth.format(prices_date=shown), nen.format(prices_date=shown)


def _product(e, where):
    """The product's name and detail, with its size filled in, and its size."""
    size = check(FILE, f"{where} size", e.get("size", {}), SIZE)
    fill = {f"{k}{u}": f"{v / div:g}" for k, v in size.items() for u, div in SIZE_UNITS.items()}
    names = {}
    for field in TEXT_KEYS:
        text = e[field]
        for _, f, _, _ in string.Formatter().parse(text):
            if f is not None and f not in fill:
                k = f.split("_")[0]
                raise DataError(f"{FILE}: {where} {field} shows {{{f}}}, but its size has no {k}"
                                if k in SIZE_KEYS and f in {k + u for u in SIZE_UNITS} else
                                f"{FILE}: {where} {field} has {{{f}}} (a name can show: "
                                f"{', '.join(k + u for u in SIZE_UNITS for k in SIZE_KEYS)})")
        names[field] = text.format(**fill)
    return Product(e["id"], *(names[k] for k in TEXT_KEYS), *(size.get(k) for k in SIZE_KEYS), e.get("per_box"))


def _entry(e, shops, units):
    """A checked [[entry]]: what the product is, and how it is bought."""
    where = f"product '{e['id']}'"
    if e.get("price", 0) < 0:
        raise DataError(f"{FILE}: {where} 'price' can't be negative")
    shop = None
    if "shop" in e or "sku" in e:
        if "shop" not in e or "sku" not in e:
            raise DataError(f"{FILE}: {where} has a shop or a sku without the other — give both")
        shop = shops[e["shop"]]
        if not re.fullmatch(shop.sku, e["sku"]):
            raise DataError(f"{FILE}: {where} has sku {e['sku']!r}, which isn't a {shop.en} code")
    return Entry(_product(e, where), units.get(e.get("unit")), e.get("price"), e.get("approx", False),
                 shop, e.get("sku"))


def _line(u, p, where):
    """A checked line on the list, checked against its product by the rules of its status (STATUS)."""
    s = u["status"]
    rule = STATUS[s]
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
    if rule.by and "by_th" not in u:
        raise DataError(f"{FILE}: {where} is {s}, so it needs by_th and by_en: who brings it")
    if not rule.by and "by_th" in u:
        raise DataError(f"{FILE}: {where} is {s}, so it has no by_th / by_en")
    return Line(p, u["group"], s, u["n"], u.get("note_th", ""), u.get("note_en", ""),
                u.get("by_th", ""), u.get("by_en", ""))


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
        return both(m.by_th, m.by_en)
    return L.both("buy") if m.status == "buy" else "✓"


def name_cell(m):
    """The name (linked to the shop's page), then its shop and SKU, then the note for this line."""
    p = m.entry
    pr = p.product
    name = md_cell(both(f"{pr.th} {pr.detail_th}", f"{pr.en}, {pr.detail_en}"))
    if p.link:
        name = f"[{name}]({p.link})<br>{both(p.shop.th, p.shop.en)} {p.sku}"
    if m.note_th or m.note_en:
        name += f"<br>{note_cell(m.note_th, m.note_en)}"
    return name


def main(argv):
    path = Path(argv[1] if len(argv) > 1 else FILE)
    m = load(path)
    print("\n".join(m.render()))


if __name__ == "__main__":
    cli(lambda: main(sys.argv))
