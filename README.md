# Bathroom renovation quote

A bilingual (Thai / English) quote for the builder, published as:

- Web page: **https://joeblew999.github.io/bathroom-renovation-mon/**
- PDF: **https://joeblew999.github.io/bathroom-renovation-mon/bathroom-renovation-quote.pdf**

## Commands

`mise tasks` lists them (`mise.toml`). First time on a machine: `mise run setup`. Only `mise` is needed.

## How it's built

Three parts, each one data file read by one piece of code. `build.py` hands the products on the material list to the room, checks the tile boxes, and puts the three sections in the template.

```
phases.toml     ──► phases.py     ─┐
materials.toml  ──► materials.py  ─┼──► build.py ──► out/index.html ──► out/…pdf (printed by Chromium)
room.toml       ──► room.py       ─┘    (+ the template, style.css)
```

On every push to `main`, GitHub runs the same `setup`, `lint`, `test` and `build` and publishes `out/`. `out/` is never committed.

## Files

| File | Holds |
|---|---|
| `phases.toml` | The work: phases and steps — prose for the builder |
| `materials.toml` | Every product, once: its name and detail (Thai and English) and size, how it's bought (unit, price, shop, code) and its lines on the list (group, status, how many); the shops, units and groups; the list's wording and marks |
| `room.toml` | The room: its size and the clearance rule (how far a hole must be from a tile joint); the column, door and lintel; the tiles; the floor and the four walls, in order round the room, each with its items; the drawings' wording and marks |
| `bathroom-renovation-quote.md` | The template: the title, then a section marker for the phases and the materials, in page order (the drawings follow, one per page) |
| `style.css` | The look of the whole page, drawings included |
| `phases.py`, `materials.py`, `room.py` | The parts (see How it's built) |
| `build.py` | The only place the parts meet (see How it's built) |
| `common.py` | Helpers that know nothing about bathrooms: reading TOML, the one checker every entry goes through, labels, headings and notes |
| `test_pipeline.py` | The tests |
| `mise.toml` | The commands, and the pinned tools: Python and uv |
| `.github/workflows/pages.yml` | GitHub's build (see How it's built) |
| `pyproject.toml`, `uv.lock` | The Python packages, and uv's lock file pinning every one of them (and what they depend on) exactly |
| `docs/` | Plans, one file each, named `YYYY-MM-DD-NN-slug.md` |
| `CLAUDE.md` | Points Claude to this README |

## Rules for every change

1. **Content is data; layout is code; the look is `style.css`.** If a different bathroom would change it, it's data — every word, number, date, name and mark — in the file of the part it's about. Fixed wording is `[labels]` in that file, every label in both languages; marks that are the same in both languages are `[symbols]`; code holds none — except the error and summary messages printed for whoever runs the build, which are English only and never reach the page or the PDF. The one exception is how this bathroom is built, which stays in `room.py` and is labelled there: the existing column at the start of its wall, with the door opening beside it and the lintel over it.
2. **The data files are consistent.** Every entry of one kind has the same fields, in the same order, written to the same pattern — a product's detail, for one, follows the pattern written at the top of `materials.toml`. Things that are pointed at have an `id` that says what they are. Optional fields are left out, never moved. Each part declares the fields of every kind of entry once, and one checker (`common.check`) checks them all — including that each Thai/English pair fills in the same `{…}` placeholders and gives the same numbers, in any order, so a number is written in digits in both ("1-piece", not "one-piece") and in the same unit. When data is messy, fix the data: code never works around it with special cases.
3. **Two shapes for a name.** A name is `th` and `en` (a shop, a unit, a tile, a wall, a step); a named thing that can carry a note adds an optional `note_th` / `note_en` (a section, a phase, a group, an item on a drawing). Thai and English always say the same thing (rule 2 says what the checker compares), and are never joined by hand (the one exception is the title line in the template).
4. **One look for each shape**, from `common.py`: a heading is "Thai / English"; a note is Thai, with the English underneath.
5. **Parts don't know each other.** No part imports another, and no data file holds a fact about another part; the one link is rule 6. The phases name kinds of material in plain words ("ready-mix mortar"), never products, sizes or quantities, and never the room's facts (which tile is where) — the list and the room are the only places for those.
6. **The only link between parts:** the room names products on the material list by id, for their names and sizes and to match its tiles to the boxes on the list. `build.py` hands the products over and `room.py` checks every id. Nothing links the phases to anything.
7. **Every fact once.** A product's name, detail and size are on its entry in `materials.toml` (the detail shows the size with `{w}`, `{w_cm}` …), and the room takes them from there (rule 6); what follows from the room — where each wall is, the column, door and lintel, the tile counts — is worked out in `room.py`; numbers come from order, never typed; things point at each other by id. A note never repeats a fact held elsewhere, or a figure that can be worked out.
8. **Bad data stops the build** with one error naming the file and the problem. A broken design rule (a hole near a tile joint, a clash) is a warning, in Thai and English, shown red on the drawing.
9. **Tests never depend on today's numbers or wording.** A test finds what it breaks by what it is and works out the expected message from the real data and its labels. There is a test for every check; `mise run test` lists them.

**Before a change is done:** check it against the rules (for 2, check every entry of the kind you touched, not just the one; for 5 to 7, search the other files for what you touched; for 9, a new check gets a new test), run `lint`, `test` and `build` (all clean, 0 warnings), and look at the PDF. Commit locally. **Push** to `main` only when the owner says so — he judges whether the PDF makes sense, and asks for a push before risky work so there is a safe copy to go back to — then watch the GitHub build until it passes.
