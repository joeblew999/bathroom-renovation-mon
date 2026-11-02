-- phases.schema.sql — the scope of works: phases and their steps, in order. A step's text may refer to
-- another step or phase as {step:<id>} or {phase:<id>}; the code checks each refers to one that exists,
-- and prints its number.

CREATE TABLE phases_section_text (lang TEXT PRIMARY KEY REFERENCES language(code), name TEXT NOT NULL) STRICT;
CREATE TABLE phases_section_note (lang TEXT PRIMARY KEY REFERENCES language(code), note TEXT NOT NULL) STRICT;
CREATE TABLE phases_label  (code TEXT NOT NULL, lang TEXT NOT NULL REFERENCES language(code), text TEXT NOT NULL,
                            PRIMARY KEY (code, lang)) STRICT;
CREATE TABLE phases_symbol (code TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;

CREATE TABLE phases_phase (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (id GLOB '[0-9a-f]*' AND length(id) = 16),
  pos INTEGER NOT NULL UNIQUE
) STRICT;
CREATE TABLE phases_phase_text (phase TEXT NOT NULL REFERENCES phases_phase(id), lang TEXT NOT NULL REFERENCES language(code),
                                name TEXT NOT NULL, PRIMARY KEY (phase, lang)) STRICT;
CREATE TABLE phases_phase_note (phase TEXT NOT NULL REFERENCES phases_phase(id), lang TEXT NOT NULL REFERENCES language(code),
                                note TEXT NOT NULL, PRIMARY KEY (phase, lang)) STRICT;
CREATE TABLE phases_step (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))) CONSTRAINT "an id is 16 hex digits" CHECK (id GLOB '[0-9a-f]*' AND length(id) = 16),
  pos INTEGER NOT NULL UNIQUE,
  phase TEXT NOT NULL REFERENCES phases_phase(id)
) STRICT;
CREATE TABLE phases_step_text (step TEXT NOT NULL REFERENCES phases_step(id), lang TEXT NOT NULL REFERENCES language(code),
                               text TEXT NOT NULL, PRIMARY KEY (step, lang)) STRICT;

CREATE VIEW check_phases_rows AS
  SELECT t || ' has no row' FROM (
    SELECT 'phases_section_text' t, (SELECT count(*) FROM phases_section_text) n UNION ALL
    SELECT 'phases_phase', (SELECT count(*) FROM phases_phase)) WHERE n = 0;

-- ---------- for reading: the scope of works in order
CREATE VIEW show_phases_step AS
  SELECT ph.pos AS phase_no, pt.name AS phase, row_number() OVER (PARTITION BY s.phase ORDER BY s.pos) AS step_no, st.text
  FROM phases_step s JOIN phases_phase ph ON ph.id = s.phase
  JOIN phases_phase_text pt ON pt.phase = ph.id AND pt.lang = 'en'
  JOIN phases_step_text st ON st.step = s.id AND st.lang = 'en';
