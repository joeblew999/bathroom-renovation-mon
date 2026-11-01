# Bathroom renovation quote

A bilingual (Thai / English) quote for the builder, published at
**https://joeblew999.github.io/bathroom-renovation-mon/** as a web page and a PDF.

## Commands

`mise tasks` lists them (`mise.toml`). First time on a machine: `mise run setup`. Only `mise` is needed.

## How it's built

```
template + data files ──► phases.py, materials.py, room/ ──► quote.py ──► out/index.html ──► out/…pdf
                              (each reads its own files)      (puts it      (the web page)    (printed by
                                                               together)                       Chromium)
```

On every push to `main`, GitHub runs the same `setup`, `test` and `build` and publishes `out/`. `out/` is never committed.

## Files

| File | Holds |
|---|---|
| `bathroom-renovation-quote.md` | The template: `{title}` and a section marker per part, in page order |
| `quote.toml` | The title, and the links between parts (`[needed_in]`: which phase a product is needed in) |
| `phases.toml` | The work: phases and steps |
| `materials.toml` | How each product is bought (unit, price, shop, code) and its lines on the list (group, status, how many); the shops, suppliers, units and groups |
| `products.toml` | Every product: its names and size |
| `room.toml` | The room, its walls and tiles, the door and lintel, the design rules |
| `layout.toml` | Every position on the walls and the floor |
| `style.css` | The page's look |
| `phases.py`, `materials.py`, `room/` | The parts: each reads its own files and renders its section |
| `products.py` | Reads `products.toml` for the material list and the drawings |
| `quote.py` | The only place the parts meet: fills the template, checks the links, writes the page and the PDF |
| `common.py` | Helpers that know nothing about bathrooms: reading and checking TOML, labels, headings and notes |
| `test_pipeline.py` | The tests |

## Rules for every change

1. **Content is data; the template is layout.** If a different bathroom would change it, it's data — every word, number, date and name — in the file of the part it's about. Fixed wording is `[labels]` in that file; code holds none.
2. **One shape for every named thing** (the quote, a section, a phase, a group): `th`, `en`, and an optional `note_th` / `note_en`. Thai and English are never joined by hand.
3. **One look for each shape**, from `common.py`: a heading is "Thai / English"; a note is Thai, with the English underneath.
4. **Parts don't know each other.** No part imports another; no data file mentions another part, not even in plain words.
5. **Links between parts live only in `quote.toml`**, and `quote.py` checks both ends.
6. **Every fact once.** Names and sizes in `products.toml` (a name shows its size with `{w}`, `{w_cm}` …); what follows from the room is worked out in `room/`; numbers come from order, never typed.
7. **Bad data stops the build** with one error naming the file and the problem. A broken design rule (a hole near a tile joint, a clash) is a warning, shown red on the drawing.
8. **Tests never depend on today's numbers.** A test finds what it breaks by what it is and works out the expected message from the real data. `mise run test` lists every check.

**Before a change is done:** check it against the rules (for 4 and 5, search the other files for what you touched), run `test` and `build` (all passing, 0 warnings), and look at the PDF. **Push** to `main` only when the owner says so, then watch the GitHub build.
