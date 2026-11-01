#!/usr/bin/env python3
"""Small helpers shared by phases.py, materials.py and room.py: reading a TOML file and
checking what is in it. They know nothing about bathrooms; each part owns its own rules.

Bad data raises DataError, with a message naming the file and the problem.
"""
import datetime
import string
import sys
import tomllib


class DataError(Exception):
    """Bad or missing data in a source file. The message says where and what."""


def read_toml(path, what):
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise DataError(f"{path} not found — it holds {what}") from None
    except tomllib.TOMLDecodeError as e:
        raise DataError(f"{path} is not valid TOML: {e}") from None


def only(file, where, entry, allowed):
    """Any key not in `allowed` is a typo (`lnk` for `link`) that would be silently ignored."""
    unknown = sorted(set(entry) - set(allowed))
    if unknown:
        raise DataError(f"{file}: {where} has unknown key '{unknown[0]}' "
                        f"(allowed: {', '.join(sorted(allowed))})")


def need(file, where, entry, keys):
    for k in keys:
        if k not in entry:
            raise DataError(f"{file}: {where} has no '{k}'")


def number(file, where, key, v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise DataError(f"{file}: {where} '{key}' must be a number, not {v!r}")


def flag(file, where, key, v):
    if not isinstance(v, bool):
        raise DataError(f"{file}: {where} '{key}' must be true or false, not {v!r}")


def one_of(file, where, key, v, known):
    """`v` must be one of `known` (a list of ids, or a dict keyed by id)."""
    if v not in known:
        raise DataError(f"{file}: {where} has {key} = {v!r} (must be one of: {', '.join(known)})")


# ---------- the one checker ----------
# Each part declares every kind of entry it reads once, as {key: type}. A type is "text", "flag",
# "date", "table", "list", a number — "number" (any), "amount" (0 or more), "count" (more than
# 0) or "whole" (a whole number more than 0) — or "@name", one of the ids in known[name] (the shops, the walls …). After the type:
# "+key" — it always comes with that key; "!" — it is required. Every entry gets the same checks,
# so no part repeats them: no unknown key, every required key there, the keys in the declared
# order, each value of its type, keys that come together together, and both languages or
# neither (th with en, note_th with note_en, any x_th with its x_en).
TYPES = {"text": (str, "text"), "table": (dict, "a table"), "list": (list, "a list of tables"),
         "date": (datetime.date, "a date")}
NUMBERS = {"number": None, "amount": "can't be negative", "count": "must be more than 0",
           "whole": "must be a whole number more than 0"}


def _type(spec):
    """'@shop+sku!' → ('@shop', 'sku', True)."""
    kind, _, partner = spec.rstrip("!").partition("+")
    return kind, partner, spec.endswith("!")


def check(file, where, entry, fields, known=None, ordered=True):
    """Check one entry against its declared fields; returns it. A whole file is checked with
    ordered=False: the order of its sections doesn't matter, only the order within each entry."""
    if not isinstance(entry, dict):
        raise DataError(f"{file}: {where} must be a table")
    only(file, where, entry, fields)
    need(file, where, entry, [k for k, t in fields.items() if _type(t)[2]])
    order = [k for k in fields if k in entry]
    if ordered and list(entry) != order:
        k = next(a for a, b in zip(entry, order) if a != b)
        raise DataError(f"{file}: {where} has '{k}' out of order (the order is: {', '.join(order)})")
    for k, v in entry.items():
        kind, partner, _ = _type(fields[k])
        if kind.startswith("@"):
            one_of(file, where, k, v, known[kind[1:]])
        elif kind in NUMBERS:
            number(file, where, k, v)
            if NUMBERS[kind] and (v < 0 if kind == "amount" else v <= 0 or (kind == "whole" and v != int(v))):
                raise DataError(f"{file}: {where} '{k}' {NUMBERS[kind]}")
        elif kind == "flag":
            flag(file, where, k, v)
        elif not isinstance(v, TYPES[kind][0]):
            raise DataError(f"{file}: {where} '{k}' must be {TYPES[kind][1]}, not {v!r}")
        elif kind == "list" and not v:
            raise DataError(f"{file}: {where} '{k}' is empty — leave it out, or give it at least one")
        if partner and partner not in entry:
            raise DataError(f"{file}: {where} has {k} but no {partner} — give both, or neither")
    for k in entry:
        other = _other_language(k)
        if other in fields and other not in entry:
            raise DataError(f"{file}: {where} has {k} but no {other} — give both languages, or neither")
    return entry


def _other_language(key):
    """th ↔ en, note_th ↔ note_en, x_th ↔ x_en; None for a key with no language."""
    if key in ("th", "en"):
        return "en" if key == "th" else "th"
    stem, _, lang = key.rpartition("_")
    return f"{stem}_{'en' if lang == 'th' else 'th'}" if lang in ("th", "en") and stem else None


def check_each(file, kind, entries, fields, known=None):
    """Check every entry of one kind, and — when it has ids — that each id is used once."""
    seen = set()
    for i, e in enumerate(entries, 1):
        check(file, f"{kind} '{e['id']}'" if isinstance(e, dict) and "id" in e else f"{kind} {i}",
              e, fields, known)
        if "id" in fields:
            if e["id"] in seen:
                raise DataError(f"{file}: {kind} id '{e['id']}' is used twice")
            seen.add(e["id"])
    return entries


def both(th, en, sep=" / "):
    """Thai and English side by side: 'ไทย / English' — the one place they are joined."""
    return f"{th}{sep}{en}"


def cli(run):
    """Run a command-line tool: bad data prints one ERROR line and stops."""
    try:
        run()
    except DataError as e:
        sys.exit(f"ERROR: {e}")


def md_cell(v):
    """Text safe inside a Markdown table cell."""
    return v.replace("|", "\\|").replace("\n", " ")


# ---------- the two shapes of a name, and how they are printed ----------
# NAME: th and en — a shop, a unit, a tile, a wall, a step.
# NAMED: a name with an optional note under it, note_th and note_en — a section, a phase, a
# material group, an item on a drawing. Every one is checked and printed the same way.
NAME = {"th": "text!", "en": "text!"}
NAMED = {**NAME, "note_th": "text", "note_en": "text"}


def named(e):
    """A checked named thing as (th, en, note_th, note_en)."""
    return e["th"], e["en"], e.get("note_th", ""), e.get("note_en", "")


def heading(level, th, en):
    """A heading: 'Thai / English'."""
    return f"{'#' * level} {both(th, en)}"


def note(th, en):
    """A note under a heading: a Thai paragraph, then an English paragraph, then a blank line —
    or nothing, when there is no note."""
    return [f"> {th}", ">", f"> {en}", ""] if th or en else []


def note_cell(th, en):
    """The same note inside a table cell: Thai, then English underneath."""
    return f"*{md_cell(th)}*<br>*{md_cell(en)}*"


def placeholders(file, where, text, allowed):
    """Every {name} in `text` must be one of `allowed` — the one check for text that fills in values."""
    try:
        used = [f for _, f, _, _ in string.Formatter().parse(text) if f is not None]
    except ValueError:
        raise DataError(f"{file}: {where} has a stray {{ or }}") from None
    for f in used:
        if f not in allowed:
            raise DataError(f"{file}: {where} uses {{{f}}} (it can use: {', '.join(allowed) or 'nothing'})")


class Labels:
    """The fixed wording a part prints, read from its own data file's [labels] table:

        [labels]
        tile_top = { th = "ขอบกระเบื้อง", en = "tile top {top}" }

    Every label has th and en. {name} fills in a value; a value given as a (th, en) pair fills
    each language with its own text. `needed` is {label: (the names it may fill in)} — every
    label must be there, no others, and each may only use its own names, so a typo stops the
    build at load."""

    def __init__(self, file, raw, needed):
        check(file, "[labels]", raw, {k: "table!" for k in needed})
        for key, names in needed.items():
            check(file, f"[labels] {key}", raw[key], NAME)
            for lang in ("th", "en"):
                placeholders(file, f"[labels] {key} {lang}", raw[key][lang], names)
        self.raw = raw

    def _fill(self, key, lang, values):
        return self.raw[key][lang].format(**{k: (v[0 if lang == "th" else 1] if isinstance(v, tuple) else v)
                                             for k, v in values.items()})

    def th(self, key, **values):
        return self._fill(key, "th", values)

    def en(self, key, **values):
        return self._fill(key, "en", values)

    def both(self, key, sep=" / ", **values):
        """'ไทย / English'."""
        return both(self.th(key, **values), self.en(key, **values), sep)
