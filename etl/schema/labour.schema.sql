-- labour.schema.sql — the labour: rate books, rates, and the lines priced from the room and the materials list.

CREATE TABLE labour_setting (
  id INTEGER PRIMARY KEY CONSTRAINT "the settings are one row" CHECK (id = 1),
  date_format TEXT NOT NULL,
  round_approx INTEGER NOT NULL CONSTRAINT "round_approx is more than 0" CHECK (round_approx > 0)
) STRICT;
CREATE TABLE labour_section_text (lang TEXT PRIMARY KEY REFERENCES language(code), name TEXT NOT NULL) STRICT;
CREATE TABLE labour_section_note (lang TEXT PRIMARY KEY REFERENCES language(code), note TEXT NOT NULL) STRICT;
CREATE TABLE labour_label  (code TEXT NOT NULL, lang TEXT NOT NULL REFERENCES language(code), text TEXT NOT NULL,
                            PRIMARY KEY (code, lang)) STRICT;
CREATE TABLE labour_symbol (code TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;

-- the Comptroller General's multiplier for a contractor's overhead, profit and interest on bare cost
CREATE TABLE labour_factor_f (
  id INTEGER PRIMARY KEY CONSTRAINT "Factor F is one row" CHECK (id = 1),
  value REAL NOT NULL CONSTRAINT "Factor F is 1 or more" CHECK (value >= 1 AND value < 1e308),
  standard TEXT NOT NULL, url TEXT NOT NULL,
  checked TEXT NOT NULL CONSTRAINT "Factor F's checked is a date, YYYY-MM-DD" CHECK (date(checked) IS checked),
  remark TEXT                       -- for editors (not printed): the choice made, and when to change it
) STRICT;
CREATE TABLE labour_factor_f_text (lang TEXT PRIMARY KEY REFERENCES language(code), name TEXT NOT NULL) STRICT;

-- a rate book; a kept copy (file) comes with the page that publishes it
CREATE TABLE labour_book (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (length(id) = 16 AND id NOT GLOB '*[^0-9a-f]*'),
  pos INTEGER NOT NULL UNIQUE,
  standard TEXT NOT NULL, url TEXT NOT NULL, published TEXT, official TEXT, file TEXT,
  checked TEXT NOT NULL CONSTRAINT "a book's checked is a date, YYYY-MM-DD" CHECK (date(checked) IS checked),
  bare INTEGER NOT NULL CONSTRAINT "bare is 0 or 1" CHECK (bare IN (0, 1)),
  remark TEXT,                      -- for editors (not printed): how to take in a new edition
  CONSTRAINT "a kept copy comes with the page that publishes it" CHECK (file IS NULL OR published IS NOT NULL)
) STRICT;
-- a book's name, and how a rate names its place in it ({item})
CREATE TABLE labour_book_text (book TEXT NOT NULL REFERENCES labour_book(id), lang TEXT NOT NULL REFERENCES language(code),
                               name TEXT NOT NULL, item_format TEXT NOT NULL, PRIMARY KEY (book, lang)) STRICT;

-- a unit a rate is priced by, and what it measures (a code)
CREATE TABLE labour_unit (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (length(id) = 16 AND id NOT GLOB '*[^0-9a-f]*'),
  pos INTEGER NOT NULL UNIQUE,
  measure TEXT NOT NULL CONSTRAINT "a labour unit measures an area, a length, a count, a job or a share"
                        CHECK (measure IN ('area', 'length', 'count', 'job', 'share'))
) STRICT;
CREATE TABLE labour_unit_text (unit TEXT NOT NULL REFERENCES labour_unit(id), lang TEXT NOT NULL REFERENCES language(code),
                               name TEXT NOT NULL, PRIMARY KEY (unit, lang)) STRICT;
CREATE TABLE labour_unit_plural (unit TEXT NOT NULL REFERENCES labour_unit(id), lang TEXT NOT NULL REFERENCES language(code),
                                 many TEXT NOT NULL, PRIMARY KEY (unit, lang)) STRICT;
CREATE TABLE labour_work_section (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (length(id) = 16 AND id NOT GLOB '*[^0-9a-f]*'),
  pos INTEGER NOT NULL UNIQUE
) STRICT;
CREATE TABLE labour_work_section_text (work_section TEXT NOT NULL REFERENCES labour_work_section(id),
  lang TEXT NOT NULL REFERENCES language(code), name TEXT NOT NULL, PRIMARY KEY (work_section, lang)) STRICT;
CREATE TABLE labour_work_section_note (work_section TEXT NOT NULL REFERENCES labour_work_section(id),
  lang TEXT NOT NULL REFERENCES language(code), note TEXT NOT NULL, PRIMARY KEY (work_section, lang)) STRICT;

-- a rate: from a book (its item, or a note in it; the page in a kept copy, or the book's own page) or none
CREATE TABLE labour_rate (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (length(id) = 16 AND id NOT GLOB '*[^0-9a-f]*'),
  pos INTEGER NOT NULL UNIQUE,
  unit TEXT NOT NULL REFERENCES labour_unit(id),
  rate REAL NOT NULL CONSTRAINT "a rate is 0 or more" CHECK (rate >= 0 AND rate < 1e308),
  book TEXT REFERENCES labour_book(id),
  item TEXT,
  book_note INTEGER CONSTRAINT "a book note is more than 0" CHECK (book_note IS NULL OR book_note > 0),
  page INTEGER CONSTRAINT "a page is more than 0" CHECK (page IS NULL OR page > 0),
  url TEXT,
  CONSTRAINT "a rate from a book gives its item or a note, not both; a rate from no book gives neither"
    CHECK (CASE WHEN book IS NULL THEN item IS NULL AND book_note IS NULL AND page IS NULL AND url IS NULL
                ELSE (item IS NULL) IS NOT (book_note IS NULL) END)
) STRICT;
CREATE TABLE labour_rate_text (rate TEXT NOT NULL REFERENCES labour_rate(id), lang TEXT NOT NULL REFERENCES language(code),
                               name TEXT NOT NULL, PRIMARY KEY (rate, lang)) STRICT;
CREATE TABLE labour_rate_assumed (rate TEXT NOT NULL REFERENCES labour_rate(id),
  key TEXT NOT NULL CONSTRAINT "a rate's assumed key is one of its values" CHECK (key IN ('rate')),
  how TEXT, PRIMARY KEY (rate, key)) STRICT;

-- a line: a rate in a work section; its quantity comes from exactly one source, in the tables below
CREATE TABLE labour_line (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (length(id) = 16 AND id NOT GLOB '*[^0-9a-f]*'),
  pos INTEGER NOT NULL UNIQUE,
  rate TEXT NOT NULL REFERENCES labour_rate(id),
  work_section TEXT NOT NULL REFERENCES labour_work_section(id)
) STRICT;
-- from the room's take-off (a link to the room, README rule 6) …
CREATE TABLE labour_line_take_off (line TEXT PRIMARY KEY REFERENCES labour_line(id),
  take_off TEXT NOT NULL REFERENCES room_take_off(code),
  times INTEGER CONSTRAINT "times is more than 0" CHECK (times IS NULL OR times > 0)) STRICT;
-- … a number of sets …
CREATE TABLE labour_line_n (line TEXT PRIMARY KEY REFERENCES labour_line(id),
  n REAL NOT NULL CONSTRAINT "a line's n is more than 0" CHECK (n > 0 AND n < 1e308),
  times INTEGER CONSTRAINT "times is more than 0" CHECK (times IS NULL OR times > 0)) STRICT;
-- … a count of products on the materials list (a link to the list, README rule 6) …
CREATE TABLE labour_line_count (line TEXT PRIMARY KEY REFERENCES labour_line(id),
  times INTEGER CONSTRAINT "times is more than 0" CHECK (times IS NULL OR times > 0)) STRICT;
CREATE TABLE labour_line_count_product (line TEXT NOT NULL REFERENCES labour_line_count(line), pos INTEGER NOT NULL,
  product TEXT NOT NULL REFERENCES materials_product(id), PRIMARY KEY (line, product), UNIQUE (line, pos)) STRICT;
-- … or a share of what products on it still cost
CREATE TABLE labour_line_share_product (line TEXT NOT NULL REFERENCES labour_line(id), pos INTEGER NOT NULL,
  product TEXT NOT NULL REFERENCES materials_product(id), PRIMARY KEY (line, product), UNIQUE (line, pos)) STRICT;
CREATE TABLE labour_line_note (line TEXT NOT NULL REFERENCES labour_line(id), lang TEXT NOT NULL REFERENCES language(code),
                               note TEXT NOT NULL, PRIMARY KEY (line, lang)) STRICT;
CREATE TABLE labour_line_assumed (line TEXT NOT NULL REFERENCES labour_line(id),
  key TEXT NOT NULL CONSTRAINT "a line's assumed key is one of its values" CHECK (key IN ('n', 'take_off')),
  how TEXT, PRIMARY KEY (line, key)) STRICT;

CREATE VIEW labour_line_source AS    -- each line's source, from the table it is in
  SELECT line, 'take_off' AS source FROM labour_line_take_off UNION ALL SELECT line, 'n' FROM labour_line_n UNION ALL
  SELECT line, 'count' FROM labour_line_count UNION ALL SELECT DISTINCT line, 'share' FROM labour_line_share_product;

CREATE VIEW check_labour_rows AS
  SELECT t || ' has ' || n || ' rows, not 1' FROM (
    SELECT 'labour_setting' t, (SELECT count(*) FROM labour_setting) n UNION ALL
    SELECT 'labour_factor_f', (SELECT count(*) FROM labour_factor_f)) WHERE n <> 1
  UNION ALL SELECT t || ' has no row' FROM (
    SELECT 'labour_book' t, (SELECT count(*) FROM labour_book) n UNION ALL
    SELECT 'labour_unit', (SELECT count(*) FROM labour_unit) UNION ALL
    SELECT 'labour_work_section', (SELECT count(*) FROM labour_work_section) UNION ALL
    SELECT 'labour_rate', (SELECT count(*) FROM labour_rate) UNION ALL
    SELECT 'labour_line', (SELECT count(*) FROM labour_line)) WHERE n = 0;
CREATE VIEW check_labour_line_one_source AS
  SELECT 'line ' || l.id || ' takes its quantity from ' || count(s.line) || ' sources, not 1'
  FROM labour_line l LEFT JOIN labour_line_source s ON s.line = l.id GROUP BY l.id HAVING count(s.line) <> 1;
CREATE VIEW check_labour_count_has_products AS
  SELECT 'line ' || line || ' counts no products' FROM labour_line_count WHERE line NOT IN (SELECT line FROM labour_line_count_product);
CREATE VIEW check_labour_rate_without_book AS
  SELECT 'rate ' || id || ' has no book, so its rate must be marked assumed' FROM labour_rate
  WHERE book IS NULL AND id NOT IN (SELECT rate FROM labour_rate_assumed WHERE key = 'rate');
CREATE VIEW check_labour_rate_where_in_book AS
  SELECT 'rate ' || r.id || CASE WHEN b.file IS NOT NULL THEN ' is from a kept copy, so it gives its page and no url'
                                 ELSE ' is from a book with no copy, so it gives its url and no page' END
  FROM labour_rate r JOIN labour_book b ON b.id = r.book
  WHERE (b.file IS NOT NULL AND (r.page IS NULL OR r.url IS NOT NULL)) OR (b.file IS NULL AND (r.url IS NULL OR r.page IS NOT NULL));
-- what each source needs the rate's unit to measure
CREATE VIEW check_labour_line_measure AS
  SELECT 'line ' || l.id || ' is priced by a rate that measures ' || u.measure || ', but its quantity is ' || need.measure
  FROM labour_line l JOIN labour_rate r ON r.id = l.rate JOIN labour_unit u ON u.id = r.unit JOIN (
    SELECT t.line, k.measure FROM labour_line_take_off t JOIN room_take_off k ON k.code = t.take_off
    UNION ALL SELECT c.line, CASE WHEN min(mu.measure) = 'length' AND max(mu.measure) = 'length' THEN 'length' ELSE 'count' END
      FROM labour_line_count_product c JOIN materials_product p ON p.id = c.product JOIN materials_unit mu ON mu.id = p.unit GROUP BY c.line
    UNION ALL SELECT DISTINCT line, 'share' FROM labour_line_share_product) need ON need.line = l.id
  WHERE u.measure IS NOT need.measure
  -- a plain number (n) can be of any unit but a share
  UNION ALL SELECT 'line ' || n.line || ' gives a number, so its rate can''t be a share'
  FROM labour_line_n n JOIN labour_line l ON l.id = n.line JOIN labour_rate r ON r.id = l.rate JOIN labour_unit u ON u.id = r.unit
  WHERE u.measure = 'share';

-- ---------- for reading: every labour line as people say it
CREATE VIEW show_labour_line AS
  SELECT l.pos, ws.name AS work_section, rt.name AS rate_name, r.rate, ut.name AS unit, src.source,
         coalesce(t.take_off, n.n, (SELECT group_concat(pt.name, ', ') FROM labour_line_count_product cp
                                    JOIN materials_product_text pt ON pt.product = cp.product AND pt.lang = 'en' WHERE cp.line = l.id),
                  (SELECT group_concat(pt.name, ', ') FROM labour_line_share_product sp
                   JOIN materials_product_text pt ON pt.product = sp.product AND pt.lang = 'en' WHERE sp.line = l.id)) AS quantity_from,
         coalesce(t.times, n.times, c.times) AS times, nt.note
  FROM labour_line l JOIN labour_rate r ON r.id = l.rate
  JOIN labour_rate_text rt ON rt.rate = r.id AND rt.lang = 'en'
  JOIN labour_unit_text ut ON ut.unit = r.unit AND ut.lang = 'en'
  JOIN labour_work_section_text ws ON ws.work_section = l.work_section AND ws.lang = 'en'
  LEFT JOIN labour_line_source src ON src.line = l.id
  LEFT JOIN labour_line_take_off t ON t.line = l.id LEFT JOIN labour_line_n n ON n.line = l.id
  LEFT JOIN labour_line_count c ON c.line = l.id
  LEFT JOIN labour_line_note nt ON nt.line = l.id AND nt.lang = 'en';
