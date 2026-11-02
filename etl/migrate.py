"""Trial: the TOML → SQL migration (ETL), run as often as the design changes (mise run etl:run).

    writes out/etl/migrations/0001_initial.sql (the schema: etl/schema/*.sql in load order) and out/etl/data/<part>.sql
    (each part's rows, as sqlite3 ".dump --data-only <part>_%" writes them), then loads both the way D1 does and checks

  Extract    read the four TOML files, after today's code has checked them (so nothing it would refuse moves)
  Transform  reshape them into the design in schema/ — every difference between the TOML's shape and the
             design is here, and only here
  Load       write one INSERT per line per data file (the dump layout), then load the schema and those files
             into a fresh SQLite database and run every check

Keys: an entity's key is a version 5 UUID worked out from its kind and its id in the TOML, so running this again gives
the same keys and the files don't change. Rows made after the switch get SQLite's version 4 (random) UUIDs. Changes
nothing in the repo.
"""
import os, re, shutil, sqlite3, subprocess, sys, tempfile, tomllib, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCHEMA, OUT = HERE / "schema", REPO / "out" / "etl"
MIGRATIONS, DATA = OUT / "migrations", OUT / "data"
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
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/joeblew999/bathroom-renovation-mon")
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def key(kind, old):
    """A migrated entity's key: the version 5 UUID of its kind and its id in the TOML (the same every run)."""
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{old}"))


STEP = 10        # positions leave gaps, so inserting a row between two touches only that row


class Rows:
    """Rows per table, in order. pos counts in STEPs within the row's parent (`within`: the parent column),
    or within the table."""
    def __init__(self):
        self.tables, self._pos = {}, {}

    def add(self, table, pos=False, within=None, **row):
        if pos:
            k = (table, row.get(within))
            self._pos[k] = self._pos.get(k, 0) + STEP
            lead = {c: row.pop(c) for c in ("id", "code", "line") if c in row}
            row = {**lead, "pos": self._pos[k], **row}
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

    def assumed(self, table, keys, e, old=None):
        for k in e.get("assumed", []):
            if (table, old, k) not in HOW:
                sys.exit(f"ERROR: {table} {old}: {k} is assumed, but the ETL has no note on how to find its real value")
            self.add(table, **keys, key=k, how=HOW[(table, old, k)])


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
# How to find each assumed value's real figure. The first three are TOML comments today (materials.toml:881,
# room.toml:246); the rest are new, written for the owner to check.
HOW = {("materials_product_assumed", "heater", "ip"): "an existing heater: its rating isn't known — read it off its label",
       ("room_item_assumed", "shower_head", "x"): "taken as the top of the shower rail: measure the real head",
       ("room_item_assumed", "shower_head", "y"): "taken as the top of the shower rail: measure the real head",
       ("room_floor_assumed", "floor", "fall_wet"): "the fall on the wet side, from the step down to the drain: "
                                                     "check with a level on site once the old floor is up",
       ("room_floor_assumed", "floor", "fall_dry"): "the fall on the dry side, towards the step: "
                                                     "check with a level on site once the old floor is up",
       ("room_item_assumed", "shower_zone", "waterproofing"): "how high the membrane goes in the shower zone: "
                                                               "confirm with the builder against the waterproofing product's instructions",
       ("labour_rate_assumed", "disposal", "rate"): "no rate book lists it: ask the builder what taking the debris away costs",
       ("labour_line_assumed", "wall_out", "n"): "the old door wall's area in m²: measure its length and height on site",
       ("labour_line_assumed", "tiles_off", "take_off"): "taken as the area tiled on the existing walls: "
                                                          "measure the old tiles still on the walls",
       ("labour_line_assumed", "water_pipe", "n"): "metres of supply pipe: measure the runs on site",
       ("labour_line_assumed", "waste_pipe_small", "n"): "metres of basin waste pipe: measure the run on site",
       ("labour_line_assumed", "waste_pipe_large", "n"): "metres of toilet waste pipe, in its floor trench: measure the run on site"}
COLUMN_REMARK = "depth and into_room were measured on site (room.toml:22-23)"
REF_GAP = re.compile(r"\{(step|phase):([a-z0-9_]+)\}")
FACTOR_F_REMARK = ("Its table (ว481), building work, the smallest band (direct cost up to 0.5 million baht): 1.2199 in the "
                   "column without VAT, 1.3052 with 7% VAT. A small builder usually doesn't charge VAT; if this one does, use 1.3052.")
BOOK_REMARK = {"cgd_w480": "To get the book again, or a newer edition: url downloads this copy; published is the page that publishes "
               "it (with the download link); official is a government page for the circular. A new edition comes as a new circular "
               "titled \"การปรับปรุงบัญชีค่าแรงงาน/ดำเนินการสำหรับถอดแบบคำนวณราคากลางงานก่อสร้าง\" — the edition before this one was "
               "กค 0433.2/ว 809 of 14/11/2568 (https://www.yotathai.com/passadu/w809). For a new edition: keep its PDF in sources/ "
               "under its own date, point file, url, published and standard at it, check every rate's item, page and value against it, "
               "and set checked."}


def transform(raw, take_off, statuses):
    r = Rows()
    rm0 = raw["room"]
    kinds = {rm0["door"]["product"]: "door_frame", rm0["lintel"]["product"]: "lintel", **{t["product"]: "tile" for t in rm0["tile"]}}
    for i, lang in enumerate(LANGS, 1):
        r.add("common_language", code=lang, pos=i)
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
              electrical=e.get("electrical", False), ip=e.get("ip"), kind=kinds.get(e["id"]), unit=key("materials_unit", e["unit"]),
              price=e.get("price"), approx=e.get("approx", False))
        r.texts("materials_product_text", {"product": pk}, e, {"name": "", "detail": "detail"})
        if "shop" in e:
            r.add("materials_product_shop", product=pk, shop=key("shop", e["shop"]), sku=e["sku"])
        r.assumed("materials_product_assumed", {"product": pk}, e, e["id"])
        for ln in e["line"]:
            lk = key("materials_line", f'{e["id"]}/{ln["work_section"]}/{ln["status"]}')
            r.add("materials_line", pos=True, within="product", id=lk, product=pk, work_section=key("materials_work_section", ln["work_section"]),
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
        r.assumed("room_wall_assumed", {"wall": wk}, w, w["id"])
    r.add("room_floor", surface=floor, drain=key("item", fl["drain"]), fall_wet=fl["fall_wet"], fall_dry=fl["fall_dry"])
    r.assumed("room_floor_assumed", {"floor": floor}, fl, "floor")
    c = rm["column"]
    r.add("room_column", id=1, width=c["width"], depth=c["depth"], into_room=c["into_room"], wall=key("surface", c["wall"]),
          remark=COLUMN_REMARK)
    r.texts("room_column_text", {}, c, {"name": ""}); r.note("room_column_note", {}, c)
    d = rm["door"]
    r.add("room_door", id=1, product=key("product", d["product"]), hinge=d["hinge"], swing=d["swing"]); r.note("room_door_note", {}, d)
    li = rm["lintel"]
    r.add("room_lintel", id=1, product=key("product", li["product"]), bearing=li["bearing"]); r.note("room_lintel_note", {}, li)
    for surface, items in [(floor, fl.get("item", []))] + [(key("surface", w["id"]), w.get("item", [])) for w in rm["wall"]]:
        for it in items:
            ik = key("item", it["id"])
            r.add("room_item", pos=True, within="surface", id=ik, surface=surface, product=key("product", it["product"]) if "product" in it else None,
                  fitting=key("item", it["fitting"]) if "fitting" in it else None)
            r.add(f'room_item_{it["shape"]}', item=ik, **{k: it.get(k) for k in SHAPE_COLUMNS[it["shape"]]})
            r.texts("room_item_name", {"item": ik}, it, {"name": ""}, required=False)
            r.note("room_item_note", {"item": ik}, it)
            r.assumed("room_item_assumed", {"item": ik}, it, it["id"])
    for n in rm["norm"]:
        r.add("room_norm", pos=True, code=n["id"], item=key("item", n["item"]) if "item" in n else None, value=n["value"],
              standard=n["standard"], url=n["url"], checked=n["checked"].isoformat())
        r.texts("room_norm_text", {"norm": n["id"]}, n, {"name": ""})
    # ---------- labour
    lb = raw["labour"]
    r.add("labour_setting", id=1, date_format=lb["date_format"], round_approx=lb["round_approx"])
    section(r, "labour", lb); labels(r, "labour", lb)
    f = lb["factor_f"]
    r.add("labour_factor_f", id=1, value=f["value"], standard=f["standard"], url=f["url"], checked=f["checked"].isoformat(),
          remark=FACTOR_F_REMARK)
    r.texts("labour_factor_f_text", {}, f, {"name": ""})
    for b in lb["book"]:
        bk = key("book", b["id"])
        r.add("labour_book", pos=True, id=bk, standard=b["standard"], url=b["url"], published=b.get("published"), official=b.get("official"),
              file=b.get("file"), checked=b["checked"].isoformat(), bare=b.get("bare", False), remark=BOOK_REMARK.get(b["id"]))
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
        r.assumed("labour_rate_assumed", {"rate": rk}, x, x["id"])
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
                r.add("labour_line_count_product", pos=True, within="line", line=lk, product=key("product", p))
        if "of_products" in x:
            r.add("labour_line_share", line=lk)
        for p in x.get("of_products", []):
            r.add("labour_line_share_product", pos=True, within="line", line=lk, product=key("product", p))
        r.note("labour_line_note", {"line": lk}, x)
        r.assumed("labour_line_assumed", {"line": lk}, x, x["rate"])
    # ---------- phases
    p = raw["phases"]
    def gaps(e, table, owner, cols):
        """Turn {step:x} / {phase:x} in a thing's texts into {1}, {2} … (numbered by first appearance in English) and
        add a ref row for each, pointing at the step or phase."""
        found = []
        for col in cols:
            for lang in ("en",) + tuple(l for l in LANGS if l != "en"):
                for kind, old in REF_GAP.findall(e.get(f"{col}_{lang}" if col else lang, "") or ""):
                    if (kind, old) not in found:
                        found.append((kind, old))
        for n, (kind, old) in enumerate(found, 1):
            r.add(table, **owner, n=n, **{f"to_{kind}": key(kind, old)})
        sub = lambda v: REF_GAP.sub(lambda mt: "{%d}" % (found.index((mt[1], mt[2])) + 1), v) if isinstance(v, str) else v
        return {k: sub(v) for k, v in e.items()}
    for text in [p["section"]] + [ph.get(k, "") for ph in p["phase"] for k in ("th", "en")]:
        if REF_GAP.search(str(text)):
            sys.exit("ERROR: a reference in the phases section or a phase's name: the design has gaps only in steps and phase notes")
    section(r, "phases", p); labels(r, "phases", p)
    for ph in p["phase"]:
        pk = key("phase", ph["id"])
        r.add("phases_phase", pos=True, id=pk)
        r.texts("phases_phase_text", {"phase": pk}, ph, {"name": ""})
        r.note("phases_phase_note", {"phase": pk}, gaps(ph, "phases_phase_note_ref", {"phase": pk}, ("note",)))
        for st in ph.get("step", []):
            sk = key("step", st["id"])
            r.add("phases_step", pos=True, within="phase", id=sk, phase=pk)
            r.texts("phases_step_text", {"step": sk}, gaps(st, "phases_step_ref", {"step": sk}, ("",)), {"text": ""})
    return r


# ============================== load ==============================
# Cloudflare D1's limits (developers.cloudflare.com/d1/platform/limits, read 2 Nov 2026; the compound SELECT limit isn't
# documented there — found by running wrangler 4.156.0's local D1). Every database we open has them, so whatever loads
# here loads on D1.
D1_LIMITS = {sqlite3.SQLITE_LIMIT_COMPOUND_SELECT: 5, sqlite3.SQLITE_LIMIT_SQL_LENGTH: 100_000,
             sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER: 100, sqlite3.SQLITE_LIMIT_COLUMN: 100, sqlite3.SQLITE_LIMIT_FUNCTION_ARG: 32,
             sqlite3.SQLITE_LIMIT_LIKE_PATTERN_LENGTH: 50, sqlite3.SQLITE_LIMIT_LENGTH: 2_000_000}


def connect(path=":memory:"):
    """A database that behaves like D1: its limits, foreign keys always on. We begin and commit transactions ourselves."""
    db = sqlite3.connect(path, isolation_level=None)
    for limit, value in D1_LIMITS.items():
        db.setlimit(limit, value)
    db.execute("PRAGMA foreign_keys = ON")
    return db


def statements(text):
    """A file's statements, each with the line it starts on — split at every ';' that ends a complete statement, so two
    statements on one line are two."""
    out, last = [], 0
    for m in re.finditer(";", text):
        piece = text[last:m.end()]
        if sqlite3.complete_statement(piece):
            body = piece.strip()
            if body:
                lead = len(piece) - len(piece.lstrip())
                out.append((text.count("\n", 0, last + lead) + 1, body))
            last = m.end()
    if text[last:].strip() and not all(l.strip().startswith("--") for l in text[last:].strip().splitlines()):
        out.append((text.count("\n", 0, last) + 1, text[last:].strip()))
    return out


def run_file(db, f, guard=None):
    """Run a file as one transaction with foreign keys deferred to its end, as D1 runs `wrangler d1 execute --file`. A
    failing statement names the file and line; a link left broken at the end names the rows."""
    db.execute("BEGIN")
    db.execute("PRAGMA defer_foreign_keys = ON")
    for n, st in statements(f.read_text(encoding="utf-8")):
        if guard:
            guard(f, n, st)
        try:
            db.execute(st)
        except sqlite3.Error as e:
            db.execute("ROLLBACK")
            raise SystemExit(f"ERROR: {f.name} line {n}: {e}")
    broken = db.execute("PRAGMA foreign_key_check").fetchall()
    if broken:
        db.execute("ROLLBACK")
        t, rowid, parent, _ = broken[0]
        raise SystemExit(f"ERROR: {f.name}: {len(broken)} link(s) to rows that aren't there, the first in {t} (row {rowid}) to {parent}")
    db.execute("COMMIT")


LITERAL = r"(?:NULL|-?\d+(?:\.\d+)?(?:e[+-]?\d+)?|'(?:[^']|'')*')"
SEED_ROW = re.compile(rf"INSERT INTO ([a-z_]+) VALUES\(({LITERAL}(?:,{LITERAL})*)\);")


def seed_guard(part):
    """A part's seed file holds only rows of plain values for its own tables — what .dump --data-only writes."""
    last = [0]
    def guard(f, n, st):
        m = SEED_ROW.fullmatch(st)
        if not m or part_of(m[1]) != part:
            raise SystemExit(f"ERROR: {f.name} line {n}: not a row of plain values for one of {part}'s tables: {st[:80]}")
        if n == last[0]:
            raise SystemExit(f"ERROR: {f.name} line {n}: two rows on one line — a seed file has one row per line, as .dump writes it")
        last[0] = n
    return guard


def migrated(folder=None):
    """A fresh database with the schema: every migration, in order."""
    db = connect()
    for f in sorted((folder or MIGRATIONS).glob("*.sql")):
        run_file(db, f)
        for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'").fetchall():
            if db.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone():
                raise SystemExit(f"ERROR: {f.name} puts rows in {t}: a migration changes the schema only (and moves the data it "
                                 "has); new rows — a code, a label — are data, added with db:sql and saved")
    return db


def schema_db():
    return migrated()


def schema_of(db):
    """The schema a database holds: every table, view and index, as SQLite keeps it."""
    return sorted(db.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"))


def sql(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(int(v)) if isinstance(v, float) and v.is_integer() else repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def part_of(name):
    """The part a table or view belongs to: the start of its name (common_, materials_, room_, labour_, phases_)."""
    return name.split("_", 1)[0]


def write_migration():
    """migrations/0001_initial.sql: the design in etl/schema, in load order — as written, comments and all."""
    MIGRATIONS.mkdir(parents=True, exist_ok=True)
    text = "\n".join((SCHEMA / f"{part}.schema.sql").read_text(encoding="utf-8") for part in PARTS)
    (MIGRATIONS / "0001_initial.sql").write_text(text, encoding="utf-8")


def write(r):
    """The transform's rows into a fresh database built from the migrations (the schema refuses what doesn't fit), then
    each part's rows dumped by sqlite3 — so the migration and every later save write one layout."""
    db = schema_db()
    db.execute("BEGIN"); db.execute("PRAGMA defer_foreign_keys = ON")
    for t, rows in r.tables.items():
        for row in rows:
            try:
                db.execute(f"INSERT INTO {t} ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                           [int(v) if isinstance(v, bool) else v for v in row.values()])
            except sqlite3.Error as e:
                sys.exit(f"ERROR: the transform made a row the schema refuses: {t} {row}: {e}")
    if db.execute("PRAGMA foreign_key_check").fetchall():
        sys.exit(f"ERROR: the transform left links to rows that aren't there: {db.execute('PRAGMA foreign_key_check').fetchall()[:3]}")
    db.execute("COMMIT")
    return dump(db, DATA)


def parent_of(db, t):
    """A table's parent link (column, parent table, parent column): the other column of a UNIQUE (parent, pos), or
    the link on its first key column. None for a table on its own."""
    fks = {f[3]: (f[2], f[4]) for f in db.execute(f"PRAGMA foreign_key_list({t})") if f[2] != "common_language"}
    for ix in db.execute(f"PRAGMA index_list({t})"):
        cols = [c[2] for c in db.execute(f"PRAGMA index_info({ix[1]})")]
        if ix[2] and len(cols) == 2 and "pos" in cols:
            col = cols[0] if cols[1] == "pos" else cols[1]
            return (col, *fks[col])
    pk = [c[1] for c in sorted(db.execute(f"PRAGMA table_info({t})"), key=lambda c: c[5]) if c[5]]
    return (pk[0], *fks[pk[0]]) if pk and pk[0] in fks else None


def cli():
    """SQLite's own command-line tool, pinned in mise.toml (http:sqlite-tools)."""
    return shutil.which("sqlite3") or sys.exit("ERROR: sqlite3 isn't on the PATH — run this under mise, which pins it (mise.toml)")


def dump(db, folder, before_swap=None):
    """Each part's seed file is sqlite3's own data-only dump of it — sqlite3 <db> ".dump --data-only <part>_%": one INSERT
    of plain values per row, in the order the rows went in. Written to a folder beside `folder` and then moved into place,
    so the five files change together or not at all. before_swap(that folder) may return problems: then nothing is moved
    and they are returned. Returns {part: lines}."""
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    with tempfile.TemporaryDirectory(dir=folder.parent) as t:
        f = Path(t) / "quote.db"
        out = sqlite3.connect(f); db.backup(out); out.close()
        for part in PARTS:
            text = subprocess.run([cli(), str(f), f".dump --data-only {part}_%"], capture_output=True, text=True, check=True).stdout
            (Path(t) / f"{part}.sql").write_text(text, encoding="utf-8")
            files[part] = text.splitlines()
        late = before_swap(Path(t)) if before_swap else []
        if late:
            return late
        for part in PARTS:
            os.replace(Path(t) / f"{part}.sql", folder / f"{part}.sql")
    return files


def load(folder=None, migrations=None):
    """A fresh database the way every build makes one, and as D1 would: the migrations, then each part's seed file — each
    file one transaction, foreign keys on and deferred to its end, D1's limits; a seed file may hold only rows of plain
    values for its own part's tables."""
    db = migrated(migrations)
    for part in PARTS:
        run_file(db, (folder or DATA) / f"{part}.sql", seed_guard(part))
    return db


# ============================== checks ==============================
def names(db):
    """Every entity key → a name that tells it from every other (its English name; an item with its number and wall;
    a line with its place), for messages."""
    out = {}
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name GLOB '*_text'"):
        cols = [c[1] for c in db.execute(f"PRAGMA table_info({t})")]
        col = next((c for c in ("name", "text") if c in cols), None)
        fk = [f[3] for f in db.execute(f"PRAGMA foreign_key_list({t})") if f[2] != "common_language"]
        if col and fk:
            for k, v in db.execute(f"SELECT {fk[0]}, {col} FROM {t} WHERE lang = 'en'"):
                out[k] = v[:50]
    for k, item, n, wall in db.execute(
            "SELECT i.id, coalesce(nm.name, p.name), (SELECT count(*) FROM room_item j WHERE j.surface = i.surface AND j.pos <= i.pos), "
            "coalesce(w.name, 'the floor') FROM room_item i LEFT JOIN room_item_name nm ON nm.item = i.id AND nm.lang = 'en' "
            "LEFT JOIN materials_product_text p ON p.product = i.product AND p.lang = 'en' "
            "LEFT JOIN room_wall_text w ON w.wall = i.surface AND w.lang = 'en'"):
        out[k] = f"{item} (item {n}, {wall})"
    for k, n, rate in db.execute("SELECT l.id, (SELECT count(*) FROM labour_line j WHERE j.pos <= l.pos), t.name FROM labour_line l "
                                 "JOIN labour_rate_text t ON t.rate = l.rate AND t.lang = 'en'"):
        out[k] = f"labour line {n} ({rate[:40]})"
    for k, prod, status, ws in db.execute("SELECT l.id, t.name, l.status, w.name FROM materials_line l "
                                          "JOIN materials_product_text t ON t.product = l.product AND t.lang = 'en' "
                                          "JOIN materials_work_section_text w ON w.work_section = l.work_section AND w.lang = 'en'"):
        out[k] = f"{prod[:40]} ({status}, {ws})"
    return out


def text_tables(db):
    """The tables of text in a person's language: translations, and each part's labels."""
    return [t for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND (name GLOB '*_text' OR name GLOB '*_note' "
                                     "OR name GLOB '*_name' OR name GLOB '*_by' OR name GLOB '*_plural' OR name GLOB '*_label')")]


def file_of(table):
    return f"{part_of(table)}.sql"


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
    for kind, name in db.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"):
        if part_of(name) not in PARTS:                 # the seed files hold the five parts only: anything else would be lost
            out.append(f"{kind} {name} belongs to no part: its name must start with one of {', '.join(p + '_' for p in PARTS)}")
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'").fetchall():
        for col in [c[1] for c in db.execute(f"PRAGMA table_info({t})") if c[2] == "TEXT"]:
            n = db.execute(f"SELECT count(*) FROM {t} WHERE {col} GLOB '*[' || char(9) || char(10) || char(13) || ']*'").fetchone()[0]
            if n:
                out.append(f"{file_of(t)}: {t}: {n} {col} with a line break or tab — a text is one line")
    for t, rowid, parent, fk in db.execute("PRAGMA foreign_key_check"):
        col = [f[3] for f in db.execute(f"PRAGMA foreign_key_list({t})") if f[0] == fk][0]
        val = db.execute(f"SELECT {col} FROM {t} WHERE rowid = ?", (rowid,)).fetchone()[0]
        out.append(f"{file_of(t)}: {t}.{col} = {val}: no such {parent}")
    for (v,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'view' AND name GLOB '*_check_*'"):
        out += [f"{part_of(v)}.sql: {m}" for (m,) in db.execute(f"SELECT * FROM {v}")]
    langs = {l for (l,) in db.execute("SELECT code FROM common_language")}
    for t in text_tables(db):
        cols = [c[1] for c in db.execute(f"PRAGMA table_info({t})")]
        for col in [c for c in cols if c not in ("lang", "code") and c not in [f[3] for f in db.execute(f"PRAGMA foreign_key_list({t})")]]:
            for (n,) in db.execute(f"SELECT count(*) FROM {t} WHERE {col} = ''"):
                if n:
                    out.append(f"{file_of(t)}: {t}: {n} empty {col}")
        if t.endswith("_label"):                       # each code in every language
            for code, got in db.execute(f"SELECT code, group_concat(lang) FROM {t} GROUP BY code HAVING count(*) <> {len(langs)}"):
                out.append(f"{file_of(t)}: {t}: label {code} only in {got}")
            continue
        fks = [(f[3], f[2], f[4]) for f in db.execute(f"PRAGMA foreign_key_list({t})") if f[2] != "common_language"]
        if not fks:                                     # a one-row thing's text
            have = {l for (l,) in db.execute(f"SELECT lang FROM {t}")}
            if (have or t.endswith("_text")) and have != langs:
                out.append(f"{file_of(t)}: {t} in {sorted(have)}, not {sorted(langs)}")
            continue
        col, parent, pcol = fks[0]
        if not t.endswith("_plural"):                   # a plural is only where a language has one
            for k, got in db.execute(f"SELECT {col}, group_concat(lang) FROM {t} GROUP BY {col} HAVING count(*) <> {len(langs)}"):
                out.append(f"{file_of(t)}: {t}: {k} only in {got}")
        if t.endswith("_text"):
            for (k,) in db.execute(f"SELECT {pcol} FROM {parent} WHERE {pcol} NOT IN (SELECT {col} FROM {t})"):
                out.append(f"{file_of(t)}: {t}: {parent} {k} has no text")
        if t.endswith("_plural"):                      # English has a form for more than 1
            for (k,) in db.execute(f"SELECT {pcol} FROM {parent} WHERE {pcol} NOT IN (SELECT {col} FROM {t} WHERE lang = 'en')"):
                out.append(f"{file_of(t)}: {t}: {parent} {k} has no English plural")
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
                out.append(f"{file_of(t)}: {t}: {k or ''} marks {col} as assumed, but it has no {col}")
    # every numbered gap in a text has its ref row, and every ref row its gap, in every language
    for text_t, col, ref_t, owner in (("phases_step_text", "text", "phases_step_ref", "step"),
                                      ("phases_phase_note", "note", "phases_phase_note_ref", "phase")):
        refs = {}
        for k, n in db.execute(f"SELECT {owner}, n FROM {ref_t}"):
            refs.setdefault(k, set()).add(n)
        for k, lang, text in db.execute(f"SELECT {owner}, lang, {col} FROM {text_t}"):
            have = {int(g) for g in re.findall(r"\{(\d+)\}", text)}
            if have != refs.get(k, set()):
                out.append(f"phases.sql: {text_t}: {k} ({lang}) has gaps {sorted(have)} but references {sorted(refs.get(k, set()))}")
        for k in set(refs) - {k for (k,) in db.execute(f"SELECT {owner} FROM {text_t}")}:
            out.append(f"phases.sql: {ref_t}: {k} has references but no text")
    for (text,) in db.execute("SELECT text FROM phases_step_text UNION ALL SELECT note FROM phases_phase_note"):
        for old in re.findall(r"\{(?:step|phase):[^}]*\}", text):
            out.append(f"phases.sql: a reference written into the text ({old}): it must be a gap with a ref row")
    # Thai and English fill the same placeholders and give the same numbers (README rule 3), and no brace is left open
    sys.path.insert(0, str(REPO))
    from common import _facts
    for t in [t for t in text_tables(db) if not t.endswith("_plural")]:
        cols = [c[1] for c in db.execute(f"PRAGMA table_info({t})")]
        keys = ["code"] if t.endswith("_label") else \
               [c for c in cols if c in [f[3] for f in db.execute(f"PRAGMA foreign_key_list({t})") if f[2] != "common_language"]]
        for col in [c for c in cols if c != "lang" and c not in keys]:
            by = {}
            for row in db.execute(f"SELECT {', '.join(keys + ['lang', col])} FROM {t}"):
                by.setdefault(tuple(row[:len(keys)]), {})[row[len(keys)]] = row[-1]
            for k, texts in by.items():
                for lang, text in texts.items():
                    if text and re.search(r"[{}]", re.sub(r"\{[^{}]*\}", "", text)):
                        out.append(f"{file_of(t)}: {t} {k[0] if k else ''} ({lang}): a brace that opens or closes nothing in its {col}")
                th, en = texts.get("th"), texts.get("en")
                if th and en:
                    for what, a, b in zip(("placeholders", "numbers"), _facts(th), _facts(en)):
                        if a != b:
                            out.append(f"{file_of(t)}: {t} {k[0] if k else ''}: its Thai and English {col} have different {what} "
                                       f"(Thai: {', '.join(a) or 'none'}; English: {', '.join(b) or 'none'})")
    out += today_checks(db)
    nm = names(db)
    return [re.sub(rf"\b{UUID}\b", lambda mt: f"'{nm.get(mt[0], mt[0])}'", m) for m in out]


PLACEHOLDERS = {   # what each text may fill in: (table, column) → its placeholders (a product's text: its own sizes and IP)
    ("materials_shop", "link"): ("sku", "sku_digits"),
    ("materials_section_note", "note"): ("prices_date", "approx"),
    ("labour_section_note", "note"): ("books", "approx"),
    ("labour_book_text", "item_format"): ("item",),
}


def today_checks(db):
    """Today's data checks in the parts' code, run on the database so save refuses what the build would (in the trial
    here; at the switch, save runs the parts' own loaders): each text fills in only its own placeholders; each sku looks
    like its shop's codes; the sizes the room needs from a product."""
    import string
    sys.path.insert(0, str(REPO))
    from materials import SIZE_KEYS, SIZE_UNITS
    out = []
    def fills(text):
        try:
            return [f for _, f, _, _ in string.Formatter().parse(text) if f is not None]
        except ValueError:
            return None                                   # a stray brace: reported by the brace check
    sizes = {k: (set(SIZE_KEYS) & {c for c in SIZE_KEYS if r[c] is not None}, r["ip"])
             for r in [dict(zip(("id", *SIZE_KEYS, "ip"), row)) for row in db.execute(f"SELECT id, {', '.join(SIZE_KEYS)}, ip FROM materials_product")]
             for k in [r["id"]]}
    for t in [t for t in text_tables(db) if not t.endswith(("_label", "_plural"))]:
        cols = [c[1] for c in db.execute(f"PRAGMA table_info({t})")]
        keys = [f[3] for f in db.execute(f"PRAGMA foreign_key_list({t})") if f[2] != "common_language"]
        for col in [c for c in cols if c != "lang" and c not in keys]:
            for row in db.execute(f"SELECT {', '.join(keys + [col])} FROM {t}"):
                used = fills(row[-1] or "")
                if used is None:
                    continue
                if t == "materials_product_text":
                    have, ip = sizes[row[0]]
                    allowed = {k + u for k in have for u in SIZE_UNITS} | ({"ip"} if ip else set())
                elif t in ("phases_step_text", "phases_phase_note"):
                    allowed = {f for f in used if f.isdigit()}  # numbered gaps (checked against their refs)
                else:
                    allowed = set(PLACEHOLDERS.get((t, col), ()))
                for f in used:
                    if f not in allowed:
                        out.append(f"{file_of(t)}: {t} {row[0] if keys else ''}: its {col} uses {{{f}}} (it can use: {', '.join(sorted(allowed)) or 'nothing'})")
    for t, col in PLACEHOLDERS:                              # texts kept on their row: a shop's link
        if not t.endswith(("_text", "_note")):
            for k, text in db.execute(f"SELECT id, {col} FROM {t}"):
                for f in fills(text) or []:
                    if f not in PLACEHOLDERS[(t, col)]:
                        out.append(f"{file_of(t)}: {t} {k}: its {col} uses {{{f}}} (it can use: {', '.join(PLACEHOLDERS[(t, col)])})")
    shops = {}
    for k, pattern in db.execute("SELECT id, sku_pattern FROM materials_shop"):
        try:
            shops[k] = re.compile(pattern)
        except re.error as e:
            out.append(f"materials.sql: materials_shop {k}: its sku_pattern isn't a pattern ({e})")
    for product, shop, sku in db.execute("SELECT product, shop, sku FROM materials_product_shop"):
        if shop in shops and not shops[shop].fullmatch(sku):
            out.append(f"materials.sql: materials_product_shop {product}: sku {sku!r} doesn't look like its shop's codes")
    for k, w, h, per_box in db.execute("SELECT t.id, p.w, p.h, p.per_box FROM room_tile t JOIN materials_product p ON p.id = t.product"):
        if None in (w, h, per_box):
            out.append(f"room.sql: room_tile {k}: its product needs w, h and per_box for the tile count")
        elif w != h or w != int(w):
            out.append(f"room.sql: room_tile {k}: its product is {w:g} × {h:g} — the tile count needs square tiles, in whole mm")
    for what, sql, need in (("the door", "SELECT p.w, p.h FROM room_door d JOIN materials_product p ON p.id = d.product", "w and h"),
                            ("the lintel", "SELECT p.h FROM room_lintel l JOIN materials_product p ON p.id = l.product", "h")):
        for row in db.execute(sql):
            if None in row:
                out.append(f"room.sql: {what}'s product needs {need}")
    return out


READS = {   # what each part's code may read besides its own tables: nothing — what a part needs from another
    "phases": set(),   # (the room: products' names, sizes and IP ratings; the labour: the take-off and the list's counts)
    "materials": set(),  # build.py reads from the part that owns it and hands over (README rules 5 and 6)
    "room": set(),
    "labour": set(),
}


def reading(db, part):
    """Let `part`'s code read the database: SQLite refuses any table outside its own, the language table, and READS
    (rule 5). Returns the database; reading(db, None) lifts the limit."""
    allowed = None if part is None else READS[part] | {"common_language", "sqlite_master"}
    def judge(action, table, column, schema, trigger):
        if action == sqlite3.SQLITE_READ and allowed is not None and table and not (
                table in allowed or table.startswith(part + "_")):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    db.set_authorizer(judge if part else None)
    return db


def vocabulary(db, take_off):
    """The codes the code is written against must be exactly the codes in the data (K3): labels and symbols per part,
    the norms, the take-offs (and what each measures), the statuses (and what each means). In the real parts each part
    makes its own comparison when it loads."""
    sys.path.insert(0, str(REPO))
    import materials, room, labour, phases
    out = []
    def same(what, file, code, data):
        for c in sorted(set(code) - set(data)):
            out.append(f"{file}: {what} {c} is used by the code but isn't in the data")
        for c in sorted(set(data) - set(code)):
            out.append(f"{file}: {what} {c} is in the data but the code doesn't know it")
    for part, mod in (("materials", materials), ("room", room), ("labour", labour), ("phases", phases)):
        same("label", f"{part}.data.sql", mod.LABELS, [c for (c,) in db.execute(f"SELECT DISTINCT code FROM {part}_label")])
        same("symbol", f"{part}.data.sql", mod.SYMBOLS, [c for (c,) in db.execute(f"SELECT code FROM {part}_symbol")])
    same("norm", "room.data.sql", room.NORMS, [c for (c,) in db.execute("SELECT code FROM room_norm")])
    measure = {"m2": "area", "metre": "length"}
    same("take-off", "room.data.sql", [f"{k} ({measure[u]})" for k, (_, u) in take_off.items()],
         [f"{c} ({m})" for c, m in db.execute("SELECT code, measure FROM room_take_off")])
    same("status", "materials.data.sql", [f"{k} {(r.to_buy, r.paid, r.on_site, r.by)}" for k, r in materials.STATUS.items()],
         [f"{c} {(bool(a), bool(b), bool(d), bool(e))}" for c, a, b, d, e in
          db.execute("SELECT code, to_buy, paid, on_site, by_trade FROM materials_status")])
    return out


def changed_alone(before, after):
    """A text whose Thai changed without its English, or the other way round — comparing two versions of the data
    (in the real check: the files as last committed, and as they are now)."""
    out = []
    langs = [l for (l,) in after.execute("SELECT code FROM common_language ORDER BY pos")]
    nm = names(after)
    for t in [t for t in text_tables(after) if not t.endswith("_plural")]:
        cols = [c[1] for c in after.execute(f"PRAGMA table_info({t})")]
        keys = ["code"] if t.endswith("_label") else \
               [c for c in cols if c in [f[3] for f in after.execute(f"PRAGMA foreign_key_list({t})") if f[2] != "common_language"]]
        had = {c[1] for c in before.execute(f"PRAGMA table_info({t})")}
        if not had:                                          # a table a migration added: nothing to compare
            continue
        texts = [c for c in cols if c != "lang" and c not in keys and c in had]
        read = lambda db: {(tuple(r[:len(keys)]), r[len(keys)]): r[len(keys) + 1:]
                           for r in db.execute(f"SELECT {', '.join(keys + ['lang'] + texts)} FROM {t}")}
        old, new = read(before), read(after)
        for thing in {k for k, _ in new}:
            for i, col in enumerate(texts):                 # each text on its own: a name and a detail are two texts
                changed = [l for l in langs if (thing, l) in old and old[(thing, l)][i] != new.get((thing, l), [None] * len(texts))[i]]
                if changed and len(changed) < len(langs):
                    what = nm.get(thing[0], thing[0]) if thing else ""
                    out.append(f"{file_of(t)}: {t} '{what}': its {', '.join(changed)} {col} changed but not the other language")
    return out


if __name__ == "__main__":
    raw, take_off, statuses = extract()
    rows = transform(raw, take_off, statuses)
    write_migration()
    out = write(rows)
    print("wrote migrations/0001_initial.sql, and", ", ".join(f"data/{p}.sql ({len(l)} rows)" for p, l in out.items()),
          "with", cli(), "(.dump --data-only)")
    db = load()
    print("SQLite", sqlite3.sqlite_version, "·", db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0], "tables ·",
          sum(db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()),
          "rows ·", db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'view' AND name GLOB '*_check_*'").fetchone()[0], "check views")
    found = problems(db) + vocabulary(db, take_off)
    print(len(found), "problems"); [print("  ", p) for p in found]
    # the round trip: the loaded database, dumped again, must give the very same files
    again = DATA.parent / "data-again"
    dump(db, again)
    same = all((DATA / f.name).read_bytes() == f.read_bytes() for f in again.iterdir())
    print("round trip (load the files, dump them again):", "identical" if same else "DIFFERENT")
