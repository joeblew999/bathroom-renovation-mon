CREATE TABLE common_language (
  -- common.schema.sql — what every part shares. Loaded first.
  --
  -- How every table is designed (one way, everywhere):
  --   * An ENTITY (a product, an item, a wall, a step, a rate …) has a UUID for its key: id TEXT PRIMARY KEY,
  --     made by SQLite (version 4, random) for a new row; rows migrated from the TOML got version 5 UUIDs
  --     worked out from their old ids. It never changes and nothing reads meaning into it. Every link is a
  --     foreign key to it, and every foreign key has an index. What a person calls the thing is a fact in its
  --     translation table, free to change.
  --   * A CODE is the schema's own vocabulary, which the code is written against: a shape, a status, a
  --     measure, a kind, a norm, a take-off, a label. It is readable on purpose, like a column name; changing
  --     one is a change to the design (a migration).
  --   * Order is a position, pos: unique within the row's parent (a step within its phase, an item within its
  --     surface) or within its table, with gaps (10, 20 …) so a row can go between two others. The ETL and
  --     pos_after() / pos_first() (mise run db:sql) work positions out — nobody types one. Every query that
  --     needs order says ORDER BY pos.
  --   * Text in a person's language (Thai, English) is never on an entity's row; text that is the same in every
  --     language (a code, a standard's number, a url, a drawing letter) may be. It is in a translation table with
  --     the language in its key: <thing>_text (required in every language); <thing>_note, _name, _by and _plural
  --     (every language, or none — a plural only where a language has one); and each part's _label, its fixed
  --     wording (every code in every language). The code checks these conventions for every such table, and
  --     that no text is empty.
  --   * A link inside text is never written in the text: the text has a numbered gap ({1}, {2} …) and a
  --     <thing>_ref row says what the gap points at, with a foreign key.
  --   * A note for whoever edits the data or measures on site (how, remark) is English only and never printed,
  --     like the messages printed for whoever runs the build; it may sit on the row it is about.
  --   * A value still to be measured or read off a label (README rule 10) is a row in <thing>_assumed: the
  --     thing, the column, and how to find the real value (required).
  --   * A one-row table has id INTEGER PRIMARY KEY CHECK (id = 1), and a view checks the row is there.
  --   * Every rule has a name, and is written so a missing value can't pass it.
  --   * The schema is the migrations (migrations/0001_initial.sql, then each design change); the data is each
  --     part's seed file (sqlite3 .dump --data-only). A database is built from the migrations and the seed files;
  --     the working database (.work/quote.db) is read and changed with any SQLite tool and saved back to the seed
  --     files (mise run db:save), which writes data only — the schema changes only by a migration.
  --   * It runs the same on Cloudflare D1: no compound SELECT has more than 5 terms (D1's limit), and loading
  --     keeps foreign keys on, deferred to the end of each file, as D1 does.
  code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') PRIMARY KEY CONSTRAINT "a language is 2 small letters" CHECK (code GLOB '[a-z][a-z]'),
  pos INTEGER NOT NULL UNIQUE
) STRICT;

CREATE VIEW common_check_language_rows AS SELECT 'there is no language' FROM (SELECT count(*) n FROM common_language) WHERE n = 0;

CREATE VIEW common_show_product_reach AS
  -- ---------- for review: everything a change to a product reaches, across the parts — the items that use it and, down
  -- each one's chain of fittings, the items that serve them (a recursive query; depth 1, 2 … down the chain); the tile,
  -- door or lintel it is; its lines on the materials list; the labour lines priced from it. Read by people (db:show), never
  -- by a part's code. (Made here, before the tables it reads: SQLite resolves a view's tables when it is read.)
  WITH RECURSIVE served(product, item, depth, sort) AS (
    SELECT product, id, 0, printf('%08d', pos) FROM room_item WHERE product IS NOT NULL
    UNION ALL
    SELECT s.product, i.id, s.depth + 1, s.sort || '.' || printf('%08d', i.pos) FROM served s JOIN room_item i ON i.fitting = s.item)
  SELECT pt.name AS product, x.place, x.what, x.depth
  FROM (
    -- groups of at most 5: D1 allows 5 terms in a compound SELECT
    SELECT s.product, 1 AS place_pos, 'room item' AS place, coalesce(n.name, p.name) || ' (' || coalesce(wt.name, 'floor') || ')' AS what,
           s.depth, s.sort
    FROM served s JOIN room_item i ON i.id = s.item
    LEFT JOIN room_wall_text wt ON wt.wall = i.surface AND wt.lang = 'en'
    LEFT JOIN room_item_name n ON n.item = i.id AND n.lang = 'en'
    LEFT JOIN materials_product_text p ON p.product = i.product AND p.lang = 'en'
    UNION ALL SELECT t.product, 2, 'tile', tt.name, 0, printf('%08d', t.pos) FROM room_tile t JOIN room_tile_text tt ON tt.tile = t.id AND tt.lang = 'en'
    UNION ALL SELECT product, 3, 'door', 'the door', 0, '' FROM room_door
    UNION ALL SELECT product, 4, 'lintel', 'the lintel', 0, '' FROM room_lintel
    UNION ALL SELECT * FROM (
      SELECT l.product, 5, 'materials line', l.status || ', ' || w.name, 0, printf('%08d', l.pos)
      FROM materials_line l JOIN materials_work_section_text w ON w.work_section = l.work_section AND w.lang = 'en'
      UNION ALL SELECT c.product, 6, 'labour line', r.name, 0, printf('%08d', ll.pos)
      FROM labour_line_count_product c JOIN labour_line ll ON ll.id = c.line JOIN labour_rate_text r ON r.rate = ll.rate AND r.lang = 'en'
      UNION ALL SELECT c.product, 6, 'labour line', r.name, 0, printf('%08d', ll.pos)
      FROM labour_line_share_product c JOIN labour_line ll ON ll.id = c.line JOIN labour_rate_text r ON r.rate = ll.rate AND r.lang = 'en')
  ) x JOIN materials_product mp ON mp.id = x.product JOIN materials_product_text pt ON pt.product = x.product AND pt.lang = 'en'
  ORDER BY mp.pos, x.place_pos, x.sort;
