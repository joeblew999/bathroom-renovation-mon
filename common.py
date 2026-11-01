#!/usr/bin/env python3
"""Small helpers shared by phases.py, materials.py and room/: reading a TOML file and
checking what is in it. They know nothing about bathrooms; each part owns its own rules.

Bad data raises DataError, with a message naming the file and the problem.
"""
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
    """`v` must be one of `known` (a list, or a dict whose entry is returned)."""
    if v not in known:
        raise DataError(f"{file}: {where} has {key} = {v!r} (must be one of: {', '.join(known)})")
    return known[v] if isinstance(known, dict) else v


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


# ---------- the one shape of a named thing, and how it is printed ----------
# A section, a phase, a material group, the quote itself: th and en (its name), and an
# optional note under it, note_th and note_en. Every one is checked and printed the same way.
NAMED = ("th", "en", "note_th", "note_en")


def named(file, where, e):
    """Check the name and optional note of a named thing; returns (th, en, note_th, note_en)."""
    need(file, where, e, ("th", "en"))
    if ("note_th" in e) != ("note_en" in e):
        raise DataError(f"{file}: {where} has a note in one language only — give note_th and note_en")
    return e["th"], e["en"], e.get("note_th", ""), e.get("note_en", "")


def heading(level, th, en):
    """A heading: 'Thai / English'."""
    return f"{'#' * level} {both(th, en)}"


def note(th, en):
    """A note under a heading: a Thai paragraph, then an English paragraph."""
    return [f"> {th}", ">", f"> {en}"] if th or en else []


def note_cell(th, en):
    """The same note inside a table cell: Thai, then English underneath."""
    return f"*{md_cell(th)}*<br>*{md_cell(en)}*"


class Labels:
    """The fixed wording a part prints, read from its own data file's [labels] table:

        [labels]
        tile_top = { th = "ขอบกระเบื้อง", en = "tile top {top}" }

    Each label has `en` and, unless there is nothing to translate, `th`. {name} fills in a
    value; a value given as a (th, en) pair fills each language with its own text.
    `needed` is {label: (the names it may fill in)} — every label must be there, no others,
    and each may only use its own names, so a typo stops the build at load."""

    def __init__(self, file, raw, needed):
        only(file, "[labels]", raw, needed)
        for key, names in needed.items():
            where = f"[labels] {key}"
            if key not in raw:
                raise DataError(f"{file}: [labels] has no '{key}'")
            if not isinstance(raw[key], dict):
                raise DataError(f"{file}: {where} must be {{ th = \"…\", en = \"…\" }}")
            only(file, where, raw[key], {"th", "en"})
            need(file, where, raw[key], ("en",))
            for lang, text in raw[key].items():
                used = {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}
                if not used <= set(names):
                    bad = sorted(used - set(names))[0]
                    raise DataError(f"{file}: {where} {lang} uses {{{bad}}} "
                                    f"(it can use: {', '.join(names) or 'nothing'})")
        self.raw = raw

    def _fill(self, key, lang, values):
        text = self.raw[key].get(lang, "")
        return text.format(**{k: (v[0 if lang == "th" else 1] if isinstance(v, tuple) else v)
                              for k, v in values.items()})

    def th(self, key, **values):
        return self._fill(key, "th", values)

    def en(self, key, **values):
        return self._fill(key, "en", values)

    def both(self, key, sep=" / ", **values):
        """'ไทย / English', or just the English when the label has no Thai."""
        th = self.th(key, **values)
        return both(th, self.en(key, **values), sep) if th else self.en(key, **values)
