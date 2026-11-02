"""SQLite's analytical and structural features, on the quote's real data, run by the three engines the data meets —
Python's sqlite3 (the build), SQLite's own sqlite3 (the seed files) and wrangler's local D1 (Cloudflare) — with the
results required to be identical.

    python features.py      (after `python d1.py push --local`; it changes the local D1, which etl:d1 starts afresh)

  window functions   a running total of the priced products, in list order, and each one's rank by price within its unit
  recursive CTE      the tree of items that serve other items (a tap serving a basin …), each with its root and depth
  generated column   a migration adds a product's face area (w × h, in m²) as a VIRTUAL generated column with an index:
                     a lookup by area uses the index; the seed files hold no generated value (.dump --data-only leaves
                     it out), so they load unchanged under the new schema and dump back identical
INSERT … RETURNING, full-text search with the trigram tokenizer (Thai) and JSON were tried on 2 Nov 2026 (the plan, decision 21).
"""
import json, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path
from migrate import DATA, MIGRATIONS, PARTS, cli, dump, load
from d1 import query, wrangler

GENERATED = """ALTER TABLE materials_product ADD COLUMN area_m2 REAL GENERATED ALWAYS AS (w * h / 1e6) VIRTUAL;
CREATE INDEX materials_product_area_m2 ON materials_product(area_m2);
"""   # ADD COLUMN can add a VIRTUAL generated column; a STORED one needs the table rebuilt

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
}
INDEX_USED = "EXPLAIN QUERY PLAN SELECT id FROM materials_product WHERE area_m2 > 0.1"
DIGITS = 9            # floats compared to this many decimal places (each engine prints them its own way)


def same_rows(rows):
    return [{k: round(v, DIGITS) if isinstance(v, float) else v for k, v in r.items()} for r in rows]


def main():
    out, ok = [], True
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        mig = t / "migrations"; shutil.copytree(MIGRATIONS, mig)
        (mig / "0002_product_face_area.sql").write_text(GENERATED, encoding="utf-8")
        db = load(DATA, mig)                                           # 1. Python's sqlite3, as the build loads it
        db.row_factory = sqlite3.Row
        f = t / "quote.db"; c = sqlite3.connect(f); db.backup(c); c.close()
        again = dump(db, t / "again")
        seeds_same = again == {p: (DATA / f"{p}.sql").read_text(encoding="utf-8").splitlines() for p in PARTS}
        plan = " ".join(r[3] for r in db.execute(INDEX_USED))
        wrangler("--local", "execute", "--file", str(mig / "0002_product_face_area.sql"), "--yes")   # 3. local D1
        for what, sql in QUERIES.items():
            py = same_rows([dict(r) for r in db.execute(sql)])
            run = subprocess.run([cli(), "-json", str(f), sql], capture_output=True, text=True, check=True).stdout   # 2. sqlite3
            tool = same_rows(json.loads(run) if run.strip() else [])
            d1 = same_rows(query("--local", sql))
            good = py == tool == d1 and len(py) > 0
            ok &= good
            out.append(f"{'OK     ' if good else 'DIFFERS'}  {what}: {len(py)} rows, "
                       + ("identical on Python's sqlite3, sqlite3 and local D1" if good else f"Python {len(py)}, sqlite3 {len(tool)}, D1 {len(d1)}"))
        good = "USING INDEX materials_product_area_m2" in plan
        ok &= good
        out.append(f"{'OK     ' if good else 'MISSED '}  generated column: a lookup by area uses its index ({plan})")
        ok &= seeds_same
        out.append(f"{'OK     ' if seeds_same else 'MISSED '}  generated column: the seed files load under the new schema and dump back identical")
    print("\n".join(out))
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
