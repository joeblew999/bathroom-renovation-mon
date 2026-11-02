"""Trial: break a copy of the database loaded from the data files, one copy per break, and see each refused —
by the rule meant to refuse it. Includes every case the first review found v1 let through."""
import sqlite3, time
from migrate import load, problems

ITEM = lambda name: f"(SELECT i.id FROM room_item i LEFT JOIN room_item_name n ON n.item = i.id AND n.lang = 'en' " \
                    f"LEFT JOIN materials_product_text p ON p.product = i.product AND p.lang = 'en' WHERE coalesce(n.name, p.name) = '{name}')"
WALL = lambda name: f"(SELECT wall FROM room_wall_text WHERE lang = 'en' AND name = '{name}')"
PRODUCT_WITH = lambda cond: f"(SELECT id FROM materials_product WHERE {cond} ORDER BY pos LIMIT 1)"

BREAKS = [  # (what, SQL, words the refusal must contain)
    # types and values
    ("text in a number column", "UPDATE room_room SET ceiling = 'high'", "cannot store TEXT value in REAL column"),
    ("a whole number that isn't", f"UPDATE materials_product SET per_box = 4.5 WHERE id = {PRODUCT_WITH('per_box IS NOT NULL')}",
     "cannot store REAL value in INTEGER"),
    ("a negative price", f"UPDATE materials_product SET price = -1 WHERE id = {PRODUCT_WITH('price IS NOT NULL')}", "a price is 0 or more"),
    ("an infinite size", "UPDATE room_room SET length = 1e999", "the room's length is more than 0"),
    ("a key that isn't 16 hex digits", "UPDATE phases_phase SET id = 'tile' WHERE pos = 1", "an id is 16 hex digits"),
    ("a date that isn't one", "UPDATE room_norm SET checked = 'yesterday'", "a norm's checked is a date"),
    ("a required value missing", "UPDATE materials_shop SET link = NULL", "NOT NULL constraint failed: materials_shop.link"),
    ("two things in one place in the order", "UPDATE room_item SET pos = 1 WHERE pos = 2", "UNIQUE constraint failed: room_item.pos"),
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
    ("a rect with no x", f"UPDATE room_item_rect SET x = NULL WHERE item = {ITEM('MOYA wall-hung basin')}", "NOT NULL constraint failed: room_item_rect.x"),
    ("a step with no high side", "UPDATE room_item_step SET high = NULL", "NOT NULL constraint failed: room_item_step.high"),
    ("a floor rect with a height", f"UPDATE room_item_rect SET h = 10 WHERE item = {ITEM('DEXZON floor drain grate')}",
     "is a rect on the floor, which is seen from above, so it has no h"),
    ("an item with two shapes", f"INSERT INTO room_item_point (item, x, y) VALUES ({ITEM('MOYA wall-hung basin')}, 1, 1)", "has 2 shapes, not 1"),
    ("an item with no shape", f"DELETE FROM room_item_rect WHERE item = {ITEM('MOYA wall-hung basin')}", "has 0 shapes, not 1"),
    ("a step on a wall", f"UPDATE room_item SET surface = {WALL('Main wall')} WHERE id IN (SELECT item FROM room_item_step)", "which can't be on the wall"),
    ("an item with a product giving its own size", f"UPDATE room_item_rect SET w = 10 WHERE item = {ITEM('MOYA wall-hung basin')}",
     "has a product, so it takes its size from it"),
    ("an item with a product and its own name", f"INSERT INTO room_item_name VALUES ({ITEM('MOYA wall-hung basin')}, 'th', 'x')",
     "has a product and its own name"),
    ("an item with neither", f"DELETE FROM room_item_name WHERE item = {ITEM('Floor step')}", "has neither a product nor a name"),
    # assumed values (the review's D4)
    ("an assumed key that isn't one of its values", f"INSERT INTO room_item_assumed (item, key) VALUES ({ITEM('MOYA wall-hung basin')}, 'colour')",
     "an item's assumed key is one of its values"),
    ("an assumed value that isn't there", f"INSERT INTO materials_product_assumed (product, key) VALUES ({PRODUCT_WITH('price IS NULL')}, 'price')",
     "marks price as assumed, but it has no price"),
    ("an assumed size on an item that takes its size from its product",
     f"INSERT INTO room_item_assumed (item, key) VALUES ({ITEM('MOYA wall-hung basin')}, 'w')", "marks w as assumed, but it has no w"),
    ("an assumed n on a line with no n", "INSERT INTO labour_line_assumed (line, key) SELECT line, 'n' FROM labour_line_take_off LIMIT 1",
     "marks n as assumed, but it has no n"),
    # links
    ("a product that doesn't exist", f"UPDATE room_item SET product = 'ffffffffffffffff' WHERE id = {ITEM('MOYA wall-hung basin')}",
     "room_item.product = 'ffffffffffffffff': no such materials_product"),
    ("a fitting on another wall", f"UPDATE room_item SET fitting = {ITEM('DEXZON floor drain grate')} WHERE fitting IS NOT NULL", "no such room_item"),
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
