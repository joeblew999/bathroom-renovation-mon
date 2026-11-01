"""The drawings: site.toml and layout.toml, read, checked, and drawn as the floor plan and
the wall elevations. It knows nothing about the phases or the materials.

    d = drawings.load(Path("."))     # the folder holding site.toml and layout.toml
    d.render()                       # {file name: svg text}
    d.warnings()                     # [(wall id, warning)]
    d.tiles_needed()                 # [TilesNeeded]

  model.py   reads and checks the two files, builds every wall, the design rules
  svg.py     draws them

Usage:  python3 -m drawings [folder]    (prints the tiles needed and any warnings)
"""
from .model import Drawings, TilesNeeded, load

__all__ = ["Drawings", "TilesNeeded", "load"]
