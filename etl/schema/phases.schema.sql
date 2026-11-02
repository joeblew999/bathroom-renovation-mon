CREATE TABLE phases_section_text (
  -- phases.schema.sql — the scope of works: phases and their steps, in order. A step's text, or a phase's note,
  -- may refer to a step or a phase: the text has a numbered gap ({1}, {2} …) and a _ref row says what it points at;
  -- the build prints that step's or phase's number there.
  lang TEXT PRIMARY KEY REFERENCES common_language(code), name TEXT NOT NULL) STRICT;
CREATE TABLE phases_section_note (lang TEXT PRIMARY KEY REFERENCES common_language(code), note TEXT NOT NULL) STRICT;
CREATE TABLE phases_label  (code TEXT NOT NULL, lang TEXT NOT NULL REFERENCES common_language(code), text TEXT NOT NULL,
                            PRIMARY KEY (code, lang)) STRICT;
CREATE TABLE phases_symbol (code TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;

CREATE TABLE phases_phase (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (length(id) = 16 AND id NOT GLOB '*[^0-9a-f]*'),
  pos INTEGER NOT NULL UNIQUE
) STRICT;
CREATE TABLE phases_phase_text (phase TEXT NOT NULL REFERENCES phases_phase(id), lang TEXT NOT NULL REFERENCES common_language(code),
                                name TEXT NOT NULL, PRIMARY KEY (phase, lang)) STRICT;
CREATE TABLE phases_phase_note (phase TEXT NOT NULL REFERENCES phases_phase(id), lang TEXT NOT NULL REFERENCES common_language(code),
                                note TEXT NOT NULL, PRIMARY KEY (phase, lang)) STRICT;
CREATE TABLE phases_step (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (length(id) = 16 AND id NOT GLOB '*[^0-9a-f]*'),
  pos INTEGER NOT NULL,
  phase TEXT NOT NULL REFERENCES phases_phase(id),
  UNIQUE (phase, pos)
) STRICT;
CREATE TABLE phases_step_text (step TEXT NOT NULL REFERENCES phases_step(id), lang TEXT NOT NULL REFERENCES common_language(code),
                               text TEXT NOT NULL, PRIMARY KEY (step, lang)) STRICT;

CREATE TABLE phases_step_ref (
  -- what each numbered gap in a step's text, or in a phase's note, points at: a step or a phase
  step TEXT NOT NULL REFERENCES phases_step(id),
  n INTEGER NOT NULL CONSTRAINT "a gap is numbered from 1" CHECK (n >= 1),
  to_step TEXT REFERENCES phases_step(id), to_phase TEXT REFERENCES phases_phase(id),
  CONSTRAINT "a reference points at a step or a phase, one of the two" CHECK ((to_step IS NULL) IS NOT (to_phase IS NULL)),
  PRIMARY KEY (step, n)) STRICT;
CREATE TABLE phases_phase_note_ref (phase TEXT NOT NULL REFERENCES phases_phase(id),
  n INTEGER NOT NULL CONSTRAINT "a gap is numbered from 1" CHECK (n >= 1),
  to_step TEXT REFERENCES phases_step(id), to_phase TEXT REFERENCES phases_phase(id),
  CONSTRAINT "a reference points at a step or a phase, one of the two" CHECK ((to_step IS NULL) IS NOT (to_phase IS NULL)),
  PRIMARY KEY (phase, n)) STRICT;

CREATE VIEW phases_check_rows AS
  SELECT t || ' has no row' FROM (
    SELECT 'phases_section_text' t, (SELECT count(*) FROM phases_section_text) n UNION ALL
    SELECT 'phases_phase', (SELECT count(*) FROM phases_phase)) WHERE n = 0;

CREATE VIEW phases_show_step AS
  -- ---------- for reading: the scope of works in order
  SELECT dense_rank() OVER (ORDER BY ph.pos) AS phase_no, pt.name AS phase,
         row_number() OVER (PARTITION BY s.phase ORDER BY s.pos) AS step_no, st.text
  FROM phases_step s JOIN phases_phase ph ON ph.id = s.phase
  JOIN phases_phase_text pt ON pt.phase = ph.id AND pt.lang = 'en'
  JOIN phases_step_text st ON st.step = s.id AND st.lang = 'en'
  ORDER BY ph.pos, s.pos;
