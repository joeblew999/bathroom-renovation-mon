"""The room: room.toml, read, checked, and drawn as the floor plan and the wall elevations.
It knows nothing about the phases; product sizes are handed to it from the material list.

    r = room.load(Path("room.toml"), products)   # products = materials.load(...).products
    r.render()                  # {file name: svg text}
    r.warnings()                # [(wall id, warning)]
    r.tiles_needed()            # [TilesNeeded]

  model.py   reads and checks room.toml, builds every wall, the design rules
  svg.py     draws them

Usage:  python3 -m room [folder]    (prints the tiles needed and any warnings)
"""
from .model import ROOM_FILE, Room, TilesNeeded, load

__all__ = ["ROOM_FILE", "Room", "TilesNeeded", "load"]
