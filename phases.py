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

from common import NAME, NAMED, DataError, Labels, check, check_each, cli, heading, md_cell, named, note, read_toml

FILE = "phases.toml"
# Every kind of entry in phases.toml, declared once (common.check: "!" = required).
FILE_FIELDS = {"section": "table!", "labels": "table!", "symbols": "table!", "phase": "list!"}
PHASE = {"id": "text!", **NAMED, "step": "list"}
STEP = {"id": "text!", **NAME}
SYMBOLS = {"number": "text!"}
LABELS = {"phase_heading": ("number", "name"), "step_columns": ()}
REF = re.compile(r"\{([a-z]+):([a-z0-9_]+)\}")


@dataclass(frozen=True)
class Step:
    number: str          # "1.8": its place in the file
    th: str
    en: str


@dataclass(frozen=True)
class Phase:
    number: int
    th: str
    en: str
    note_th: str
    note_en: str
    steps: tuple


@dataclass(frozen=True)
class Work:
    """The work, phase by phase."""
    section: tuple                        # (th, en, note_th, note_en): this part's heading and note
    phases: tuple
    labels: Labels = field(repr=False)
    symbols: dict = field(repr=False)     # the step-number column's heading
    numbers: dict = field(repr=False)     # {("phase" | "step", id): "5" | "1.8"}

    def render(self):
        """The section as Markdown lines: its heading and note, then for each phase a heading,
        its note and its step table."""
        L = self.labels
        th, en, nth, nen = self.section
        out = [heading(2, th, en), "", *note(nth, nen)]
        for ph in self.phases:
            name = dict(number=ph.number, name=(ph.th, ph.en))
            out += [heading(3, L.th("phase_heading", **name), L.en("phase_heading", **name)), "",
                    *note(ph.note_th, ph.note_en)]
            if ph.steps:
                out += [f"| {self.symbols['number']} | {L.th('step_columns')} | {L.en('step_columns')} |",
                        "|---|---------|---------|"]
                out += [f"| {st.number} | {md_cell(st.th)} | {md_cell(st.en)} |" for st in ph.steps]
                out.append("")
        return out[:-1]


def resolve(numbers, text):
    """`text` with every {phase:id} and {step:id} replaced by its number."""
    def sub(m):
        if (m.group(1), m.group(2)) not in numbers:
            raise DataError(f"{FILE}: reference {{{m.group(1)}:{m.group(2)}}} doesn't match any phase or step id")
        return numbers[(m.group(1), m.group(2))]
    return REF.sub(sub, text)


def load(path):
    """Read and check phases.toml, and number every phase and step."""
    raw = read_toml(Path(path), "the work, phase by phase")
    check(FILE, "the file", raw, FILE_FIELDS, ordered=False)
    section = named(check(FILE, "[section]", raw["section"], NAMED))
    labels = Labels(FILE, raw["labels"], LABELS)
    check(FILE, "[symbols]", raw["symbols"], SYMBOLS)
    check_each(FILE, "phase", raw["phase"], PHASE)
    for ph in raw["phase"]:
        check_each(FILE, f"phase '{ph['id']}' step", ph.get("step", []), STEP)
    check_each(FILE, "step", [st for ph in raw["phase"] for st in ph.get("step", [])], STEP)   # ids used once
    numbers = {}
    for p_no, ph in enumerate(raw["phase"], 1):
        numbers[("phase", ph["id"])] = str(p_no)
        for s_no, st in enumerate(ph.get("step", []), 1):
            numbers[("step", st["id"])] = f"{p_no}.{s_no}"
    # references are resolved once every number is known (a step may refer forward)
    return Work(tuple(resolve(numbers, s) for s in section), tuple(
        Phase(p_no, *(resolve(numbers, ph.get(k, "")) for k in ("th", "en", "note_th", "note_en")),
              tuple(Step(numbers[("step", st["id"])], resolve(numbers, st["th"]), resolve(numbers, st["en"]))
                    for st in ph.get("step", [])))
        for p_no, ph in enumerate(raw["phase"], 1)), labels, raw["symbols"], numbers)


def main(argv):
    print("\n".join(load(argv[1] if len(argv) > 1 else FILE).render()))


if __name__ == "__main__":
    cli(lambda: main(sys.argv))
