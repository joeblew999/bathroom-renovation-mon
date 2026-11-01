"""python3 -m room [folder] — the tiles needed and any warnings. The product sizes come from
the material list beside room.toml."""
import sys
from pathlib import Path

import materials
from common import cli

from .model import ROOM_FILE, load


def main(argv):
    folder = Path(argv[1] if len(argv) > 1 else ".")
    r = load(folder / ROOM_FILE, materials.load(folder / materials.FILE).products)
    for t in r.tiles_needed():
        print(f"{t.name}: {t.need} tiles → {t.boxes} boxes")
    for where, w in r.warnings():
        print(f"WARNING ({where}): {w}")
    print(f"{len(r.render())} drawings · {len(r.warnings())} warnings")


cli(lambda: main(sys.argv))
