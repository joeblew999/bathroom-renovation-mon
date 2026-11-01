# Bathroom renovation quote

A quote for the builder, in Thai and English: the work, the materials schedule and the drawings. It is published as:

- Web page: **https://joeblew999.github.io/bathroom-renovation-mon/**
- PDF: **https://joeblew999.github.io/bathroom-renovation-mon/bathroom-renovation-quote.pdf**

## Commands

`mise tasks` lists every command (they are in `mise.toml`). Only `mise` needs to be installed; on a new machine, run `mise run setup` first.

## How the quote is made

The quote has three **parts**: the phases (the scope of works, in sequence), the materials (the materials schedule) and the room (the floor plan and elevations). Each part is a data file and the code that reads it; the materials and the room also have a design-checks file.

```
phases.toml     ──► phases.py                                      ─┐
materials.toml  ──► materials.py    + materials_design_checks.py   ─┼──► build.py ──► out/index.html ──► out/…pdf
     ▲                                                              │
     │ the room names products by id (rule 6)                       │
room.toml       ──► room.py         + room_design_checks.py        ─┘
```

`build.py` is the only place the parts meet. It puts the phases and the materials schedule into the template, `bathroom-renovation-quote.md`, adds the drawings after them, one per page, writes the web page to `out/index.html`, and has Chromium print the same page as the PDF. `out/` is never committed.

On every push to `main`, GitHub runs `mise run setup` and `mise run ci` — the same commands you can run here — and publishes `out/` only if `mise run ci` passes.

## Files

| File | Holds |
|---|---|
| `phases.toml` | The work: phases and steps, in prose for the builder |
| `materials.toml` | Every product once — its name and detail in Thai and English, its size, how it's bought (unit, price, shop, code) and its lines on the list (group, status, how many); the shops, units and groups; the list's wording and marks |
| `room.toml` | The room: its size and the clearance a hole needs from a tile joint; the column, door and lintel; the tiles; the floor and the four walls in order round the room, each with its items; the drawings' wording and marks |
| `phases.py`, `materials.py`, `room.py` | The parts' code: each reads and checks its own data file and renders its section |
| `room_design_checks.py`, `materials_design_checks.py` | The design checks: setting out and clashes; quantities (see Checks) |
| `bathroom-renovation-quote.md` | The template: the title, then a marker for the phases and one for the materials schedule (the drawings follow, one per page) |
| `style.css` | The look of the whole page, drawings included |
| `build.py` | Puts the parts together and writes the page and the PDF |
| `common.py` | Helpers that know nothing about bathrooms: reading TOML, the one checker every entry goes through, labels, headings and notes |
| `test_pipeline.py` | The tests |
| `mise.toml` | The commands, and the pinned tools (Python and uv) |
| `pyproject.toml`, `uv.lock` | The Python packages, pinned exactly; `mise run setup` installs exactly the lock |
| `.github/workflows/pages.yml` | GitHub's build: `mise run setup`, `mise run ci`, then publish |
| `docs/` | Plans, one file each, named `YYYY-MM-DD-NN-slug.md` |
| `CLAUDE.md`, `AGENTS.md` | Point Claude, and other AI agents, to this README |

## Rules for every change

1. **Everything specific to this bathroom is data.**
   - Every word, number, date, name and mark on the page is in the data file of the part it's about.
   - Fixed wording is that file's `[labels]`, each label in Thai and English; marks that are the same in both languages are its `[symbols]`.
   - The code holds no wording, except the messages printed for whoever runs the build: English only, never on the page or the PDF.
   - Layout is code; the look is `style.css`.
   - The one exception: the existing structure and the opening — the existing column at the start of its wall, the door opening beside it, the lintel over it — are set out in `room.py`, labelled there.
2. **The data files are consistent.**
   - Every entry of one kind has the same fields, in the same order, written to the same pattern; a product's detail, for one, follows the pattern at the top of `materials.toml`.
   - Optional fields are left out, never moved.
   - Things that are pointed at have an `id` that says what they are.
   - Each part declares the fields of every kind of entry once, and `common.check` checks them all.
   - When data is messy, fix the data: code never works around it with special cases.
3. **Names, in Thai and English.**
   - A name is `th` and `en` (a shop, a unit, a tile, a wall, a step); a named thing that can carry a note adds an optional `note_th` and `note_en` (a section, a phase, a group, an item on a drawing).
   - Thai and English always say the same thing. `common.check` makes each pair fill in the same `{…}` placeholders and give the same numbers, in any order — so a number is written in digits in both ("1-piece", not "one-piece"), in the same unit.
   - Thai and English are never joined by hand; the one exception is the title line in the template.
4. **One look for each shape**, from `common.py`: a heading is "Thai / English"; a note is Thai, with the English underneath.
5. **Parts don't know each other.**
   - No part's code imports another part's code; the parts meet only in `build.py`.
   - No data file holds a fact about another part. The phases name kinds of material in plain words ("ready-mix mortar"), never products, sizes or quantities, and never which tile goes where.
   - The one link is rule 6.
6. **The one link between parts: the room and the materials schedule.** The room names products on the materials schedule by id, for their names and sizes, and `room.py` checks every id; the tiles the room needs are set against the boxes on the schedule by the quantities check (see Checks). `build.py` hands both over. Nothing links the phases to anything.
7. **Every fact once.**
   - A product's name, detail and size are written only on its entry in `materials.toml`; its detail shows the size with `{w}`, `{w_cm}` and so on, and the room takes them from there.
   - What follows from the room is worked out in `room.py`, never typed: where each wall is, the column, door and lintel, the tile counts.
   - Numbers come from order, never typed; things point at each other by id.
   - A note never repeats a fact held elsewhere, or a figure that can be worked out.
8. **Bad data stops the build; a design problem is never published** (see Checks).
9. **Tests never depend on today's numbers or wording.**
   - A test finds what it breaks by what it is, and works out the expected message from the real data and its labels.
   - Every check has a test; `mise run test` lists them.

## Checks

Every check is one of two kinds, and they never mix: a **data check** asks whether a data file is written correctly; a **design check** asks whether the bathroom it describes is well designed.

### Data checks

A data file written wrongly: a missing or misspelt field, an id that points at nothing, Thai without English. Fixing it means correcting the file.
- A data check lives in the part's own code (`phases.py`, `materials.py`, `room.py`), or in `common.check` when every entry shares it; the template's two checks are in `build.py`.
- It raises `DataError`: the build stops with one English line naming the file and the problem, and nothing is written.

### Design checks

The judgement an architect and a builder bring — good building practice, sound architectural design and how it will look. Fixing a design problem means changing the design. There are two aspects, each in its own file, named for the part it checks:

- **Setting out and clashes** — `room_design_checks.py`, beside `room.toml` and `room.py`: whether every item is set out where it belongs and fits, keeps clear of the tile joints, doesn't clash with another item or sit in an opening, and will look right.
- **Quantities** — `materials_design_checks.py`, beside `materials.toml` and `materials.py`: the quantity take-off from the drawings set against the materials schedule — whether enough is ordered.

The phases have no design checks. Each design-checks file lists its checks at the top.

How a design problem is reported:
- A design check never raises `DataError`. It returns a design problem: a note for the architect, in Thai and English — where, what, the rule, what to do — worded by a label in the part's `[labels]`.
- `mise run build` still writes the page and the PDF, with each problem in red under its drawing, and prints each one and the count.
- `mise run ci` refuses any design problem, so neither `mise run publish` nor GitHub publishes it.

### Placing a new check

Ask what fixing it would take:
- **Correcting the file** → a data check, in the part's own code (`phases.py`, `materials.py`, `room.py`), or in `common.check` if every entry shares it.
- **Changing the setting out** — where something goes, its size, how it fits or looks → a setting-out and clashes check, in `room_design_checks.py`.
- **Ordering more, or ordering something different** → a quantities check, in `materials_design_checks.py`.

A design check never goes in a part's own code, and a data check never goes in a design-checks file. For example:
- "An item names a product that isn't on the materials schedule": correct the id — a data check, in `room.py`.
- "The door is too wide to fit beside the column": a different door frame — a setting-out and clashes check, in `room_design_checks.py`.
- "Too few tile boxes for the tiles the room needs": order more — a quantities check, in `materials_design_checks.py`.

## Before a change is done

1. Check it against the rules: for 2, every entry of the kind you touched, not just the one; for 5 to 7, search the other files for what you touched; for 9, a new check gets a new test.
2. Run `mise run ci`: clean, 0 design problems.
3. Look at the PDF.
4. Commit locally.
5. Push to `main` only when the owner says so — he judges whether the PDF makes sense, and asks for a push before risky work so there is a safe copy to go back to — and only with `mise run publish`, which refuses unless you're on `main`, nothing is uncommitted and `mise run ci` passes. Then watch the GitHub build until it passes.
