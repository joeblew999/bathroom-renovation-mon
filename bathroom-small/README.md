# Bathroom (small) — renovate the existing bathroom at the same size

A separate, smaller job from the main quote in this repo: renovate the **existing** bathroom and keep it the same size — no new wall, no moving the door. The main quote (the root of this repo) is the bigger plan, where the door wall is broken out and the room is made bigger; nothing here changes it.

## Size (from this repo's data)

| | mm | Where it comes from |
|---|---|---|
| Width | **1,380** | `room.toml` `[room] width` — along the window wall, an existing wall that doesn't move |
| Ceiling height | **2,800** | `room.toml` `[room] ceiling` |
| Length | **2,500** | From the window wall to the existing door wall: exactly 5 tiles of 500 × 500 (per Gerard, 2026-11-05). Fits the plan: the bigger room is 3,000 mm (6 tiles, `room.toml` `[room] length`), and the existing floor step (`room.toml` `floor_step`, 2,000 mm from the window wall) is inside the existing room. |

Floor and ceiling area: 2.5 × 1.38 = **3.45 m²**.

## 1. Ceiling

**Done first.** The same build as the main quote's new ceiling (`phases.toml` phase `build_ceiling`, `materials.toml` work section `new_ceiling`), sized for this room — plus painting the ceiling, the walls and the window's steel protector.

**Steps**
1. Take down the old ceiling light and pull out its cable; take down the whole old ceiling, tiles and grid.
2. **Frame:** galvanised steel wall angle round the room at the old ceiling height (2,800 mm); C-channels across the room (the 1,380 mm span) at 40 cm centres, resting on the wall angle on both long walls — the span is short, so no hanger wire.
3. **Board:** screw up moisture-resistant gypsum board over the whole ceiling, for a flush finish.
4. **Joints:** tape and fill every joint and screw head smooth.
5. **Paint:** the ceiling, the walls and the window's steel protector, with the white paint already on site.

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

## 2. Fittings

The same fittings as the main quote — **all already bought** (`materials.toml`, status "procured"). They all go into this room.

| Fitting | Product | Size (W × H × D) | HomePro SKU | Price paid |
|---|---|---|---|---|
| Toilet | [MOYA 1-piece toilet 323, 3/6 L, white](https://www.homepro.co.th/p/1170662) | 37.5 × 70 × 69 cm | 1170662 | ฿3,490 |
| Basin | [MOYA wall-hung basin 179, white](https://www.homepro.co.th/p/1249118) | 60 × 13 × 31 cm | 1249118 | ฿1,190 |
| Basin tap | [MOYA basin tap 832-1](https://www.homepro.co.th/p/1254863) | | 1254863 | ฿929 |
| Basin trap | [KARAT bottle trap KA-02-112-50, 25 cm](https://www.homepro.co.th/p/1225658) | | 1225658 | ฿485 |
| Mirror | [MOYA round mirror HLP004](https://www.homepro.co.th/p/1319896) | Ø 60 cm | 1319896 | ฿429 |
| Towel rail | [LUZERN shelf with towel rail AS-5012S, chrome](https://www.homepro.co.th/p/1215163) | 62 × 14.5 × 23 cm | 1215163 | ฿799 |
| | | | **Total (already paid)** | **฿7,322** |

Where each one goes in this room: to set out.
