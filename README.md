# Bathroom renovation quote

A quote for the builder, in Thai and English: the work, the materials list, the labour and the drawings. It is published as:

- Web page: **https://joeblew999.github.io/bathroom-renovation-mon/**
- PDF: **https://joeblew999.github.io/bathroom-renovation-mon/bathroom-renovation-quote.pdf**

## How to think about this work

This is a real bathroom: an architect designs it, and a Thai builder constructs it from this quote. Work as the architect and the construction company would.
- Judge every change by what the builder will read and do on site: is it unambiguous, is it good building practice, is it sound design, will it look right?
- Use the trade's words — the ones in the Glossary, in Thai and English — and no others. "Build" only ever means the software build (`mise run quote:build`, `mise run quote:check`, `mise run root:ci`); the bathroom is *constructed*.
- Say only what is there. Name a file, a check, a size or a step only after you have looked at it; write no plans, guesses or made-up examples into the README, the data or the notes.
- Write each design problem as a note to the architect: where, what, the rule, and what to do about it.

## Glossary

| Term | Here | Thai |
|---|---|---|
| scope of works | the work, step by step, in the order it is done (`phases.toml`) | ขอบเขตงาน* |
| materials list | what to buy: every product, how many, the price and the shop (`materials.toml`) — data for purchasing, not a schedule on the drawings | รายการวัสดุ |
| schedule of fittings | the table of items on each drawing: every fitting, numbered, with its setting out | รายการอุปกรณ์* |
| floor plan, elevation | the drawings: the floor seen from above, and each wall seen from inside | ผังพื้น, รูปด้าน* |
| setting out | placing each item on site from the dimensions on the drawing, measured from the corner and the floor | การวางตำแหน่ง* |
| clash | a **hard clash**: two items taking the same place; a **soft clash**: an item inside a clearance it must keep, such as a hole too near a tile joint | ชนกัน* |
| opening | a gap in a wall: the window, the door | ช่องเปิด* |
| existing structure | what is already there and stays: the column | โครงสร้างเดิม* |
| lintel | the beam over the door opening | คานทับหลัง |
| tile joint | the line between two tiles | แนวยาแนว* |
| quantity take-off | the quantities measured from the drawings | การถอดปริมาณ* |
| batch, shade | tiles made together, which match in colour | ล็อต, เฉดสี |
| fitting | a fixture on the wall or floor: basin, toilet, shower, lamp | อุปกรณ์* |
| clearance | the clear space a fitting needs in front of it | ระยะว่าง* |
| electrical zones | the zones round the shower (1, then 2) where anything electrical must be rated against water | โซนไฟฟ้า* |
| IP rating | a product's protection rating; its second digit is the protection against water (IPX4) | ระดับ IP* |
| waterproofing | the membrane under the tiles, up to a set height on each wall | กันซึม |
| fall | the floor's slope to the drain, 1 in so many | ความลาดเอียง* |
| norm | an outside value a design check holds the room to, with its source | เกณฑ์* |
| labour rate | the price of a unit of work (a m² of tiling, a set fitted), from a rate book (`labour.toml`) | อัตราค่าแรง* |
| rate book | a published list of labour rates a rate comes from: the Comptroller General's (กค 0433.2/ว 480), or HomePro's installation service prices | บัญชีค่าแรงงาน |
| Factor F | the Comptroller General's multiplier (table ว481) for a contractor's overhead, profit and interest on bare cost; it turns the bare labour rates into a reference price for the builder's quote | Factor F |

\* Not yet checked by a Thai speaker; the unmarked Thai terms were checked against Thai sources.

## Commands

`mise tasks` lists every command (they are in `mise.toml`). Only `mise` needs to be installed; on a new machine, run `mise run root:setup` first.

Every task has one structure, held by [mise-check](https://github.com/joeblew999/mise-check) (`mise run root:check-mise`, part of `root:ci` and `root:publish`): it is named `namespace:task`; its `run` and `usage` are each one line; the flags and arguments it takes are declared in its `usage` and passed by name; and its `run` has no POSIX shell syntax — so every task runs the same on macOS, Linux and Windows. Longer logic is code: `repo.py`, `etl/`, `web/`.

## How the quote is made

The quote has four **parts**: the phases (the scope of works, in sequence), the materials (the materials list), the room (the floor plan and elevations) and the labour (priced from the room and the materials list). Each part is a data file and the code that reads it; the materials and the room also have a design-checks file, and the room's drawings have their own code and their own design checks.

```
phases.toml     ──► phases.py                                      ─┐
materials.toml  ──► materials.py    + materials_design_checks.py   ─┤
     ▲                                                              │
     │ the room names products by id (rule 6)                       ├──► build.py ──► out/index.html ──► out/…pdf
room.toml       ──► room.py         + room_design_checks.py        ─┤
                   └─► room_drawings.py + drawing_design_checks.py ─┤
labour.toml     ──► labour.py   ◄── the room's take-off and         │
                                    the list's counts and costs    ─┘
```

`build.py` is the only place the parts meet. It puts the phases, the materials list and the labour into the template, `bathroom-renovation-quote.md`, has the drawings measured as drawn (`drawing_design_checks.py`), adds them after the list, one per page, writes the web page to `out/index.html`, and has Chromium print the same page as the PDF. `out/` is never committed.

On every push to `main`, GitHub runs `mise run root:setup` and `mise run root:ci` — the same commands you can run here — and publishes `out/` only if `mise run root:ci` passes.

## Files

| File | Holds |
|---|---|
| `phases.toml` | The work: phases and steps, in prose for the builder |
| `materials.toml` | Every product once — its name and detail in Thai and English, its size, whether it's electrical and its IP rating, how it's bought (unit, price, shop, code) and its lines on the materials list (work section, status, how many); the shops, units and work sections; the list's wording and marks |
| `room.toml` | The room: its size and the clearance a hole needs from a tile joint; the column, door (which end it's hinged at, and whether it opens in or out) and lintel; the tiles; the floor (its drain, and its fall on each side of the step) and the four walls (each with its waterproofing height; the shower zone has its own) in order round the room, each with its items, the shower head among them; the norms the design checks use, each with its source; the drawings' wording and marks |
| `labour.toml` | The labour: Factor F (its value, its table and the case it is for); the rate books (which document, how a rate names its place there, and whether its rates are bare) — the Comptroller General's and HomePro's installation service prices — every rate (its name in Thai and English, unit, price, and its item or note in the book, with the page it was read from), and the lines — each a rate, a work section and where its quantity comes from; the units and work sections; the section's wording and marks |
| `phases.py`, `materials.py`, `room.py`, `labour.py` | The parts' code: each reads and checks its own data file; the phases, materials and labour render their sections, the room is worked out (every wall and item, the column, door and lintel, the tile counts, the quantities labour is priced by) |
| `room_drawings.py` | The room's drawings: lays out the floor plan and each elevation as SVG, with its design problems under it |
| `room_design_checks.py`, `materials_design_checks.py`, `drawing_design_checks.py` | The design checks: the room (setting out, clashes, clearances, heights, wet areas); quantities; how the drawings read (see Checks) |
| `bathroom-renovation-quote.md` | The template: the title, then a marker for the phases, one for the materials list and one for the labour (the drawings follow, one per page) |
| `style.css` | The look of the whole page, drawings included |
| `build.py` | Puts the parts together and writes the page and the PDF |
| `common.py` | Helpers that know nothing about bathrooms: reading TOML, the one checker every entry goes through, labels, headings and notes, the one Chromium a run uses |
| `test_pipeline.py` | The tests: `mise run quote:test` measures the drawings in Chromium only in the tests about them; `mise run quote:fuzz` measures them in every test |
| `mise.toml` | The commands, and the pinned tools |
| `repo.py` | The repo's chores as code, so each task stays one line: setting up, linting, publishing |
| `go.mod`, `go.sum`, `mise_test.go` | mise-check, pinned, and the one-line test `mise run root:check-mise` runs on `mise.toml` (Go runs only this) |
| `pyproject.toml`, `uv.lock` | The Python packages, pinned exactly; `mise run root:setup` installs exactly the lock |
| `.github/workflows/pages.yml` | GitHub's build: `mise run root:setup`, `mise run root:ci` (`root:check-mise`, `quote:check`, then `quote:fuzz`), then publish |
| `etl/`, `web/` | The trial of the quote's data as SQLite, and its web app on Cloudflare (plan: `docs/2026-11-02-01-sqlite-data.md`); not used by the build |
| `docs/` | Plans, one file each, named `YYYY-MM-DD-NN-slug.md` |
| `lighting/` | The house's light fittings order (bedrooms, kitchen, bathroom ceiling, living room, eaves): what goes where, the orders and the installation; its own README; not used by the build |
| `appliances/` | The house's appliances and office furniture (TV and wall bracket, fridge, induction cooktop, Ethernet cables, office table and stool): the picks from HomePro, the options looked at, and the order once placed; not used by the build |
| `wardrobe/` | The open wardrobe in bedroom 2, 3 m wide: 6 steel rails in 3 pairs set into pockets in the brick walls, with plywood shelves on U blocks — layout, the builders' steps and the HomePro materials (`README.md`); and the IKEA BOAXEL version, parts and installation (`ikea.md`); not used by the build |
| `bathroom-small/` | A separate, smaller job: renovating the existing bathroom at its current size (no new wall), written for the builders; its own README; not used by the build |
| `sources/` | Copies of the outside documents figures are read from, named by the document's own date — the Comptroller General's labour rate book, `2026-06-26-cgd-w480-labour-rates.pdf` |
| `CLAUDE.md`, `AGENTS.md` | Point Claude, and other AI agents, to this README |

## Rules for every change

1. **Everything specific to this bathroom is data.**
   - Every word, number, date, name and mark on the page is in the data file of the part it's about.
   - Fixed wording is that file's `[labels]`, each label in Thai and English; marks that are the same in both languages are its `[symbols]`.
   - The code holds no wording, except the messages printed for whoever runs the build: English only, never on the page or the PDF.
   - Layout is code; the look is `style.css`. What is the same for any bathroom — the drawing scale, margins, gaps, how far a tag moves to clear another, the drawing checks' tolerances — is a named constant at the top of the code file that uses it, each with a comment saying what it is; never a bare number in the middle of the code, and never in a data file.
   - The one exception: the existing structure and the opening — the existing column at the start of its wall, the door opening beside it, the lintel over it — are set out in `room.py`, labelled there.
2. **The data files are consistent.**
   - Every entry of one kind has the same fields, in the same order, written to the same pattern; a product's detail, for one, follows the pattern at the top of `materials.toml`.
   - Optional fields are left out, never moved.
   - Things that are pointed at have an `id` that says what they are.
   - Each part declares the fields of every kind of entry once, and `common.check` checks them all.
   - When data is messy, fix the data: code never works around it with special cases.
3. **Names, in Thai and English.**
   - A name is `th` and `en` (a shop, a unit, a tile, a wall, a step); a named thing that can carry a note adds an optional `note_th` and `note_en` (a section, a phase, a work section, an item on a drawing).
   - Thai and English always say the same thing. `common.check` makes each pair fill in the same `{…}` placeholders and give the same numbers, in any order — so a number is written in digits in both ("1-piece", not "one-piece"), in the same unit.
   - Thai and English are never joined by hand; the one exception is the title line in the template.
4. **One look for each shape**, from `common.py`: a heading is "Thai / English"; a note is Thai, with the English underneath.
5. **Parts don't know each other.**
   - No part's code imports another part's code; the parts meet only in `build.py`.
   - No data file holds a fact about another part. The phases name kinds of material in plain words ("ready-mix mortar"), never products, sizes or quantities, and never which tile goes where.
   - The only links are rule 6.
6. **The links between parts**, each handed over by `build.py`; nothing links the phases to anything.
   - **The room and the materials list.** The room names products on the materials list by id, for their names, sizes and IP ratings, and `room.py` checks every id; the tiles the room needs are set against the boxes on the materials list by the quantities check (see Checks).
   - **The labour, from the room and the materials list.** A labour line takes its quantity from the room's take-off (areas and lengths `room.py` works out), from a count of products on the materials list, or as a share of what products on it still cost, and shows those products' names from the list; `labour.py` checks every take-off name and product id. Factor F adds overhead, profit and interest to the lines priced from a book of bare rates (the Comptroller General's), and to no other line; the owner buys the materials, so it isn't put on them. The grand total adds what the materials still cost to the labour with its overhead.
7. **Every fact once.**
   - A product's name, detail and size are written only on its entry in `materials.toml`; its detail shows the size with `{w}`, `{w_cm}` and so on, and the room takes them from there.
   - What follows from the room is worked out in `room.py`, never typed: where each wall is, the column, door and lintel, the tile counts, the quantities labour is priced by.
   - Numbers come from order, never typed; things point at each other by id.
   - A note never repeats a fact held elsewhere, or a figure that can be worked out.
8. **Bad data stops the build; a design problem is never published** (see Checks).
9. **Tests never depend on today's numbers or wording.**
   - A test finds what it breaks by what it is, and works out the expected message from the real data and its labels.
   - Every check has a test; `mise run quote:test` lists them.
   - Measuring the drawings in Chromium is the slow part, so `mise run quote:test` (part of `mise run quote:check`, which `mise run root:publish` runs before pushing) does it only in the tests about drawings; `mise run quote:fuzz` runs every test with its drawings measured. `mise run root:ci` is `root:check-mise`, `quote:check`, then `quote:fuzz` — what GitHub runs. A test whose build must always measure its drawings is marked `drawn(…)`.
10. **Every figure from outside says where it came from and when.** A norm (`[[norm]]` in `room.toml`) gives its `standard`, `url` and the date it was `checked`; a price comes from its product's shop page (`shop`, `sku`) on `prices_date`; a product's IP rating from its shop page too; a labour rate from its rate book (`[[book]]` in `labour.toml`, with the day it was `checked`), with its item or note there and where: its `page` in the book's copy kept in `sources/` (`file`, with the page that publishes it, `published`, to fetch it again or find a newer edition — the comment above the book in `labour.toml` says how to take one in), or, for a book with no copy — a shop's service pages — its own page's `url`; Factor F (`[factor_f]`) from its table, with its `standard`, `url` and the day it was `checked`. When a source changes, the figure can be checked again; a norm without its source stops the build.
   - A value not yet known for real — still to be measured on site, or read off a product's label — is marked as assumed: its key goes in the entry's `assumed` list (`assumed = ["x", "y"]`). It is a stand-in until the real figure replaces it, and then it comes off the list.

## Checks

Every check is one of two kinds, and they never mix: a **data check** asks whether a data file is written correctly; a **design check** asks whether the bathroom it describes is well designed. Apart from both, the build warns of every assumed value (see Assumed values).

### Data checks

A data file written wrongly: a missing or misspelt field, an id that points at nothing, Thai without English. Fixing it means correcting the file.
- A data check lives in the part's own code (`phases.py`, `materials.py`, `room.py`, `labour.py`), or in `common.check` when every entry shares it; the template's two checks are in `build.py`.
- It raises `DataError`: the build stops with one English line naming the file and the problem, and nothing is written.

### Design checks

The judgement an architect and a builder bring — good building practice, sound architectural design and how it will look. Fixing a design problem means changing the design. There are three aspects, each in its own file:

- **The room** — `room_design_checks.py`, beside `room.toml` and `room.py`: setting out and clashes — every item set out where it belongs and fits, clear of the tile joints, not clashing with another item or sitting in an opening; clearances and heights — enough space in front of each fitting, clear of the door's swing when it opens in, the basin rim at its height; wet areas — every electrical item in the zones round the shower head with an IP rating recorded and high enough, the shower zone waterproofed high enough, the floor's wet side falling enough to the drain, and the drain on the wet (low) side of the step.
- **Quantities** — `materials_design_checks.py`, beside `materials.toml` and `materials.py`: the quantity take-off from the drawings set against the materials list — whether enough is ordered.
- **The drawings** — `drawing_design_checks.py`: how each drawing reads, measured in Chromium on the drawings as drawn — nothing runs off the edge of its drawing; no two words or tags are drawn over each other or closer than a clear gap; no line or fill runs through a label that needs clear ground (a wall name, a joint mark, a heading). The layout code places things so these hold — a tag or number moves the least it takes to clear what is already placed (`place` in `room_drawings.py`) — and the check proves it on every build.

The room and the drawings are told apart by what fixing a problem changes: a room problem changes what is constructed; a drawing problem changes only how the drawing is laid out or worded — nothing on site.

The phases and the labour have no design checks. Each design-checks file lists its checks at the top.

How a design problem is reported:
- A design check never raises `DataError`. It returns a design problem: a note for the architect, in Thai and English — where, what, the rule, what to do — worded by a label in the part's `[labels]`.
- `mise run quote:build` still writes the page and the PDF, with each problem in red under its drawing, and prints each one and the count.
- `mise run quote:check` (and so `mise run root:ci`) refuses any design problem, so neither `mise run root:publish` nor GitHub publishes it.

### Assumed values

A value marked as assumed (rule 10) is neither bad data nor a design problem: the design checks use it as written, so the room is checked as if it were true. `mise run quote:build`, `mise run quote:summary` and `mise run quote:check` print each one as `ASSUMED`, with where it is and its value, and the count — a warning: it doesn't stop `mise run quote:check`, `mise run root:ci` or publishing. The owner measures each one on site, the real figure replaces it, and its key comes off the `assumed` list; a design problem the real figure brings out then shows like any other.

### Placing a new check

Ask what fixing it would take:
- **Correcting the file** → a data check, in the part's own code (`phases.py`, `materials.py`, `room.py`, `labour.py`), or in `common.check` if every entry shares it.
- **Changing the room** — where something goes, its size, how it fits or looks, its waterproofing or fall → a room design check, in `room_design_checks.py`.
- **Ordering more, or ordering something different** → a quantities check, in `materials_design_checks.py`.
- **Changing only how a drawing is laid out or worded** — nothing on site → a drawing design check, in `drawing_design_checks.py`.

A design check never goes in a part's own code, and a data check never goes in a design-checks file. A value a design check holds the room to from outside — a clearance, a height, a fall — is a `[[norm]]` in `room.toml`, with its source (rule 10). For example:
- "An item names a product that isn't on the materials list": correct the id — a data check, in `room.py`.
- "The door is too wide to fit beside the column": a different door frame — a room design check, in `room_design_checks.py`.
- "Too few tile boxes for the tiles the room needs": order more — a quantities check, in `materials_design_checks.py`.
- "The door's swing runs off the floor plan": make the drawing bigger on that side — a drawing design check, in `drawing_design_checks.py`.

## Before a change is done

1. Check it against the rules: for 2, every entry of the kind you touched, not just the one; for 5 to 7, search the other files for what you touched; for 9, a new check gets a new test.
2. Run `mise run root:ci`: clean, 0 design problems — the same run GitHub makes.
3. Look at the PDF.
4. Commit locally.
5. Push to `main` only when the owner says so — he judges whether the PDF makes sense, and asks for a push before risky work so there is a safe copy to go back to — and only with `mise run root:publish`, which refuses unless you're on `main`, nothing is uncommitted and `mise run quote:check` passes. Then watch the GitHub build until it passes.
