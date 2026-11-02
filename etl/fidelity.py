# fidelity.py — the transform carried every TOML value across: rebuild each TOML file from the database loaded from data/*.data.sql, keys mapped back to TOML ids; diff.
import sys, tomllib, datetime, re
from pathlib import Path
V2 = Path(__file__).resolve().parent
sys.path.insert(0, str(V2))
import migrate
from migrate import key, REPO
db = migrate.load()
raw = {p: tomllib.loads((REPO / f"{p}.toml").read_text(encoding="utf-8")) for p in ("phases", "materials", "room", "labour")}
inv = {}
def reg(kind, old): inv[key(kind, old)] = old
m, r, lb, p = raw["materials"], raw["room"], raw["labour"], raw["phases"]
for u in m["unit"]: reg("materials_unit", u["id"])
for s in m["shop"]: reg("shop", s["id"])
for w in m["work_section"]: reg("materials_work_section", w["id"])
for e in m["entry"]: reg("product", e["id"])
for t in r["tile"]: reg("tile", t["id"])
reg("surface", "floor")
for w in r["wall"]:
    reg("surface", w["id"])
    for it in w.get("item", []): reg("item", it["id"])
for it in r["floor"].get("item", []): reg("item", it["id"])
for b in lb["book"]: reg("book", b["id"])
for u in lb["unit"]: reg("labour_unit", u["id"])
for w in lb["work_section"]: reg("labour_work_section", w["id"])
for x in lb["rate"]: reg("rate", x["id"])
for ph in p["phase"]:
    reg("phase", ph["id"])
    for s in ph.get("step", []): reg("step", s["id"])
I = lambda k: inv.get(k, k)
READ = set()          # every table this comparison reads, to show the database holds nothing it doesn't account for
def rows(t, where="", *a, order="rowid"):
    READ.add(t)
    cur = db.execute(f"SELECT * FROM {t} {where} ORDER BY {order}", a); n = [c[0] for c in cur.description]
    return [dict(zip(n, x)) for x in cur.fetchall()]
def txt(t, kc, k, cols):
    out = {}
    for x in rows(t, f"WHERE {kc} IS ?" if kc else "", *([k] if kc else [])):
        for c, b in cols.items(): out[f"{b}_{x['lang']}" if b else x["lang"]] = x[c]
    return out
dn = lambda d: {k: v for k, v in d.items() if v is not None}
def asm(t, kc, k):
    a = [x["key"] for x in rows(t, f"WHERE {kc} IS ?" if kc else "", *([k] if kc else []))]
    hows = [x["how"] for x in rows(t, f"WHERE {kc} IS ?" if kc else "", *([k] if kc else [])) if x["how"]]
    return ({"assumed": sorted(a)} if a else {})
def labs(part):
    l = {}
    for x in rows(f"{part}_label"): l.setdefault(x["code"], {})[x["lang"]] = x["text"]
    return l, {x["code"]: x["value"] for x in rows(f"{part}_symbol")}
def ungap(d, ref_t, owner, k):
    """Put each numbered gap back as the reference it was in the TOML, from the thing's ref rows."""
    to = {x["n"]: "{step:%s}" % I(x["to_step"]) if x["to_step"] else "{phase:%s}" % I(x["to_phase"])
          for x in rows(ref_t, f"WHERE {owner} = ?", k)}
    return {key_: re.sub(r"\{(\d+)\}", lambda mt: to.get(int(mt[1]), mt[0]), v) if isinstance(v, str) else v for key_, v in d.items()}
un = lambda d: d
P = {"section": un({**txt("phases_section_text", None, None, {"name": ""}), **txt("phases_section_note", None, None, {"note": "note"})})}
P["labels"], P["symbols"] = labs("phases"); P["phase"] = []
for ph in rows("phases_phase", order="pos"):
    e = {"id": I(ph["id"]), **txt("phases_phase_text", "phase", ph["id"], {"name": ""}),
         **ungap(txt("phases_phase_note", "phase", ph["id"], {"note": "note"}), "phases_phase_note_ref", "phase", ph["id"])}
    st = [{"id": I(s["id"]), **ungap(txt("phases_step_text", "step", s["id"], {"text": ""}), "phases_step_ref", "step", s["id"])}
          for s in rows("phases_step", "WHERE phase = ?", ph["id"], order="pos")]
    if st: e["step"] = st
    P["phase"].append(e)
M = {}; s = rows("materials_setting")[0]; M.update(prices_date=s["prices_date"], date_format=s["date_format"], round_approx=s["round_approx"])
M["section"] = {**txt("materials_section_text", None, None, {"name": ""}), **txt("materials_section_note", None, None, {"note": "note"})}
M["labels"], M["symbols"] = labs("materials")
M["shop"] = [{"id": I(x["id"]), **txt("materials_shop_text", "shop", x["id"], {"name": ""}), "sku": x["sku_pattern"], "link": x["link"]} for x in rows("materials_shop", order="pos")]
M["unit"] = [{"id": I(u["id"]), **txt("materials_unit_text", "unit", u["id"], {"name": ""}), "en_many": rows("materials_unit_plural", "WHERE unit=? AND lang='en'", u["id"])[0]["many"]} for u in rows("materials_unit", order="pos")]
M["work_section"] = [{"id": I(w["id"]), **txt("materials_work_section_text", "work_section", w["id"], {"name": ""}), **txt("materials_work_section_note", "work_section", w["id"], {"note": "note"})} for w in rows("materials_work_section", order="pos")]
M["entry"] = []
for x in rows("materials_product", order="pos"):
    e = {"id": I(x["id"]), **txt("materials_product_text", "product", x["id"], {"name": "", "detail": "detail"})}
    sz = dn({k: x[k] for k in "whd"})
    if sz: e["size"] = sz
    e.update(dn({"per_box": x["per_box"], "ip": x["ip"], "price": x["price"]}))
    if x["electrical"]: e["electrical"] = True
    if x["approx"]: e["approx"] = True
    e["unit"] = I(x["unit"])
    sh = rows("materials_product_shop", "WHERE product=?", x["id"])
    if sh: e.update(shop=I(sh[0]["shop"]), sku=sh[0]["sku"])
    e.update(asm("materials_product_assumed", "product", x["id"]))
    e["line"] = [{"work_section": I(l["work_section"]), "status": l["status"], "n": l["n"],
                  **txt("materials_line_note", "line", l["id"], {"note": "note"}), **txt("materials_line_by", "line", l["id"], {"who": "by"})}
                 for l in rows("materials_line", "WHERE product=?", x["id"], order="pos")]
    M["entry"].append(e)
R = {}; rr = rows("room_room")[0]; R["room"] = {k: rr[k] for k in ("length", "width", "ceiling", "joint_clearance")}
R["labels"], R["symbols"] = labs("room")
R["tile"] = [{"id": I(t["id"]), "product": I(t["product"]), **txt("room_tile_text", "tile", t["id"], {"name": ""}), "tiling_height": t["tiling_height"], "fill": t["fill"]} for t in rows("room_tile", order="pos")]
SH = ("rect", "circle", "point", "zone", "opening", "step")
def items(surf):
    out = []
    for it in rows("room_item", "WHERE surface=?", surf, order="pos"):
        shape, geo = next((s, rows(f"room_item_{s}", "WHERE item=?", it["id"])) for s in SH if rows(f"room_item_{s}", "WHERE item=?", it["id"]))
        g = dn({k: v for k, v in geo[0].items() if k != "item"})
        e = {"id": I(it["id"]), **({"product": I(it["product"])} if it["product"] else {}), **txt("room_item_name", "item", it["id"], {"name": ""}), "shape": shape,
             **{k: g[k] for k in ("x", "y", "w", "h", "d", "high") if k in g}, **({"fitting": I(it["fitting"])} if it["fitting"] else {}),
             **txt("room_item_note", "item", it["id"], {"note": "note"}), **({"waterproofing": g["waterproofing"]} if "waterproofing" in g else {}),
             **asm("room_item_assumed", "item", it["id"])}
        out.append(e)
    return out
fsurf = rows("room_surface", "WHERE kind='floor'")[0]; fl = rows("room_floor")[0]
R["floor"] = {"ref": fsurf["ref"], "tile": I(fsurf["tile"]), "drain": I(fl["drain"]), "fall_wet": fl["fall_wet"], "fall_dry": fl["fall_dry"], **asm("room_floor_assumed", None, None)}
fi = items(fsurf["id"]);  R["floor"].update({"item": fi} if fi else {})
R["wall"] = []
for sf in rows("room_surface", "WHERE kind='wall'", order="pos"):
    w = rows("room_wall", "WHERE surface=?", sf["id"])[0]
    e = {"id": I(sf["id"]), **txt("room_wall_text", "wall", sf["id"], {"name": ""}), "ref": sf["ref"], "tile": I(sf["tile"]), "waterproofing": w["waterproofing"],
         "elevation": bool(w["elevation"]), **asm("room_wall_assumed", "wall", sf["id"])}
    wi = items(sf["id"]); e.update({"item": wi} if wi else {}); R["wall"].append(e)
c = rows("room_column")[0]
R["column"] = {**txt("room_column_text", None, None, {"name": ""}), **txt("room_column_note", None, None, {"note": "note"}), "width": c["width"], "depth": c["depth"], "into_room": c["into_room"], "wall": I(c["wall"])}
d = rows("room_door")[0]; R["door"] = {"product": I(d["product"]), "hinge": d["hinge"], "swing": d["swing"], **txt("room_door_note", None, None, {"note": "note"})}
l = rows("room_lintel")[0]; R["lintel"] = {"product": I(l["product"]), "bearing": l["bearing"], **txt("room_lintel_note", None, None, {"note": "note"})}
R["norm"] = [{"id": n["code"], **txt("room_norm_text", "norm", n["code"], {"name": ""}), **({"item": I(n["item"])} if n["item"] else {}), "value": n["value"], "standard": n["standard"], "url": n["url"], "checked": n["checked"]} for n in rows("room_norm", order="pos")]
L = {}; s = rows("labour_setting")[0]; L.update(date_format=s["date_format"], round_approx=s["round_approx"])
L["section"] = {**txt("labour_section_text", None, None, {"name": ""}), **txt("labour_section_note", None, None, {"note": "note"})}
L["labels"], L["symbols"] = labs("labour")
f = rows("labour_factor_f")[0]; L["factor_f"] = {**txt("labour_factor_f_text", None, None, {"name": ""}), **{k: f[k] for k in ("value", "standard", "url", "checked")}}
L["book"] = []
for b in rows("labour_book", order="pos"):
    e = {"id": I(b["id"]), **txt("labour_book_text", "book", b["id"], {"name": "", "item_format": "item"}), **dn({k: b[k] for k in ("standard", "url", "published", "official", "file", "checked")})}
    if b["bare"]: e["bare"] = True
    L["book"].append(e)
L["unit"] = [{"id": I(u["id"]), **txt("labour_unit_text", "unit", u["id"], {"name": ""}), "en_many": rows("labour_unit_plural", "WHERE unit=? AND lang='en'", u["id"])[0]["many"]} for u in rows("labour_unit", order="pos")]
L["work_section"] = [{"id": I(w["id"]), **txt("labour_work_section_text", "work_section", w["id"], {"name": ""}), **txt("labour_work_section_note", "work_section", w["id"], {"note": "note"})} for w in rows("labour_work_section", order="pos")]
L["rate"] = [{"id": I(x["id"]), **txt("labour_rate_text", "rate", x["id"], {"name": ""}), "unit": I(x["unit"]), "rate": x["rate"], **({"book": I(x["book"])} if x["book"] else {}),
              **dn({k: x[k] for k in ("item", "book_note", "page", "url")}), **asm("labour_rate_assumed", "rate", x["id"])} for x in rows("labour_rate", order="pos")]
L["line"] = []
for x in rows("labour_line", order="pos"):
    e = {"rate": I(x["rate"]), "work_section": I(x["work_section"])}
    for t, col in (("labour_line_take_off", "take_off"), ("labour_line_n", "n")):
        g = rows(t, "WHERE line=?", x["id"])
        if g: e[col] = g[0][col]; e.update({"times": g[0]["times"]} if g[0]["times"] else {})
    g = rows("labour_line_count", "WHERE line=?", x["id"])
    if g:
        e["count"] = [I(y["product"]) for y in rows("labour_line_count_product", "WHERE line=?", x["id"])]   # rowid = dump order
        e.update({"times": g[0]["times"]} if g[0]["times"] else {})
    sh = [I(y["product"]) for y in rows("labour_line_share_product", "WHERE line=?", x["id"])]
    if sh: e["of_products"] = sh
    e.update(txt("labour_line_note", "line", x["id"], {"note": "note"})); e.update(asm("labour_line_assumed", "line", x["id"]))
    L["line"].append(e)
def norm(v):
    if isinstance(v, datetime.date): return v.isoformat()
    if isinstance(v, bool): return int(v)
    if isinstance(v, dict): return {k: norm(x) for k, x in v.items()}
    if isinstance(v, list): return [norm(x) for x in v]
    return v
def diff(a, b, path=""):
    a, b, out = norm(a), norm(b), []
    if path.endswith(".assumed") and isinstance(a, list):     # a set: no order to keep
        a = sorted(a)
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in b: out.append(f"{path}.{k}: in TOML only ({a[k]!r:.70})")
            elif k not in a: out.append(f"{path}.{k}: in DB only ({b[k]!r:.70})")
            else: out += diff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b): out.append(f"{path}: {len(a)} vs {len(b)}")
        out += [x for i, (p_, q) in enumerate(zip(a, b)) for x in diff(p_, q, f"{path}[{i}]")]
    elif a != b: out.append(f"{path}: TOML {a!r:.70} vs DB {b!r:.70}")
    return out
tot = 0
for name, rebuilt in (("phases", P), ("materials", M), ("room", R), ("labour", L)):
    found = diff(raw[name], rebuilt, name); tot += len(found)
    print(f"{name}: {len(found)}"); [print("  ", x) for x in found[:15]]
print("total", tot, "differences between the TOML and the data rebuilt from the SQL files")
# the other way: nothing in the database that the TOML doesn't account for, except what the design adds on purpose
DESIGN_ONLY = {"language": "the languages, in order",
               "materials_status": "the statuses and their flags (materials.STATUS today)",
               "room_take_off": "the take-offs room.py works out, with their measure",
               "labour_line_share": "a share line's own row (its products are compared)",
               "labour_line_count": "a count line's own row, with times (its products are compared)"}
unread = [t for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY rowid")
          if t not in READ and db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]]
extra = [t for t in unread if t not in DESIGN_ONLY]
for t in unread:
    print(f"   not from the TOML: {t} ({db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]} rows) — {DESIGN_ONLY.get(t, 'UNACCOUNTED FOR')}")
tot += len(extra)
# labels, symbols and assumed keys are looked up by name, so they have no order to keep (compared as sets above)
print("'how' filled:", db.execute("SELECT count(*) FROM (SELECT how FROM materials_product_assumed UNION ALL SELECT how FROM room_item_assumed UNION ALL SELECT how FROM room_wall_assumed UNION ALL SELECT how FROM room_floor_assumed UNION ALL SELECT how FROM labour_rate_assumed UNION ALL SELECT how FROM labour_line_assumed) WHERE how IS NOT NULL").fetchone()[0])
if tot: sys.exit(1)
