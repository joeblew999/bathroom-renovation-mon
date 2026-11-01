#!/usr/bin/env python3
"""The labour: labour.toml, read, checked, priced and rendered. It knows nothing about the phases or the
drawings; the room's take-off and the materials list's counts and costs are handed to it.

    lab = load(Path("labour.toml"), take_off, materials)
        # take_off = {name: (value, unit)} from room.take_off(); materials = the loaded materials list
    lab.render(materials_total)   # the labour section as Markdown, with its total and the grand total
    lab.total()         # (labour total, whether any of it is approximate)

Every rate names the book it comes from and its item there (README rule 10); a rate with no book is a
stand-in, marked assumed. Each line's quantity comes from exactly one place — the room's take-off, a count of
products on the materials list, a share of what products cost, or a figure written in the file — and its unit
must be the rate's.

Usage:  python3 build.py --summary    (the labour total prints with the rest)
"""
from dataclasses import dataclass
from pathlib import Path

from common import NAME, NAMED, DataError, Labels, assumed, both, check, check_each, heading, md_cell, named, \
    note, note_cell, placeholders, read_toml

FILE = "labour.toml"
FILE_FIELDS = {"checked": "date!", "date_format": "text!", "round_approx": "count!", "section": "table!",
               "labels": "table!", "symbols": "table!", "book": "list!", "unit": "list!", "work_section": "list!",
               "rate": "list!", "line": "list!"}
SYMBOLS = {k: "text!" for k in ("currency", "times", "percent")}
BOOK = {"id": "text!", **NAME, "standard": "text!", "url": "text!"}
UNIT = {"id": "text!", **NAME, "en_many": "text!"}
WORK_SECTION = {"id": "text!", **NAMED}
RATE = {"id": "text!", **NAME, "unit": "@unit!", "rate": "amount!", "book": "@book+url", "item": "text+book",
        "book_note": "whole+book", "url": "text+book", "assumed": "list"}
SOURCES = ("take_off", "count", "of_products", "n")      # where a line's quantity comes from: exactly one
LINE = {"rate": "@rate!", "work_section": "@work_section!", "take_off": "text", "count": "list", "of_products": "list",
        "n": "count", "times": "whole", "note_th": "text", "note_en": "text", "assumed": "list"}
SOURCE_UNIT = {"count": "set", "of_products": "percent"}  # the rate unit these sources need (take_off: its own)
LABELS = {"item": (), "qty": (), "amount": (), "book_item": ("item",), "book_note": ("note",), "of_products": ("percent", "cost"),
          "labour_total": (), "grand_total": (), "approx": (), "about": ()}
DECIMALS = 1                                              # a measured quantity is shown, and priced, to this


@dataclass(frozen=True)
class Rate:
    id: str
    th: str
    en: str
    unit_id: str         # m2, metre, set, job, percent
    unit: dict           # its names: {th, en, en_many}
    rate: float
    item: str            # its item number in the book, or ""
    book_note: int       # or the number of the note in the book it comes from, or None (a stand-in has neither)
    approx: bool         # a stand-in (assumed), or a share of materials (the book gives a range)


@dataclass(frozen=True)
class Line:
    rate: Rate
    work_section: str
    qty: float           # in the rate's unit (percent: the rate is the share, qty is the materials' cost)
    names: tuple         # ((th, en), …): the products it counts or takes a share of, from the materials list
    share: bool          # priced as a share of materials
    note_th: str
    note_en: str
    approx: bool

    @property
    def amount(self):
        return self.rate.rate / 100 * self.qty if self.share else self.rate.rate * self.qty


@dataclass(frozen=True)
class Labour:
    section: tuple       # (th, en, note_th, note_en), filled in
    work_sections: tuple  # ((id, th, en, note_th, note_en), …)
    lines: tuple
    labels: Labels
    symbols: dict
    round_approx: int
    assumed: tuple = ()  # [(where, key, value)]: values not yet known for real (README rule 10)

    def total(self):
        """(labour total, whether any of it is approximate)."""
        return sum(m.amount for m in self.lines), any(m.approx for m in self.lines)

    def money(self, v):
        """Baht: whole when it is whole, else to the satang, so every line adds up as shown."""
        return f"{self.symbols['currency']}{v:,.0f}" if v == round(v) else f"{self.symbols['currency']}{v:,.2f}"

    def total_text(self, v, approx):
        """A total: rounded, and marked "about", when any of it is approximate."""
        return f"{self.labels.both('about')} {self.money(round(v / self.round_approx) * self.round_approx)}" \
            if approx else self.money(v)

    def render(self, materials_total):
        """The section as Markdown: its heading and note, then the table — a heading row per work section, then
        its lines — then the labour total and the grand total (`materials_total` = (what the materials still
        cost, whether approximate), handed over by build.py)."""
        L = self.labels
        th, en, nth, nen = self.section
        rows = [heading(2, th, en), "", *note(nth, nen),
                f"| {L.both('item')} | {L.both('qty')} | {L.both('amount')} |", "|---|---|---|"]
        for sid, sth, sen, snth, snen in self.work_sections:
            lines = [m for m in self.lines if m.work_section == sid]
            if lines:
                rows.append(f"| **{both(sth, sen)}** | | |")
                rows += [f"| {note_cell(snth, snen)} | | |"] if snth else []
            rows += [f"| {self.name_cell(m)} | {self.qty_cell(m)} | {self.amount_cell(m)} |" for m in lines]
        total, approx = self.total()
        grand, grand_approx = total + materials_total[0], approx or materials_total[1]
        rows.append(f"| **{L.both('labour_total')}** | | **{self.total_text(total, approx)}** |")
        rows.append(f"| **{L.both('grand_total')}** | | **{self.total_text(grand, grand_approx)}** |")
        return rows

    def name_cell(self, m):
        """The work and its item in the book, then what it counts (from the materials list), then its note."""
        L, r = self.labels, m.rate
        place = L.both("book_item", item=r.item) if r.item else L.both("book_note", note=r.book_note) if r.book_note else ""
        name = md_cell(both(r.th, r.en)) + (f" ({place})" if place else "")
        name += "".join(f"<br>{md_cell(both(t, e))}" for t, e in m.names)
        return name + (f"<br>{note_cell(m.note_th, m.note_en)}" if m.note_th else "")

    def qty_cell(self, m):
        """The quantity and its unit × the rate — or, for a share, the share of what the materials cost."""
        r, s = m.rate, self.symbols
        if m.share:
            return self.labels.both("of_products", percent=f"{r.rate:g}{s['percent']}", cost=self.money(m.qty))
        unit = r.unit["en" if m.qty == 1 else "en_many"]
        return f"{m.qty:g} {both(r.unit['th'], unit)} {s['times']} {self.money(r.rate)}"

    def amount_cell(self, m):
        return (f"{self.labels.both('approx')} " if m.approx else "") + self.money(m.amount)


# ---------- reading ----------
def load(path, take_off, materials):
    """Read and check labour.toml, and price every line. `take_off` = {name: (value, unit)} from the room;
    `materials` = the materials list (for counts, costs and names)."""
    raw = read_toml(Path(path), "the labour and its rates")
    check(FILE, "the file", raw, FILE_FIELDS, ordered=False)
    labels = Labels(FILE, raw["labels"], LABELS)
    check(FILE, "[symbols]", raw["symbols"], SYMBOLS)
    books = {b["id"]: b for b in check_each(FILE, "book", raw["book"], BOOK)}
    units = {u["id"]: u for u in check_each(FILE, "unit", raw["unit"], UNIT)}
    sections = tuple((s["id"], *named(s)) for s in check_each(FILE, "work section", raw["work_section"], WORK_SECTION))
    guesses = []
    rates = {}
    for e in check_each(FILE, "rate", raw["rate"], RATE, {"unit": units, "book": books}):
        if "book" in e and ("item" in e) == ("book_note" in e):
            raise DataError(f"{FILE}: rate '{e['id']}' must give its place in its book: an item or a book_note, not both")
        if "book" not in e and "rate" not in e.get("assumed", []):
            raise DataError(f"{FILE}: rate '{e['id']}' has no book, so its rate must be marked assumed (README rule 10)")
        guesses += assumed(e, f"{FILE} rate '{e['id']}'")
        rates[e["id"]] = Rate(e["id"], e["th"], e["en"], e["unit"], units[e["unit"]], e["rate"], e.get("item", ""), e.get("book_note"),
                              "assumed" in e or e["unit"] == "percent")
    products = materials.products
    known = {"rate": rates, "work_section": [s[0] for s in sections]}
    lines = []
    for i, e in enumerate(check_each(FILE, "line", raw["line"], LINE, known), 1):
        where = f"line {i} ({e['rate']})"
        guesses += assumed(e, f"{FILE} {where}")
        lines.append(_line(e, where, rates[e["rate"]], take_off, materials, products))
    return Labour(_section(raw, labels, books), sections, tuple(lines), labels, raw["symbols"], raw["round_approx"],
                  tuple(guesses))


def _section(raw, labels, books):
    """This part's heading and note; the note's {book}, {standard}, {checked} and {approx} filled in. The note
    names the first book (the one most rates come from)."""
    th, en, nth, nen = named(check(FILE, "[section]", raw["section"], NAMED))
    book, date = next(iter(books.values())), raw["checked"].strftime(raw["date_format"])
    out = []
    for lang, text in (("th", nth), ("en", nen)):
        placeholders(FILE, f"[section] note_{lang}", text, ("book", "standard", "checked", "approx"))
        out.append(text.format(book=book[lang], standard=book["standard"], checked=date,
                               approx=getattr(labels, lang)("approx")))
    return th, en, *out


def _line(e, where, rate, take_off, materials, products):
    """One line, priced: its quantity from exactly one source, in the rate's unit."""
    given = [k for k in SOURCES if k in e]
    if len(given) != 1:
        raise DataError(f"{FILE}: {where} must take its quantity from exactly one of {', '.join(SOURCES)} "
                        f"(it gives {', '.join(given) or 'none'})")
    source = given[0]
    names = ()
    if source == "take_off":
        if e["take_off"] not in take_off:
            raise DataError(f"{FILE}: {where} takes off '{e['take_off']}', which the room doesn't work out "
                            f"(it works out: {', '.join(take_off)})")
        qty, unit = take_off[e["take_off"]]
        qty = round(qty * e.get("times", 1), DECIMALS)
    else:
        unit = SOURCE_UNIT.get(source)
        if source in SOURCE_UNIT:
            for pid in e[source]:
                if pid not in products:
                    raise DataError(f"{FILE}: {where} names product '{pid}', which is not on the materials list")
            names = tuple((products[pid].th, products[pid].en) for pid in e[source])
        if source == "count":
            qty = materials.count_of(e["count"]) * e.get("times", 1)
        elif source == "of_products":
            qty = materials.cost_of(e["of_products"])[0]
        else:
            qty = e["n"] * e.get("times", 1)
    if unit is not None and unit != rate.unit_id:
        raise DataError(f"{FILE}: {where} measures in {unit}, but rate '{rate.id}' is per {rate.unit_id}")
    if source == "n" and rate.unit_id == "percent":
        raise DataError(f"{FILE}: {where} writes a quantity, but rate '{rate.id}' is a share of materials — use of_products")
    approx = rate.approx or bool(e.get("assumed")) or (source == "of_products" and materials.cost_of(e["of_products"])[1])
    return Line(rate, e["work_section"], qty, names, source == "of_products", e.get("note_th", ""), e.get("note_en", ""),
                approx)
