"""Self-contained .def parser — JSON primary, legacy text as fallback.

ExoMol has moved from the old line-based `.def` (`value # comment`) to a
structured `.def.json` file. The JSON gives an explicit, ordered
`states_file_fields` list — name, description, and Fortran/C format per
column — so there's no more guessing column order or matching comment
text. Older datasets may still ship the legacy text `.def`; that parser
is kept as a fallback, unchanged in spirit (label-driven, tolerant of
unrecognized lines) but now the secondary path, not the primary one.

Either way, parsing never touches the paired .states/.trans files —
building a Schema needs only the .def(.json).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# --- shared result type -----------------------------------------------


@dataclass
class Column:
    name: str
    dtype: str
    unit: Optional[str]
    description: str


@dataclass
class Schema:
    source: Path
    columns: list = field(default_factory=list)  # ordered Column list
    flags: dict = field(default_factory=dict)  # lifetime/lande/uncertainty availability
    extra_metadata: dict = field(
        default_factory=dict
    )  # unrecognized/unused fields, kept not dropped
    trans_file_count: int = 1

    def states_columns(self) -> list:
        return self.columns

    @staticmethod
    def render_a(columns: list) -> str:
        """Bare column names, one line — for injection & convert header rows."""
        return ",".join(c.name for c in columns)

    @staticmethod
    def render_c(columns: list) -> str:
        """Full schema, human-readable — for stdout & .header sidecars."""
        lines = []
        for c in columns:
            unit = f" [{c.unit}]" if c.unit else ""
            lines.append(f"{c.name}{unit}: {c.dtype} - {c.description}")
        return "\n".join(lines)


# --- JSON .def.json parser (current ExoMol format) ---------------------


def _dtype_from_ffmt(ffmt: str) -> str:
    """Fortran format code -> dtype. I=int, F/E/ES/D/G=float, A=str."""
    ffmt = (ffmt or "").strip().upper()
    if ffmt.startswith("I"):
        return "int64"
    if ffmt[:1] in ("F", "E", "D", "G"):
        return "float64"
    if ffmt.startswith("A"):
        return "str"
    return "str"


def _unit_from_desc(desc: str) -> Optional[str]:
    """Best-effort unit extraction from a free-text description (e.g.
    'State energy in cm-1' -> 'cm-1'). Purely cosmetic for render_c;
    never affects parsing or column identity."""
    if not desc:
        return None
    m = re.search(r"\bin (cm-1|s|K|Da)\b", desc)
    return m.group(1) if m else None


def parse_def_json(path: Path) -> Schema:
    data = json.loads(path.read_text(encoding="utf-8"))
    schema = Schema(source=path)

    states = data.get("dataset", {}).get("states", {})
    schema.flags = {
        "uncertainty": bool(states.get("uncertainties_available")),
        "lifetime": bool(states.get("lifetime_available")),
        "lande": bool(states.get("lande_g_available")),
    }

    for f in states.get("states_file_fields", []):
        name = f.get("name", "?")
        desc = f.get("desc", "")
        schema.columns.append(
            Column(
                name, _dtype_from_ffmt(f.get("ffmt", "")), _unit_from_desc(desc), desc
            )
        )

    schema.trans_file_count = (
        data.get("dataset", {})
        .get("transitions", {})
        .get("number_of_transition_files", 1)
    )

    # Keep top-level metadata that isn't part of the column schema —
    # visible, not lost, same "never drop what you don't specially
    # handle" principle as the legacy parser's extra_metadata.
    for key in (
        "isotopologue",
        "atoms",
        "irreducible_representations",
        "partition_function",
        "broad",
    ):
        if key in data:
            schema.extra_metadata[key] = data[key]

    return schema


# --- legacy line-based .def parser (fallback for pre-JSON datasets) ----

_FLAG_KEYWORDS = {
    "uncertainty": re.compile(r"uncertain", re.I),
    "lifetime": re.compile(r"lifetime", re.I),
    "lande": re.compile(
        r"land", re.I
    ),  # covers "Lande"/"Landé" without depending on encoding
}
_QUANTA_COUNT_KEYWORD = re.compile(r"number of quantum", re.I)
_QUANTA_LABEL_KEYWORD = re.compile(r"quantum (label|number)|label of.*quantum", re.I)

# Base states-file columns present in every legacy-format ExoMol dataset.
_BASE_COLUMNS = [
    ("i", "int64", None, "state ID"),
    ("E", "float64", "cm-1", "term value (energy)"),
    ("g_tot", "int64", None, "total degeneracy"),
    ("J", "float64", None, "total angular momentum quantum number"),
]

# Legacy-format optional-column order is unverified against a real
# pre-JSON .def (none obtained yet). Wrong guess only warns (cli.py
# mismatch check), never silently mislabels.
_OPTIONAL_COLUMNS = {
    "uncertainty": ("unc", "float64", "cm-1", "uncertainty in the energy"),
    "lifetime": ("tau", "float64", "s", "radiative lifetime"),
    "lande": ("g_J", "float64", None, "Landé g-factor"),
}


def _split_line(line: str):
    line = line.strip()
    if not line:
        return None
    if "#" in line:
        value, comment = line.split("#", 1)
    else:
        value, comment = line, ""
    return value.strip(), comment.strip()


def parse_def_text(path: Path) -> Schema:
    schema = Schema(source=path)

    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        parsed = _split_line(raw)
        if parsed is not None:
            lines.append(parsed)

    pending_quanta_count = None
    quanta_labels = []

    for value, comment in lines:
        matched = False
        for key, pattern in _FLAG_KEYWORDS.items():
            if pattern.search(comment):
                schema.flags[key] = value.strip() in ("1", "true", "True")
                matched = True
                break
        if matched:
            continue

        if _QUANTA_COUNT_KEYWORD.search(comment):
            try:
                pending_quanta_count = int(value.split()[0])
            except (ValueError, IndexError):
                pass
            continue

        if _QUANTA_LABEL_KEYWORD.search(comment):
            token = value.split()[0] if value.split() else value
            quanta_labels.append(token)
            continue

        key = comment if comment else value
        if key:
            schema.extra_metadata[key] = value

    if pending_quanta_count is not None and len(quanta_labels) > pending_quanta_count:
        quanta_labels = quanta_labels[:pending_quanta_count]

    schema.columns = [Column(n, dt, u, d) for n, dt, u, d in _BASE_COLUMNS]
    for key in ("uncertainty", "lifetime", "lande"):
        if schema.flags.get(key):
            n, dt, u, d = _OPTIONAL_COLUMNS[key]
            schema.columns.append(Column(n, dt, u, d))
    schema.columns.extend(
        Column(label, "str", None, "quantum number (see .def for meaning)")
        for label in quanta_labels
    )
    return schema


# --- dispatch ------------------------------------------------------------


def parse_def(path) -> Schema:
    """Parse a .def or .def.json file into a Schema. Format is detected
    by content (leading '{'), not by trusting the file extension."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("{"):
        return parse_def_json(path)
    return parse_def_text(path)
