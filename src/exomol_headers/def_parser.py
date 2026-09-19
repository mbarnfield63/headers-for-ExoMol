"""Self-contained `.def.json` parser.

ExoMol has moved from the old line-based `.def` (`value # comment`) to a
structured `.def.json` file. The JSON gives an explicit, ordered
`states_file_fields` list — name, description, and Fortran/C format per
column — so there's no more guessing column order or matching comment
text. The whole database has migrated, so only `.def.json` is supported;
the legacy text format is not.

Parsing never touches the paired .states/.trans files — building a
Schema needs only the .def.json.
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
    # visible on Schema, not silently dropped.
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


# --- dispatch ------------------------------------------------------------


def parse_def(path) -> Schema:
    """Parse a `.def.json` file into a Schema.

    Legacy text `.def` is not supported — the ExoMol database has fully
    migrated to `.def.json`.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if not text.lstrip().startswith("{"):
        raise ValueError(
            f"{path}: not a .def.json file — legacy text .def is not supported"
        )
    return parse_def_json(path)
