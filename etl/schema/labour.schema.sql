CREATE TABLE labour_setting (
  -- the labour part — the labour: rate books, rates, and the lines priced from the room and the materials list.
  id INTEGER PRIMARY KEY CONSTRAINT "the settings are one row" CHECK (id = 1),
  date_format TEXT CONSTRAINT "date_format isn't empty" CHECK (date_format <> '') NOT NULL,
  round_approx INTEGER NOT NULL CONSTRAINT "round_approx is more than 0" CHECK (round_approx > 0)
) STRICT;
CREATE TABLE labour_section_text (lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') PRIMARY KEY REFERENCES common_language(code), name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL) STRICT;
CREATE TABLE labour_section_note (lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') PRIMARY KEY REFERENCES common_language(code), note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL) STRICT;
CREATE TABLE labour_label  (code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') NOT NULL, lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code), text TEXT CONSTRAINT "text isn't empty" CHECK (text <> '') NOT NULL,
                            PRIMARY KEY (code, lang)) STRICT;
CREATE TABLE labour_symbol (code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') PRIMARY KEY, value TEXT CONSTRAINT "value isn't empty" CHECK (value <> '') NOT NULL) STRICT;

CREATE TABLE labour_factor_f (
  -- the Comptroller General's multiplier for a contractor's overhead, profit and interest on bare cost
  id INTEGER PRIMARY KEY CONSTRAINT "Factor F is one row" CHECK (id = 1),
  value REAL NOT NULL CONSTRAINT "Factor F is 1 or more" CHECK (value >= 1 AND value < 1e308),
  standard TEXT CONSTRAINT "standard isn't empty" CHECK (standard <> '') NOT NULL, url TEXT CONSTRAINT "url isn't empty" CHECK (url <> '') NOT NULL,
  checked TEXT CONSTRAINT "checked isn't empty" CHECK (checked <> '') NOT NULL CONSTRAINT "Factor F's checked is a date, YYYY-MM-DD" CHECK (date(checked) IS checked),
  remark TEXT CONSTRAINT "remark isn't empty" CHECK (remark <> '')                       -- for editors (not printed): the choice made, and when to change it
) STRICT;
CREATE TABLE labour_factor_f_text (lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') PRIMARY KEY REFERENCES common_language(code), name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL) STRICT;

CREATE TABLE labour_book (
  -- a rate book; a kept copy (file) comes with the page that publishes it
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE,
  standard TEXT CONSTRAINT "standard isn't empty" CHECK (standard <> '') NOT NULL, url TEXT CONSTRAINT "url isn't empty" CHECK (url <> '') NOT NULL, published TEXT CONSTRAINT "published isn't empty" CHECK (published <> ''), official TEXT CONSTRAINT "official isn't empty" CHECK (official <> ''), file TEXT CONSTRAINT "file isn't empty" CHECK (file <> ''),
  checked TEXT CONSTRAINT "checked isn't empty" CHECK (checked <> '') NOT NULL CONSTRAINT "a book's checked is a date, YYYY-MM-DD" CHECK (date(checked) IS checked),
  bare INTEGER NOT NULL CONSTRAINT "bare is 0 or 1" CHECK (bare IN (0, 1)),
  remark TEXT CONSTRAINT "remark isn't empty" CHECK (remark <> ''),                      -- for editors (not printed): how to take in a new edition
  CONSTRAINT "a kept copy comes with the page that publishes it" CHECK (file IS NULL OR published IS NOT NULL)
) STRICT;
CREATE TABLE labour_book_text (
  -- a book's name, and how a rate names its place in it ({item})
  book TEXT CONSTRAINT "book isn't empty" CHECK (book <> '') NOT NULL REFERENCES labour_book(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                               name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, item_format TEXT CONSTRAINT "item_format isn't empty" CHECK (item_format <> '') NOT NULL, PRIMARY KEY (book, lang)) STRICT;

CREATE TABLE labour_unit (
  -- a unit a rate is priced by, and what it measures (a code)
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE,
  measure TEXT CONSTRAINT "measure isn't empty" CHECK (measure <> '') NOT NULL CONSTRAINT "a labour unit measures an area, a length, a count, a job or a share"
                        CHECK (measure IN ('area', 'length', 'count', 'job', 'share'))
) STRICT;
CREATE TABLE labour_unit_text (unit TEXT CONSTRAINT "unit isn't empty" CHECK (unit <> '') NOT NULL REFERENCES labour_unit(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                               name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, PRIMARY KEY (unit, lang)) STRICT;
CREATE TABLE labour_unit_plural (unit TEXT CONSTRAINT "unit isn't empty" CHECK (unit <> '') NOT NULL REFERENCES labour_unit(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                                 many TEXT CONSTRAINT "many isn't empty" CHECK (many <> '') NOT NULL, PRIMARY KEY (unit, lang)) STRICT;
CREATE TABLE labour_work_section (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE
) STRICT;
CREATE TABLE labour_work_section_text (work_section TEXT CONSTRAINT "work_section isn't empty" CHECK (work_section <> '') NOT NULL REFERENCES labour_work_section(id),
  lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code), name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, PRIMARY KEY (work_section, lang)) STRICT;
CREATE TABLE labour_work_section_note (work_section TEXT CONSTRAINT "work_section isn't empty" CHECK (work_section <> '') NOT NULL REFERENCES labour_work_section(id),
  lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code), note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL, PRIMARY KEY (work_section, lang)) STRICT;

CREATE TABLE labour_rate (
  -- a rate: from a book (its item, or a note in it; the page in a kept copy, or the book's own page) or none
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE,
  unit TEXT CONSTRAINT "unit isn't empty" CHECK (unit <> '') NOT NULL REFERENCES labour_unit(id),
  rate REAL NOT NULL CONSTRAINT "a rate is 0 or more" CHECK (rate >= 0 AND rate < 1e308),
  book TEXT CONSTRAINT "book isn't empty" CHECK (book <> '') REFERENCES labour_book(id),
  item TEXT CONSTRAINT "item isn't empty" CHECK (item <> ''),
  book_note INTEGER CONSTRAINT "a book note is more than 0" CHECK (book_note IS NULL OR book_note > 0),
  page INTEGER CONSTRAINT "a page is more than 0" CHECK (page IS NULL OR page > 0),
  url TEXT CONSTRAINT "url isn't empty" CHECK (url <> ''),
  CONSTRAINT "a rate from a book gives its item or a note, not both; a rate from no book gives neither"
    CHECK (CASE WHEN book IS NULL THEN item IS NULL AND book_note IS NULL AND page IS NULL AND url IS NULL
                ELSE (item IS NULL) IS NOT (book_note IS NULL) END)
) STRICT;
CREATE TABLE labour_rate_text (rate TEXT CONSTRAINT "rate isn't empty" CHECK (rate <> '') NOT NULL REFERENCES labour_rate(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                               name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, PRIMARY KEY (rate, lang)) STRICT;
CREATE TABLE labour_rate_assumed (rate TEXT CONSTRAINT "rate isn't empty" CHECK (rate <> '') NOT NULL REFERENCES labour_rate(id),
  key TEXT CONSTRAINT "key isn't empty" CHECK (key <> '') NOT NULL CONSTRAINT "a rate's assumed key is one of its values" CHECK (key IN ('rate')),
  how TEXT CONSTRAINT "how isn't empty" CHECK (how <> '') NOT NULL, PRIMARY KEY (rate, key)) STRICT;

CREATE TABLE labour_line (
  -- a line: a rate in a work section; its quantity comes from exactly one source, in the tables below
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE,
  rate TEXT CONSTRAINT "rate isn't empty" CHECK (rate <> '') NOT NULL REFERENCES labour_rate(id),
  work_section TEXT CONSTRAINT "work_section isn't empty" CHECK (work_section <> '') NOT NULL REFERENCES labour_work_section(id)
) STRICT;
CREATE TABLE labour_line_take_off (
  -- from the room's take-off (a link to the room, README rule 6) …
  line TEXT CONSTRAINT "line isn't empty" CHECK (line <> '') PRIMARY KEY REFERENCES labour_line(id),
  take_off TEXT CONSTRAINT "take_off isn't empty" CHECK (take_off <> '') NOT NULL REFERENCES room_take_off(code),
  times INTEGER CONSTRAINT "times is more than 0" CHECK (times IS NULL OR times > 0)) STRICT;
CREATE TABLE labour_line_n (
  -- … a number of sets …
  line TEXT CONSTRAINT "line isn't empty" CHECK (line <> '') PRIMARY KEY REFERENCES labour_line(id),
  n REAL NOT NULL CONSTRAINT "a line's n is more than 0" CHECK (n > 0 AND n < 1e308),
  times INTEGER CONSTRAINT "times is more than 0" CHECK (times IS NULL OR times > 0)) STRICT;
CREATE TABLE labour_line_count (
  -- … a count of products on the materials list (a link to the list, README rule 6) …
  line TEXT CONSTRAINT "line isn't empty" CHECK (line <> '') PRIMARY KEY REFERENCES labour_line(id),
  times INTEGER CONSTRAINT "times is more than 0" CHECK (times IS NULL OR times > 0)) STRICT;
CREATE TABLE labour_line_count_product (line TEXT CONSTRAINT "line isn't empty" CHECK (line <> '') NOT NULL REFERENCES labour_line_count(line), pos INTEGER NOT NULL,
  product TEXT CONSTRAINT "product isn't empty" CHECK (product <> '') NOT NULL REFERENCES materials_product(id), PRIMARY KEY (line, product), UNIQUE (line, pos)) STRICT;
CREATE TABLE labour_line_share (
  -- … or a share of what products on it still cost
  line TEXT CONSTRAINT "line isn't empty" CHECK (line <> '') PRIMARY KEY REFERENCES labour_line(id)) STRICT;
CREATE TABLE labour_line_share_product (line TEXT CONSTRAINT "line isn't empty" CHECK (line <> '') NOT NULL REFERENCES labour_line_share(line), pos INTEGER NOT NULL,
  product TEXT CONSTRAINT "product isn't empty" CHECK (product <> '') NOT NULL REFERENCES materials_product(id), PRIMARY KEY (line, product), UNIQUE (line, pos)) STRICT;
CREATE TABLE labour_line_note (line TEXT CONSTRAINT "line isn't empty" CHECK (line <> '') NOT NULL REFERENCES labour_line(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                               note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL, PRIMARY KEY (line, lang)) STRICT;
CREATE TABLE labour_line_assumed (line TEXT CONSTRAINT "line isn't empty" CHECK (line <> '') NOT NULL REFERENCES labour_line(id),
  key TEXT CONSTRAINT "key isn't empty" CHECK (key <> '') NOT NULL CONSTRAINT "a line's assumed key is one of its values" CHECK (key IN ('n', 'take_off')),
  how TEXT CONSTRAINT "how isn't empty" CHECK (how <> '') NOT NULL, PRIMARY KEY (line, key)) STRICT;

CREATE VIEW labour_line_source AS    -- each line's source, from the table it is in
  SELECT line, 'take_off' AS source FROM labour_line_take_off UNION ALL SELECT line, 'n' FROM labour_line_n UNION ALL
  SELECT line, 'count' FROM labour_line_count UNION ALL SELECT line, 'share' FROM labour_line_share;

CREATE VIEW labour_check_rows AS
  SELECT column1 || ' has ' || column2 || ' rows, not 1' FROM (VALUES
    ('labour_setting', (SELECT count(*) FROM labour_setting)),
    ('labour_factor_f', (SELECT count(*) FROM labour_factor_f))) WHERE column2 <> 1
  UNION ALL SELECT column1 || ' has no row' FROM (VALUES
    ('labour_book', (SELECT count(*) FROM labour_book)),
    ('labour_unit', (SELECT count(*) FROM labour_unit)),
    ('labour_work_section', (SELECT count(*) FROM labour_work_section)),
    ('labour_rate', (SELECT count(*) FROM labour_rate)),
    ('labour_line', (SELECT count(*) FROM labour_line))) WHERE column2 = 0;
CREATE VIEW labour_check_line_one_source AS
  SELECT 'line ' || l.id || ' takes its quantity from ' || count(s.line) || ' sources, not 1'
  FROM labour_line l LEFT JOIN labour_line_source s ON s.line = l.id GROUP BY l.id HAVING count(s.line) <> 1;
CREATE VIEW labour_check_count_has_products AS
  SELECT 'line ' || line || ' counts no products' FROM labour_line_count WHERE line NOT IN (SELECT line FROM labour_line_count_product)
  UNION ALL SELECT 'line ' || line || ' is a share of no products' FROM labour_line_share WHERE line NOT IN (SELECT line FROM labour_line_share_product)
  UNION ALL SELECT 'line ' || c.line || ' counts products bought by length and by count together'
  FROM labour_line_count_product c JOIN materials_product p ON p.id = c.product JOIN materials_unit u ON u.id = p.unit
  GROUP BY c.line HAVING min(u.measure) <> max(u.measure);
CREATE VIEW labour_check_rate_without_book AS
  SELECT 'rate ' || id || ' has no book, so its rate must be marked assumed' FROM labour_rate
  WHERE book IS NULL AND id NOT IN (SELECT rate FROM labour_rate_assumed WHERE key = 'rate');
CREATE VIEW labour_check_rate_where_in_book AS
  SELECT 'rate ' || r.id || CASE WHEN b.file IS NOT NULL THEN ' is from a kept copy, so it gives its page and no url'
                                 ELSE ' is from a book with no copy, so it gives its url and no page' END
  FROM labour_rate r JOIN labour_book b ON b.id = r.book
  WHERE (b.file IS NOT NULL AND (r.page IS NULL OR r.url IS NOT NULL)) OR (b.file IS NULL AND (r.url IS NULL OR r.page IS NOT NULL));
CREATE VIEW labour_check_line_measure AS
  -- what each source needs the rate's unit to measure
  SELECT 'line ' || l.id || ' is priced by a rate that measures ' || u.measure || ', but its quantity is ' || need.measure
  FROM labour_line l JOIN labour_rate r ON r.id = l.rate JOIN labour_unit u ON u.id = r.unit JOIN (
    SELECT t.line, k.measure FROM labour_line_take_off t JOIN room_take_off k ON k.code = t.take_off
    UNION ALL SELECT c.line, CASE WHEN min(mu.measure) = 'length' AND max(mu.measure) = 'length' THEN 'length' ELSE 'count' END
      FROM labour_line_count_product c JOIN materials_product p ON p.id = c.product JOIN materials_unit mu ON mu.id = p.unit GROUP BY c.line
    UNION ALL SELECT line, 'share' FROM labour_line_share) need ON need.line = l.id
  WHERE u.measure IS NOT need.measure
  -- a plain number (n) can be of any unit but a share
  UNION ALL SELECT 'line ' || n.line || ' gives a number, so its rate can''t be a share'
  FROM labour_line_n n JOIN labour_line l ON l.id = n.line JOIN labour_rate r ON r.id = l.rate JOIN labour_unit u ON u.id = r.unit
  WHERE u.measure = 'share';

CREATE VIEW labour_show_line AS
  -- ---------- for reading: every labour line as people say it
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

-- every foreign key has an index (sqlite3 .lint fkey-indexes prints nothing): links stay fast as the data grows
CREATE INDEX labour_book_text_lang ON labour_book_text(lang);
CREATE INDEX labour_label_lang ON labour_label(lang);
CREATE INDEX labour_line_count_product_product ON labour_line_count_product(product);
CREATE INDEX labour_line_note_lang ON labour_line_note(lang);
CREATE INDEX labour_line_rate ON labour_line(rate);
CREATE INDEX labour_line_share_product_product ON labour_line_share_product(product);
CREATE INDEX labour_line_take_off_take_off ON labour_line_take_off(take_off);
CREATE INDEX labour_line_work_section ON labour_line(work_section);
CREATE INDEX labour_rate_book ON labour_rate(book);
CREATE INDEX labour_rate_text_lang ON labour_rate_text(lang);
CREATE INDEX labour_rate_unit ON labour_rate(unit);
CREATE INDEX labour_unit_plural_lang ON labour_unit_plural(lang);
CREATE INDEX labour_unit_text_lang ON labour_unit_text(lang);
CREATE INDEX labour_work_section_note_lang ON labour_work_section_note(lang);
CREATE INDEX labour_work_section_text_lang ON labour_work_section_text(lang);
