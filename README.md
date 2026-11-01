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
| `bathroom-renovation-quote.md` | The template: layout only. `# {title}`, then a `<!-- section:… -->` marker for each part, in page order. No words, numbers or facts — those are all data. |
| `quote.toml` | What belongs to the whole quote, not one part: its title (`th`, `en`), and the links between parts — `[needed_in]`: which phase a product is first needed in. Only `quote.py` reads it. |
| `room.toml` | The room, door (which product its opening is), lintel (which product, and its bearing), window, floor step, every tile (`[tiles.grey]` … — which product, tiling height, drawing colour; a new tile is a new table, no code), which tile the floor and each wall gets, the four walls' names, and the design rules (`[rules]`). No product sizes — those are in `products.toml`. |
| `layout.toml` | Every position: main wall, window wall, floor. Items name their product (`product = "toilet"`) and take its size from `products.toml`. Also the names of the items worked out from the room (`[room_items]`). |
| `phases.toml` | The work, phase by phase: each phase and step with its Thai and English text. Numbered by position; refer to them within the phases as `{phase:id}` / `{step:id}`, so inserting a step renumbers every reference. |
| `materials.toml` | One `[[entry]]` per product on the list, by its id in `products.toml`, saying how it's bought: unit, price, and where (`shop` and `sku` — the product link is built from them). Under each, one `[[entry.line]]` per line it takes on the list: its **group** and its **status** (`buy`, `bought`, `reused`, or `supplied` — the trade brings it, with `by` saying who) — the two things the list is ordered by — how many, and a note. The shops, suppliers, units (Thai, English singular and plural) and groups are all defined in this file. Doesn't refer to the phases or the drawings, and they don't refer to it. |
| `products.toml` | Every product, defined once: what it is — its Thai and English name, its dimensions as a size field (and tiles per box), shown in the name with `{w}`, `{h}`, `{d}` (mm), `{w_cm}` … (cm) or `{w_m}` … (m) so a dimension is never typed twice. A single figure that isn't a dimension — a weight, a volume, a stock length, an inch trade size — stays in the name. Shared: the material list takes names from it, the drawings take sizes from it. Every product in it must be used by one or the other. |

## Rules for every change

Every change — by a person or by Claude — follows these. Check a change against them before calling it done.

1. **Content is data; the template is layout.** If a different bathroom would change it, it's data: every word, number, date and name, in the file of the part it's about. The template holds only `{title}` and a `<!-- section:… -->` marker per part, in page order. Code holds no wording — fixed words are `[labels]` in the data file of the part that prints them.
2. **One shape for every named thing.** The quote, a section, a phase, a material group: `th`, `en`, and an optional note `note_th` / `note_en` (both or neither). Thai and English are always separate fields, never joined by hand.
3. **One look for each shape**, from `common.py`: a heading is "Thai / English" (`heading()`), a note is a Thai paragraph with the English underneath (`note()`, `note_cell()`). Nothing lays out a heading or a note any other way.
4. **Parts don't know each other.** No part imports another, and no data file mentions another part — no phase id or phase name outside `phases.toml`, no material in the room's files, and so on. Not even as plain words.
5. **Anything that connects two parts lives in `quote.toml`, and only `quote.py` reads it**, checking that both ends exist: the tile boxes matched to the room by product, every product used somewhere, and which phase a product is needed in (`[needed_in]`).
6. **Every fact once.** A product's names and dimensions are in `products.toml`; a name shows its size with `{w}`, `{w_cm}`, `{w_m}` … and never retypes it. Things that follow from the room — the column, the door opening, the lintel, the window, the door on the floor plan — are worked out in `room/`. Numbers are worked out from order (phases, steps), never typed, and only what is referred to by number gets one.
7. **Bad data stops the build** with one `DataError` naming the file and the problem; a broken design rule (a hole near a joint, a clash) is a warning, shown red on the drawing.
8. **Tests never depend on today's numbers** (see Tests).

**Before a change is done:** check it against every rule — for 4 and 5, search the other data files for the ids and names of anything touched; run `mise run test` and `mise run build` (all tests passing, 0 warnings); look at what changed in the PDF. Nothing is called consistent, tested or unchanged without having been checked.

**How changes go in:** build locally and look at the PDF; commit locally; push to `main` only when the owner says so, then watch the GitHub build.

## The document

The title, then Work by phase, then Materials — then the drawings, one per page (floor plan and three walls). The order is the template's.

## Code

Three parts that stand on their own, a shared product catalogue, and one file that puts them together (rules 4 and 5).

| File | Reads | Gives |
|---|---|---|
| `phases.py` | `phases.toml` | the phases, numbered, as Markdown · `mise run phases` prints it |
| `materials.py` | `materials.toml` (+ the catalogue) | the material list as Markdown, the still-to-buy total, how many of each product it has · `mise run materials` prints it |
| `room/` | `room.toml`, `layout.toml` (+ the catalogue) | `model.py` reads and checks them, builds every wall and the design-rule warnings and the tiles the room needs; `svg.py` draws the floor plan and wall elevations · `python -m room` prints the tiles and warnings |
| `quote.py` | the template, `quote.toml` | the only combiner: fills the template with the title and each part's section, adds the drawings, runs the checks that span parts (tile boxes on the list vs tiles needed, matched by product; every product used somewhere; every `[needed_in]` product on the list and its phase in `phases.toml`), writes the web page and the PDF |
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
- a drawing item: with no shape or an unknown shape, missing what its shape needs (a rect without a height), naming a product that isn't in `products.toml`, sharing its number with another item, or belonging (`part`) to an item that isn't there
- a material: naming a group the file doesn't define, a status that isn't `buy`, `bought`, `reused` or `supplied`, a supplied item with no known `by` or with a price, no quantity, something to buy with no price, a reused fitting with a price, a missing or unknown shop, supplier or unit, a product that isn't on the list, or an SKU that isn't that shop's kind of code
- a product named on the list or the drawings that isn't in `products.toml`, a product there that nothing uses (checked in `quote.py`), a name showing a size the product doesn't have, or a tile that isn't square or has no box size
- a `{phase:…}` / `{step:…}` reference that matches nothing, or a phase or step id used twice
- a drawing note with a reference in braces (drawing notes stand on their own)
- a `[needed_in]` product that isn't on the list, or a phase that isn't in `phases.toml`
- a `<!-- section:… -->` marker or `{title}` missing from the template
- a note in one language only (every note has `note_th` and `note_en`)

**Warnings — the build goes on, shown as `WARNING (...)` and in red on the drawings.** The data fits together but breaks a design rule:

- a hole closer to a tile joint than `min_clear` in `room.toml` (exactly on one is fine)
- two items overlapping, or an item running past the end of its wall
- a fixing or outlet outside the item it belongs to
- fewer tile boxes on the list than the room needs (the one check across two parts, in `quote.py`)

## Tests

`mise run test` breaks copies of the sources on purpose, puts the quote together in-process (`assemble`, no PDF) and confirms each check fires — under a few seconds.

No test depends on today's numbers. Each one picks what it breaks by what it is (an item that belongs to another item, the floor tile's product, a line still to buy), edits it in the loaded data, and works out the message it expects from the real data. Changing a price, a position or a quantity never breaks a test; only a broken check does. The tests write their edited copies with `tomli-w`, pinned in `requirements.txt`.

## Needs

`mise` (it installs the pinned Python). Everything else comes from `mise run setup`.
