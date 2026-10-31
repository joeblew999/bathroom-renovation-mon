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
| `phases.toml` | The work, phase by phase: each phase and step with its Thai and English text. Numbered by position; refer to them anywhere as `{phase:id}` / `{step:id}`, so inserting a step renumbers every reference. A rule from `site.toml` is quoted the same way: `{rule:min_clear}`. |
| `materials.toml` | Every material: the phase it is needed for, name, quantity, price, link, approximate or not, on site or not. The material list is grouped by phase. |

Each fact lives in one place. Things that follow from the site — the column, the door opening, the lintel, the window, the door on the floor plan — are worked out in `project.py`, never typed twice. Nothing is printed twice either: sizes and positions are on the drawings only.

## The document

1. Work by phase · 2. Materials — then the drawings, one per page (floor plan and three walls)

## Pipeline

One process, one straight line. Each stage is a function that takes what the stage before it returned:

```
p = project.load(md)        read the five sources, check them, build      → Project (the model)
                            the model: phases with numbers, materials
                            with totals, walls with their items and
                            design-rule warnings
drawings = draw_all(p)      floor plan + three walls, warnings in red     → SVG text
doc = fill(p)               the phases and the material list, every       → Markdown text
                            {phase:…} / {step:…} / {rule:…} filled in
build_pdf: html, pdf        document, then the drawings full-page         → out/index.html + out/…pdf
```

- `project.py` is the only code that reads the sources, and the only code that knows a rule about the data: how phases and steps are numbered, how a price totals, which wall gets which tile, where each wall's x is measured from, and the design rules (joints, clashes, fixings, tile boxes).
- `draw_walls.py` and `tables.py` only format the model into SVG and Markdown. They read and write nothing, and decide nothing about the data.
- `build_pdf.py` writes the web page and the PDF, and nothing else.
- Bad data raises one `ProjectError` naming the file and the problem; the build prints it as `ERROR: …` and stops before writing anything.

## Checks (run on every build, in `project.py` at load)

**Errors — the build stops, nothing is written.** The data no longer fits together:

- a key a file doesn't know (a typo like `lnk` for `link`, `widht` for `w`)
- a value of the wrong type (a number typed as text, `on_site = "yes"`)
- a missing number in `site.toml`, or a door that doesn't fit in the new wall
- a drawing item: with no shape or an unknown shape, missing what its shape needs (a rect without a height), naming a product that isn't in `site.toml`, sharing its number with another item, or belonging (`part`) to an item that isn't there
- a material: naming a phase that isn't in `phases.toml`, a tile colour that isn't grey or white, or still to buy with no price
- a `{phase:…}` / `{step:…}` / `{rule:…}` reference that matches nothing, or a phase or step id used twice
- a `<!-- generated:… -->` marker missing from the document

**Warnings — the build goes on, shown as `WARNING (...)` and in red on the drawings.** The data fits together but breaks a design rule:

- a hole closer to a tile joint than `min_clear` in `site.toml` (exactly on one is fine)
- two items overlapping, or an item running past the end of its wall
- a fixing or outlet outside the item it belongs to
- fewer tile boxes on the list than the room needs

## Tests

Break copies of the sources on purpose, run the stages in-process (`load → draw_all → fill`, no PDF) and confirm each check fires. Under a second. Run after changing any script or data rule.

## Needs

`mise` (it installs the pinned Python). Everything else comes from `mise run setup`.
