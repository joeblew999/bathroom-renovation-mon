"""Break the data on purpose and see each break refused by the rule meant to refuse it:
  1. breaks made on a copy of the database loaded from the data files (one copy each);
  2. breaks made in the data files themselves (what the loader must refuse);
  3. an edit through etl/edit.py (inserting a step changes 3 lines and nothing else);
  4. English changed without its Thai, comparing two versions;
  5. a part reading another part's tables (SQLite's authorizer) — none may: build.py hands over what a part needs;
  6. the working database's guards: load won't overwrite unsaved changes; save won't write a broken change, a schema
     change, a change in one language (unless --alone), or over seed files that changed since load; re-spacing positions.
Each break finds what it breaks by what it is (README rule 9) — never by today's names, numbers, positions or rows."""
import re, shutil, sqlite3, time
from migrate import DATA, changed_alone, connect, load, problems, reading, vocabulary
from edit import edit, load_working, same, save_working, take_off, tools

FAKE = "ffffffff-ffff-4fff-bfff-ffffffffffff"     # a key in the right shape that names nothing

FIRST = lambda table, order="pos": f"(SELECT id FROM {table} ORDER BY {order} LIMIT 1)"
PRODUCT_WITH = lambda cond: f"(SELECT id FROM materials_product WHERE {cond} ORDER BY pos LIMIT 1)"
ITEM_WITH = lambda cond: f"(SELECT i.id FROM room_item i JOIN room_surface s ON s.id = i.surface WHERE {cond} ORDER BY s.pos, i.pos LIMIT 1)"
WALL_RECT_PRODUCT = ITEM_WITH("s.kind = 'wall' AND i.product IS NOT NULL AND i.id IN (SELECT item FROM room_item_rect)")
FLOOR_RECT = ITEM_WITH("s.kind = 'floor' AND i.id IN (SELECT item FROM room_item_rect)")
NAMED_ITEM = ITEM_WITH("i.product IS NULL")
A_WALL = "(SELECT surface FROM room_wall ORDER BY surface LIMIT 1)"
FIRST_PHASE = FIRST("phases_phase")
A_TAKE_OFF_LINE = "(SELECT line FROM labour_line_take_off ORDER BY line LIMIT 1)"
AN_N_LINE = "(SELECT line FROM labour_line_n ORDER BY line LIMIT 1)"
FIRST_REF = "(SELECT step, n FROM phases_step_ref ORDER BY step, n LIMIT 1)"
A_LABEL = "(SELECT code FROM materials_label ORDER BY code LIMIT 1)"
LENGTH_PRODUCT = "(SELECT p.id FROM materials_product p JOIN materials_unit u ON u.id = p.unit WHERE u.measure = 'length' ORDER BY p.pos LIMIT 1)"

BREAKS = [  # (what, SQL, words the refusal must contain)
    # ---- types and values
    ("text in a number column", "UPDATE room_room SET ceiling = 'high'", "cannot store TEXT value in REAL column"),
    ("a whole number that isn't", f"UPDATE materials_product SET per_box = 4.5 WHERE id = {PRODUCT_WITH('per_box IS NOT NULL')}",
     "cannot store REAL value in INTEGER"),
    ("a negative price", f"UPDATE materials_product SET price = -1 WHERE id = {PRODUCT_WITH('price IS NOT NULL')}", "a price is 0 or more"),
    ("an infinite size", "UPDATE room_room SET length = 1e999", "the room's length is more than 0"),
    ("a key that isn't a UUID", f"UPDATE phases_phase SET id = 'tile' WHERE id = {FIRST_PHASE}", "an id is a UUID"),
    ("a UUID-shaped key that isn't hex", f"UPDATE phases_phase SET id = 'zzzzzzzz-zzzz-4zzz-8zzz-zzzzzzzzzzzz' WHERE id = {FIRST_PHASE}", "an id is a UUID"),
    ("a key in capitals", f"UPDATE phases_phase SET id = upper(id) WHERE id = {FIRST_PHASE}", "an id is a UUID"),
    ("an empty value outside the texts", "UPDATE materials_shop SET link = ''", "link isn't empty"),
    ("a table that belongs to no part", "CREATE TABLE schedule_task (id TEXT PRIMARY KEY) STRICT", "belongs to no part"),
    ("a trigger on INSERT", "CREATE TRIGGER materials_product_new AFTER INSERT ON materials_product BEGIN "
     "UPDATE materials_product SET price = 0 WHERE id = NEW.id; END", "a trigger fires on UPDATE only"),
    ("a trigger on DELETE", "CREATE TRIGGER materials_product_gone AFTER DELETE ON materials_product BEGIN "
     "DELETE FROM materials_line WHERE product = OLD.id; END", "a trigger fires on UPDATE only"),
    ("a trigger changing another part's table", "CREATE TRIGGER materials_product_room AFTER UPDATE OF price ON materials_product BEGIN "
     "UPDATE room_room SET ceiling = ceiling; END", "changes room_room, another part's table"),
    ("a line break in a text", f"UPDATE materials_product_text SET name = name || char(10) || 'x' WHERE product = {PRODUCT_WITH('1')}",
     "with a line break or tab"),
    ("a sku that doesn't look like its shop's", "UPDATE materials_product_shop SET sku = 'not a code' WHERE rowid = (SELECT min(rowid) FROM materials_product_shop)",
     "doesn't look like its shop's codes"),
    ("a placeholder a product's text can't fill", f"UPDATE materials_product_text SET detail = detail || ' {{nonsense}}' WHERE product = {PRODUCT_WITH('1')}",
     "uses {nonsense}"),
    ("a tile product with no width", "UPDATE materials_product SET w = NULL WHERE id = (SELECT product FROM room_tile ORDER BY pos LIMIT 1)",
     "needs w, h and per_box for the tile count"),
    ("a wall's assumed key that isn't one of its values", f"INSERT INTO room_wall_assumed (wall, key, how) VALUES ({A_WALL}, 'colour', 'x')",
     "a wall's assumed key is one of its values"),
    ("a step referring to itself", "UPDATE phases_step_ref SET to_phase = NULL, to_step = step WHERE rowid = (SELECT min(rowid) FROM phases_step_ref)",
     "a step doesn't refer to itself"),
    # ---- the check views no other break reaches
    ("no language", "DELETE FROM common_language", "there is no language"),
    ("no shop", "DELETE FROM materials_product_shop; DELETE FROM materials_shop_text; DELETE FROM materials_shop", "materials_shop has no row"),
    ("a line brought by the trade that doesn't say who", "DELETE FROM materials_line_by", "so it says who brings it"),
    ("the drain on a wall", f"UPDATE room_floor SET drain = {WALL_RECT_PRODUCT}", "is not on the floor"),
    ("a floor item serving a fitting", f"UPDATE room_item SET fitting = {WALL_RECT_PRODUCT} WHERE id = {FLOOR_RECT}", "which only a wall item does"),
    ("a wall with items but no elevation", "UPDATE room_wall SET elevation = 0 WHERE surface IN (SELECT surface FROM room_item)", "has items but no elevation"),
    ("no tile", "DELETE FROM room_tile_text; DELETE FROM room_tile", "there is no tile"),
    ("an assumed wall value with an empty note on how to find it",
     f"INSERT INTO room_wall_assumed (wall, key, how) VALUES ({A_WALL}, 'waterproofing', '')", "how isn't empty"),
    ("a wall's row on the floor's surface", "UPDATE room_wall SET surface = (SELECT id FROM room_surface WHERE kind = 'floor') "
     "WHERE surface = (SELECT surface FROM room_wall ORDER BY surface LIMIT 1)", "a wall row is on a surface that is the floor"),
    ("a loop of fittings (A serves B, B serves A)", "UPDATE room_item SET fitting = (SELECT id FROM room_item j WHERE j.fitting = room_item.id "
     "ORDER BY j.pos LIMIT 1) WHERE id = (SELECT fitting FROM room_item WHERE fitting IS NOT NULL ORDER BY surface, pos LIMIT 1)",
     "serves a chain of fittings that comes back to it"),
    ("an item serving itself", f"UPDATE room_item SET fitting = id WHERE id = {WALL_RECT_PRODUCT}", "an item doesn't serve itself"),
    ("a date that isn't one", "UPDATE room_norm SET checked = 'yesterday'", "a norm's checked is a date"),
    ("a required value missing", "UPDATE materials_shop SET link = NULL", "NOT NULL constraint failed: materials_shop.link"),
    ("an empty name", f"UPDATE room_wall_text SET name = '' WHERE wall = {A_WALL} AND lang = 'en'", "name isn't empty"),
    ("two items in one place on a wall", "UPDATE room_item SET pos = (SELECT min(pos) FROM room_item j WHERE j.surface = room_item.surface) "
     "WHERE id = (SELECT id FROM room_item WHERE surface = (SELECT surface FROM room_item GROUP BY surface HAVING count(*) > 1 "
     "ORDER BY surface LIMIT 1) ORDER BY pos DESC LIMIT 1)", "UNIQUE constraint failed: room_item.surface, room_item.pos"),
    # ---- one-row tables, counts
    ("a second settings row", "INSERT INTO materials_setting VALUES (2, '2026-01-01', 'x', 1)", "the settings are one row"),
    ("no room row", "DELETE FROM room_room", "room_room has 0 rows, not 1"),
    ("no door", "DELETE FROM room_door", "room_door has 0 rows, not 1"),
    ("no labour settings", "DELETE FROM labour_setting", "labour_setting has 0 rows, not 1"),
    ("no Factor F", "DELETE FROM labour_factor_f", "labour_factor_f has 0 rows, not 1"),
    ("a fifth wall", f"INSERT INTO room_surface (id, pos, kind, ref, tile) SELECT '{FAKE}', (SELECT max(pos) + 10 FROM room_surface), "
     "'wall', 'Z', tile FROM room_surface ORDER BY pos LIMIT 1", "there are 5 wall surfaces, not 4"),
    ("no walls at all", "DELETE FROM room_wall; DELETE FROM room_surface WHERE kind = 'wall'", "there are 0 wall surfaces, not 4"),
    ("no phases", "DELETE FROM phases_step_ref; DELETE FROM phases_phase_note_ref; DELETE FROM phases_step_text; DELETE FROM phases_step; "
     "DELETE FROM phases_phase_text; DELETE FROM phases_phase_note; DELETE FROM phases_phase", "phases_phase has no row"),
    # ---- shapes
    ("a rect with no x", f"UPDATE room_item_rect SET x = NULL WHERE item = {WALL_RECT_PRODUCT}", "NOT NULL constraint failed: room_item_rect.x"),
    ("a step with no high side", "UPDATE room_item_step SET high = NULL", "NOT NULL constraint failed: room_item_step.high"),
    ("a floor rect with a height", f"UPDATE room_item_rect SET h = 10 WHERE item = {FLOOR_RECT}",
     "is a rect on the floor, which is seen from above, so it has no h"),
    ("an item with two shapes", f"INSERT INTO room_item_point (item, x, y) VALUES ({WALL_RECT_PRODUCT}, 1, 1)", "has 2 shapes, not 1"),
    ("an item with no shape", f"DELETE FROM room_item_rect WHERE item = {WALL_RECT_PRODUCT}", "has 0 shapes, not 1"),
    ("a step on a wall", f"UPDATE room_item SET surface = {A_WALL}, pos = (SELECT max(pos) + 10 FROM room_item) WHERE id IN "
     "(SELECT item FROM room_item_step)", "which can't be on the wall"),
    ("an item with a product giving its own size", f"UPDATE room_item_rect SET w = 10 WHERE item = {WALL_RECT_PRODUCT}",
     "has a product, so it takes its size from it"),
    ("an item with a product and its own name", f"INSERT INTO room_item_name VALUES ({WALL_RECT_PRODUCT}, 'th', 'x')",
     "has a product and its own name"),
    ("an item with neither", f"DELETE FROM room_item_name WHERE item = {NAMED_ITEM}", "has neither a product nor a name"),
    # ---- the product the room needs in each slot
    ("the door naming a product that isn't a door frame", "UPDATE room_door SET product = (SELECT product FROM room_tile ORDER BY pos LIMIT 1)",
     "the door names a product that isn't a door frame"),
    ("a tile naming a product that isn't a tile", "UPDATE materials_product SET kind = NULL WHERE id = (SELECT product FROM room_tile ORDER BY pos LIMIT 1)",
     "names a product that isn't a tile"),
    # ---- references in the scope of works
    ("a gap with no reference", f"DELETE FROM phases_step_ref WHERE (step, n) = {FIRST_REF}", "but references"),
    ("a reference with no gap", "INSERT INTO phases_step_ref (step, n, to_phase) SELECT s.id, 99, " + FIRST_PHASE +
     " FROM phases_step s ORDER BY s.phase, s.pos LIMIT 1", "but references"),
    ("a reference to a phase that doesn't exist", f"UPDATE phases_step_ref SET to_step = NULL, to_phase = '{FAKE}' "
     f"WHERE (step, n) = {FIRST_REF}", "no such phases_phase"),
    ("a reference to a step and a phase at once", f"UPDATE phases_step_ref SET to_step = step, to_phase = {FIRST_PHASE} WHERE (step, n) = {FIRST_REF}",
     "a reference points at a step or a phase, one of the two"),
    ("a reference written into the text", "UPDATE phases_step_text SET text = text || ' {step:clear_mark}' WHERE (step, lang) = "
     "(SELECT step, lang FROM phases_step_text ORDER BY step, lang LIMIT 1)", "a reference written into the text"),
    # ---- assumed values
    ("an assumed key that isn't one of its values", f"INSERT INTO room_item_assumed (item, key, how) VALUES ({WALL_RECT_PRODUCT}, 'colour', 'x')",
     "an item's assumed key is one of its values"),
    ("an assumed value with no note on how to find it", "UPDATE room_item_assumed SET how = NULL", "NOT NULL constraint failed: room_item_assumed.how"),
    ("an assumed value that isn't there", f"INSERT INTO materials_product_assumed (product, key, how) VALUES ({PRODUCT_WITH('price IS NULL')}, 'price', 'x')",
     "marks price as assumed, but it has no price"),
    ("an assumed size on an item that takes its size from its product",
     f"INSERT INTO room_item_assumed (item, key, how) VALUES ({WALL_RECT_PRODUCT}, 'w', 'x')", "marks w as assumed, but it has no w"),
    ("an assumed n on a line with no n", f"INSERT INTO labour_line_assumed (line, key, how) VALUES ({A_TAKE_OFF_LINE}, 'n', 'x')",
     "marks n as assumed, but it has no n"),
    # ---- links
    ("a product that doesn't exist", f"UPDATE room_item SET product = '{FAKE}' WHERE id = {WALL_RECT_PRODUCT}",
     f"room_item.product = '{FAKE}': no such materials_product"),
    ("a fitting on another wall", f"UPDATE room_item SET fitting = {FLOOR_RECT} WHERE fitting IS NOT NULL", "no such room_item"),
    ("a take-off room.py doesn't work out", f"UPDATE labour_line_take_off SET take_off = 'roof_m2' WHERE line = {A_TAKE_OFF_LINE}",
     "labour_line_take_off.take_off = roof_m2: no such room_take_off"),
    ("a counted product that doesn't exist", f"UPDATE labour_line_count_product SET product = '{FAKE}' WHERE (line, pos) = "
     "(SELECT line, pos FROM labour_line_count_product ORDER BY line, pos LIMIT 1)", f"labour_line_count_product.product = '{FAKE}'"),
    # ---- materials rules
    ("a product with no line", f"DELETE FROM materials_line_note WHERE line IN (SELECT id FROM materials_line WHERE product = {PRODUCT_WITH('1')}); "
     f"DELETE FROM materials_line_by WHERE line IN (SELECT id FROM materials_line WHERE product = {PRODUCT_WITH('1')}); "
     f"DELETE FROM materials_line WHERE product = {PRODUCT_WITH('1')}", "has no line, so it isn't on the list"),
    ("a product to buy with no price", "UPDATE materials_product SET price = NULL, approx = 0 WHERE id IN (SELECT product FROM materials_line l "
     "JOIN materials_status s ON s.code = l.status WHERE s.to_buy)", "so it needs a price"),
    ("a product to buy with no shop", "DELETE FROM materials_product_shop", "so it needs a shop and its code"),
    ("an IP rating on a product that isn't electrical", f"UPDATE materials_product SET ip = 'IPX4' WHERE id = {PRODUCT_WITH('electrical = 0')}",
     "only an electrical product has an IP rating"),
    ("a unit with no English plural", f"DELETE FROM materials_unit_plural WHERE unit = {FIRST('materials_unit')}", "has no English plural"),
    # ---- labour rules
    ("a line with 2 sources", f"INSERT INTO labour_line_n (line, n) VALUES ({A_TAKE_OFF_LINE}, 3)", "2 sources, not 1"),
    ("a line with no source", f"DELETE FROM labour_line_n WHERE line = {AN_N_LINE}", "0 sources, not 1"),
    ("a take-off line priced by the set", "UPDATE labour_rate SET unit = (SELECT id FROM labour_unit WHERE measure = 'count') "
     f"WHERE id = (SELECT rate FROM labour_line WHERE id = {A_TAKE_OFF_LINE})", "but its quantity is"),
    ("a number of a share", "UPDATE labour_rate SET unit = (SELECT id FROM labour_unit WHERE measure = 'share') "
     f"WHERE id = (SELECT rate FROM labour_line WHERE id = {AN_N_LINE})", "so its rate can't be a share"),
    ("a count of products bought by length and by count together",
     f"INSERT INTO labour_line_count_product (line, pos, product) SELECT c.line, (SELECT max(pos) + 10 FROM labour_line_count_product), {LENGTH_PRODUCT} "
     "FROM labour_line_count c WHERE c.line NOT IN (SELECT cp.line FROM labour_line_count_product cp JOIN materials_product p ON p.id = cp.product "
     "JOIN materials_unit u ON u.id = p.unit WHERE u.measure = 'length') ORDER BY c.line LIMIT 1", "bought by length and by count together"),
    ("a rate from no book not marked assumed", "DELETE FROM labour_rate_assumed", "must be marked assumed"),
    ("a kept book's rate with a url", "UPDATE labour_rate SET url = 'https://x' WHERE id = (SELECT id FROM labour_rate WHERE book IN "
     "(SELECT id FROM labour_book WHERE file IS NOT NULL) ORDER BY pos LIMIT 1)", "so it gives its page and no url"),
    ("Factor F below 1", "UPDATE labour_factor_f SET value = 0.9", "Factor F is 1 or more"),
    # ---- translations
    ("Thai but no English", f"DELETE FROM materials_product_text WHERE lang = 'en' AND product = {PRODUCT_WITH('1')}", "only in th"),
    ("a step with no text", "DELETE FROM phases_step_text WHERE step = (SELECT id FROM phases_step ORDER BY phase, pos LIMIT 1)", "has no text"),
    ("a note in one language", "DELETE FROM room_item_note WHERE lang = 'th' AND item = (SELECT item FROM room_item_note ORDER BY item LIMIT 1)",
     "only in en"),
    ("a label in one language", f"DELETE FROM materials_label WHERE lang = 'en' AND code = {A_LABEL}", "only in th"),
    ("a number in the English but not the Thai", f"UPDATE materials_product_text SET name = name || ' 3' WHERE lang = 'en' AND product = {PRODUCT_WITH('1')}",
     "have different numbers"),
    ("a placeholder in the Thai but not the English", f"UPDATE materials_product_text SET detail = detail || ' {{w}}' WHERE lang = 'th' AND product = {PRODUCT_WITH('1')}",
     "have different placeholders"),
    ("a brace left open", "UPDATE phases_step_text SET text = text || ' {' WHERE step = (SELECT id FROM phases_step ORDER BY phase, pos LIMIT 1)",
     "a brace that opens or closes nothing"),
    # ---- the codes the code is written against
    ("a label the code doesn't know", "INSERT INTO materials_label (code, lang, text) VALUES ('nobody_uses_this', 'th', 'x'), ('nobody_uses_this', 'en', 'x')",
     "label nobody_uses_this is in the data but the code doesn't know it"),
    ("a label the code needs, gone", f"DELETE FROM materials_label WHERE code = {A_LABEL}", "is used by the code but isn't in the data"),
]

base = load()
print("real data:", len(problems(base)), "problems")
total = ok = 0
VIEWS = [v for (v,) in base.execute("SELECT name FROM sqlite_master WHERE type = 'view' AND name GLOB '*_check_*'")]
fired = set()                                      # the check views some break makes speak


def copy():
    """A copy of the real database with D1's limits, and foreign keys off — as any SQLite tool may leave them — so a
    broken link reaches the checks, which must name it."""
    db = connect(); base.backup(db); db.execute("PRAGMA foreign_keys = OFF"); return db


t0 = time.perf_counter()
for what, sql, want in BREAKS:
    db = copy()
    try:
        db.executescript(sql); found = problems(db) + vocabulary(db, take_off())
        fired.update(v for v in VIEWS if db.execute(f"SELECT 1 FROM {v} LIMIT 1").fetchone())
    except sqlite3.Error as e:
        found = [str(e)]
    hit = any(want in f for f in found); ok += hit; total += 1
    print(f"{'REFUSED' if hit else 'MISSED '}  {what}" + ("" if hit else f"\n          wanted {want!r}, got {found[:3]}"))
dt = time.perf_counter() - t0
print(f"  ({len(BREAKS)} database breaks, {dt / len(BREAKS) * 1000:.1f} ms each: copy, break, every check)")
for v in sorted(set(VIEWS) - fired):
    total += 1
    print(f"MISSED   check view {v}: no break makes it speak")
ok += len(fired); total += len(fired)
print(f"OK       every check view speaks in some break ({len(fired)} of {len(VIEWS)})")

# ---------- 1b. every named rule in the schema: set the columns it reads, on one real row, to wrong values (or to the
# row's own key, for a rule against linking to itself) until SQLite refuses with that rule's name — or a break above
# expects it by name. A rule nothing breaks is a rule with no test.
def named_rules(db):
    for t, sql in db.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table'").fetchall():
        cols = [c[1] for c in db.execute(f"PRAGMA table_info({t})")]
        for m in re.finditer(r'CONSTRAINT "([^"]+)" CHECK \(', sql):
            i, depth = m.end(), 1
            while depth:
                depth += {"(": 1, ")": -1}.get(sql[i], 0); i += 1
            yield t, m[1], [c for c in cols if re.search(rf"\b{c}\b", sql[m.end():i - 1])]
WRONG = [None, -1, 0, 0.5, 2, 99, 1e999, -1e999, "", "x", "zzz", "2026-13-45", "IPX", 1, "door_frame"]
expected = {w for _, _, w in BREAKS}
untested = []
for t, rule, used in named_rules(base):
    if rule in expected:
        continue
    tries = [(c, "?", v) for c in used for v in WRONG] + [(c, other, None) for c in used for other in used if other != c]
    info = list(base.execute(f"PRAGMA table_info({t})"))
    empty = not base.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone()
    for col, value, v in tries:
        db = copy()
        try:
            if empty:                                  # a table with no row today: a new row, plain elsewhere, wrong in col
                plain = {"TEXT": "'en'" , "INTEGER": "1", "REAL": "1.0"}
                vals = [value if c[1] == col else plain[c[2]] for c in info]
                db.execute(f"INSERT INTO {t} VALUES ({', '.join(vals)})", (v,) if value == "?" else ())
            else:
                db.execute(f"UPDATE {t} SET {col} = {value} WHERE rowid = (SELECT min(rowid) FROM {t})", (v,) if value == "?" else ())
        except sqlite3.Error as e:
            if rule in str(e):
                break
    else:
        untested.append(f"{t}: {rule!r}")
rules = sum(1 for _ in named_rules(base))
for u in untested:
    print(f"MISSED   rule {u}: nothing breaks it")
ok += rules - len(untested); total += rules
print(f"OK       every named rule refuses a wrong value by its name ({rules - len(untested)} of {rules})\n")

# ---------- 2. the data files themselves
A_ROOM_LINE = lambda: next(l for l in open(DATA / "room.sql") if l.startswith("INSERT INTO room_room ")).strip()
NOT_DUMP = "not a row of plain values for one of phases's tables"
FILE_BREAKS = [  # (what, file, change(lines) -> lines, words the refusal must contain)
    ("a statement that isn't in a dump", "phases", lambda ls: ls + ["DROP VIEW room_check_rows;"], NOT_DUMP),
    ("a trigger", "phases", lambda ls: ls + ["CREATE TRIGGER phases_t AFTER INSERT ON phases_phase BEGIN DELETE FROM phases_phase; END;"], NOT_DUMP),
    ("another part's table created here", "phases", lambda ls: ls + ["CREATE TABLE room_extra (x TEXT);"], NOT_DUMP),
    ("an INSERT into another part's table", "phases", lambda ls: ls + [A_ROOM_LINE()], NOT_DUMP),
    ("an INSERT that reads other tables", "phases", lambda ls: ls + ["INSERT INTO phases_symbol SELECT id, id FROM room_item;"], NOT_DUMP),
    ("a value that is a query", "phases", lambda ls: ls + ["INSERT INTO phases_symbol VALUES('x',(SELECT 1));"], NOT_DUMP),
    ("an upsert that overwrites a row", "phases", lambda ls: ls + ["INSERT INTO phases_symbol VALUES('number','x') ON CONFLICT(code) DO UPDATE SET value = 'x';"],
     NOT_DUMP),
    ("two INSERTs on one line", "phases", lambda ls: ls + ["INSERT INTO phases_symbol VALUES('a','1'); INSERT INTO phases_symbol VALUES('b','2');"],
     "two rows on one line"),
    ("a row with a value too many", "room", lambda ls: [l.replace(");", ",1);", 1) if l.startswith("INSERT INTO room_room ") else l for l in ls],
     "values were supplied"),
]
for what, part, change, want in FILE_BREAKS:
    tmp = DATA.parent / "data-broken"
    shutil.rmtree(tmp, ignore_errors=True); shutil.copytree(DATA, tmp)
    f = tmp / f"{part}.sql"
    f.write_text("\n".join(change(f.read_text(encoding="utf-8").splitlines())) + "\n", encoding="utf-8")
    try:
        load(tmp); got = "loaded without complaint"
    except SystemExit as e:
        got = str(e)
    hit = want in got; ok += hit; total += 1
    print(f"{'REFUSED' if hit else 'MISSED '}  file: {what}" + ("" if hit else f"\n          wanted {want!r}, got {got[:150]}"))

# ---------- 3. an edit: a new step between two others, in both languages — 3 lines added, none changed, every check passing
tmp = DATA.parent / "data-edit"
shutil.rmtree(tmp, ignore_errors=True); shutil.copytree(DATA, tmp)
step = load(tmp).execute("SELECT id FROM phases_step ORDER BY phase, pos LIMIT 1").fetchone()[0]
before = set((tmp / "phases.sql").read_text().splitlines())
found = edit(f"INSERT INTO phases_step (id, pos, phase) SELECT new_id(), pos_after('phases_step', id), phase FROM phases_step WHERE id = '{step}'; "
             "INSERT INTO phases_step_text (step, lang, text) VALUES (new_id(), 'th', 'ทดสอบ'), (new_id(), 'en', 'A test step');", tmp)
after = set((tmp / "phases.sql").read_text().splitlines())
good = not found and len(after - before) == 3 and not before - after
ok += good; total += 1
print(f"{'OK     ' if good else 'MISSED '}  edit: a step inserted between two others adds {len(after - before)} lines, changes "
      f"{len(before - after)}, problems {found}")
half = edit(f"INSERT INTO phases_step (id, pos, phase) SELECT new_id(), pos_after('phases_step', id), phase FROM phases_step WHERE id = '{step}'; "
            "INSERT INTO phases_step_text (step, lang, text) VALUES (new_id(), 'th', 'ทดสอบ');", tmp)
hit = any("only in th" in p for p in half) and set((tmp / "phases.sql").read_text().splitlines()) == after
ok += hit; total += 1
print(f"{'REFUSED' if hit else 'MISSED '}  edit: a step in Thai only — refused, and the files are untouched")

# ---------- 4. one language changed without the other, comparing two versions — each text on its own
def changed(sql):
    db = sqlite3.connect(":memory:"); base.backup(db); db.executescript(sql)
    return changed_alone(base, db)
P = PRODUCT_WITH('1')
for what, sql, refused in (
        ("a product's English name changed without its Thai", f"UPDATE materials_product_text SET name = name || ' (new)' WHERE lang = 'en' AND product = {P}", True),
        ("a label's English changed without its Thai", f"UPDATE materials_label SET text = text || ' (new)' WHERE lang = 'en' AND code = {A_LABEL}", True),
        ("the Thai name and the English detail changed (each text alone)",
         f"UPDATE materials_product_text SET name = name || ' (ใหม่)' WHERE lang = 'th' AND product = {P}; "
         f"UPDATE materials_product_text SET detail = detail || ' (new)' WHERE lang = 'en' AND product = {P}", True),
        ("a product's name changed in both languages", f"UPDATE materials_product_text SET name = name || ' (x)' WHERE product = {P}", False)):
    got = bool([g for g in changed(sql) if "changed but not the other language" in g])
    hit = got == refused; ok += hit; total += 1
    print(f"{'OK     ' if hit else 'MISSED '}  {what}: {'refused' if got else 'accepted'}")

# ---------- 5. a part's code reads only its own tables — build.py hands over what one part needs from another (README rules 5, 6)
for part, sql, allowed in (("room", "SELECT count(*) FROM room_item", True), ("room", "SELECT count(*) FROM materials_product", False),
                           ("labour", "SELECT count(*) FROM labour_rate", True), ("labour", "SELECT count(*) FROM room_take_off", False),
                           ("phases", "SELECT count(*) FROM materials_product", False), ("materials", "SELECT count(*) FROM room_item", False),
                           ("phases", "SELECT count(*) FROM room_show_item", False),          # another part's table, read through a view
                           ("room", "SELECT count(*) FROM room_show_item", False)):           # its own view, which reads the materials list
    db = sqlite3.connect(":memory:"); base.backup(db)
    reading(db, part)
    try:
        db.execute(sql).fetchone(); got, why = True, ""
    except sqlite3.DatabaseError as e:
        got, why = False, str(e)
    hit = got == allowed and (allowed or "not authorized" in why or "prohibited" in why); ok += hit; total += 1
    print(f"{'OK     ' if hit else 'MISSED '}  {part}: {sql[21:]}: {'allowed' if got else 'refused (' + why + ')'}")

# ---------- 6. the working database's guards
tmp = DATA.parent / "data-working"; working = tmp / "quote.db"
shutil.rmtree(tmp, ignore_errors=True); shutil.copytree(DATA, tmp)
files = lambda: {f.name: f.read_text() for f in tmp.glob("*.sql")}
def fresh():
    for f in tmp.glob("quote*"):
        f.unlink()
    assert load_working(tmp, working) is None
    w = sqlite3.connect(working); return w, w.execute("SELECT id FROM materials_product ORDER BY pos LIMIT 1").fetchone()[0]
checks = []
w, product = fresh()
w.execute("UPDATE materials_product_text SET name = name || ' X' WHERE lang = 'en' AND product = ?", (product,)); w.commit()
before = files()
checks += [("status sees the unsaved change", not same(tmp, working)),
           ("load refuses to overwrite it", load_working(tmp, working) is not None),
           ("save refuses English changed without its Thai, and writes nothing",
            any("changed but not the other language" in x for x in save_working(tmp, working)[0]) and before == files())]
found, lone = save_working(tmp, working, alone=True)
checks += [("save --alone writes it, and names it", not found and len(lone) == 1 and before != files())]
w.execute("UPDATE materials_product_text SET name = name || ' Y' WHERE product = ?", (product,)); w.commit()
before = files()
checks += [("save writes both languages changed together", save_working(tmp, working) == ([], []) and before != files()),
           ("after save, the database and the files hold the same", same(tmp, working))]
# a tool with foreign keys off (any SQLite tool) leaves a link broken: save refuses it
w.execute("PRAGMA foreign_keys = OFF"); w.execute("UPDATE room_item SET product = ? WHERE product IS NOT NULL", (FAKE,)); w.commit()
before = files()
checks += [("save refuses a link broken by a tool with foreign keys off", any("no such materials_product" in x for x in save_working(tmp, working)[0]) and before == files())]
w, product = fresh()
w.execute("CREATE TABLE room_extra (x TEXT) STRICT"); w.commit()
checks += [("save refuses a schema changed by hand", any("schema isn't the migrations'" in x for x in save_working(tmp, working)[0]))]
w, product = fresh()
w.execute("UPDATE materials_product SET price = price + 1 WHERE id = ?", (product,)); w.commit()
step_line = next(l for l in (tmp / "phases.sql").read_text().splitlines() if l.startswith("INSERT INTO phases_symbol"))
(tmp / "phases.sql").write_text((tmp / "phases.sql").read_text().replace(step_line + "\n", "", 1) + step_line + "\n")   # as a pull would change it
before = files()
checks += [("save refuses after the seed files changed since load (a pull)",
            any("changed since quote.db was loaded" in x for x in save_working(tmp, working)[0]) and before == files())]
# re-spacing: insert steps between the same two until no room is left; the positions stay unique and in order, and save passes
w, product = fresh(); w.close()
db = tools(__import__("migrate").connect(working))
first, second = db.execute("SELECT id FROM phases_step WHERE phase = (SELECT phase FROM phases_step ORDER BY phase, pos LIMIT 1) ORDER BY pos LIMIT 2").fetchall()
order = [first[0]]
for n in range(6):                                  # 10 → 5 → 2 → 1: room runs out on the 4th, and the phase is spaced out again
    db.execute("SELECT next_id()").fetchone()
    db.execute("INSERT INTO phases_step (id, pos, phase) SELECT new_id(), pos_after('phases_step', ?), phase FROM phases_step WHERE id = ?", (first[0], first[0]))
    new = db.execute("SELECT new_id()").fetchone()[0]
    db.execute("INSERT INTO phases_step_text (step, lang, text) VALUES (?, 'th', ?), (?, 'en', ?)", (new, f"ทดสอบ {n}", new, f"test {n}"))
    order.insert(1, new)
got = [r for (r,) in db.execute("SELECT id FROM phases_step WHERE phase = (SELECT phase FROM phases_step WHERE id = ?) ORDER BY pos", (first[0],))]
checks += [("re-spacing: 6 steps put after one step, each in front of the last, in order", got[:7] == order and got[7] == second[0]),
           ("re-spacing: and save writes them", save_working(tmp, working) == ([], []))]
# a design change: a new migration (a column added, and filled from the data) — migrate, save, and the files load from nothing
from migrate import MIGRATIONS, load as load_files
from edit import migrate_working
mig = tmp / "migrations"; shutil.copytree(MIGRATIONS, mig)
for f in tmp.glob("quote*"):
    f.unlink()
assert load_working(tmp, working, mig) is None
(mig / "0002_product_has_lead_time.sql").write_text(
    "ALTER TABLE materials_product ADD COLUMN lead_days INTEGER CONSTRAINT \"lead_days is 0 or more\" CHECK (lead_days >= 0);\n"
    "UPDATE materials_product SET lead_days = 7 WHERE price IS NOT NULL;\n", encoding="utf-8")
refused = any("`migrate` first" in x for x in save_working(tmp, working, migrations=mig)[0])
ran = migrate_working(working, mig)
saved = save_working(tmp, working, migrations=mig)
again = load_files(tmp, mig)
filled = again.execute("SELECT count(*) FROM materials_product WHERE lead_days = 7").fetchone()[0]
checks += [("a new migration: save refuses until it's run", refused),
           ("a new migration: migrate runs it on quote.db, save writes the seed files in its shape, and they load from nothing",
            # on a load from nothing the migration runs on empty tables, so the 7s can only have come from the seed files
            ran == ["0002_product_has_lead_time.sql"] and saved == ([], []) and filled > 0),
           ("a new migration: migrate again runs nothing", migrate_working(working, mig) == [])]
(mig / "0003_a_setting_row.sql").write_text("INSERT INTO phases_symbol VALUES ('extra', 'x');\n", encoding="utf-8")
try:
    load_files(tmp, mig); rows_refused = ""
except SystemExit as e:
    rows_refused = str(e)
checks += [("a migration that puts rows in a table is refused, by name", "0003_a_setting_row.sql puts rows in phases_symbol" in rows_refused)]
(mig / "0003_a_setting_row.sql").unlink()
# a pull changes the seed files, with nothing changed in quote.db: nothing is unsaved, and load takes the new files
for f in tmp.glob("quote*"):
    f.unlink()
load_working(tmp, working, mig)
pulled = edit("UPDATE materials_product SET price = price + 1 WHERE pos = (SELECT min(pos) FROM materials_product)", tmp, migrations=mig) == []
checks += [("after a pull, with nothing changed in quote.db, status is clean", pulled and same(tmp, working)),
           ("after a pull, load takes the new seed files", load_working(tmp, working, mig) is None and same(tmp, working))]
w = sqlite3.connect(working); w.execute("UPDATE materials_product SET price = price + 1 WHERE pos = (SELECT min(pos) FROM materials_product)"); w.commit(); w.close()
checks += [("load refuses unsaved changes", load_working(tmp, working, mig) is not None),
           ("load --discard throws them away", load_working(tmp, working, mig, discard=True) is None and same(tmp, working))]
for what, good in checks:
    ok += good; total += 1
    print(f"{'OK     ' if good else 'MISSED '}  working database: {what}")
shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{ok}/{total} as they should be")
