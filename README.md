# Bathroom renovation quote

A bilingual (Thai / English) quote for the builder, published at
**https://joeblew999.github.io/bathroom-renovation-mon/** as a web page and a PDF.

## Commands

`mise tasks` lists them (`mise.toml`). First time on a machine: `mise run setup`. Only `mise` is needed.

## How it's built

Three parts, each one data file read by one piece of code. `build.py` puts them in the template.

```
phases.toml     ──► phases.py     ─┐
materials.toml  ──► materials.py  ─┼──► build.py ──► out/index.html ──► out/…pdf (printed by Chromium)
room.toml       ──► room/         ─┘    (+ the template, style.css)
```

On every push to `main`, GitHub runs the same `setup`, `test` and `build` and publishes `out/`. `out/` is never committed.

## Files

| File | Holds |
|---|---|
| `phases.toml` | The work: phases and steps — prose for the builder |
| `materials.toml` | Every product, once: its names and size, how it's bought (unit, price, shop, code) and its lines on the list (group, status, how many); the shops, units and groups |
| `room.toml` | The room: its size; each wall (which way it runs, the walls at either end, whether it's drawn); the floor plan's sides; the existing column, the tiles, door, lintel and window (and which wall each is in); the clearance rule (how far a hole must be from a tile joint); the drawing wording; and every position on the walls and floor |
| `bathroom-renovation-quote.md` | The template: the title, then a section marker per part, in page order |
| `style.css` | The page's look |
| `phases.py`, `materials.py`, `room/` | The parts: each reads its own file and renders its section |
| `build.py` | The only place the parts meet: hands the products' sizes to the room, checks the tile boxes, fills the template, writes the page and the PDF |
| `common.py` | Helpers that know nothing about bathrooms: reading and checking TOML, labels, headings and notes |
| `test_pipeline.py` | The tests |
| `mise.toml`, `requirements.txt` | The commands and pinned tools; the pinned Python packages |
| `CLAUDE.md` | Points Claude to this README |

## Rules for every change

1. **Content is data; the template is layout.** If a different bathroom would change it, it's data — every word, number, date and name — in the file of the part it's about. Fixed wording is `[labels]` in that file; code holds none. The one exception is how this bathroom is built, which stays in `room/` and is labelled there: the existing column at the start of the door's wall, with the door opening beside it and the lintel over it.
2. **One shape for every named thing** (a section, a phase, a group): `th`, `en`, and an optional `note_th` / `note_en`. Thai and English are never joined by hand — the one exception is the title line in the template.
3. **One look for each shape**, from `common.py`: a heading is "Thai / English"; a note is Thai, with the English underneath.
4. **Parts don't know each other.** No part imports another, and no data file holds a fact about another part. The phases name kinds of material in plain words ("ready-mix mortar"), never products or quantities — the list is the only place for those.
5. **The only links between parts:** the room names products on the material list by id (for their sizes, and to match its tiles to the boxes on the list). `build.py` passes the sizes over and checks every id. Nothing links the phases to anything.
6. **Every fact once.** A product's names and size are on its entry in `materials.toml` (a name shows its size with `{w}`, `{w_cm}` …); what follows from the room is worked out in `room/`; numbers come from order, never typed.
7. **Bad data stops the build** with one error naming the file and the problem. A broken design rule (a hole near a tile joint, a clash) is a warning, shown red on the drawing.
8. **Tests never depend on today's numbers.** A test finds what it breaks by what it is and works out the expected message from the real data. `mise run test` lists every check.

**Before a change is done:** check it against the rules (for 4 and 5, search the other files for what you touched), run `test` and `build` (all passing, 0 warnings), and look at the PDF. **Push** to `main` only when the owner says so, then watch the GitHub build.
