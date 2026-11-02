"""The quote's data on Cloudflare D1 — the same commands for wrangler's local D1 and for the real one.

    python d1.py push  --local|--remote   apply the migrations D1 hasn't had (wrangler d1 migrations apply), then make its
                                          data exactly the seed files: every row deleted and the seed rows put in, as one file
    python d1.py check --local|--remote   run every check view on D1 itself, and compare its data with the seed files
    python d1.py show  --local|--remote "…"  run a query on D1 and print the rows (read the views: room_show_fitting …)
    python d1.py pull  --local|--remote   export D1 (wrangler d1 export) to .work/d1.sql and .work/d1.db — never committed —
                                          and show how it differs from the seed files (sqldiff)

The seed files stay the data: push sends them, pull only shows what D1 holds, for you to bring over by hand if it's right.
"""
import json, re, sqlite3, subprocess, sys, tempfile
from pathlib import Path
from migrate import DATA, MIGRATIONS, OUT, PARTS, REPO, cli, load, migrated, problems, schema_of

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "wrangler.toml"
WORK = REPO / ".work"
PLACEHOLDER = "00000000-0000-0000-0000-000000000000"
D1_COMPOUND = 5                             # the most terms D1 lets one compound SELECT have
WRANGLER_OWN = {"d1_migrations", "sqlite_sequence"}   # tables wrangler keeps for itself in D1 (and Cloudflare's own _cf_…)


def own(name):
    return name in WRANGLER_OWN or name.startswith("_cf_")
COUNTS_PER_QUERY = 50                       # tables counted in one query (one column each; D1 allows 100)


def wrangler(where, sub, *args):
    """wrangler d1 <sub> <the database> <args>, on the local copy or the real one."""
    name = re.search(r'database_name = "([^"]+)"', CONFIG.read_text())[1]
    cmd = ["wrangler", "d1", *sub.split(), name, *args, "--config", str(CONFIG), where]
    run = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, env={**__import__("os").environ, "CI": "1"})
    if run.returncode:
        sys.exit(f"ERROR: {' '.join(cmd[:4])} failed:\n{run.stdout[-2000:]}{run.stderr[-2000:]}")
    return run.stdout


def tables(db):
    """Every table of the data, children before their parents (the reverse of the order they're made in)."""
    return [t for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                                     "AND name <> 'd1_migrations' ORDER BY rowid DESC")]


def ready():
    """What push sends must be what git holds, and must pass every check — before anything is sent."""
    dirty = subprocess.run(["git", "status", "--porcelain", "--", str(DATA), str(MIGRATIONS)], cwd=REPO,
                           capture_output=True, text=True, check=True).stdout
    if dirty:
        sys.exit(f"ERROR: the seed files or migrations hold changes git doesn't: commit them first, so D1 gets what git has\n{dirty}")
    db = load()
    found = problems(db)
    if found:
        sys.exit("ERROR: the seed files don't pass the checks, so nothing was sent:\n  " + "\n  ".join(found))
    return db


def push(where):
    db = ready()
    wrangler(where, "migrations apply")
    with tempfile.NamedTemporaryFile("w", suffix=".sql", dir=OUT, delete=False, encoding="utf-8") as f:
        f.write("PRAGMA defer_foreign_keys = true;\n")
        f.writelines(f"DELETE FROM {t};\n" for t in tables(db))
        for part in PARTS:
            f.write((DATA / f"{part}.sql").read_text(encoding="utf-8"))
    try:
        wrangler(where, "execute", "--file", f.name, "--yes")
    finally:
        Path(f.name).unlink()
    print(f"D1 ({where[2:]}): migrations applied, and its data is now the seed files ({rows(db)} rows).")


def rows(db):
    return sum(db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables(db))


def query(where, sql):
    out = json.loads(wrangler(where, "execute", "--command", sql, "--json"))
    return out[0]["results"]


def check(where):
    """The check views, run by D1; and D1's row counts against the seed files'."""
    db = load()
    views = [v for (v,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'view' AND name GLOB '*_check_*' ORDER BY name")]
    theirs = sorted((r["type"], r["name"], r["sql"]) for r in query(where, "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL")
                    if not own(r["name"]) and not r["name"].startswith("sqlite_"))
    differ = sorted({f"{t} {n}" for t, n, _ in set(theirs) ^ set(schema_of(db))})
    found = [f"D1's schema isn't the migrations' ({', '.join(differ)}): a change no migration made, or a migration "
             "edited after D1 had it"] if differ else []
    for i in range(0, len(views), D1_COMPOUND):              # D1 allows 5 terms in one UNION
        sql = " UNION ALL ".join(f"SELECT '{v}' AS v, * FROM {v}" for v in views[i:i + D1_COMPOUND])
        found += [f"{r['v']}: {[x for k, x in r.items() if k != 'v'][0]}" for r in query(where, sql)]
    counts = {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables(db)}
    d1, names = {}, list(counts)
    for i in range(0, len(names), COUNTS_PER_QUERY):          # one row, a column per table (D1 allows 100 columns)
        d1.update(query(where, "SELECT " + ", ".join(f"(SELECT count(*) FROM {t}) AS {t}" for t in names[i:i + COUNTS_PER_QUERY]))[0])
    found += [f"{t}: D1 has {d1.get(t)} rows, the seed files {n}" for t, n in counts.items() if d1.get(t) != n]
    print(f"D1 ({where[2:]}): its schema, {len(views)} check views and {len(counts)} tables' row counts —", f"{len(found)} problems")
    for p in found:
        print("  ", p)
    return found


def pull(where):
    WORK.mkdir(exist_ok=True)
    sql, got = WORK / "d1.sql", WORK / "d1.db"
    db = load()
    wrangler(where, "export", "--output", str(sql))
    with tempfile.TemporaryDirectory() as t:
        whole = Path(t) / "export.db"                       # all D1 holds, wrangler's own table included
        subprocess.run([cli(), str(whole)], input=sql.read_text(encoding="utf-8"), text=True, check=True)
        exported = sqlite3.connect(whole)
        theirs = [r for r in schema_of(exported) if not own(r[1])]
        diff = "" if theirs == schema_of(db) else "D1's schema isn't the migrations': it has had a change no migration made\n"
        got.unlink(missing_ok=True)                         # the data alone, in the migrations' schema
        g = sqlite3.connect(got); migrated().backup(g)
        g.execute("ATTACH ? AS d1", (str(whole),))
        for table in reversed(tables(db)):
            g.execute(f"INSERT INTO {table} SELECT * FROM d1.{table}")
        g.commit(); g.execute("DETACH d1"); g.close()
        seed = Path(t) / "seed.db"
        s = sqlite3.connect(seed); db.backup(s); s.close()
        diff += subprocess.run([str(Path(cli()).parent / "sqldiff"), "--primarykey", str(seed), str(got)], capture_output=True, text=True, check=True).stdout
    print(f"D1 ({where[2:]}) exported to {sql.relative_to(REPO)} and {got.relative_to(REPO)} (never committed).")
    print("It holds exactly the seed files." if not diff else f"How it differs from the seed files (sqldiff):\n{diff}")
    return diff


if __name__ == "__main__":
    cmd, where = (sys.argv[1:3] + ["", ""])[:2]
    if cmd not in ("push", "check", "pull", "show") or where not in ("--local", "--remote") or (cmd == "show" and len(sys.argv) < 4):
        sys.exit(__doc__)
    if where == "--remote" and PLACEHOLDER in CONFIG.read_text():
        sys.exit("ERROR: there is no D1 database yet: make it (wrangler d1 create bathroom-quote) and put its id in etl/wrangler.toml")
    if cmd == "push":
        push(where)
    elif cmd == "show":
        got = query(where, sys.argv[3])
        if got:
            print(" | ".join(got[0]))
            for r in got:
                print(" | ".join("" if v is None else str(v) for v in r.values()))
    elif cmd == "check":
        sys.exit(1 if check(where) else 0)
    else:
        pull(where)
