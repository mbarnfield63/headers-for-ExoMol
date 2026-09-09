"""Transparent compressed-file I/O and .trans column sniffing.

.def is a hint; the file on disk is ground truth (see DESIGN.md). Column
counts here are always observed from the data, never trusted from a .def
flag alone.
"""

from __future__ import annotations

import bz2
import gzip
from pathlib import Path


def open_text(path):
    """Open .gz/.bz2/plain text transparently, by extension.

    Always UTF-8: the platform-default codepage (cp1252 on Windows) would
    otherwise silently corrupt or fail on any non-ASCII byte.
    """
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    if path.suffix == ".bz2":
        return bz2.open(path, "rt", encoding="utf-8")
    return open(path, "rt", encoding="utf-8")


def open_output(path, compress: str = "none"):
    """Open an output file, optionally compressing (opt-in, default none)."""
    path = Path(path)
    if compress == "gz":
        return gzip.open(f"{path}.gz", "wt", encoding="utf-8")
    if compress == "bz2":
        return bz2.open(f"{path}.bz2", "wt", encoding="utf-8")
    return open(path, "wt", encoding="utf-8")


def sniff_column_count(path) -> int:
    """Count whitespace-separated fields on the first non-empty line."""
    with open_text(path) as f:
        for line in f:
            if line.strip():
                return len(line.split())
    return 0
