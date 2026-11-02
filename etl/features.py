"""SQLite's analytical and structural features, on the quote's real data, run by the three engines the data meets —
Python's sqlite3 (the build), SQLite's own sqlite3 (the seed files) and wrangler's local D1 (Cloudflare) — with the
results required to be identical.

    python features.py      (after `python d1.py push --local`; it changes the local D1, which etl:d1 starts afresh)

A migration (0002, made here, never kept) adds to the products:
  - their face area (w × h, in m²) as a VIRTUAL generated column, with an index;
  - updated_at, and a trigger that stamps it when a product's price or size is updated.
Then the same changes are made on each engine — a price updated (the trigger fires), and a label written twice by an upsert
(INSERT … ON CONFLICT DO UPDATE: the second write updates the first, no error, still 2 rows) — and these are compared:

  window functions   a running total of the priced products, in list order, and each one's rank by price within its unit
  recursive CTE      the tree of items that serve other items (a tap serving a basin …), each with its root and depth
  generated column   the products over 0.1 m² by face area; a lookup by area uses the index
  upsert             the label written twice: its last text, once per language
  trigger            which products are stamped: only the one whose price was updated
  view               materials_show_line, the materials list as people read it

and the seed-file cycle holds: the migrated, changed data dumps (generated values left out), loads from nothing under the
new schema without the trigger firing (an INSERT is not an UPDATE: the stamps stay as they were), and dumps back identical.
INSERT … RETURNING, full-text search with the trigram tokenizer (Thai) and JSON were tried on 2 Nov 2026 (the plan, decision 21).
"""
import json, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path
from migrate import DATA, MIGRATIONS, cli, dump, load, problems, run_file
from d1 import query, wrangler

MIGRATION = """ALTER TABLE materials_product ADD COLUMN area_m2 REAL GENERATED ALWAYS AS (w * h / 1e6) VIRTUAL;
CREATE INDEX materials_product_area_m2 ON materials_product(area_m2);
ALTER TABLE materials_product ADD COLUMN updated_at INTEGER;
CREATE TRIGGER materials_product_stamp AFTER UPDATE OF price, w, h, d ON materials_product FOR EACH ROW
BEGIN UPDATE materials_product SET updated_at = unixepoch() WHERE id = NEW.id; END;
"""   # ADD COLUMN can add a VIRTUAL generated column (a STORED one needs the table rebuilt); the trigger fires on the
      # columns it names only, so its own UPDATE of updated_at can't set it off again

UPSERT = ("INSERT INTO materials_label (code, lang, text) VALUES ('upsert_test', 'th', '{th}'), ('upsert_test', 'en', '{en}') "
          "ON CONFLICT (code, lang) DO UPDATE SET text = excluded.text;")
CHANGES = ("UPDATE materials_product SET price = price + 1 WHERE pos = (SELECT min(pos) FROM materials_product WHERE price IS NOT NULL);\n"
           + UPSERT.format(th="ครั้งแรก", en="first") + "\n" + UPSERT.format(th="ครั้งที่ 2", en="second 2"))

QUERIES = {
    "window functions":
        "SELECT id, price, sum(price) OVER (ORDER BY pos) AS running_total, "
        "rank() OVER (PARTITION BY unit ORDER BY price DESC, pos) AS rank_in_unit "
        "FROM materials_product WHERE price IS NOT NULL ORDER BY pos",
    "recursive CTE":
        "WITH RECURSIVE tree(id, root, depth) AS ("
        "SELECT id, id, 0 FROM room_item WHERE fitting IS NULL AND id IN (SELECT fitting FROM room_item) "
        "UNION ALL SELECT i.id, t.root, t.depth + 1 FROM room_item i JOIN tree t ON i.fitting = t.id) "
        "SELECT id, root, depth FROM tree ORDER BY root, depth, id",
    "generated column":
        "SELECT id, area_m2 FROM materials_product WHERE area_m2 > 0.1 ORDER BY area_m2 DESC, pos",
    "upsert":
        "SELECT code, lang, text FROM materials_label WHERE code = 'upsert_test' ORDER BY lang",
    "trigger":
        "SELECT id FROM materials_product WHERE updated_at IS NOT NULL ORDER BY pos",
    "view":
        "SELECT * FROM materials_show_line",
}
EXPECT = {"upsert": 2, "trigger": 1}        # rows each must give: 2 languages, the last write; 1 product stamped
INDEX_USED = "EXPLAIN QUERY PLAN SELECT id FROM materials_product WHERE area_m2 > 0.1"
DIGITS = 9            # floats compared to this many decimal places (each engine prints them its own way)


def same_rows(rows, ordered=True):
    out = [{k: round(v, DIGITS) if isinstance(v, float) else v for k, v in r.items()} for r in rows]
    return out if ordered else sorted(out, key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False))


def main():
    out, ok = [], True
    def report(good, what):
        nonlocal ok
        ok &= bool(good)
        out.append(f"{'OK     ' if good else 'MISSED '}  {what}")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        mig = t / "migrations"; shutil.copytree(MIGRATIONS, mig)
        (mig / "0002_features.sql").write_text(MIGRATION, encoding="utf-8")
        db = load(DATA)                                                        # 1. Python's sqlite3: the data as loaded,
        run_file(db, mig / "0002_features.sql")                                #    then the migration, as db:migrate runs it
        db.row_factory = sqlite3.Row
        f = t / "quote.db"; c = sqlite3.connect(f); db.backup(c); c.close()    # 2. sqlite3, from the same start
        wrangler("--local", "execute", "--file", str(mig / "0002_features.sql"), "--yes")   # 3. local D1 (pushed already)
        db.executescript(CHANGES)
        subprocess.run([cli(), str(f)], input=CHANGES, text=True, check=True)
        changes = t / "changes.sql"; changes.write_text(CHANGES, encoding="utf-8")
        wrangler("--local", "execute", "--file", str(changes), "--yes")
        for what, sql in QUERIES.items():
            ordered = "ORDER BY" in sql
            py = same_rows([dict(r) for r in db.execute(sql)], ordered)
            run = subprocess.run([cli(), "-json", str(f), sql], capture_output=True, text=True, check=True).stdout
            tool = same_rows(json.loads(run) if run.strip() else [], ordered)
            d1 = same_rows(query("--local", sql), ordered)
            good = py == tool == d1 and len(py) == EXPECT.get(what, len(py)) > 0
            report(good, f"{what}: {len(py)} rows, " + ("identical on Python's sqlite3, sqlite3 and local D1" if good else
                                                         f"Python {len(py)}, sqlite3 {len(tool)}, D1 {len(d1)}"))
        found = problems(db)
        report(not found, "every check passes on the migrated, changed data: the trigger (on UPDATE, its own part's table) is allowed"
               + (f" — but {found[:3]}" if found else ""))
        plan = " ".join(r[3] for r in db.execute(INDEX_USED))
        report("USING INDEX materials_product_area_m2" in plan, f"generated column: a lookup by area uses its index ({plan})")
        stamps = [tuple(r) for r in db.execute("SELECT id, updated_at FROM materials_product ORDER BY pos")]
        after = dump(db, t / "after")                                          # the changed data, saved and loaded again
        back = load(t / "after", mig)
        report(dump(back, t / "again") == after and [tuple(r) for r in back.execute("SELECT id, updated_at FROM materials_product ORDER BY pos")] == stamps,
               "seed-file cycle: the migrated, changed data dumps (no generated value in it), loads from nothing under the new "
               "schema without the trigger firing (the stamp kept), and dumps back identical")
    print("\n".join(out))
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
