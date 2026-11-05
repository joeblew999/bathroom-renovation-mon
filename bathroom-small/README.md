# Bathroom (small) — renovate the existing bathroom at the same size

A separate, smaller job from the main quote in this repo: renovate the **existing** bathroom and keep it the same size — no new wall, no moving the door. The main quote (the root of this repo) is the bigger plan, where the door wall is broken out and the room is made bigger; nothing here changes it.

## Size (from this repo's data)

| | mm | Where it comes from |
|---|---|---|
| Width | **1,380** | `room.toml` `[room] width` — along the window wall, an existing wall that doesn't move |
| Ceiling height | **2,800** | `room.toml` `[room] ceiling` |
| Length | **2,500** | From the window wall to the existing door wall: exactly 5 tiles of 500 × 500 (per Gerard, 2026-11-05). Fits the plan: the bigger room is 3,000 mm (6 tiles, `room.toml` `[room] length`), and the existing floor step (`room.toml` `floor_step`, 2,000 mm from the window wall) is inside the existing room. |

Floor and ceiling area: 2.5 × 1.38 = **3.45 m²**.

## Ceiling

- Existing ceiling: suspended gypsum tiles on a grid, like the rest of the house.
- What's to be done to it: to fill in.

## 1. Ceiling

The same build as the main quote's new ceiling (`phases.toml` phase `build_ceiling`, `materials.toml` work section `new_ceiling`), sized for this room. Done before the walls and floor are tiled.

**Steps**
1. Take down the old ceiling light and pull out its cable; take down the whole old ceiling, tiles and grid.
2. **Frame:** galvanised steel wall angle round the room at the old ceiling height (2,800 mm); C-channels across the room (the 1,380 mm span) at 40 cm centres, resting on the wall angle on both long walls — the span is short, so no hanger wire.
3. **Board:** screw up moisture-resistant gypsum board over the whole ceiling, for a flush finish.
4. **Joints:** tape and fill every joint and screw head smooth.
5. **Paint:** with the existing paint (no primer), before tiling.

**Materials** (HomePro; products and prices from `materials.toml`, prices checked 2026-10-31)

| Item | SKU | How many | Why that many | Each | Total |
|---|---|---|---|---|---|
| [DURAONE moisture-resistant gypsum board, 120 × 240 × 0.9 cm](https://www.homepro.co.th/p/1110611) | 1110611 | 2 sheets | 3.45 m² ÷ 2.88 m² a sheet | ฿245 | ฿490 |
| [SANKI C-channel, 4 m](https://www.homepro.co.th/p/1110231) | 1110231 | 4 lengths | 7 channels across the 2,500 mm at 40 cm; each 4 m length cuts 2 × 1,380 mm | ฿29 | ฿116 |
| [SANKI wall angle, 2.44 m](https://www.homepro.co.th/p/1110271) | 1110271 | 4 lengths | 7.76 m round the room | ฿16 | ฿64 |
| [TPI drywall screws, 6 × 1", black](https://www.homepro.co.th/p/1110148) | 1110148 | 1 box | board to C-channel | ฿89 | ฿89 |
| [DURAONE jointing compound, 1 kg](https://www.homepro.co.th/p/1110109) | 1110109 | 2 bags | | ฿16 | ฿32 |
| [PYRAMID joint tape, 1", pack of 3](https://www.homepro.co.th/p/1024381) | 1024381 | 1 pack | | ฿42 | ฿42 |
| [BY TORA wall plugs with screws, no. 7, pack of 50](https://www.homepro.co.th/p/1064892) | 1064892 | 1 pack | for fixing the wall angle | ฿65 | ฿65 |
| | | | | **Total** | **฿898** |

Same quantities as the main quote: the smaller room still needs 2 sheets, 4 C-channel lengths and 4 wall-angle lengths.
