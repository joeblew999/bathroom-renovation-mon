"""The working database: where the data is read and changed, between the seed files that are committed.

    python edit.py load            make .work/quote.db from the migrations and the seed files (refused if it holds unsaved
                                   changes; --discard throws them away — to redo a migration being written, say)
    python edit.py save [--alone]  check quote.db, then write each part's seed file with sqlite3 .dump --data-only;
                                   if anything fails, write nothing and say why. --alone lets through a text changed in one
                                   language only (a fix to a Thai typo, say) — each one is printed, to go in the commit message
    python edit.py migrate         run on quote.db each migration it hasn't had (then save writes the seed files in the new shape)
    python edit.py status          say whether quote.db and the seed files hold the same data (exit 1 if not)
    python edit.py sql "…"         run SQL on quote.db, as one transaction (any change waits for save); the functions below are there
    python edit.py show "…"        run a query on quote.db and print the rows (read the views: room_show_item …)
    python edit.py diff            how quote.db differs from the seed files, as SQL (sqldiff)
    python edit.py lint            sqlite3 .lint fkey-indexes on the seed files: every foreign key has an index

quote.db is never committed: the seed files are the data. Any SQLite tool can open quote.db too (sqlite3, a browser);
`save` checks everything before writing, so a tool that leaves foreign keys off can't save a broken link.

What save refuses, before it writes anything:
  - the seed files changed since load (a git pull, a checkout): saving would undo those changes
  - a schema that isn't the migrations' (a table changed by hand: schema changes are a new migration)
  - any problem: a broken link, a check view, the translation rules, a code the code doesn't know
  - a text changed in one language only (unless --alone)
and then it dumps to a folder beside the seed files, loads that back as a build would, checks it again, and only then
moves the five files into place, one after another (git shows a mix, if one is ever interrupted).

Inside the SQL (`sql`, or edit() below):
  new_id()                    a new random key (UUID v4), the same one each time it's called until next_id()
  next_id()                   start a new key (for the next new thing)
  pos_after(table, key)       a position just after that row, within its parent (between it and the next one)
  pos_first(table, parent)    the first position under that parent ('' for a table with no parent)
                              — if there's no room left between two rows, the parent's rows are spaced out again
Example — a new step after another, in Thai and English:
  INSERT INTO phases_step (id, pos, phase) SELECT new_id(), pos_after('phases_step', id), phase FROM phases_step WHERE id = '…';
  INSERT INTO phases_step_text (step, lang, text) VALUES (new_id(), 'th', '…'), (new_id(), 'en', '…');
"""
import hashlib, sqlite3, sys, tempfile, uuid
from pathlib import Path
from migrate import (DATA, MIGRATIONS, PARTS, REPO, STEP, changed_alone, connect, dump, extract, load, migrated,
                     parent_of, problems, run_file, schema_of, vocabulary)

WORK = REPO / ".work"                      # gitignored: the working database and what it was loaded from
WORKING = WORK / "quote.db"


def fingerprint(folder=DATA):
    """One hash of the seed files: what a load was made from. (A new migration is brought in by `migrate`; the schema
    check in save refuses a working database that hasn't had every migration.)"""
    h = hashlib.sha256()
    for f in [folder / f"{p}.sql" for p in PARTS]:
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def loaded_from(working):
    return working.with_suffix(".loaded")  # beside quote.db: the fingerprint of the seed files it was loaded from


def as_loaded(working):
    return working.with_name(working.stem + "-loaded.db")   # beside quote.db: the data as it was loaded (or last saved),
                                                             # what "changed in one language only" is judged against


def applied(working):
    return working.with_suffix(".migrations")   # beside quote.db: the migrations it has had, one name a line


def migrate_working(working=WORKING, migrations=None):
    """Run on quote.db, in order, each migration it hasn't had — each one transaction, links checked at its end, as D1
    runs them. Then `save` writes the seed files in the new shape. Returns the names run."""
    rec = applied(working)
    done = set(rec.read_text().split()) if rec.exists() else set()
    new = [f for f in sorted((migrations or MIGRATIONS).glob("*.sql")) if f.name not in done]
    db = connect(working)
    for f in new:
        run_file(db, f)
        done.add(f.name)
        rec.write_text("\n".join(sorted(done)) + "\n")
    return [f.name for f in new]


def tools(db):
    """The SQL functions an edit can use."""
    state = {"id": str(uuid.uuid4())}
    def new_id():
        return state["id"]
    def next_id():
        state["id"] = str(uuid.uuid4())
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


def run_sql(db, sql):
    """Run an edit as one transaction, links checked at its end (as D1 runs a file); on any error, nothing changes."""
    try:
        db.executescript(f"BEGIN; PRAGMA defer_foreign_keys = ON;\n{sql}\n;COMMIT;")
    except sqlite3.Error as e:
        if db.in_transaction:
            db.execute("ROLLBACK")
        return str(e)
    return None


_TAKE_OFF = []
def take_off():
    """room.py's take-offs (the trial reads them from today's code; at the switch, room.py's own constant)."""
    if not _TAKE_OFF:
        _TAKE_OFF.append(extract()[1])
    return _TAKE_OFF[0]


def check_and_dump(db, folder, alone=False, base=None, migrations=None):
    """Every check on db, and each text against the seed files (one language changed alone); if all pass, dump db to the
    files — through a folder beside them, loaded back and checked again before the files are moved into place.
    Returns (problems, one-language changes let through)."""
    if schema_of(db) != schema_of(migrated(migrations)):
        return ["the schema isn't the migrations': if there's a new migration, `migrate` first; a schema change by hand "
                "isn't saved — a schema change is a new migration"], []
    found = problems(db) + vocabulary(db, take_off())
    lone = changed_alone(base or load(folder, migrations), db)
    if not alone:
        found += lone
    if found:
        return found, []
    def again(t):                                           # the dump, loaded back as a build loads it, checked again
        try:
            back = load(t, migrations)
        except SystemExit as e:
            return [f"the dump doesn't load back: {e}"]
        with tempfile.TemporaryDirectory(dir=t.parent) as t2:
            same_again = dump(back, Path(t2)) == {p: (t / f"{p}.sql").read_text(encoding="utf-8").splitlines() for p in PARTS}
        return problems(back) + ([] if same_again else ["the dump, loaded back and dumped again, isn't the same"])
    late = dump(db, folder, before_swap=again)
    return (late, []) if isinstance(late, list) else ([], lone)


def edit(sql, folder=DATA, alone=False, migrations=None):
    """Apply `sql` to the data in `folder` and write the files only if every check passes. Returns the problems
    ([] = written). (The same as sql then save, without a working database.)"""
    base = load(folder, migrations)
    db = tools(load(folder, migrations))
    err = run_sql(db, sql)
    return [f"the SQL failed, so nothing changed: {err}"] if err else check_and_dump(db, folder, alone, base, migrations)[0]


def same(folder=DATA, working=WORKING):
    """Whether quote.db holds no unsaved change: the same data as when it was loaded (or last saved). A pull that changes
    the seed files is not a change in quote.db."""
    if not working.exists():
        return True
    with tempfile.TemporaryDirectory() as t:
        now = dump(connect(working), Path(t) / "now")
        if as_loaded(working).exists():
            then = dump(connect(as_loaded(working)), Path(t) / "then")
        else:
            then = {p: (folder / f"{p}.sql").read_text(encoding="utf-8").splitlines() for p in PARTS}
    return now == then


def files_moved(folder=DATA, working=WORKING):
    """Whether the seed files changed since quote.db was loaded from them (or last saved)."""
    rec = loaded_from(working)
    return not rec.exists() or rec.read_text().strip() != fingerprint(folder)


def load_working(folder=DATA, working=WORKING, migrations=None, discard=False):
    if working.exists() and not discard and not same(folder, working):
        return "quote.db holds unsaved changes: save them first, or `load --discard` to throw them away"
    working.parent.mkdir(parents=True, exist_ok=True)
    working.unlink(missing_ok=True)
    db = load(folder, migrations)
    for path in (working, as_loaded(working)):
        path.unlink(missing_ok=True)
        out = sqlite3.connect(path); db.backup(out); out.close()
    loaded_from(working).write_text(fingerprint(folder))
    applied(working).write_text("".join(f.name + "\n" for f in sorted((migrations or MIGRATIONS).glob("*.sql"))))
    return None


def take_in(source, folder=DATA, working=WORKING, migrations=None):
    """Make quote.db hold `source`'s data (D1's, from a pull), judged against the seed files: so `status` shows it as unsaved,
    `diff` shows what it changes, and `save` checks it like any other change before writing the seed files."""
    if working.exists() and not same(folder, working):
        return "quote.db holds unsaved changes: save them first, or `load --discard` to throw them away"
    working.parent.mkdir(parents=True, exist_ok=True)
    for path, db in ((working, source), (as_loaded(working), load(folder, migrations))):
        path.unlink(missing_ok=True)
        out = sqlite3.connect(path); db.backup(out); out.close()
    loaded_from(working).write_text(fingerprint(folder))
    applied(working).write_text("".join(f.name + "\n" for f in sorted((migrations or MIGRATIONS).glob("*.sql"))))
    return None


def save_working(folder=DATA, working=WORKING, alone=False, migrations=None):
    """(problems, one-language changes let through)."""
    if not working.exists():
        return ["there is no quote.db to save: `load` first"], []
    if files_moved(folder, working):
        return ["the seed files changed since quote.db was loaded (a git pull or checkout?): saving would undo that. "
                "Copy your changes out, `load` again, and make them again"], []
    db = tools(connect(working))
    found, lone = check_and_dump(db, folder, alone, connect(as_loaded(working)), migrations)
    if not found:
        loaded_from(working).write_text(fingerprint(folder))
        out = sqlite3.connect(as_loaded(working)); db.backup(out); out.close()
    return found, lone


def seed_db(folder, path):
    """The seed files loaded into a database file, for SQLite's own tools to open."""
    out = sqlite3.connect(path); load(folder).backup(out); out.close()
    return path


def diff(folder=DATA, working=WORKING):
    """sqldiff from the seed files to the working database: the SQL that would turn one into the other."""
    import shutil, subprocess
    with tempfile.TemporaryDirectory() as t:
        return subprocess.run([shutil.which("sqldiff"), "--primarykey", str(seed_db(folder, Path(t) / "seed.db")), str(working)],
                              capture_output=True, text=True, check=True).stdout


def lint(folder=DATA):
    """sqlite3's .lint fkey-indexes on the loaded data: the index each foreign key lacks (nothing = every one has one)."""
    import shutil, subprocess
    with tempfile.TemporaryDirectory() as t:
        return subprocess.run([shutil.which("sqlite3"), str(seed_db(folder, Path(t) / "seed.db")), ".lint fkey-indexes"],
                              capture_output=True, text=True, check=True).stdout


def open_working():
    if not WORKING.exists():
        sys.exit("There is no quote.db: run `load` first.")
    return tools(connect(WORKING))


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if cmd == "load":
        err = load_working(discard="--discard" in args)
        sys.exit(f"Not loaded: {err}") if err else print(f"Loaded {WORKING.relative_to(REPO)} from the migrations and seed files.")
    elif cmd == "save":
        found, lone = save_working(alone="--alone" in args)
        if found:
            print("Nothing written:"); [print("  ", p) for p in found]; sys.exit(1)
        for p in lone:
            print("  changed in one language only (say why in the commit message):", p)
        print("Saved: the seed files now hold quote.db, and every check passes.")
    elif cmd == "status":
        if not WORKING.exists():
            print("There is no quote.db (nothing unsaved)."); sys.exit(0)
        ok, moved = same(), files_moved()
        print("quote.db and the seed files hold the same data." if ok else "quote.db holds unsaved changes.")
        if moved:
            print("The seed files changed since quote.db was loaded: `load` again" + (" (after copying your changes out)." if not ok else "."))
        sys.exit(0 if ok else 1)
    elif cmd == "migrate":
        if not WORKING.exists():
            sys.exit("There is no quote.db: run `load` first.")
        ran = migrate_working()
        print(f"Ran {', '.join(ran)} on quote.db — `save` to check it and write the seed files." if ran else "quote.db has had every migration.")
    elif cmd == "diff":
        if not WORKING.exists():
            sys.exit("There is no quote.db: run `load` first.")
        out = diff()
        print(out if out else "quote.db holds exactly the seed files.")
    elif cmd == "lint":
        out = lint()
        print(out if out else "Every foreign key has an index (sqlite3 .lint fkey-indexes prints nothing).")
        sys.exit(1 if out else 0)
    elif cmd in ("sql", "show") and args:
        db = open_working()
        if cmd == "show":
            cur = db.execute(args[0])
            print(" | ".join(d[0] for d in cur.description))
            for row in cur.fetchall():
                print(" | ".join("" if v is None else str(v) for v in row))
        else:
            err = run_sql(db, args[0])
            sys.exit(f"Nothing changed: {err}") if err else print("Done in quote.db — `save` to check it and write the seed files.")
    else:
        sys.exit(__doc__)
