"""The material list's design checks: problems with the quantities on the list, found when it is
set against what the room needs.

    tiles, warnings = materials_design_checks.tile_check(materials, tiles_needed)

The checks, each worded by its label in materials.toml:
  - too few tile boxes on the list for the tiles the room needs                 tile_short

`tiles_needed` is the room's count, tile by tile (room.py works it out from the room's sizes),
handed over by build.py — this file knows nothing about the room beyond those counts, and each
tile is matched to its boxes on the list by product. A problem is shown in red on the floor plan,
where the tiles are, and printed by the build.
"""


def tile_check(m, tiles_needed):
    """[(tiles needed, boxes on the list)] per tile, and a problem (th, en) where there are too few."""
    tiles = [(t, m.boxes_of(t.tile.product)) for t in tiles_needed]
    short = [dict(tile=(t.tile.th, t.tile.en), planned=f"{planned:g}", boxes=t.boxes)
             for t, planned in tiles if planned < t.boxes]
    return tiles, [("materials", (m.labels.th("tile_short", **v), m.labels.en("tile_short", **v))) for v in short]
