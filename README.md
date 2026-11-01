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
| `room.toml` | The room, door (which product its opening is), lintel, window, floor step, every tile (`[tiles.grey]` … — which product, tiling height, drawing colour; a new tile is a new table, no code), which tile the floor and each wall gets, the four walls' names, and the design rules (`[rules]`). No product sizes — those are in `products.toml`. |
| `layout.toml` | Every position: main wall, window wall, floor. Items name their product (`product = "toilet"`) and take its size from `products.toml`. Also the names of the items worked out from the site (`[room_items]`). |
| `phases.toml` | The work, phase by phase: each phase and step with its Thai and English text. Numbered by position; refer to them within the phases, or in the skeleton, as `{phase:id}` / `{step:id}`, so inserting a step renumbers every reference. |
| `materials.toml` | One `[[entry]]` per product on the list, by its id in `products.toml`, saying how it's bought: unit, price, and where (`shop` and `sku` — the product link is built from them). Under each, one `[[entry.line]]` per line it takes on the list: its **group** and its **status** (`buy`, `bought`, `reused`, or `supplied` — the trade brings it, with `by` saying who) — the two things the list is ordered by — how many, and a note. The shops, suppliers, units (Thai, English singular and plural) and groups are all defined in this file. Doesn't refer to the phases or the drawings, and they don't refer to it. |
| `products.toml` | Every product, defined once: what it is — its Thai and English name and, for products the drawings or the tile count use, its size (and tiles per box). A name shows the size with `{w}`, `{h}`, `{d}` (mm) or `{w_cm}` … (cm), so it's never typed twice. Shared: the material list takes names from it, the drawings take sizes from it. Every product in it must be used by one or the other. |

All the fixed wording the PDF prints — column headings, "Phase", "Still to buy", every label on the drawings — is in the `[labels]` table of the file its part reads (`phases.toml`, `materials.toml`, `room.toml`), in Thai and English. The code holds no wording, only layout. The page title is the document's own first heading.

Each fact lives in one place. Things that follow from the site — the column, the door opening, the lintel, the window, the door on the floor plan — are worked out in `room/`, never typed twice. Nothing is printed twice either: sizes and positions are on the drawings only.

## The document

1. Work by phase · 2. Materials — then the drawings, one per page (floor plan and three walls)

## Code

Three parts that stand on their own, and one file that puts them together. No part imports another, and no text in one part refers to another — a drawing note doesn't name a step, a step doesn't quote a number from `room.toml`, a material doesn't name a phase.

| File | Reads | Gives |
|---|---|---|
| `phases.py` | `phases.toml` | the phases, numbered, as Markdown · `mise run phases` prints it |
| `materials.py` | `materials.toml` (+ the catalogue) | the material list as Markdown, the still-to-buy total, how many of each product it has · `mise run materials` prints it |
| `room/` | `room.toml`, `layout.toml` (+ the catalogue) | `model.py` reads and checks them, builds every wall and the design-rule warnings and the tiles the room needs; `svg.py` draws the floor plan and wall elevations · `python -m room` prints the tiles and warnings |
| `quote.py` | the skeleton | the only combiner: fills the skeleton with the phases and the material list, adds the drawings, runs the two checks that span parts (tile boxes on the list vs tiles needed, matched by product; every product used somewhere), writes the web page and the PDF |
| `style.css` | — | the page's look (fonts, tables, page breaks), read by `quote.py` |
| `common.py` | — | reading a TOML file and checking its keys and types, the `[labels]` reader, the one Thai/English join, the one ERROR-and-stop wrapper; knows nothing about bathrooms |
| `products.py` | `products.toml` | the product catalogue — names (with sizes filled in) and sizes — handed to both the material list and the drawings; knows nothing about either · `mise run products` lists it |

What the PDF prints for the phases and the materials is exactly what `mise run phases` and `mise run materials` print — the same function.

Bad data raises one `DataError` naming the file and the problem; the build prints it as `ERROR: …` and stops before writing anything.

## Checks (run on every build)

**Errors — the build stops, nothing is written.** The data no longer fits together:

- a key a file doesn't know (a typo like `lnk` for `link`, `widht` for `w`)
- a value of the wrong type (a number typed as text, `approx = "yes"`)
- a missing number in `room.toml`, or a door that doesn't fit in the new wall
- a drawing item: with no shape or an unknown shape, missing what its shape needs (a rect without a height), naming a product that isn't in `room.toml`, sharing its number with another item, or belonging (`part`) to an item that isn't there
- a material: naming a group the file doesn't define, a status that isn't `buy`, `bought`, `reused` or `supplied`, a supplied item with no known `by` or with a price, no quantity, something to buy with no price, a reused fitting with a price, a missing or unknown shop, supplier or unit, a product that isn't on the list, or an SKU that isn't that shop's kind of code
- a product named on the list or the drawings that isn't in `products.toml`, a product there that nothing uses (checked in `quote.py`), a name showing a size the product doesn't have, or a tile that isn't square or has no box size
- a `{phase:…}` / `{step:…}` reference that matches nothing, or a phase or step id used twice
- a drawing note with a reference in braces (drawing notes stand on their own)
- a `<!-- generated:… -->` marker missing from the document

**Warnings — the build goes on, shown as `WARNING (...)` and in red on the drawings.** The data fits together but breaks a design rule:

- a hole closer to a tile joint than `min_clear` in `room.toml` (exactly on one is fine)
- two items overlapping, or an item running past the end of its wall
- a fixing or outlet outside the item it belongs to
- fewer tile boxes on the list than the room needs (the one check across two parts, in `quote.py`)

## Tests

Break copies of the sources on purpose, put the quote together in-process (`assemble`, no PDF) and confirm each check fires. Under a second. Run after changing any script or data rule.

## Needs

`mise` (it installs the pinned Python). Everything else comes from `mise run setup`.
