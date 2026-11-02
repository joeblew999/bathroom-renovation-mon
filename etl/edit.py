"""The working database: where the data is read and changed, between the part files that are committed.

    python edit.py load       build out/etl/quote.db from the part files (refused if quote.db holds unsaved changes)
    python edit.py save       check quote.db (every rule and check, and English changed with its Thai), then write each
                              part's file with sqlite3 .dump — or, if anything fails, write nothing and say why
    python edit.py status     say whether quote.db and the part files hold the same data (exit 1 if not)
    python edit.py sql "…"    run SQL on quote.db (any change waits for save); the functions below are there
    python edit.py show "…"   run a query on quote.db and print the rows (read the views: room_show_item …)

quote.db is never committed: the part files are the data. Any SQLite tool can open quote.db too (sqlite3, a browser);
`save` checks everything before writing, so a tool that leaves foreign keys off can't save a broken link.

Inside the SQL (`sql`, or edit() below):
  new_id()                    a new random key, the same one each time it's called until next_id()
  next_id()                   start a new key (for the next new thing)
  pos_after(table, key)       a position just after that row, within its parent (between it and the next one)
  pos_first(table, parent)    the first position under that parent ('' for a table with no parent)
                              — if there's no room left between two rows, the parent's rows are spaced out again
Example — a new step after another, in Thai and English:
  INSERT INTO phases_step (id, pos, phase) SELECT new_id(), pos_after('phases_step', id), phase FROM phases_step WHERE id = '…';
  INSERT INTO phases_step_text (step, lang, text) VALUES (new_id(), 'th', '…'), (new_id(), 'en', '…');
"""
import secrets, sqlite3, sys
from migrate import DATA, STEP, changed_alone, dump, load, parent_of, problems

WORKING = DATA.parent / "quote.db"


def tools(db):
    """The SQL functions an edit can use."""
    state = {"id": secrets.token_hex(8)}
    def new_id():
        return state["id"]
    def next_id():
        state["id"] = secrets.token_hex(8)
        return state["id"]

    def siblings(table, parent_value):
        """The rows a position is unique among: those with the same parent, or the whole table."""
        parent = parent_of(db, table)
        return (parent, f"WHERE {parent[0]} IS ?", [parent_value]) if parent else (None, "", [])

    def key_of(table):
        pk = [c[1] for c in db.execute(f"PRAGMA table_info({table})") if c[5]]
        return pk[0] if len(pk) == 1 else "rowid"

    def respace(table, where, args, key):
        rows = [r for (r,) in db.execute(f"SELECT {key} FROM {table} {where} ORDER BY pos", args)]
        db.execute(f"UPDATE {table} SET pos = -pos {where}", args)                 # out of the way of the unique rule
        for i, r in enumerate(rows, 1):
            db.execute(f"UPDATE {table} SET pos = ? WHERE {key} = ?", (i * STEP, r))

    def pos_after(table, k):
        key, parent = key_of(table), parent_of(db, table)
        pv = db.execute(f"SELECT {parent[0]} FROM {table} WHERE {key} = ?", (k,)).fetchone()[0] if parent else None
        _, where, args = siblings(table, pv)
        here = db.execute(f"SELECT pos FROM {table} WHERE {key} = ?", (k,)).fetchone()[0]
        nxt = db.execute(f"SELECT min(pos) FROM {table} {where + (' AND' if where else 'WHERE')} pos > ?", args + [here]).fetchone()[0]
        if nxt is None:
            return here + STEP
        if nxt - here < 2:                                   # no room: space the parent's rows out again
            respace(table, where, args, key)
            return pos_after(table, k)
        return (here + nxt) // 2

    def pos_first(table, pv):
        _, where, args = siblings(table, pv or None)
        first = db.execute(f"SELECT min(pos) FROM {table} {where}", args).fetchone()[0]
        if first is None:
            return STEP
        if first < 2:
            respace(table, where, args, key_of(table))
            return pos_first(table, pv)
        return first // 2

    db.create_function("new_id", 0, new_id)
    db.create_function("next_id", 0, next_id)
    db.create_function("pos_after", 2, pos_after)
    db.create_function("pos_first", 2, pos_first)
    return db


def check_and_dump(db, folder):
    """Every check on db, and English changed with its Thai against the files; if all pass, dump db to the files."""
    found = problems(db) + changed_alone(load(folder), db)
    if not found:
        dump(db, folder)
    return found


def edit(sql, folder=DATA):
    """Apply `sql` to the data in `folder` and write the files only if every check passes. Returns the problems
    ([] = written). (The same as sql then save, without a working database.)"""
    db = tools(load(folder))
    db.executescript(sql)
    return check_and_dump(db, folder)


def same(folder=DATA, working=WORKING):
    """Whether the working database holds exactly what the part files hold."""
    if not working.exists():
        return True
    db = sqlite3.connect(working)
    with __import__("tempfile").TemporaryDirectory() as t:
        from pathlib import Path
        now = dump(db, Path(t))
    return all(now[p] == (folder / f"{p}.sql").read_text(encoding="utf-8").splitlines() for p in now)


def load_working(folder=DATA, working=WORKING):
    if not same(folder, working):
        return "quote.db holds changes that aren't in the part files: save them first (or delete quote.db to throw them away)"
    working.unlink(missing_ok=True)
    out = sqlite3.connect(working); load(folder).backup(out); out.close()
    return None


def save_working(folder=DATA, working=WORKING):
    if not working.exists():
        return ["there is no quote.db to save: load it first"]
    return check_and_dump(sqlite3.connect(working), folder)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "load":
        err = load_working()
        sys.exit(f"Not loaded: {err}") if err else print(f"Loaded {WORKING} from the part files.")
    elif cmd == "save":
        found = save_working()
        if found:
            print("Nothing written:"); [print("  ", p) for p in found]; sys.exit(1)
        print("Saved: the part files now hold quote.db, and every check passes.")
    elif cmd == "status":
        ok = same()
        print("quote.db and the part files hold the same data." if ok else "quote.db holds unsaved changes.")
        sys.exit(0 if ok else 1)
    elif cmd in ("sql", "show"):
        db = tools(sqlite3.connect(WORKING))
        cur = db.execute(sys.argv[2]) if cmd == "show" else db.executescript(sys.argv[2])
        if cmd == "show":
            print(" | ".join(d[0] for d in cur.description))
            for row in cur.fetchall():
                print(" | ".join("" if v is None else str(v) for v in row))
        else:
            db.commit(); print("Done in quote.db — `save` to check it and write the part files.")
    else:
        sys.exit(__doc__)
