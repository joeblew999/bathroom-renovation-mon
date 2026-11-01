"""The room: room.toml and layout.toml, read, checked, and drawn as the floor plan and the
wall elevations. It knows nothing about the phases or the materials.

    r = room.load(Path("."), catalogue)   # the folder holding room.toml and layout.toml;
                                          # catalogue = products.load(...)
    r.render()                  # {file name: svg text}
    r.warnings()                # [(wall id, warning)]
    r.tiles_needed()            # [TilesNeeded]

  model.py   reads and checks the two files, builds every wall, the design rules
  svg.py     draws them

Usage:  python3 -m room [folder]    (prints the tiles needed and any warnings)
"""
from .model import Room, TilesNeeded, load

__all__ = ["Room", "TilesNeeded", "load"]
