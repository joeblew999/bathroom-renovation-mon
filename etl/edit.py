"""Change the data: the one way a change gets into the SQL data files.

    python edit.py "<SQL>"        apply the SQL to a database built from the data files, check everything, and write
                                  the data files — or, if any check fails, write nothing and say why
    python edit.py --show "<SQL>" just run a query (read the views: show_room_item, show_labour_line …) — nothing changes

The database is built from the files, used, and thrown away: the files are the data. Inside the SQL:
  new_id()                    a new random key, the same one each time it's called in this edit until next_id()
  next_id()                   start a new key (for the next new thing)
  pos_after(table, key)       a position just after that row, within its parent (between it and the next one);
  pos_first(table, parent)    … the first position under that parent ('' for a table with no parent);
                              if there is no room left between two rows, the parent's rows are spaced out again
Example — a new step after another, with its Thai and English:
  INSERT INTO phases_step (id, pos, phase) SELECT new_id(), pos_after('phases_step', id), phase FROM phases_step WHERE id = '…';
  INSERT INTO phases_step_text (step, lang, text) VALUES (new_id(), 'th', '…'), (new_id(), 'en', '…');
"""
import secrets, sqlite3, sys
from migrate import DATA, STEP, dump, load, parent_of, problems, changed_alone


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

    def respace(table, where, args, key):
        rows = [r for (r,) in db.execute(f"SELECT {key} FROM {table} {where} ORDER BY pos", args)]
        db.execute(f"UPDATE {table} SET pos = -pos {where}", args)                 # out of the way of the unique rule
        for i, r in enumerate(rows, 1):
            db.execute(f"UPDATE {table} SET pos = ? WHERE {key} = ?", (i * STEP, r))

    def key_of(table):
        pk = [c[1] for c in db.execute(f"PRAGMA table_info({table})") if c[5]]
        return pk[0] if len(pk) == 1 else "rowid"

    def pos_after(table, k):
        key = key_of(table)
        parent = parent_of(db, table)
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


def edit(sql, folder=DATA):
    """Apply `sql` to the data in `folder`; write the files only if every check passes. Returns the problems ([] = written)."""
    before = load(folder)
    db = load(folder)
    tools(db)
    db.executescript(sql)
    found = problems(db) + changed_alone(before, db)
    if not found:
        dump(db, folder)
    return found


if __name__ == "__main__":
    if sys.argv[1:2] == ["--show"]:
        db = load()
        cur = db.execute(sys.argv[2])
        cols = [d[0] for d in cur.description]
        print(" | ".join(cols))
        for row in cur.fetchall():
            print(" | ".join("" if v is None else str(v) for v in row))
    else:
        found = edit(sys.argv[1])
        if found:
            print("Nothing written:"); [print("  ", p) for p in found]; sys.exit(1)
        print("Written: the data files now hold the change, and every check passes.")
