#!/usr/bin/env python3
"""The work, phase by phase: phases.toml, read, checked, numbered and rendered. It knows
nothing about the materials or the drawings.

    work = load(Path("phases.toml"))
    work.phases         # every Phase, each with its Steps, numbered
    work.render()       # the phases as Markdown — the PDF prints exactly this
    work.resolve(text)  # every {phase:id} / {step:id} in `text` turned into its number

Phases and steps are numbered by their position in the file, so inserting a step renumbers
it and every reference to it.

Usage:  python3 phases.py [phases.toml]    (prints the phases)
"""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from common import DataError, Labels, cli, md_cell, need, only, read_toml

FILE = "phases.toml"
PHASE_KEYS = {"id", "th", "en", "note_th", "note_en", "step"}
STEP_KEYS = {"id", "th", "en"}
LABELS = {"phase_heading": ("number", "name"), "step_columns": ()}
REF = re.compile(r"\{([a-z]+):([a-z0-9_]+)\}")


@dataclass(frozen=True)
class Step:
    id: str
    number: str          # "1.8"
    th: str
    en: str


@dataclass(frozen=True)
class Phase:
    id: str
    number: int
    th: str
    en: str
    note_th: str
    note_en: str
    steps: tuple


@dataclass(frozen=True)
class Work:
    """The work, phase by phase."""
    phases: tuple
    labels: Labels = field(repr=False)
    numbers: dict = field(repr=False)     # {("phase" | "step", id): "5" | "1.8"}

    def resolve(self, text):
        """Replace every {phase:id} and {step:id} with its number."""
        def sub(m):
            if (m.group(1), m.group(2)) not in self.numbers:
                raise DataError(f"Reference {{{m.group(1)}:{m.group(2)}}} doesn't match any phase or step id in {FILE}")
            return self.numbers[(m.group(1), m.group(2))]
        return REF.sub(sub, text)

    def render(self):
        """The phases as Markdown lines: a heading, the note, and the step table for each."""
        L, out = self.labels, []
        for ph in self.phases:
            out += [f"### {L.both('phase_heading', number=ph.number, name=(ph.th, ph.en))}", ""]
            if ph.note_th or ph.note_en:
                out += [f"> {ph.note_th}", f"> {ph.note_en}", ""]
            if ph.steps:
                out += [f"| # | {L.th('step_columns')} | {L.en('step_columns')} |", "|---|---------|---------|"]
                out += [f"| {st.number} | {md_cell(st.th)} | {md_cell(st.en)} |" for st in ph.steps]
                out.append("")
        return out[:-1]


def load(path):
    """Read and check phases.toml, and number every phase and step."""
    raw = read_toml(Path(path), "the work, phase by phase")
    only(FILE, "the file", raw, {"labels", "phase"})
    labels = Labels(FILE, raw.get("labels", {}), LABELS)
    numbers, found = {}, []

    def add(kind, key, num):
        if (kind, key) in numbers:
            raise DataError(f"{FILE}: {kind} id '{key}' is used twice")
        numbers[(kind, key)] = num

    for p_no, ph in enumerate(raw.get("phase", []), 1):
        only(FILE, f"phase '{ph.get('id', p_no)}'", ph, PHASE_KEYS)
        need(FILE, f"phase {p_no}", ph, ("id", "th", "en"))
        add("phase", ph["id"], str(p_no))
        steps = []
        for s_no, st in enumerate(ph.get("step", []), 1):
            only(FILE, f"step '{st.get('id', '?')}'", st, STEP_KEYS)
            need(FILE, f"step {p_no}.{s_no} in '{ph['id']}'", st, ("id", "th", "en"))
            add("step", st["id"], f"{p_no}.{s_no}")
            steps.append((st["id"], f"{p_no}.{s_no}", st["th"], st["en"]))
        found.append((ph, p_no, steps))

    # references are resolved once every number is known (a step may refer forward)
    unresolved = Work((), labels, numbers)
    r = unresolved.resolve
    return Work(tuple(
        Phase(ph["id"], p_no, ph["th"], ph["en"], r(ph.get("note_th", "")), r(ph.get("note_en", "")),
              tuple(Step(i, n, r(th), r(en)) for i, n, th, en in steps))
        for ph, p_no, steps in found), labels, numbers)


def main(argv):
    print("\n".join(load(argv[1] if len(argv) > 1 else FILE).render()))


if __name__ == "__main__":
    cli(lambda: main(sys.argv))
