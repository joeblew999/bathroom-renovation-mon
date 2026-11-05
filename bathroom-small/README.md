# Bathroom (small) — renovate the existing bathroom at the same size

A separate, smaller job from the main quote in this repo: renovate the **existing** bathroom and keep it the same size — no new wall, no moving the door. The main quote (the root of this repo) is the bigger plan, where the door wall is broken out and the room is made bigger; nothing here changes it.

## Size (from this repo's data)

| | mm | Where it comes from |
|---|---|---|
| Width | **1,380** | `room.toml` `[room] width` — along the window wall, an existing wall that doesn't move |
| Ceiling height | **2,800** | `room.toml` `[room] ceiling` |
| Length | **2,500** | From the window wall to the existing door wall: exactly 5 tiles of 500 × 500 (per Gerard, 2026-11-05). Fits the plan: the bigger room is 3,000 mm (6 tiles, `room.toml` `[room] length`), and the existing floor step (`room.toml` `floor_step`, 2,000 mm from the window wall) is inside the existing room. |

Floor and ceiling area: 2.5 × 1.38 = **3.45 m²**.

## The work, in order

| # | Phase | What |
|---|---|---|
| 1 | Strip out | Remove everything, the old ceiling included, except the shower, water heater, soap holder and toilet paper holder |
| 2 | Ceiling | New gypsum ceiling, then paint the ceiling, walls and window's steel protector |
| 3 | Tiling | Grey floor tiles, the drain, and the step's riser up to the existing pink edge trim |
| 4 | Fit-out | Fit the toilet, basin, tap, trap, mirror and towel rail; **last**, the new door |

### 1. Strip out

Remove **everything** in the bathroom — including the old ceiling: take down the ceiling light (**leave its cable in place** — the new light goes on that cable later), then the whole old ceiling, tiles and grid — **except these, which stay**:

| Stays | |
|---|---|
| Shower | the existing shower |
| Water heater | the existing shower water heater |
| Soap holder | the existing one |
| Toilet paper holder | the existing one |

Cover them up while the rest is stripped out, the ceiling built and painted, and the floor tiled. The old door comes out last, when the new one goes in (phase 4).

### 2. Ceiling

The same build as the main quote's new ceiling (`phases.toml` phase `build_ceiling`, `materials.toml` work section `new_ceiling`), sized for this room — plus painting the ceiling, the walls and the window's steel protector.

**Steps**
1. **Frame:** galvanised steel wall angle round the room at the old ceiling height (2,800 mm); C-channels across the room (the 1,380 mm span) at 40 cm centres, resting on the wall angle on both long walls — the span is short, so no hanger wire.
2. **Board:** screw up moisture-resistant gypsum board over the whole ceiling, for a flush finish — bring the ceiling light's cable out through the board where the light goes.
3. **Joints:** tape and fill every joint and screw head smooth.
4. **Paint:** the ceiling, the walls and the window's steel protector, with the white paint already on site.

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

### 3. Tiling

The floor in the grey tiles, the new drain grate, and the riser (the upright face) of the floor step — tiled up to meet the **existing pink plastic edge trim on top of the step**, which stays.

**How many tiles** (500 × 500 mm, 4 to a box):
- Floor 2,500 × 1,380 mm: 5 tiles along × 3 rows (the third row cut to 380 mm) = **15 tiles**.
- Step riser: 1,380 mm long, cut in strips from **1 tile**.
- Allow **2 tiles** for cuts and breakage → **18 tiles**, 5 boxes (20 tiles).
- **3 boxes (12 tiles) are already on site** (main quote's materials list) → **buy 2 more boxes**.

| Item | Product | SKU | Buy | Price |
|---|---|---|---|---|
| Grey floor tiles | [TARA Stone Blast 50 × 50 cm, grey, shade H07, matt, rectified](https://www.homepro.co.th/p/1292488) | 1292488 | 2 boxes (3 already on site) | ฿418 |
| Floor drain grate | [DEXZON plastic square 10 × 10 cm, 4", anti-odour](https://www.homepro.co.th/p/1240420) | 1240420 | already bought | — |
| Tile adhesive | [Crocodile Gold, 20 kg](https://www.homepro.co.th/p/14428) | 14428 | 1 bag (estimate for 3.45 m² plus the riser) | ฿799 |
| Grout | [Crocodile Premium Plus, 1 kg, granite grey](https://www.homepro.co.th/p/138786) | 138786 | 1 bag (estimate) | ฿63 |
| | | | **Total to buy** | **฿1,280** |

- **Same shade:** the 2 new boxes must be **shade H07**, the same as the 3 on site — check the box labels.
- Products and prices from `materials.toml` (prices checked 2026-10-31). Adhesive and grout amounts are estimates for this room, not from the main quote.

### 4. Fit-out

Fit the toilet, basin, basin tap, trap, mirror and towel rail — the same fittings as the main quote, **all already bought** (`materials.toml`, status "procured").

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

**Last: the door.** Same door, hinges and handle as the main quote, but **70 cm wide** — the existing door is 700 mm wide (per Gerard, 2026-11-05), so the new one matches it (the main quote's is 80 cm). HomePro, checked 2026-11-05:

| Item | Product | HomePro SKU | Price |
|---|---|---|---|
| Door | [AZLE WB2 UPVC bathroom door, 70 × 200 cm, brown, pre-drilled for the knob](https://www.homepro.co.th/p/1259829) | 1259829 | ฿1,990 |
| Hinges | [YALE hinges, 304 stainless, 4 × 3", pack of 3](https://www.homepro.co.th/p/1123585) | 1123585 | ฿199 |
| Handle | [SOLEX bathroom knob 9500 SS-BK, stainless](https://www.homepro.co.th/p/89869) | 89869 | ฿399 |
| | | **Total** | **฿2,588** |

- The main quote's door is the 80 cm WB2 in **light brown, not pre-drilled** ([1320577](https://www.homepro.co.th/p/1320577)). HomePro's 70 cm WB2 comes in **brown** (pre-drilled for the knob) or white/grey — no light brown in 70 cm.
- The existing frame stays — the new door is the same width as the old one. If the frame ever needs replacing: [AZLE UPVC frame 70 × 200 cm, white](https://www.homepro.co.th/p/1017131), ฿850.

