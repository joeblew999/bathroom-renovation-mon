-- materials.schema.sql — the materials list: every product once, its lines, the shops, units and work sections.

CREATE TABLE materials_setting (
  id INTEGER PRIMARY KEY CONSTRAINT "the settings are one row" CHECK (id = 1),
  prices_date  TEXT NOT NULL CONSTRAINT "prices_date is a date, YYYY-MM-DD" CHECK (date(prices_date) IS prices_date),
  date_format  TEXT NOT NULL,
  round_approx INTEGER NOT NULL CONSTRAINT "round_approx is more than 0" CHECK (round_approx > 0)
) STRICT;
CREATE TABLE materials_section_text (lang TEXT PRIMARY KEY REFERENCES language(code), name TEXT NOT NULL) STRICT;
CREATE TABLE materials_section_note (lang TEXT PRIMARY KEY REFERENCES language(code), note TEXT NOT NULL) STRICT;
CREATE TABLE materials_label  (code TEXT NOT NULL, lang TEXT NOT NULL REFERENCES language(code), text TEXT NOT NULL,
                               PRIMARY KEY (code, lang)) STRICT;
CREATE TABLE materials_symbol (code TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;

-- a unit: what it measures (a code), its name, and its form for more than 1 where a language has one
CREATE TABLE materials_unit (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (id GLOB '[0-9a-f]*' AND length(id) = 16),
  pos INTEGER NOT NULL UNIQUE,
  measure TEXT NOT NULL CONSTRAINT "a material is counted or bought by length" CHECK (measure IN ('count', 'length'))
) STRICT;
CREATE TABLE materials_unit_text (unit TEXT NOT NULL REFERENCES materials_unit(id), lang TEXT NOT NULL REFERENCES language(code),
                                  name TEXT NOT NULL, PRIMARY KEY (unit, lang)) STRICT;
CREATE TABLE materials_unit_plural (unit TEXT NOT NULL REFERENCES materials_unit(id), lang TEXT NOT NULL REFERENCES language(code),
                                    many TEXT NOT NULL, PRIMARY KEY (unit, lang)) STRICT;

CREATE TABLE materials_shop (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (id GLOB '[0-9a-f]*' AND length(id) = 16),
  pos INTEGER NOT NULL UNIQUE,
  sku_pattern TEXT NOT NULL,        -- what a product code at this shop looks like (a regular expression)
  link TEXT NOT NULL                -- a product's page, with {sku} or {sku_digits}
) STRICT;
CREATE TABLE materials_shop_text (shop TEXT NOT NULL REFERENCES materials_shop(id), lang TEXT NOT NULL REFERENCES language(code),
                                  name TEXT NOT NULL, PRIMARY KEY (shop, lang)) STRICT;

CREATE TABLE materials_work_section (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (id GLOB '[0-9a-f]*' AND length(id) = 16),
  pos INTEGER NOT NULL UNIQUE
) STRICT;
CREATE TABLE materials_work_section_text (work_section TEXT NOT NULL REFERENCES materials_work_section(id),
  lang TEXT NOT NULL REFERENCES language(code), name TEXT NOT NULL, PRIMARY KEY (work_section, lang)) STRICT;
CREATE TABLE materials_work_section_note (work_section TEXT NOT NULL REFERENCES materials_work_section(id),
  lang TEXT NOT NULL REFERENCES language(code), note TEXT NOT NULL, PRIMARY KEY (work_section, lang)) STRICT;

-- a status (a code): what it means; their order is the order within a work section
CREATE TABLE materials_status (
  code TEXT PRIMARY KEY,
  pos INTEGER NOT NULL UNIQUE,
  to_buy   INTEGER NOT NULL CONSTRAINT "to_buy is 0 or 1"   CHECK (to_buy IN (0, 1)),
  paid     INTEGER NOT NULL CONSTRAINT "paid is 0 or 1"     CHECK (paid IN (0, 1)),
  on_site  INTEGER NOT NULL CONSTRAINT "on_site is 0 or 1"  CHECK (on_site IN (0, 1)),
  by_trade INTEGER NOT NULL CONSTRAINT "by_trade is 0 or 1" CHECK (by_trade IN (0, 1))
) STRICT;

CREATE TABLE materials_product (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (id GLOB '[0-9a-f]*' AND length(id) = 16),
  pos INTEGER NOT NULL UNIQUE,
  w REAL CONSTRAINT "a product's w is more than 0" CHECK (w IS NULL OR (w > 0 AND w < 1e308)),
  h REAL CONSTRAINT "a product's h is more than 0" CHECK (h IS NULL OR (h > 0 AND h < 1e308)),
  d REAL CONSTRAINT "a product's d is more than 0" CHECK (d IS NULL OR (d > 0 AND d < 1e308)),
  per_box INTEGER CONSTRAINT "per_box is more than 0" CHECK (per_box IS NULL OR per_box > 0),
  electrical INTEGER NOT NULL CONSTRAINT "electrical is 0 or 1" CHECK (electrical IN (0, 1)),
  ip TEXT CONSTRAINT "only an electrical product has an IP rating" CHECK (ip IS NULL OR electrical = 1),
  unit TEXT NOT NULL REFERENCES materials_unit(id),
  price REAL CONSTRAINT "a price is 0 or more" CHECK (price IS NULL OR (price >= 0 AND price < 1e308)),
  approx INTEGER NOT NULL CONSTRAINT "approx is 0 or 1, and 1 only with a price" CHECK (approx IN (0, 1) AND (approx = 0 OR price IS NOT NULL))
) STRICT;
-- its name and detail; the detail shows its size with {w}, {w_cm} …
CREATE TABLE materials_product_text (product TEXT NOT NULL REFERENCES materials_product(id), lang TEXT NOT NULL REFERENCES language(code),
                                     name TEXT NOT NULL, detail TEXT NOT NULL, PRIMARY KEY (product, lang)) STRICT;
-- where it is bought: a shop and its code there come together, as one row
CREATE TABLE materials_product_shop (product TEXT PRIMARY KEY REFERENCES materials_product(id),
                                     shop TEXT NOT NULL REFERENCES materials_shop(id), sku TEXT NOT NULL) STRICT;
CREATE TABLE materials_product_assumed (product TEXT NOT NULL REFERENCES materials_product(id),
  key TEXT NOT NULL CONSTRAINT "a product's assumed key is one of its values" CHECK (key IN ('w', 'h', 'd', 'per_box', 'ip', 'price')),
  how TEXT,                         -- how to find the real value (for whoever measures it; not printed)
  PRIMARY KEY (product, key)) STRICT;

-- a line on the materials list: a product, in a work section, with a status
CREATE TABLE materials_line (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (id GLOB '[0-9a-f]*' AND length(id) = 16),
  pos INTEGER NOT NULL UNIQUE,
  product TEXT NOT NULL REFERENCES materials_product(id),
  work_section TEXT NOT NULL REFERENCES materials_work_section(id),
  status TEXT NOT NULL REFERENCES materials_status(code),
  n REAL NOT NULL CONSTRAINT "a line's n is more than 0" CHECK (n > 0 AND n < 1e308),
  CONSTRAINT "a product has one line per work section and status" UNIQUE (product, work_section, status)
) STRICT;
CREATE TABLE materials_line_note (line TEXT NOT NULL REFERENCES materials_line(id), lang TEXT NOT NULL REFERENCES language(code),
                                  note TEXT NOT NULL, PRIMARY KEY (line, lang)) STRICT;
-- who brings it, on a line the trade supplies
CREATE TABLE materials_line_by (line TEXT NOT NULL REFERENCES materials_line(id), lang TEXT NOT NULL REFERENCES language(code),
                                who TEXT NOT NULL, PRIMARY KEY (line, lang)) STRICT;

CREATE VIEW check_materials_rows AS
  SELECT t || ' has no row' FROM (
    SELECT 'materials_setting' t, (SELECT count(*) FROM materials_setting) n UNION ALL
    SELECT 'materials_section_text', (SELECT count(*) FROM materials_section_text) UNION ALL
    SELECT 'materials_shop', (SELECT count(*) FROM materials_shop) UNION ALL
    SELECT 'materials_unit', (SELECT count(*) FROM materials_unit) UNION ALL
    SELECT 'materials_work_section', (SELECT count(*) FROM materials_work_section) UNION ALL
    SELECT 'materials_status', (SELECT count(*) FROM materials_status) UNION ALL
    SELECT 'materials_product', (SELECT count(*) FROM materials_product)) WHERE n = 0;
CREATE VIEW check_materials_product_has_a_line AS
  SELECT 'product ' || id || ' has no line, so it isn''t on the list' FROM materials_product
  WHERE id NOT IN (SELECT product FROM materials_line);
CREATE VIEW check_materials_status_price AS
  SELECT 'product ' || p.id || ' is ' || s.code || CASE WHEN s.to_buy THEN ', so it needs a price' ELSE ', so it has no price' END
  FROM materials_line l JOIN materials_product p ON p.id = l.product JOIN materials_status s ON s.code = l.status
  WHERE (s.to_buy AND p.price IS NULL) OR (NOT s.to_buy AND NOT s.paid AND p.price IS NOT NULL);
CREATE VIEW check_materials_status_shop AS
  SELECT 'product ' || l.product || ' is ' || s.code ||
         CASE WHEN s.to_buy OR s.paid THEN ', so it needs a shop and its code' ELSE ', so it has no shop' END
  FROM materials_line l JOIN materials_status s ON s.code = l.status
  WHERE (s.to_buy OR s.paid) IS NOT (l.product IN (SELECT product FROM materials_product_shop));
CREATE VIEW check_materials_status_by AS
  SELECT 'line ' || l.id || ' is ' || s.code ||
         CASE WHEN s.by_trade THEN ', so it says who brings it' ELSE ', so it doesn''t say who brings it' END
  FROM materials_line l JOIN materials_status s ON s.code = l.status
  WHERE s.by_trade IS NOT (l.id IN (SELECT line FROM materials_line_by));

-- ---------- for reading: the materials list as people say it (following the foreign keys to the names)
CREATE VIEW show_materials_line AS
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
