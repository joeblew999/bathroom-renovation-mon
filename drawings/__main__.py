"""python3 -m drawings [folder] — the tiles needed and any warnings."""
import sys

import products
from common import DataError

from .model import load


def main(argv):
    try:
        folder = argv[1] if len(argv) > 1 else "."
        d = load(folder, products.load(f"{folder}/{products.FILE}"))
    except DataError as e:
        sys.exit(f"ERROR: {e}")
    for t in d.tiles_needed():
        print(f"{t.colour}: {t.need} tiles → {t.boxes} boxes")
    for where, w in d.warnings():
        print(f"WARNING ({where}): {w}")
    print(f"{len(d.render())} drawings · {len(d.warnings())} warnings")


main(sys.argv)
