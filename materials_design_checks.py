"""The materials list's design checks — quantities: the quantity take-off from the drawings,
set against what the materials list orders.

    tiles, warnings = materials_design_checks.tile_check(materials, tiles_needed)

The checks, each worded by its label in materials.toml:
  - too few tile boxes on the materials list for the take-off                   warn_take_off_short

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
    return tiles, [("materials", (m.labels.th("warn_take_off_short", **v), m.labels.en("warn_take_off_short", **v))) for v in short]
