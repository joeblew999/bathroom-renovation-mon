CREATE TABLE common_language (
  -- common.schema.sql — what every part shares. Loaded first.
  --
  -- How every table is designed (one way, everywhere):
  --   * An ENTITY (a product, an item, a wall, a step, a rate …) has a random key: id TEXT PRIMARY KEY,
  --     16 small hex digits, made by SQLite (lower(hex(randomblob(8)))). It never changes and nothing reads
  --     meaning into it. Every link is a foreign key to it. What a person calls the thing is a fact in its
  --     translation table, free to change.
  --   * A CODE is the schema's own vocabulary, which the code is written against: a shape, a status, a
  --     measure, a kind, a norm, a take-off, a label. It is readable on purpose, like a column name; changing
  --     one is a change to the design (a migration).
  --   * Order is a position, pos: unique within the row's parent (a step within its phase, an item within its
  --     surface) or within its table, with gaps (10, 20 …) so a row can go between two others. The ETL and the
  --     edit tool (etl/edit.py, pos_after) work positions out — nobody types one. Every query that needs order
  --     says ORDER BY pos.
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
  --   * Any database is built from the schema files and the data files when it is needed, and thrown away
  --     after: changes are made to the data files only (etl/edit.py), so nothing can drift from them.
  code TEXT PRIMARY KEY CONSTRAINT "a language is 2 small letters" CHECK (code GLOB '[a-z][a-z]'),
  pos INTEGER NOT NULL UNIQUE
) STRICT;

CREATE VIEW common_check_language_rows AS SELECT 'there is no language' FROM (SELECT count(*) n FROM common_language) WHERE n = 0;
