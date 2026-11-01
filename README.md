# Bathroom renovation — project files

The builder and family get the quote at **https://joeblew999.github.io/bathroom-renovation-mon/** — as a web page, with the PDF beside it (`bathroom-renovation-quote.pdf`). Both are built from the sources below; everything else is how it's made.

## Commands

All commands, and the tool versions they run with, are in `mise.toml`. To see them:

```
mise tasks
```

First time on a machine: `mise run setup`.

## Output

`mise run build` writes two files into `out/`, always together from the same page:

- `out/index.html` — the quote as one web page (phases, materials, drawings)
- `out/bathroom-renovation-quote.pdf` — that same page printed to A4

Nothing else is ever written. `out/` is not committed: on every push to `main`, `.github/workflows/pages.yml` runs the same `mise run setup`, `mise run test` and `mise run build`, and publishes `out/` to GitHub Pages. If a test fails, nothing is published.

## Sources (edit these)

| File | Holds |
|---|---|
| `bathroom-renovation-quote.md` | The document skeleton: the title, the two headings and their one-line intros. Hand-written. `<!-- generated:… -->` markers mark where generated tables go in the PDF; nothing ever rewrites this file. |
| `site.toml` | The room, door, lintel, window, floor step, tile sizes, every product size, the four walls (names, tile), and the design rules (`[rules]`). The drawings, checks and tile counts are worked out from it. |
| `layout.toml` | Every position: main wall, window wall, floor. Items name their product (`product = "toilet"`) and take its size from `site.toml`. Also the names of the items worked out from the site (`[site_items]`). |
| `phases.toml` | The work, phase by phase: each phase and step with its Thai and English text. Numbered by position; refer to them within the phases, or in the skeleton, as `{phase:id}` / `{step:id}`, so inserting a step renumbers every reference. |
| `materials.toml` | Every material: its **group** and its **status** (`buy`, `bought` or `reused`) — the two things the list is ordered by — plus name, note, how many (`n`), unit price, and where it's bought: `shop` and `sku` (the shop's product code — the product link is built from them). The groups are defined in this file. Stands on its own: it doesn't refer to the phases or the drawings, and they don't refer to it. |

Each fact lives in one place. Things that follow from the site — the column, the door opening, the lintel, the window, the door on the floor plan — are worked out in `drawings.py`, never typed twice. Nothing is printed twice either: sizes and positions are on the drawings only.

## The document

1. Work by phase · 2. Materials — then the drawings, one per page (floor plan and three walls)

## Code

Three parts that stand on their own, and one file that puts them together. No part imports another, and no text in one part refers to another — a drawing note doesn't name a step, a step doesn't quote a site number, a material doesn't name a phase.

| File | Reads | Gives |
|---|---|---|
| `phases.py` | `phases.toml` | the phases, numbered, as Markdown · `mise run phases` prints it |
| `materials.py` | `materials.toml` | the material list as Markdown, the still-to-buy total, the tile boxes on the list · `mise run materials` prints it |
| `drawings.py` | `site.toml`, `layout.toml` | the floor plan and wall elevations as SVG, the design-rule warnings, the tiles the room needs |
| `build_pdf.py` | the skeleton | the only combiner: fills the skeleton with the phases and the material list, adds the drawings, runs the one check that spans two parts (tile boxes on the list vs tiles needed), writes the web page and the PDF |
| `common.py` | — | reading a TOML file and checking its keys and types; knows nothing about bathrooms |

What the PDF prints for the phases and the materials is exactly what `mise run phases` and `mise run materials` print — the same function.

Bad data raises one `DataError` naming the file and the problem; the build prints it as `ERROR: …` and stops before writing anything.

## Checks (run on every build)

**Errors — the build stops, nothing is written.** The data no longer fits together:

- a key a file doesn't know (a typo like `lnk` for `link`, `widht` for `w`)
- a value of the wrong type (a number typed as text, `approx = "yes"`)
- a missing number in `site.toml`, or a door that doesn't fit in the new wall
- a drawing item: with no shape or an unknown shape, missing what its shape needs (a rect without a height), naming a product that isn't in `site.toml`, sharing its number with another item, or belonging (`part`) to an item that isn't there
- a material: naming a group the file doesn't define, a status that isn't `buy`, `bought` or `reused`, no quantity, something to buy with no price, a reused fitting with a price, a missing or unknown shop, or an SKU that isn't that shop's kind of code
- a tile colour on the material list that isn't a tile on the drawings (checked in `build_pdf.py`, the one place that sees both)
- a `{phase:…}` / `{step:…}` reference that matches nothing, or a phase or step id used twice
- a drawing note with a reference in braces (drawing notes stand on their own)
- a `<!-- generated:… -->` marker missing from the document

**Warnings — the build goes on, shown as `WARNING (...)` and in red on the drawings.** The data fits together but breaks a design rule:

- a hole closer to a tile joint than `min_clear` in `site.toml` (exactly on one is fine)
- two items overlapping, or an item running past the end of its wall
- a fixing or outlet outside the item it belongs to
- fewer tile boxes on the list than the room needs (the one check across two parts, in `build_pdf.py`)

## Tests

Break copies of the sources on purpose, put the quote together in-process (`assemble`, no PDF) and confirm each check fires. Under a second. Run after changing any script or data rule.

## Needs

`mise` (it installs the pinned Python). Everything else comes from `mise run setup`.
