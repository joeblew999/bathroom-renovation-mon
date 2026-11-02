-- common.schema.sql — what every part shares. Loaded first.
--
-- How every table is designed (one way, everywhere):
--   * An ENTITY (a product, an item, a wall, a step, a rate …) has a random key: id TEXT PRIMARY KEY,
--     16 small hex digits, made by SQLite (lower(hex(randomblob(8)))). It never changes and nothing reads
--     meaning into it. Every link is a foreign key to it. What a person calls the thing is a fact in its
--     translation table, free to change.
--   * A CODE is the schema's own vocabulary, which the code is written against: a shape, a status, a
--     measure, a norm, a take-off, a label. It is readable on purpose, like a column name; changing one is a
--     change to the design (a migration).
--   * Order is a position, pos, unique in its table, written by the migration and the dump — never typed.
--   * Text a person reads is never on an entity's row. It is in a translation table with the language in
--     its key: <thing>_text (required in every language), <thing>_note and <thing>_plural (optional: every
--     language, or none). The code checks these conventions for every such table.
--   * A value still to be measured or read off a label (README rule 10) is a row in <thing>_assumed:
--     the thing, the column, and how to find the real value.
--   * A one-row table has id INTEGER PRIMARY KEY CHECK (id = 1), and a view checks the row is there.
--   * Every rule has a name, and is written so a missing value can't pass it.

CREATE TABLE language (
  code TEXT PRIMARY KEY CONSTRAINT "a language is 2 small letters" CHECK (code GLOB '[a-z][a-z]'),
  pos INTEGER NOT NULL UNIQUE
) STRICT;

CREATE VIEW check_language_rows AS SELECT 'there is no language' FROM (SELECT count(*) n FROM language) WHERE n = 0;
