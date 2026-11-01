#!/usr/bin/env python3
"""Small helpers shared by phases.py, materials.py and drawings/: reading a TOML file and
checking what is in it. They know nothing about bathrooms; each part owns its own rules.

Bad data raises DataError, with a message naming the file and the problem.
"""
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


def md_cell(v):
    """Text safe inside a Markdown table cell."""
    return v.replace("|", "\\|").replace("\n", " ")
