"""python3 -m room [folder] — the tiles needed and any warnings."""
import sys

import products
from common import cli

from .model import load


def main(argv):
    folder = argv[1] if len(argv) > 1 else "."
    r = load(folder, products.load(f"{folder}/{products.FILE}"))
    for t in r.tiles_needed():
        print(f"{t.name}: {t.need} tiles → {t.boxes} boxes")
    for where, w in r.warnings():
        print(f"WARNING ({where}): {w}")
    print(f"{len(r.render())} drawings · {len(r.warnings())} warnings")


cli(lambda: main(sys.argv))
