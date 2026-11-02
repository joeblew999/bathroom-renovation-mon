"""Trial: break a copy of the database loaded from the data files, one copy per break, and see each refused —
by the rule meant to refuse it. Then break the data files themselves, and compare two versions.
Each break finds what it breaks by what it is (README rule 9), never by today's names or numbers."""
import shutil, sqlite3, time
from migrate import DATA, changed_alone, load, problems

PRODUCT_WITH = lambda cond: f"(SELECT id FROM materials_product WHERE {cond} ORDER BY pos LIMIT 1)"
ITEM_WITH = lambda cond: f"(SELECT i.id FROM room_item i JOIN room_surface s ON s.id = i.surface WHERE {cond} ORDER BY s.pos, i.pos LIMIT 1)"
WALL_RECT_PRODUCT = ITEM_WITH("s.kind = 'wall' AND i.product IS NOT NULL AND i.id IN (SELECT item FROM room_item_rect)")
FLOOR_RECT = ITEM_WITH("s.kind = 'floor' AND i.id IN (SELECT item FROM room_item_rect)")
NAMED_ITEM = ITEM_WITH("i.product IS NULL")
A_WALL = "(SELECT surface FROM room_wall ORDER BY surface LIMIT 1)"

BREAKS = [  # (what, SQL, words the refusal must contain)
    # types and values
    ("text in a number column", "UPDATE room_room SET ceiling = 'high'", "cannot store TEXT value in REAL column"),
    ("a whole number that isn't", f"UPDATE materials_product SET per_box = 4.5 WHERE id = {PRODUCT_WITH('per_box IS NOT NULL')}",
     "cannot store REAL value in INTEGER"),
    ("a negative price", f"UPDATE materials_product SET price = -1 WHERE id = {PRODUCT_WITH('price IS NOT NULL')}", "a price is 0 or more"),
    ("an infinite size", "UPDATE room_room SET length = 1e999", "the room's length is more than 0"),
    ("a key that isn't 16 hex digits", "UPDATE phases_phase SET id = 'tile' WHERE pos = 10", "an id is 16 hex digits"),
    ("a 16-character key that isn't hex", "UPDATE phases_phase SET id = 'f-not-hex-at-all' WHERE pos = 10", "an id is 16 hex digits"),
    ("a key in capitals", "UPDATE phases_phase SET id = upper(id) WHERE pos = 10", "an id is 16 hex digits"),
    ("a date that isn't one", "UPDATE room_norm SET checked = 'yesterday'", "a norm's checked is a date"),
    ("a required value missing", "UPDATE materials_shop SET link = NULL", "NOT NULL constraint failed: materials_shop.link"),
    ("two items in one place on a wall", "UPDATE room_item SET pos = (SELECT min(pos) FROM room_item j WHERE j.surface = room_item.surface) "
     "WHERE id = (SELECT id FROM room_item WHERE surface = (SELECT surface FROM room_item GROUP BY surface HAVING count(*) > 1 LIMIT 1) "
     "ORDER BY pos DESC LIMIT 1)", "UNIQUE constraint failed: room_item.surface, room_item.pos"),
    # one-row tables, counts
    ("a second settings row", "INSERT INTO materials_setting VALUES (2, '2026-01-01', 'x', 1)", "the settings are one row"),
    ("no room row", "DELETE FROM room_room", "room_room has 0 rows, not 1"),
    ("no door", "DELETE FROM room_door", "room_door has 0 rows, not 1"),
    ("no labour settings", "DELETE FROM labour_setting", "labour_setting has 0 rows, not 1"),
    ("no Factor F", "DELETE FROM labour_factor_f", "labour_factor_f has 0 rows, not 1"),
    ("a fifth wall", "INSERT INTO room_surface (id, pos, kind, ref, tile) SELECT 'ffffffffffffffff', 99, 'wall', 'Z', tile FROM room_surface LIMIT 1",
     "there are 5 wall surfaces, not 4"),
    ("no phases", "DELETE FROM phases_step_text; DELETE FROM phases_step; DELETE FROM phases_phase_text; DELETE FROM phases_phase_note; DELETE FROM phases_phase",
     "phases_phase has no row"),
    # shapes (the review's D4, D5)
    ("a rect with no x", f"UPDATE room_item_rect SET x = NULL WHERE item = {WALL_RECT_PRODUCT}", "NOT NULL constraint failed: room_item_rect.x"),
    ("a step with no high side", "UPDATE room_item_step SET high = NULL", "NOT NULL constraint failed: room_item_step.high"),
    ("a floor rect with a height", f"UPDATE room_item_rect SET h = 10 WHERE item = {FLOOR_RECT}",
     "is a rect on the floor, which is seen from above, so it has no h"),
    ("an item with two shapes", f"INSERT INTO room_item_point (item, x, y) VALUES ({WALL_RECT_PRODUCT}, 1, 1)", "has 2 shapes, not 1"),
    ("an item with no shape", f"DELETE FROM room_item_rect WHERE item = {WALL_RECT_PRODUCT}", "has 0 shapes, not 1"),
    ("a step on a wall", f"UPDATE room_item SET surface = {A_WALL}, pos = 99990 WHERE id IN (SELECT item FROM room_item_step)", "which can't be on the wall"),
    ("an item with a product giving its own size", f"UPDATE room_item_rect SET w = 10 WHERE item = {WALL_RECT_PRODUCT}",
     "has a product, so it takes its size from it"),
    ("an item with a product and its own name", f"INSERT INTO room_item_name VALUES ({WALL_RECT_PRODUCT}, 'th', 'x')",
     "has a product and its own name"),
    ("an item with neither", f"DELETE FROM room_item_name WHERE item = {NAMED_ITEM}", "has neither a product nor a name"),
    ("a reference to a step that doesn't exist", "UPDATE phases_step_text SET text = text || ' {step:ffffffffffffffff}' WHERE rowid = "
     "(SELECT min(rowid) FROM phases_step_text)", "a reference to step 'ffffffffffffffff', which doesn't exist"),
    ("a reference left as an old id", "UPDATE phases_phase_note SET note = note || ' {phase:make_good}' WHERE rowid = "
     "(SELECT min(rowid) FROM phases_phase_note)", "a reference to phase make_good, which doesn't exist"),
    # assumed values (the review's D4)
    ("an assumed key that isn't one of its values", f"INSERT INTO room_item_assumed (item, key) VALUES ({WALL_RECT_PRODUCT}, 'colour')",
     "an item's assumed key is one of its values"),
    ("an assumed value that isn't there", f"INSERT INTO materials_product_assumed (product, key) VALUES ({PRODUCT_WITH('price IS NULL')}, 'price')",
     "marks price as assumed, but it has no price"),
    ("an assumed size on an item that takes its size from its product",
     f"INSERT INTO room_item_assumed (item, key) VALUES ({WALL_RECT_PRODUCT}, 'w')", "marks w as assumed, but it has no w"),
    ("an assumed n on a line with no n", "INSERT INTO labour_line_assumed (line, key) SELECT line, 'n' FROM labour_line_take_off LIMIT 1",
     "marks n as assumed, but it has no n"),
    # links
    ("a product that doesn't exist", f"UPDATE room_item SET product = 'ffffffffffffffff' WHERE id = {WALL_RECT_PRODUCT}",
     "room_item.product = 'ffffffffffffffff': no such materials_product"),
    ("a fitting on another wall", f"UPDATE room_item SET fitting = {FLOOR_RECT} WHERE fitting IS NOT NULL", "no such room_item"),
    ("a take-off room.py doesn't work out", "UPDATE labour_line_take_off SET take_off = 'roof_m2' WHERE rowid = 1", "no such room_take_off"),
    ("a counted product that doesn't exist", "UPDATE labour_line_count_product SET product = 'ffffffffffffffff' WHERE rowid = 1", "no such materials_product"),
    # materials rules
    ("a product with no line", f"DELETE FROM materials_line_note WHERE line IN (SELECT id FROM materials_line WHERE product = {PRODUCT_WITH('1')}); "
     f"DELETE FROM materials_line_by WHERE line IN (SELECT id FROM materials_line WHERE product = {PRODUCT_WITH('1')}); "
     f"DELETE FROM materials_line WHERE product = {PRODUCT_WITH('1')}", "has no line, so it isn't on the list"),
    ("a product to buy with no price", "UPDATE materials_product SET price = NULL, approx = 0 WHERE id IN (SELECT product FROM materials_line WHERE status = 'procure')",
     "so it needs a price"),
    ("a product to buy with no shop", "DELETE FROM materials_product_shop", "so it needs a shop and its code"),
    ("an IP rating on a product that isn't electrical", f"UPDATE materials_product SET ip = 'IPX4' WHERE id = {PRODUCT_WITH('electrical = 0')}",
     "only an electrical product has an IP rating"),
    # labour rules
    ("a line with 2 sources", "INSERT INTO labour_line_n (line, n) SELECT line, 3 FROM labour_line_take_off LIMIT 1", "2 sources, not 1"),
    ("a line with no source", "DELETE FROM labour_line_n WHERE rowid = (SELECT min(rowid) FROM labour_line_n)", "0 sources, not 1"),
    ("a take-off line priced by the set", "UPDATE labour_rate SET unit = (SELECT id FROM labour_unit WHERE measure = 'count') "
     "WHERE id = (SELECT rate FROM labour_line WHERE id = (SELECT line FROM labour_line_take_off LIMIT 1))", "but its quantity is"),
    ("a number of a share", "UPDATE labour_rate SET unit = (SELECT id FROM labour_unit WHERE measure = 'share') "
     "WHERE id = (SELECT rate FROM labour_line WHERE id = (SELECT line FROM labour_line_n LIMIT 1))", "so its rate can't be a share"),
    ("a rate from no book not marked assumed", "DELETE FROM labour_rate_assumed", "must be marked assumed"),
    ("a kept book's rate with a url", "UPDATE labour_rate SET url = 'https://x' WHERE book IN (SELECT id FROM labour_book WHERE file IS NOT NULL) AND rowid = "
     "(SELECT min(rowid) FROM labour_rate WHERE book IN (SELECT id FROM labour_book WHERE file IS NOT NULL))", "so it gives its page and no url"),
    ("Factor F below 1", "UPDATE labour_factor_f SET value = 0.9", "Factor F is 1 or more"),
    # translations
    ("Thai but no English", f"DELETE FROM materials_product_text WHERE lang = 'en' AND product = {PRODUCT_WITH('1')}", "only in th"),
    ("a step with no text", "DELETE FROM phases_step_text WHERE step = (SELECT id FROM phases_step ORDER BY pos LIMIT 1)", "has no text"),
    ("a note in one language", "DELETE FROM room_item_note WHERE lang = 'th' AND rowid = (SELECT min(rowid) FROM room_item_note WHERE lang = 'th')",
     "only in en"),
]

base = load()
print("real data:", len(problems(base)), "problems")
t0, ok = time.perf_counter(), 0
for what, sql, want in BREAKS:
    db = sqlite3.connect(":memory:"); base.backup(db)
    try:
        db.executescript(sql); found = problems(db)
    except sqlite3.Error as e:
        found = [str(e)]
    hit = any(want in f for f in found); ok += hit
    print(f"{'REFUSED' if hit else 'MISSED '}  {what}" + ("" if hit else f"\n          wanted {want!r}, got {found[:3]}"))
dt = time.perf_counter() - t0
print(f"\n{ok}/{len(BREAKS)} refused · {dt / len(BREAKS) * 1000:.1f} ms each (copy, break, every check)")

# ---------- the data files themselves: what the loader must refuse (each a copy of the files, one line changed)
FILE_BREAKS = [  # (what, file, change(lines) -> lines, words the refusal must contain)
    ("a statement that isn't an INSERT", "phases", lambda ls: ls + ["DROP VIEW check_room_rows;"], "not an INSERT into one of phases's tables"),
    ("an INSERT into another part's table", "phases", lambda ls: ls + [next(l for l in open(DATA / "room.data.sql") if "room_room" in l).strip()],
     "not an INSERT into one of phases's tables"),
    ("a misspelt column", "room", lambda ls: [l.replace("joint_clearance", "joint_clearence", 1) if "room_room" in l else l for l in ls],
     "has no column named joint_clearence"),
    ("two statements on one line", "phases", lambda ls: [ls[-1][:-1] + "); DELETE FROM phases_phase;"] + ls[:-1],
     "not an INSERT into one of phases's tables"),
]
fok = 0
for what, part, change, want in FILE_BREAKS:
    tmp = DATA.parent / "data-broken"
    shutil.rmtree(tmp, ignore_errors=True); shutil.copytree(DATA, tmp)
    f = tmp / f"{part}.data.sql"
    f.write_text("\n".join(change(f.read_text(encoding="utf-8").splitlines())) + "\n", encoding="utf-8")
    try:
        load(tmp); got = "loaded without complaint"
    except SystemExit as e:
        got = str(e)
    hit = want in got; fok += hit
    print(f"{'REFUSED' if hit else 'MISSED '}  file: {what}" + ("" if hit else f"\n          wanted {want!r}, got {got[:150]}"))

# ---------- inserting a step changes one line of the data files (positions leave gaps)
db = sqlite3.connect(":memory:"); base.backup(db)
db.execute("INSERT INTO phases_step (id, pos, phase) SELECT 'aaaaaaaaaaaaaaaa', (SELECT min(pos) FROM phases_step s WHERE s.phase = p.phase) + 5, "
           "p.phase FROM phases_step p ORDER BY p.rowid LIMIT 1")
from migrate import dump
tmp = DATA.parent / "data-insert"; dump(db, tmp)
before, after = (DATA / "phases.data.sql").read_text().splitlines(), (tmp / "phases.data.sql").read_text().splitlines()
changed = len(set(after) ^ set(before))
print(f"{'OK     ' if changed == 1 else 'MISSED '}  inserting a step between two others changes {changed} line(s) of phases.data.sql")

# ---------- English changed without its Thai (comparing two versions of the data)
db = sqlite3.connect(":memory:"); base.backup(db)
db.execute(f"UPDATE materials_product_text SET name = name || ' (new)' WHERE lang = 'en' AND product = {PRODUCT_WITH('1')}")
got = changed_alone(base, db)
print(f"{'REFUSED' if any('its en changed but not the other language' in g for g in got) else 'MISSED '}  English changed without its Thai")
db.execute(f"UPDATE materials_product_text SET name = name || ' (ใหม่)' WHERE lang = 'th' AND product = {PRODUCT_WITH('1')}")
print(f"{'OK     ' if not changed_alone(base, db) else 'MISSED '}  both languages changed together: accepted")
