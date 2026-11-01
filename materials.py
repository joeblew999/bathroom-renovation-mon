#!/usr/bin/env python3
"""The material list: materials.toml, read, checked, ordered and rendered. It knows nothing
about the phases or the drawings.

    m = load(Path("materials.toml"))
    m.render()          # the material list as Markdown table rows — the PDF prints exactly this
    m.products          # {id: Product} — every product's name, detail and size (the room uses them)
    m.still_to_buy()    # (total, whether any of it is approximate)
    m.on_site()         # how many lines are already on site
    m.boxes_of(id)      # how many of one product are on the list, bought or to buy

Each [[entry]] is one product: what it is (name, detail, size), how it is bought (unit, price,
shop, code) and, under it, an [[entry.line]] for every line it takes on the list. The shops,
units and groups are defined in the file too; the only fixed list here is the four statuses,
because each one has its own rules (STATUS).

Ordered by exactly two things written in the file: the group (in the order the groups are
listed), then the status (in STATUS order); lines with the same group and status keep the order
of their products in the file.

Usage:  python3 materials.py [materials.toml]    (prints the material list)
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from common import (NAME, NAMED, DataError, Labels, both, check, check_each, cli, heading, md_cell, named,
                    note, note_cell, placeholders, read_toml)

FILE = "materials.toml"
# Every kind of entry in materials.toml, declared once (common.check).
FILE_FIELDS = {"prices_date": "date!", "date_format": "text!", "round_approx": "count!", "section": "table!",
               "labels": "table!", "symbols": "table!", "shop": "list!", "unit": "list!", "group": "list!",
               "entry": "list!"}
SYMBOLS = {k: "text!" for k in ("currency", "on_site", "none", "times")}
SHOP = {"id": "text!", **NAME, "sku": "text!", "link": "text!"}
UNIT = {"id": "text!", **NAME, "en_many": "text!"}
GROUP = {"id": "text!", **NAMED}
TEXT_KEYS = ("th", "detail_th", "en", "detail_en")      # a product's name and detail, sizes filled in
ENTRY = {"id": "text!", **{k: "text!" for k in TEXT_KEYS}, "size": "table", "per_box": "count",
         "unit": "@unit!", "price": "amount", "approx": "flag+price", "shop": "@shop+sku", "sku": "text+shop",
         "line": "list!"}
LINE = {"group": "@group!", "status": "@status!", "n": "count!", "note_th": "text", "note_en": "text",
        "by_th": "text", "by_en": "text"}
SIZE_KEYS = ("w", "h", "d")
SIZE = {k: "count" for k in SIZE_KEYS}
SIZE_UNITS = {"": 1, "_cm": 10, "_m": 1000}          # {w} in mm, {w_cm} in cm, {w_m} in m
LABELS = {k: () for k in ("item", "qty", "price", "on_site", "still_to_buy", "buy", "approx", "about")}


@dataclass(frozen=True)
class Rule:
    to_buy: bool         # still to buy: needs a price, counts in the total, marked "buy"
    paid: bool           # on site and paid for: may have the price it cost, shown as paid
    on_site: bool        # already in the bathroom
    by: bool             # the trade brings it: by_th / by_en say who; no price

    @property
    def shop(self):
        """Bought from a shop (to buy, or paid for): has a shop and code, and its boxes count."""
        return self.to_buy or self.paid


# Each status's rules, stated once — and their order is the order within a group.
STATUS = {
    "buy": Rule(to_buy=True, paid=False, on_site=False, by=False),
    "bought": Rule(to_buy=False, paid=True, on_site=True, by=False),
    "reused": Rule(to_buy=False, paid=False, on_site=True, by=False),
    "supplied": Rule(to_buy=False, paid=False, on_site=False, by=True),
}
STATUSES = tuple(STATUS)


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
    th: str
    en: str
    sku: str             # what its product codes look like (a regular expression)
    link: str            # the product page, with {sku} or {sku_digits} (the code without dots)

    def url(self, sku):
        return self.link.format(sku=sku, sku_digits=re.sub(r"\D", "", sku))


@dataclass(frozen=True)
class Product:
    """What a product is: its name and detail (model, size, pack, colour — any size filled in), in
    Thai and English, and its size in mm."""
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
    unit: Unit
    price: float = None  # unit price in baht
    approx: bool = False
    shop: Shop = None    # where it is bought
    sku: str = None      # the shop's product code

    @property
    def link(self):
        """The product page, built from the shop and the code."""
        return self.shop.url(self.sku) if self.shop else None


@dataclass(frozen=True)
class Line:
    """One line on the list: an entry (a product, as bought), where it goes, and how many."""
    entry: Entry
    group: str           # the id of its group
    status: str          # one of STATUS
    n: float             # how many
    note_th: str = ""
    note_en: str = ""
    by_th: str = ""      # who brings it, when the trade does
    by_en: str = ""

    @property
    def rule(self):
        return STATUS[self.status]

    @property
    def total(self):
        """What is still to pay for it."""
        return self.n * self.entry.price if self.rule.to_buy else 0

    @property
    def paid(self):
        """What was paid for it, when it is paid for and the price is known."""
        return self.n * self.entry.price if self.rule.paid and self.entry.price is not None else 0


@dataclass(frozen=True)
class Materials:
    section: tuple       # (th, en, note_th, note_en): this part's heading and note, filled in
    groups: tuple
    lines: tuple         # every line on the list, in file order
    labels: Labels
    symbols: dict        # the marks on the list: ฿, ✓, —, ×
    round_approx: int    # an approximate total is rounded to this

    def in_order(self, group):
        """The lines of one group as the list shows them: by status, then file order."""
        return sorted((m for m in self.lines if m.group == group.id), key=lambda m: STATUSES.index(m.status))

    def on_site(self):
        return sum(1 for m in self.lines if m.rule.on_site)

    def still_to_buy(self):
        """(total, whether any of it is approximate)."""
        buy = [m for m in self.lines if m.rule.to_buy]
        return sum(m.total for m in buy), any(m.entry.approx for m in buy)

    @property
    def products(self):
        """{id: Product} — every product on the list."""
        return {m.entry.product.id: m.entry.product for m in self.lines}

    def boxes_of(self, product_id):
        """How many of one product the list has, bought or still to buy."""
        return sum(m.n for m in self.lines if m.entry.product.id == product_id and m.rule.shop)

    def money(self, v):
        return f"{self.symbols['currency']}{v:,.0f}"

    def render(self):
        """The section as Markdown lines: its heading and note, then the table — a heading row (and
        its note) per group, then its lines."""
        L = self.labels
        th, en, nth, nen = self.section
        rows = [heading(2, th, en), "", *note(nth, nen)]
        rows += [f"| {L.both('item')} | {L.both('qty')} | {L.both('price')} | {L.both('on_site')} |", "|---|---|---|---|"]
        for g in self.groups:
            lines = self.in_order(g)
            if lines:
                rows.append(f"| **{both(g.th, g.en)}** | | | |")
                rows += [f"| {note_cell(g.note_th, g.note_en)} | | | |"] if g.note_th else []
            rows += [f"| {name_cell(m)} | {self.qty_cell(m)} | {self.money_cell(m)} | {self.site_cell(m)} |"
                     for m in lines]
        rows.append(f"| **{L.both('still_to_buy')}** | | {self.total_cell()} | |")
        return rows

    def total_cell(self, bold=True):
        """The still-to-buy total: rounded, and marked "about", if any of it is approximate."""
        total, approx = self.still_to_buy()
        v = f"{self.labels.both('about')} {self.money(round(total / self.round_approx) * self.round_approx)}" \
            if approx else self.money(total)
        return f"**{v}**" if bold else v

    def qty_cell(self, m):
        """How many (with the unit, singular or plural) and, for what is to buy, × the unit price."""
        n = f"{m.n:g} {m.entry.unit.of(m.n)}"
        return f"{n} {self.symbols['times']} {self.money(m.entry.price)}" if m.rule.to_buy else n

    def money_cell(self, m):
        """What is still to pay, or what was paid."""
        if m.rule.to_buy:
            return (f"{self.labels.both('approx')} " if m.entry.approx else "") + self.money(m.total)
        return self.money(m.paid) if m.paid else self.symbols["none"]

    def site_cell(self, m):
        """Who brings it, "buy", or on site."""
        if m.rule.by:
            return both(m.by_th, m.by_en)
        return self.labels.both("buy") if m.rule.to_buy else self.symbols["on_site"]


def name_cell(m):
    """The name and detail (linked to the shop's page), then the shop and code, then the line's note."""
    p, pr = m.entry, m.entry.product
    name = md_cell(both(f"{pr.th} {pr.detail_th}", f"{pr.en}, {pr.detail_en}"))
    if p.link:
        name = f"[{name}]({p.link})<br>{both(p.shop.th, p.shop.en)} {p.sku}"
    return name + (f"<br>{note_cell(m.note_th, m.note_en)}" if m.note_th else "")


# ---------- reading ----------
def load(path):
    """Read and check materials.toml."""
    raw = read_toml(Path(path), "all the materials and prices")
    check(FILE, "the file", raw, FILE_FIELDS, ordered=False)
    labels = Labels(FILE, raw["labels"], LABELS)
    section = _section(raw, labels)
    check(FILE, "[symbols]", raw["symbols"], SYMBOLS)
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
    return Materials(section, groups, tuple(lines), labels, raw["symbols"], raw["round_approx"])


def _section(raw, labels):
    """This part's heading and note; the note's {prices_date} and {approx} (the label) filled in."""
    th, en, nth, nen = named(check(FILE, "[section]", raw["section"], NAMED))
    date = raw["prices_date"].strftime(raw["date_format"])
    out = []
    for lang, text in (("th", nth), ("en", nen)):
        placeholders(FILE, f"[section] note_{lang}", text, ("prices_date", "approx"))
        out.append(text.format(prices_date=date, approx=getattr(labels, lang)("approx")))
    return th, en, *out


def _product(e, where):
    """The product's name and detail, with its size filled in ({w} in mm, {w_cm}, {w_m} …), and its size."""
    size = check(FILE, f"{where} size", e.get("size", {}), SIZE)
    fill = {f"{k}{u}": f"{v / div:g}" for k, v in size.items() for u, div in SIZE_UNITS.items()}
    for field in TEXT_KEYS:
        placeholders(FILE, f"{where} {field}", e[field], tuple(fill))
    return Product(e["id"], *(e[k].format(**fill) for k in TEXT_KEYS), *(size.get(k) for k in SIZE_KEYS),
                   e.get("per_box"))


def _entry(e, shops, units):
    """A checked [[entry]]: what the product is, and how it is bought. Its code must look like its
    shop's codes."""
    shop = shops.get(e.get("shop"))
    if shop and not re.fullmatch(shop.sku, e["sku"]):
        raise DataError(f"{FILE}: product '{e['id']}' has sku {e['sku']!r}, which isn't a {shop.en} code")
    return Entry(_product(e, f"product '{e['id']}'"), units[e["unit"]], e.get("price"), e.get("approx", False),
                 shop, e.get("sku"))


def _line(u, p, where):
    """A checked line, checked against its product by the rules of its status (STATUS)."""
    s, rule = u["status"], STATUS[u["status"]]
    # (what, whether it has it, whether its status needs it, whether its status allows it)
    for what, has, needed, allowed in (("a price", p.price is not None, rule.to_buy, rule.to_buy or rule.paid),
                                       ("a shop and sku", p.shop is not None, rule.shop, rule.shop),
                                       ("by_th and by_en", "by_th" in u, rule.by, rule.by)):
        if needed and not has:
            raise DataError(f"{FILE}: {where} is {s}, so it needs {what}")
        if has and not allowed:
            raise DataError(f"{FILE}: {where} is {s}, so it has no {what.removeprefix('a ')}")
    return Line(p, u["group"], s, u["n"], u.get("note_th", ""), u.get("note_en", ""),
                u.get("by_th", ""), u.get("by_en", ""))


def main(argv):
    print("\n".join(load(Path(argv[1] if len(argv) > 1 else FILE)).render()))


if __name__ == "__main__":
    cli(lambda: main(sys.argv))
