"""python3 -m drawings [folder] — the tiles needed and any warnings."""
import sys

from common import DataError

from .model import load


def main(argv):
    try:
        d = load(argv[1] if len(argv) > 1 else ".")
    except DataError as e:
        sys.exit(f"ERROR: {e}")
    for t in d.tiles_needed():
        print(f"{t.colour}: {t.need} tiles → {t.boxes} boxes")
    for where, w in d.warnings():
        print(f"WARNING ({where}): {w}")
    print(f"{len(d.render())} drawings · {len(d.warnings())} warnings")


main(sys.argv)
