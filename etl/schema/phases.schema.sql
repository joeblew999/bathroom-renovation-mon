CREATE TABLE phases_section_text (
  -- the phases part — the scope of works: phases and their steps, in order. A step's text, or a phase's note,
  -- may refer to a step or a phase: the text has a numbered gap ({1}, {2} …) and a _ref row says what it points at;
  -- the build prints that step's or phase's number there.
  lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') PRIMARY KEY REFERENCES common_language(code), name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL) STRICT;
CREATE TABLE phases_section_note (lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') PRIMARY KEY REFERENCES common_language(code), note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL) STRICT;
CREATE TABLE phases_label  (code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') NOT NULL, lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code), text TEXT CONSTRAINT "text isn't empty" CHECK (text <> '') NOT NULL,
                            PRIMARY KEY (code, lang)) STRICT;
CREATE TABLE phases_symbol (code TEXT CONSTRAINT "code isn't empty" CHECK (code <> '') PRIMARY KEY, value TEXT CONSTRAINT "value isn't empty" CHECK (value <> '') NOT NULL) STRICT;

CREATE TABLE phases_phase (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL UNIQUE
) STRICT;
CREATE TABLE phases_phase_text (phase TEXT CONSTRAINT "phase isn't empty" CHECK (phase <> '') NOT NULL REFERENCES phases_phase(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                                name TEXT CONSTRAINT "name isn't empty" CHECK (name <> '') NOT NULL, PRIMARY KEY (phase, lang)) STRICT;
CREATE TABLE phases_phase_note (phase TEXT CONSTRAINT "phase isn't empty" CHECK (phase <> '') NOT NULL REFERENCES phases_phase(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                                note TEXT CONSTRAINT "note isn't empty" CHECK (note <> '') NOT NULL, PRIMARY KEY (phase, lang)) STRICT;
CREATE TABLE phases_step (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', 1 + abs(random()) % 4, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))))
    CONSTRAINT "an id is a UUID: 8-4-4-4-12 small hex digits" CHECK (length(id) = 36 AND id GLOB '????????-????-????-????-????????????' AND id NOT GLOB '*[^0-9a-f-]*'),
  pos INTEGER NOT NULL,
  phase TEXT CONSTRAINT "phase isn't empty" CHECK (phase <> '') NOT NULL REFERENCES phases_phase(id),
  UNIQUE (phase, pos)
) STRICT;
CREATE TABLE phases_step_text (step TEXT CONSTRAINT "step isn't empty" CHECK (step <> '') NOT NULL REFERENCES phases_step(id), lang TEXT CONSTRAINT "lang isn't empty" CHECK (lang <> '') NOT NULL REFERENCES common_language(code),
                               text TEXT CONSTRAINT "text isn't empty" CHECK (text <> '') NOT NULL, PRIMARY KEY (step, lang)) STRICT;

CREATE TABLE phases_step_ref (
  -- what each numbered gap in a step's text, or in a phase's note, points at: a step or a phase
  step TEXT CONSTRAINT "step isn't empty" CHECK (step <> '') NOT NULL REFERENCES phases_step(id),
  n INTEGER NOT NULL CONSTRAINT "a gap is numbered from 1" CHECK (n >= 1),
  to_step TEXT CONSTRAINT "to_step isn't empty" CHECK (to_step <> '') REFERENCES phases_step(id), to_phase TEXT CONSTRAINT "to_phase isn't empty" CHECK (to_phase <> '') REFERENCES phases_phase(id),
  CONSTRAINT "a reference points at a step or a phase, one of the two" CHECK ((to_step IS NULL) IS NOT (to_phase IS NULL)),
  CONSTRAINT "a step doesn't refer to itself" CHECK (to_step IS NULL OR to_step <> step),
  PRIMARY KEY (step, n)) STRICT;
CREATE TABLE phases_phase_note_ref (phase TEXT CONSTRAINT "phase isn't empty" CHECK (phase <> '') NOT NULL REFERENCES phases_phase(id),
  n INTEGER NOT NULL CONSTRAINT "a gap is numbered from 1" CHECK (n >= 1),
  to_step TEXT CONSTRAINT "to_step isn't empty" CHECK (to_step <> '') REFERENCES phases_step(id), to_phase TEXT CONSTRAINT "to_phase isn't empty" CHECK (to_phase <> '') REFERENCES phases_phase(id),
  CONSTRAINT "a reference points at a step or a phase, one of the two" CHECK ((to_step IS NULL) IS NOT (to_phase IS NULL)),
  PRIMARY KEY (phase, n)) STRICT;

CREATE VIEW phases_check_rows AS
  SELECT column1 || ' has no row' FROM (VALUES
    ('phases_section_text', (SELECT count(*) FROM phases_section_text)),
    ('phases_phase', (SELECT count(*) FROM phases_phase))) WHERE column2 = 0;

CREATE VIEW phases_show_step AS
  -- ---------- for reading: the scope of works in order
  SELECT dense_rank() OVER (ORDER BY ph.pos) AS phase_no, pt.name AS phase,
         row_number() OVER (PARTITION BY s.phase ORDER BY s.pos) AS step_no, st.text
  FROM phases_step s JOIN phases_phase ph ON ph.id = s.phase
  JOIN phases_phase_text pt ON pt.phase = ph.id AND pt.lang = 'en'
  JOIN phases_step_text st ON st.step = s.id AND st.lang = 'en'
  ORDER BY ph.pos, s.pos;

CREATE VIEW phases_show_text AS
  -- ---------- for reading, and for printing: each step's text and each phase's note, in each language, as the quote
  -- prints them — every numbered gap filled with the number of the step ("2.3") or phase ("2") its reference points at.
  -- A recursive query fills the gaps one at a time, {1}, then {2} … until a text has no reference left
  WITH RECURSIVE
  number(id, no) AS (                                        -- phases and steps numbered by their place, as printed
    SELECT id, CAST(row_number() OVER (ORDER BY pos) AS TEXT) FROM phases_phase
    UNION ALL
    SELECT s.id, (SELECT count(*) FROM phases_phase p WHERE p.pos <= ph.pos) || '.' || row_number() OVER (PARTITION BY s.phase ORDER BY s.pos)
    FROM phases_step s JOIN phases_phase ph ON ph.id = s.phase),
  ref(owner, n, target) AS (                                 -- every reference, from a step's text or a phase's note
    SELECT step, n, coalesce(to_step, to_phase) FROM phases_step_ref
    UNION ALL SELECT phase, n, coalesce(to_step, to_phase) FROM phases_phase_note_ref),
  fill(kind, owner, sort, lang, text, n) AS (
    SELECT 'step', s.id, printf('%08d%08d', ph.pos, s.pos), t.lang, t.text, 0
    FROM phases_step_text t JOIN phases_step s ON s.id = t.step JOIN phases_phase ph ON ph.id = s.phase
    UNION ALL
    SELECT 'phase note', ph.id, printf('%08d', ph.pos), t.lang, t.note, 0 FROM phases_phase_note t JOIN phases_phase ph ON ph.id = t.phase
    UNION ALL
    SELECT f.kind, f.owner, f.sort, f.lang, replace(f.text, '{' || (f.n + 1) || '}', nb.no), f.n + 1
    FROM fill f JOIN ref r ON r.owner = f.owner AND r.n = f.n + 1 JOIN number nb ON nb.id = r.target)
  SELECT f.kind, nb.no AS number, f.lang, f.text
  FROM fill f JOIN number nb ON nb.id = f.owner
  WHERE NOT EXISTS (SELECT 1 FROM ref r WHERE r.owner = f.owner AND r.n = f.n + 1)     -- the text with every gap filled
  ORDER BY f.sort, f.lang;

-- every foreign key has an index (sqlite3 .lint fkey-indexes prints nothing): links stay fast as the data grows
CREATE INDEX phases_label_lang ON phases_label(lang);
CREATE INDEX phases_phase_note_lang ON phases_phase_note(lang);
CREATE INDEX phases_phase_note_ref_to_phase ON phases_phase_note_ref(to_phase);
CREATE INDEX phases_phase_note_ref_to_step ON phases_phase_note_ref(to_step);
CREATE INDEX phases_phase_text_lang ON phases_phase_text(lang);
CREATE INDEX phases_step_ref_to_phase ON phases_step_ref(to_phase);
CREATE INDEX phases_step_ref_to_step ON phases_step_ref(to_step);
CREATE INDEX phases_step_text_lang ON phases_step_text(lang);
