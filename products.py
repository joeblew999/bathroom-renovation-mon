#!/usr/bin/env python3
"""The product catalogue: products.toml, read and checked. Shared by the material list and the
drawings — like common.py, it knows nothing about either; both read it, neither reads the other.

    cat = load(Path("products.toml"))      # {id: Product}
    cat["toilet"].w                        # 375
    cat["grey_tile"].name_en               # "Grey tile TARA Stone Blast 500 × 500 mm, …"

A name can show the product's size with {w} {h} {d} (mm) or {w_cm} {h_cm} {d_cm} (cm), so the
size is typed once.
"""
import string
import sys
from dataclasses import dataclass
from pathlib import Path

from common import DataError, cli, need, number, only, read_toml

FILE = "products.toml"
KEYS = {"id", "name_th", "name_en", "size", "per_box"}
SIZE_KEYS = ("w", "h", "d")


@dataclass(frozen=True)
class Product:
    id: str
    name_th: str         # with any size filled in
    name_en: str
    w: float = None      # mm: wide, high, deep — only for products the drawings or tile count use
    h: float = None
    d: float = None
    per_box: int = None  # tiles in a box (tiles only)

    def size(self):
        """{w, h, d} that are given."""
        return {k: getattr(self, k) for k in SIZE_KEYS if getattr(self, k) is not None}


def load(path):
    raw = read_toml(Path(path), "every product: names and sizes")
    only(FILE, "the file", raw, {"product"})
    out = {}
    for e in raw.get("product", []):
        where = f"product '{e.get('id', '?')}'"
        only(FILE, where, e, KEYS)
        need(FILE, where, e, ("id", "name_th", "name_en"))
        if e["id"] in out:
            raise DataError(f"{FILE}: product id '{e['id']}' is used twice")
        size = e.get("size", {})
        if not isinstance(size, dict):
            raise DataError(f"{FILE}: {where} 'size' must be {{ w = …, h = …, d = … }}")
        only(FILE, f"{where} size", size, SIZE_KEYS)
        for k, v in size.items():
            number(FILE, f"{where} size", k, v)
        if "per_box" in e:
            number(FILE, where, "per_box", e["per_box"])
        fill = {**{k: f"{v:g}" for k, v in size.items()}, **{f"{k}_cm": f"{v / 10:g}" for k, v in size.items()}}
        names = {}
        for lang in ("th", "en"):
            text = e[f"name_{lang}"]
            for _, f, _, _ in string.Formatter().parse(text):
                if f is not None and f not in fill:
                    raise DataError(f"{FILE}: {where} name_{lang} shows {{{f}}}, but its size has no "
                                    f"{f.removesuffix('_cm')}" if f.removesuffix('_cm') in SIZE_KEYS else
                                    f"{FILE}: {where} name_{lang} has {{{f}}} (a name can show: "
                                    f"{', '.join(k + s for s in ('', '_cm') for k in SIZE_KEYS)})")
            names[lang] = text.format(**fill)
        out[e["id"]] = Product(e["id"], names["th"], names["en"], *(size.get(k) for k in SIZE_KEYS),
                               e.get("per_box"))
    return out


def main(argv):
    for p in load(argv[1] if len(argv) > 1 else FILE).values():
        size = " × ".join(f"{k} {v:g}" for k, v in p.size().items())
        print(f"{p.id:18} {p.name_en}" + (f"   [{size}]" if size else ""))


if __name__ == "__main__":
    cli(lambda: main(sys.argv))
