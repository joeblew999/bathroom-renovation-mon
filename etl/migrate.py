"""Trial: the TOML → SQL migration (ETL), run as often as the design changes.

    python migrate.py        writes data/<part>.data.sql, then loads schema/ + data/ into SQLite and checks it

  Extract    read the four TOML files, after today's code has checked them (so nothing it would refuse moves)
  Transform  reshape them into the design in schema/ — every difference between the TOML's shape and the
             design is here, and only here
  Load       write one INSERT per line per data file (the dump layout), then load the schema and those files
             into a fresh SQLite database and run every check

Keys: an entity's key is worked out from its id in the TOML (the first 16 hex digits of a SHA-256 of its kind and
id), so running this again gives the same keys and the data files don't change. Rows made after the switch get
SQLite's random keys instead. Changes nothing in the repo.
"""
import hashlib, re, sqlite3, sys, tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCHEMA, DATA = HERE / "schema", REPO / "out" / "etl" / "data"
PARTS = ("common", "materials", "room", "labour", "phases")          # load order: what is linked to comes first
LANGS = ("th", "en")


# ============================== extract ==============================
def extract():
    """The four files, after today's checks pass on them (they raise DataError otherwise), and the room as
    room.py works it out (for the take-off names it computes)."""
    sys.path.insert(0, str(REPO))
    import build, materials
    q = build.assemble(REPO / "bathroom-renovation-quote.md", measure=False)
    raw = {p: tomllib.loads((REPO / f"{p}.toml").read_text(encoding="utf-8")) for p in ("phases", "materials", "room", "labour")}
    return raw, q.room.take_off(), materials.STATUS


# ============================== transform ==============================
def key(kind, old):
    return hashlib.sha256(f"{kind}:{old}".encode()).hexdigest()[:16]


class Rows:
    """Rows per table, in order; pos counted per table."""
    def __init__(self):
        self.tables, self._pos = {}, {}

    def add(self, table, pos=False, **row):
        if pos:
            self._pos[table] = self._pos.get(table, 0) + 1
            row = {"id": row.pop("id"), "pos": self._pos[table], **row} if "id" in row else \
                  {**{k: row.pop(k) for k in list(row) if k == "code"}, "pos": self._pos[table], **row}
        self.tables.setdefault(table, []).append({k: v for k, v in row.items() if v is not None})

    def texts(self, table, keys, e, cols, required=True):
        """One row per language; cols = {column: TOML key base} ('' for th/en, 'note' for note_th/note_en …)."""
        for lang in LANGS:
            vals = {c: e.get(f"{b}_{lang}" if b else lang) for c, b in cols.items()}
            if all(v is None for v in vals.values()) and not required:
                continue
            self.add(table, **keys, lang=lang, **vals)

    def note(self, table, keys, e):
        self.texts(table, keys, e, {"note": "note"}, required=False)

    def assumed(self, table, keys, e):
        for k in e.get("assumed", []):
            self.add(table, **keys, key=k, how=None)      # how: not in the TOML (it's in comments) — to settle


def labels(r, part, d):
    for code, v in d["labels"].items():
        for lang in LANGS:
            r.add(f"{part}_label", code=code, lang=lang, text=v[lang])
    for code, v in d["symbols"].items():
        r.add(f"{part}_symbol", code=code, value=v)


def section(r, part, d):
    r.texts(f"{part}_section_text", {}, d["section"], {"name": ""})
    r.note(f"{part}_section_note", {}, d["section"])


LABOUR_MEASURE = {"m2": "area", "metre": "length", "set": "count", "job": "job", "percent": "share"}   # old unit id → measure
TAKE_OFF_MEASURE = {"m2": "area", "metre": "length"}                                                 # room.py's unit → measure
MATERIALS_LENGTH = "metre"                                                                           # the one unit bought by length
SHAPE_COLUMNS = {"rect": ("x", "y", "w", "h", "d"), "circle": ("x", "y", "w", "d"), "point": ("x", "y"),
                 "zone": ("x", "w", "d", "waterproofing"), "opening": ("x", "y", "w", "h"), "step": ("x", "h", "d", "high")}
REF = re.compile(r"\{(step|phase):([a-z0-9_]+)\}")


def transform(raw, take_off, statuses):
    r = Rows()
    for i, lang in enumerate(LANGS, 1):
        r.add("language", code=lang, pos=i)
    # ---------- materials
    m = raw["materials"]
    r.add("materials_setting", id=1, prices_date=m["prices_date"].isoformat(), date_format=m["date_format"], round_approx=m["round_approx"])
    section(r, "materials", m); labels(r, "materials", m)
    for u in m["unit"]:
        uk = key("materials_unit", u["id"])
        r.add("materials_unit", pos=True, id=uk, measure="length" if u["id"] == MATERIALS_LENGTH else "count")
        r.texts("materials_unit_text", {"unit": uk}, u, {"name": ""})
        r.add("materials_unit_plural", unit=uk, lang="en", many=u["en_many"])       # Thai has one form
    for s in m["shop"]:
        sk = key("shop", s["id"])
        r.add("materials_shop", pos=True, id=sk, sku_pattern=s["sku"], link=s["link"])
        r.texts("materials_shop_text", {"shop": sk}, s, {"name": ""})
    for w in m["work_section"]:
        wk = key("materials_work_section", w["id"])
        r.add("materials_work_section", pos=True, id=wk)
        r.texts("materials_work_section_text", {"work_section": wk}, w, {"name": ""})
        r.note("materials_work_section_note", {"work_section": wk}, w)
    for code, rule in statuses.items():
        r.add("materials_status", pos=True, code=code, to_buy=rule.to_buy, paid=rule.paid, on_site=rule.on_site, by_trade=rule.by)
    for e in m["entry"]:
        pk = key("product", e["id"]); size = e.get("size", {})
        r.add("materials_product", pos=True, id=pk, w=size.get("w"), h=size.get("h"), d=size.get("d"), per_box=e.get("per_box"),
              electrical=e.get("electrical", False), ip=e.get("ip"), unit=key("materials_unit", e["unit"]),
              price=e.get("price"), approx=e.get("approx", False))
        r.texts("materials_product_text", {"product": pk}, e, {"name": "", "detail": "detail"})
        if "shop" in e:
            r.add("materials_product_shop", product=pk, shop=key("shop", e["shop"]), sku=e["sku"])
        r.assumed("materials_product_assumed", {"product": pk}, e)
        for ln in e["line"]:
            lk = key("materials_line", f'{e["id"]}/{ln["work_section"]}/{ln["status"]}')
            r.add("materials_line", pos=True, id=lk, product=pk, work_section=key("materials_work_section", ln["work_section"]),
                  status=ln["status"], n=ln["n"])
            r.note("materials_line_note", {"line": lk}, ln)
            r.texts("materials_line_by", {"line": lk}, ln, {"who": "by"}, required=False)
    # ---------- room
    rm = raw["room"]
    r.add("room_room", id=1, **rm["room"])
    labels(r, "room", rm)
    for code, (_, unit) in take_off.items():
        r.add("room_take_off", pos=True, code=code, measure=TAKE_OFF_MEASURE[unit])
    for t in rm["tile"]:
        tk = key("tile", t["id"])
        r.add("room_tile", pos=True, id=tk, product=key("product", t["product"]), tiling_height=t["tiling_height"], fill=t["fill"])
        r.texts("room_tile_text", {"tile": tk}, t, {"name": ""})
    fl, floor = rm["floor"], key("surface", "floor")
    r.add("room_surface", pos=True, id=floor, kind="floor", ref=fl["ref"], tile=key("tile", fl["tile"]))
    for w in rm["wall"]:
        wk = key("surface", w["id"])
        r.add("room_surface", pos=True, id=wk, kind="wall", ref=w["ref"], tile=key("tile", w["tile"]))
        r.add("room_wall", surface=wk, waterproofing=w["waterproofing"], elevation=w["elevation"])
        r.texts("room_wall_text", {"wall": wk}, w, {"name": ""})
        r.assumed("room_wall_assumed", {"wall": wk}, w)
    r.add("room_floor", id=1, surface=floor, drain=key("item", fl["drain"]), fall_wet=fl["fall_wet"], fall_dry=fl["fall_dry"])
    r.assumed("room_floor_assumed", {}, fl)
    c = rm["column"]
    r.add("room_column", id=1, width=c["width"], depth=c["depth"], into_room=c["into_room"], wall=key("surface", c["wall"]))
    r.texts("room_column_text", {}, c, {"name": ""}); r.note("room_column_note", {}, c)
    d = rm["door"]
    r.add("room_door", id=1, product=key("product", d["product"]), hinge=d["hinge"], swing=d["swing"]); r.note("room_door_note", {}, d)
    li = rm["lintel"]
    r.add("room_lintel", id=1, product=key("product", li["product"]), bearing=li["bearing"]); r.note("room_lintel_note", {}, li)
    for surface, items in [(floor, fl.get("item", []))] + [(key("surface", w["id"]), w.get("item", [])) for w in rm["wall"]]:
        for it in items:
            ik = key("item", it["id"])
            r.add("room_item", pos=True, id=ik, surface=surface, product=key("product", it["product"]) if "product" in it else None,
                  fitting=key("item", it["fitting"]) if "fitting" in it else None)
            r.add(f'room_item_{it["shape"]}', item=ik, **{k: it.get(k) for k in SHAPE_COLUMNS[it["shape"]]})
            r.texts("room_item_name", {"item": ik}, it, {"name": ""}, required=False)
            r.note("room_item_note", {"item": ik}, it)
            r.assumed("room_item_assumed", {"item": ik}, it)
    for n in rm["norm"]:
        r.add("room_norm", pos=True, code=n["id"], item=key("item", n["item"]) if "item" in n else None, value=n["value"],
              standard=n["standard"], url=n["url"], checked=n["checked"].isoformat())
        r.texts("room_norm_text", {"norm": n["id"]}, n, {"name": ""})
    # ---------- labour
    lb = raw["labour"]
    r.add("labour_setting", id=1, date_format=lb["date_format"], round_approx=lb["round_approx"])
    section(r, "labour", lb); labels(r, "labour", lb)
    f = lb["factor_f"]
    r.add("labour_factor_f", id=1, value=f["value"], standard=f["standard"], url=f["url"], checked=f["checked"].isoformat())
    r.texts("labour_factor_f_text", {}, f, {"name": ""})
    for b in lb["book"]:
        bk = key("book", b["id"])
        r.add("labour_book", pos=True, id=bk, standard=b["standard"], url=b["url"], published=b.get("published"), official=b.get("official"),
              file=b.get("file"), checked=b["checked"].isoformat(), bare=b.get("bare", False))
        r.texts("labour_book_text", {"book": bk}, b, {"name": "", "item_format": "item"})
    for u in lb["unit"]:
        uk = key("labour_unit", u["id"])
        r.add("labour_unit", pos=True, id=uk, measure=LABOUR_MEASURE[u["id"]])
        r.texts("labour_unit_text", {"unit": uk}, u, {"name": ""})
        r.add("labour_unit_plural", unit=uk, lang="en", many=u["en_many"])
    for w in lb["work_section"]:
        wk = key("labour_work_section", w["id"])
        r.add("labour_work_section", pos=True, id=wk)
        r.texts("labour_work_section_text", {"work_section": wk}, w, {"name": ""})
        r.note("labour_work_section_note", {"work_section": wk}, w)
    for x in lb["rate"]:
        rk = key("rate", x["id"])
        r.add("labour_rate", pos=True, id=rk, unit=key("labour_unit", x["unit"]), rate=x["rate"],
              book=key("book", x["book"]) if "book" in x else None, item=x.get("item"), book_note=x.get("book_note"),
              page=x.get("page"), url=x.get("url"))
        r.texts("labour_rate_text", {"rate": rk}, x, {"name": ""})
        r.assumed("labour_rate_assumed", {"rate": rk}, x)
    for i, x in enumerate(lb["line"], 1):              # lines have no id in the TOML: their place gives one
        lk = key("labour_line", i)
        r.add("labour_line", pos=True, id=lk, rate=key("rate", x["rate"]), work_section=key("labour_work_section", x["work_section"]))
        if "take_off" in x:
            r.add("labour_line_take_off", line=lk, take_off=x["take_off"], times=x.get("times"))
        if "n" in x:
            r.add("labour_line_n", line=lk, n=x["n"], times=x.get("times"))
        if "count" in x:
            r.add("labour_line_count", line=lk, times=x.get("times"))
            for p in x["count"]:
                r.add("labour_line_count_product", line=lk, product=key("product", p))
        for p in x.get("of_products", []):
            r.add("labour_line_share_product", line=lk, product=key("product", p))
        r.note("labour_line_note", {"line": lk}, x)
        r.assumed("labour_line_assumed", {"line": lk}, x)
    # ---------- phases
    p = raw["phases"]
    section(r, "phases", p); labels(r, "phases", p)
    refs = lambda text: REF.sub(lambda mt: "{%s:%s}" % (mt[1], key(mt[1], mt[2])), text)
    for ph in p["phase"]:
        pk = key("phase", ph["id"])
        r.add("phases_phase", pos=True, id=pk)
        r.texts("phases_phase_text", {"phase": pk}, ph, {"name": ""})
        r.note("phases_phase_note", {"phase": pk}, ph)
        for s in ph.get("step", []):
            sk = key("step", s["id"])
            r.add("phases_step", pos=True, id=sk, phase=pk)
            r.texts("phases_step_text", {"step": sk}, {**s, "th": refs(s["th"]), "en": refs(s["en"])}, {"text": ""})
    return r


# ============================== load ==============================
def schema_db():
    db = sqlite3.connect(":memory:")
    for part in PARTS:
        db.executescript((SCHEMA / f"{part}.schema.sql").read_text(encoding="utf-8"))
    return db


def sql(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(int(v)) if isinstance(v, float) and v.is_integer() else repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def part_of(table):
    return "common" if table == "language" else table.split("_", 1)[0]


def write(r):
    """The transform's rows into a fresh database (the schema refuses what doesn't fit), then dumped as the data
    files — so the migration and every later dump write one layout."""
    db = schema_db()
    for t, rows in r.tables.items():
        for row in rows:
            try:
                db.execute(f"INSERT INTO {t} ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                           [int(v) if isinstance(v, bool) else v for v in row.values()])
            except sqlite3.Error as e:
                sys.exit(f"ERROR: the transform made a row the schema refuses: {t} {row}: {e}")
    db.commit()
    return dump(db, DATA)


def ordering(db, t):
    """The order a table is dumped in: by pos; or by its thing's pos (its first link to a table with one), then by
    language; or by its primary key."""
    cols = [c[1] for c in db.execute(f"PRAGMA table_info({t})")]
    if "pos" in cols:
        return f"SELECT * FROM {t} ORDER BY pos"
    joins, order = [], []
    for f in db.execute(f"PRAGMA foreign_key_list({t})"):
        if f[2] != "language" and "pos" in [c[1] for c in db.execute(f"PRAGMA table_info({f[2]})")] and not joins:
            joins.append(f"LEFT JOIN {f[2]} p ON p.{f[4]} = {t}.{f[3]}"); order.append("p.pos")
    if "lang" in cols:
        joins.append(f"LEFT JOIN language l ON l.code = {t}.lang"); order.append("l.pos")
    pk = sorted([c for c in db.execute(f"PRAGMA table_info({t})") if c[5]], key=lambda c: c[5])
    order += [f"{t}.{c[1]}" for c in pk] or [f"{t}.rowid"]
    return f"SELECT {t}.* FROM {t} {' '.join(joins)} ORDER BY {', '.join(order)}"


def dump(db, folder):
    """Every table, in schema order, one INSERT per line naming its columns. Data only: people read it through
    the schema's views, which follow the foreign keys to the names."""
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY rowid").fetchall():
        cur = db.execute(ordering(db, t))
        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            kept = [(c, v) for c, v in zip(cols, row) if v is not None]
            out.setdefault(part_of(t), []).append(
                f"INSERT INTO {t} ({', '.join(c for c, _ in kept)}) VALUES ({', '.join(sql(v) for _, v in kept)});")
    for part, lines in out.items():
        (folder / f"{part}.data.sql").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def load():
    """A fresh database from the schema files and the data files — what every build would do."""
    db = schema_db()
    for part in PARTS:
        f = DATA / f"{part}.data.sql"
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            try:
                db.execute(line)
            except sqlite3.Error as e:
                raise SystemExit(f"ERROR: {f.name} line {n}: {e}")
    db.commit()
    return db


# ============================== checks ==============================
def names(db):
    """Every entity key → what a person calls it (its English name, or its product's), for messages."""
    out = {}
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name GLOB '*_text'"):
        cols = [c[1] for c in db.execute(f"PRAGMA table_info({t})")]
        col = next((c for c in ("name", "text") if c in cols), None)
        fk = [f[3] for f in db.execute(f"PRAGMA foreign_key_list({t})") if f[2] != "language"]
        if col and fk:
            for k, v in db.execute(f"SELECT {fk[0]}, {col} FROM {t} WHERE lang = 'en'"):
                out[k] = v[:40]
    for k, v in db.execute("SELECT i.id, coalesce(n.name, p.name) FROM room_item i LEFT JOIN room_item_name n ON n.item = i.id AND n.lang = 'en' "
                           "LEFT JOIN materials_product_text p ON p.product = i.product AND p.lang = 'en'"):
        out[k] = v
    for k, v in db.execute("SELECT l.id, t.name FROM labour_line l JOIN labour_rate_text t ON t.rate = l.rate AND t.lang = 'en'"):
        out[k] = v[:40]
    for k, v in db.execute("SELECT l.id, t.name FROM materials_line l JOIN materials_product_text t ON t.product = l.product AND t.lang = 'en'"):
        out[k] = v[:40]
    return out


def one_to_one(db, parent, pcol):
    """The tables whose primary key is a link to parent.pcol: [(table, column)] (an item's shapes, a line's sources)."""
    out = []
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
        pk = [c[1] for c in db.execute(f"PRAGMA table_info({t})") if c[5]]
        for f in db.execute(f"PRAGMA foreign_key_list({t})"):
            if f[2] == parent and f[4] == pcol and pk == [f[3]]:
                out.append((t, f[3]))
    return out


def problems(db):
    """Every broken link, every check view, the translation conventions, and every assumed value being there —
    each message naming things as a person calls them, not by key."""
    out = []
    for t, rowid, parent, fk in db.execute("PRAGMA foreign_key_check"):
        col = [f[3] for f in db.execute(f"PRAGMA foreign_key_list({t})") if f[0] == fk][0]
        val = db.execute(f"SELECT {col} FROM {t} WHERE rowid = ?", (rowid,)).fetchone()[0]
        out.append(f"{t}.{col} = {val}: no such {parent}")
    for (v,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'view' AND name GLOB 'check_*'"):
        out += [f"{v}: {m}" for (m,) in db.execute(f"SELECT * FROM {v}")]
    langs = {l for (l,) in db.execute("SELECT code FROM language")}
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND (name GLOB '*_text' OR name GLOB '*_note' "
                           "OR name GLOB '*_name' OR name GLOB '*_by' OR name GLOB '*_plural')"):
        fks = [(f[3], f[2], f[4]) for f in db.execute(f"PRAGMA foreign_key_list({t})") if f[2] != "language"]
        if not fks:                                     # a one-row thing's text
            have = {l for (l,) in db.execute(f"SELECT lang FROM {t}")}
            if (have or t.endswith("_text")) and have != langs:
                out.append(f"{t}: in {sorted(have)}, not {sorted(langs)}")
            continue
        col, parent, pcol = fks[0]
        if not t.endswith("_plural"):                   # a plural is only where a language has one
            for k, got in db.execute(f"SELECT {col}, group_concat(lang) FROM {t} GROUP BY {col} HAVING count(*) <> {len(langs)}"):
                out.append(f"{t}: {k} only in {got}")
        if t.endswith("_text"):
            for (k,) in db.execute(f"SELECT {pcol} FROM {parent} WHERE {pcol} NOT IN (SELECT {col} FROM {t})"):
                out.append(f"{t}: {parent} {k} has no text")
    # an assumed value must be there to be assumed
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name GLOB '*_assumed'"):
        fks = [(f[3], f[2], f[4]) for f in db.execute(f"PRAGMA foreign_key_list({t})")]
        rows = db.execute(f"SELECT {fks[0][0] + ', ' if fks else ''}key FROM {t}").fetchall()
        for row in rows:
            k, col = (row[0], row[1]) if fks else (None, row[0])
            if not fks:                                 # a one-row thing (the floor)
                val = db.execute(f"SELECT {col} FROM {t.replace('_assumed', '')}").fetchone()[0]
            else:                                       # the thing's own table, or a one-to-one table off it
                _, parent, pcol = fks[0]                # (an item's shape, a line's source), whichever has the column
                val = None
                for tab, kc in [(parent, pcol)] + one_to_one(db, parent, pcol):
                    if col in {c[1] for c in db.execute(f"PRAGMA table_info({tab})")}:
                        got = db.execute(f"SELECT {col} FROM {tab} WHERE {kc} = ?", (k,)).fetchone()
                        val = got[0] if got else val
            if val is None:
                out.append(f"{t}: {k or ''} marks {col} as assumed, but it has no {col}")
    nm = names(db)
    return [re.sub(r"\b[0-9a-f]{16}\b", lambda mt: f"'{nm.get(mt[0], mt[0])}'", m) for m in out]


if __name__ == "__main__":
    raw, take_off, statuses = extract()
    rows = transform(raw, take_off, statuses)
    out = write(rows)
    print("wrote", ", ".join(f"data/{p}.data.sql ({len(l)} lines)" for p, l in out.items()))
    db = load()
    print("SQLite", sqlite3.sqlite_version, "·", db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0], "tables ·",
          sum(db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()),
          "rows ·", db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'view' AND name GLOB 'check_*'").fetchone()[0], "check views")
    found = problems(db)
    print(len(found), "problems"); [print("  ", p) for p in found]
    # the round trip: the loaded database, dumped again, must give the very same files
    again = DATA.parent / "data-again"
    dump(db, again)
    same = all((DATA / f.name).read_bytes() == f.read_bytes() for f in again.iterdir())
    print("round trip (load the files, dump them again):", "identical" if same else "DIFFERENT")
