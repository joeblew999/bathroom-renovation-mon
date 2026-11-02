CREATE TABLE materials_setting (
  -- the materials part — the materials list: every product once, its lines, the shops, units and work sections.
  id INTEGER PRIMARY KEY CONSTRAINT "the settings are one row" CHECK (id = 1),
  prices_date  TEXT NOT NULL CONSTRAINT "prices_date is a date, YYYY-MM-DD" CHECK (date(prices_date) IS prices_date),
  date_format  TEXT NOT NULL CONSTRAINT "date_format isn't empty" CHECK (date_format <> ''),
  round_approx INTEGER NOT NULL CONSTRAINT "round_approx is more than 0" CHECK (round_approx > 0)
) STRICT;
CREATE TABLE materials_section_text (lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') PRIMARY KEY REFERENCES common_language(code), name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL) STRICT;
CREATE TABLE materials_section_note (lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') PRIMARY KEY REFERENCES common_language(code), note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL) STRICT;
CREATE TABLE materials_label  (code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') NOT NULL, lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code), text TEXT CONSTRAINT "text isn't empty" CHECK (text <> '') NOT NULL,
                               PRIMARY KEY (code, lang)) STRICT;
CREATE TABLE materials_symbol (code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') PRIMARY KEY, value TEXT CONSTRAINT "value isn't empty" CHECK (value <> '') NOT NULL) STRICT;

CREATE TABLE materials_unit (
  -- a unit: what it measures (a code), its name, and its form for more than 1 where a language has one
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE,
  measure TEXT CONSTRAINT "measure isn't empty" CHECK (measure <> '') NOT NULL CONSTRAINT "a material is counted or bought by length" CHECK (measure IN ('count', 'length'))
) STRICT;
CREATE TABLE materials_unit_text (unit TEXT CONSTRAINT "unit isn't empty" CHECK (unit <> '') NOT NULL REFERENCES materials_unit(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                                  name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, PRIMARY KEY (unit, lang)) STRICT;
CREATE TABLE materials_unit_plural (unit TEXT CONSTRAINT "unit isn't empty" CHECK (unit <> '') NOT NULL REFERENCES materials_unit(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                                    many TEXT CONSTRAINT "many isn't empty" CHECK (many <> '') NOT NULL, PRIMARY KEY (unit, lang)) STRICT;

CREATE TABLE materials_shop (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE,
  sku_pattern TEXT CONSTRAINT "sku_pattern isn't empty" CHECK (sku_pattern <> '') NOT NULL,        -- what a product code at this shop looks like (a regular expression)
  link TEXT CONSTRAINT "link isn't empty" CHECK (link <> '') NOT NULL                -- a product's page, with {sku} or {sku_digits}
) STRICT;
CREATE TABLE materials_shop_text (shop TEXT CONSTRAINT "shop isn't empty" CHECK (shop <> '') NOT NULL REFERENCES materials_shop(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                                  name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, PRIMARY KEY (shop, lang)) STRICT;

CREATE TABLE materials_work_section (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE
) STRICT;
CREATE TABLE materials_work_section_text (work_section TEXT CONSTRAINT "work_section isn't empty" CHECK (work_section <> '') NOT NULL REFERENCES materials_work_section(id),
  lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code), name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, PRIMARY KEY (work_section, lang)) STRICT;
CREATE TABLE materials_work_section_note (work_section TEXT CONSTRAINT "work_section isn't empty" CHECK (work_section <> '') NOT NULL REFERENCES materials_work_section(id),
  lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code), note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL, PRIMARY KEY (work_section, lang)) STRICT;

CREATE TABLE materials_status (
  -- a status (a code): what it means; their order is the order within a work section
  code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') PRIMARY KEY,
  pos INTEGER NOT NULL UNIQUE,
  to_buy   INTEGER NOT NULL CONSTRAINT "to_buy is 0 or 1"   CHECK (to_buy IN (0, 1)),
  paid     INTEGER NOT NULL CONSTRAINT "paid is 0 or 1"     CHECK (paid IN (0, 1)),
  on_site  INTEGER NOT NULL CONSTRAINT "on_site is 0 or 1"  CHECK (on_site IN (0, 1)),
  by_trade INTEGER NOT NULL CONSTRAINT "by_trade is 0 or 1" CHECK (by_trade IN (0, 1))
) STRICT;

CREATE TABLE materials_product (
  -- A product's kind (a code), where the room needs a particular kind in a particular place: the door is a door
  -- frame, the lintel a lintel, a tile a tile. Other products have none.
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE,
  w REAL CONSTRAINT "a product's w is more than 0" CHECK (w IS NULL OR (w > 0 AND w < 1e308)),
  h REAL CONSTRAINT "a product's h is more than 0" CHECK (h IS NULL OR (h > 0 AND h < 1e308)),
  d REAL CONSTRAINT "a product's d is more than 0" CHECK (d IS NULL OR (d > 0 AND d < 1e308)),
  per_box INTEGER CONSTRAINT "per_box is more than 0" CHECK (per_box IS NULL OR per_box > 0),
  electrical INTEGER NOT NULL CONSTRAINT "electrical is 0 or 1" CHECK (electrical IN (0, 1)),
  ip TEXT CONSTRAINT "ip isn't empty" CHECK (ip <> '') CONSTRAINT "only an electrical product has an IP rating" CHECK (ip IS NULL OR electrical = 1),
  kind TEXT CONSTRAINT "kind isn't empty" CHECK (kind <> '') CONSTRAINT "a product's kind is door_frame, lintel or tile" CHECK (kind IS NULL OR kind IN ('door_frame', 'lintel', 'tile')),
  unit TEXT CONSTRAINT "unit isn't empty" CHECK (unit <> '') NOT NULL REFERENCES materials_unit(id),
  price REAL CONSTRAINT "a price is 0 or more" CHECK (price IS NULL OR (price >= 0 AND price < 1e308)),
  approx INTEGER NOT NULL CONSTRAINT "approx is 0 or 1, and 1 only with a price" CHECK (approx IN (0, 1) AND (approx = 0 OR price IS NOT NULL))
) STRICT;
CREATE TABLE materials_product_text (
  -- Its name and detail, written to one pattern:
  --   name: the kind and the brand — Thai kind first ("ประตู AZLE"), English brand first ("AZLE door"); no brand → the
  --     kind alone. No shop codes.
  --   detail: the rest, in the same order in both: model, material, size, pack, colour, finish, then what it comes
  --     with or can do — Thai separated by spaces, English by commas. A product with a size shows it. Sizes w × h × d,
  --     with spaced ×; inches as " (Thai นิ้ว); a pack as "pack of 3" (Thai แพ็ก 3 …); a length in Thai as ยาว ….
  --     What it is for goes in a line's note, not here. The list shows "name detail" / "name, detail". Either shows
  --     the size with {w} {h} {d} in mm, {w_cm} … in cm or {w_m} … in m — never a dimension typed twice — and an
  --     electrical product its rating with {ip}.
  -- Sizes (w wide, h high, d deep; a tile is w × h) are in mm. A single figure that isn't a dimension — a weight, a
  -- volume, a stock length, an inch trade size — stays in the detail ("50 kg", "4 m", "½\"").
  product TEXT CONSTRAINT "product isn't empty" CHECK (product <> '') NOT NULL REFERENCES materials_product(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                                     name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, detail TEXT CONSTRAINT "detail isn't empty" CHECK (detail <> '') NOT NULL, PRIMARY KEY (product, lang)) STRICT;
CREATE TABLE materials_product_shop (
  -- where it is bought: a shop and its code there come together, as one row
  product TEXT CONSTRAINT "product isn't empty" CHECK (product <> '') PRIMARY KEY REFERENCES materials_product(id),
                                     shop TEXT CONSTRAINT "shop isn't empty" CHECK (shop <> '') NOT NULL REFERENCES materials_shop(id), sku TEXT CONSTRAINT "sku isn't empty" CHECK (sku <> '') NOT NULL) STRICT;
CREATE TABLE materials_product_assumed (product TEXT CONSTRAINT "product isn't empty" CHECK (product <> '') NOT NULL REFERENCES materials_product(id),
  key TEXT CONSTRAINT "key isn't empty" CHECK (key <> '') NOT NULL CONSTRAINT "a product's assumed key is one of its values" CHECK (key IN ('w', 'h', 'd', 'per_box', 'ip', 'price')),
  how TEXT CONSTRAINT "how isn't empty" CHECK (how <> '') NOT NULL,                -- how to find the real value (for whoever measures it; English; not printed)
  PRIMARY KEY (product, key)) STRICT;

CREATE TABLE materials_line (
  -- a line on the materials list: a product, in a work section, with a status
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL,
  product TEXT CONSTRAINT "product isn't empty" CHECK (product <> '') NOT NULL REFERENCES materials_product(id),
  work_section TEXT CONSTRAINT "work_section isn't empty" CHECK (work_section <> '') NOT NULL REFERENCES materials_work_section(id),
  status TEXT CONSTRAINT "status isn't empty" CHECK (status <> '') NOT NULL REFERENCES materials_status(code),
  n REAL NOT NULL CONSTRAINT "a line's n is more than 0" CHECK (n > 0 AND n < 1e308),
  CONSTRAINT "a product has one line per work section and status" UNIQUE (product, work_section, status),
  UNIQUE (product, pos)
) STRICT;
CREATE TABLE materials_line_note (line TEXT CONSTRAINT "line isn't empty" CHECK (line <> '') NOT NULL REFERENCES materials_line(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                                  note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL, PRIMARY KEY (line, lang)) STRICT;
CREATE TABLE materials_line_by (
  -- who brings it, on a line the trade supplies
  line TEXT CONSTRAINT "line isn't empty" CHECK (line <> '') NOT NULL REFERENCES materials_line(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                                who TEXT CONSTRAINT "who isn't empty" CHECK (who <> '') NOT NULL, PRIMARY KEY (line, lang)) STRICT;

CREATE VIEW materials_check_rows AS
  -- a VALUES list, not UNION ALLs: D1 allows at most 5 terms in a compound SELECT
  SELECT column1 || ' has no row' FROM (VALUES
    ('materials_setting', (SELECT count(*) FROM materials_setting)),
    ('materials_section_text', (SELECT count(*) FROM materials_section_text)),
    ('materials_shop', (SELECT count(*) FROM materials_shop)),
    ('materials_unit', (SELECT count(*) FROM materials_unit)),
    ('materials_work_section', (SELECT count(*) FROM materials_work_section)),
    ('materials_status', (SELECT count(*) FROM materials_status)),
    ('materials_product', (SELECT count(*) FROM materials_product))) WHERE column2 = 0;
CREATE VIEW materials_check_product_has_a_line AS
  SELECT 'product ' || id || ' has no line, so it isn''t on the list' FROM materials_product
  WHERE id NOT IN (SELECT product FROM materials_line);
CREATE VIEW materials_check_status_price AS
  SELECT 'product ' || p.id || ' is ' || s.code || CASE WHEN s.to_buy THEN ', so it needs a price' ELSE ', so it has no price' END
  FROM materials_line l JOIN materials_product p ON p.id = l.product JOIN materials_status s ON s.code = l.status
  WHERE (s.to_buy AND p.price IS NULL) OR (NOT s.to_buy AND NOT s.paid AND p.price IS NOT NULL);
CREATE VIEW materials_check_status_shop AS
  SELECT 'product ' || l.product || ' is ' || s.code ||
         CASE WHEN s.to_buy OR s.paid THEN ', so it needs a shop and its code' ELSE ', so it has no shop' END
  FROM materials_line l JOIN materials_status s ON s.code = l.status
  WHERE (s.to_buy OR s.paid) IS NOT (l.product IN (SELECT product FROM materials_product_shop));
CREATE VIEW materials_check_status_by AS
  SELECT 'line ' || l.id || ' is ' || s.code ||
         CASE WHEN s.by_trade THEN ', so it says who brings it' ELSE ', so it doesn''t say who brings it' END
  FROM materials_line l JOIN materials_status s ON s.code = l.status
  WHERE s.by_trade IS NOT (l.id IN (SELECT line FROM materials_line_by));

CREATE VIEW materials_show_line AS
  -- ---------- for reading: the materials list as people say it (following the foreign keys to the names)
  SELECT l.pos, ws.name AS work_section, pt.name AS product, pth.name AS product_th, l.status, l.n, ut.name AS unit,
         p.price, p.approx, st.name AS shop, ps.sku
  FROM materials_line l
  JOIN materials_product p ON p.id = l.product
  JOIN materials_product_text pt ON pt.product = p.id AND pt.lang = 'en'
  JOIN materials_product_text pth ON pth.product = p.id AND pth.lang = 'th'
  JOIN materials_work_section_text ws ON ws.work_section = l.work_section AND ws.lang = 'en'
  JOIN materials_unit_text ut ON ut.unit = p.unit AND ut.lang = 'en'
  LEFT JOIN materials_product_shop ps ON ps.product = p.id
  LEFT JOIN materials_shop_text st ON st.shop = ps.shop AND st.lang = 'en';

-- every foreign key has an index (sqlite3 .lint fkey-indexes prints nothing): links stay fast as the data grows
CREATE INDEX materials_label_lang ON materials_label(lang);
CREATE INDEX materials_line_by_lang ON materials_line_by(lang);
CREATE INDEX materials_line_note_lang ON materials_line_note(lang);
CREATE INDEX materials_line_status ON materials_line(status);
CREATE INDEX materials_line_work_section ON materials_line(work_section);
CREATE INDEX materials_product_shop_shop ON materials_product_shop(shop);
CREATE INDEX materials_product_text_lang ON materials_product_text(lang);
CREATE INDEX materials_product_unit ON materials_product(unit);
CREATE INDEX materials_shop_text_lang ON materials_shop_text(lang);
CREATE INDEX materials_unit_plural_lang ON materials_unit_plural(lang);
CREATE INDEX materials_unit_text_lang ON materials_unit_text(lang);
CREATE INDEX materials_work_section_note_lang ON materials_work_section_note(lang);
CREATE INDEX materials_work_section_text_lang ON materials_work_section_text(lang);
