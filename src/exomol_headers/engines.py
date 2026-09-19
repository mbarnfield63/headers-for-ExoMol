"""Optional polars-accelerated `convert` backend.

`polars` is a declared extra (`exomol-headers[polars]`), never a hard
dependency of the stdlib core — imported here, guarded, on first use only.

Targets the specific bottleneck measured in DESIGN.md's Testing section:
`--enrich-quanta` on the H2S chunk (7.2M transitions) took ~52s pure
Python vs ~14s without enrichment — the join itself, done as two
per-row Python dict lookups, is the expensive part. This module replaces
that with a single vectorized left-join. It is not an independent
parser: rows are split the same way as the stdlib path (`line.split()`),
and every column is read/joined/written as a plain string — this tool's
job is labelling columns, not interpreting or reformatting values (a
polars-inferred numeric dtype could silently rewrite "Inf"/"1.050000"
into something that round-trips differently).
"""

from __future__ import annotations

import sys
from pathlib import Path

from .io_utils import open_output, open_text


def _read_records(path: Path, n_cols: int) -> list:
    """Whitespace-split every non-empty line into exactly n_cols fields.

    Padded/truncated defensively so ragged rows never break the
    DataFrame construction below; in the normal case n_cols already
    matches the sniffed file width (see cli.py's _resolved_columns), so
    this is a no-op.
    """
    records = []
    with open_text(path) as f:
        for line in f:
            fields = line.split()
            if not fields:
                continue
            if len(fields) < n_cols:
                fields = fields + [""] * (n_cols - len(fields))
            elif len(fields) > n_cols:
                fields = fields[:n_cols]
            records.append(fields)
    return records


def _import_polars():
    try:
        import polars as pl
    except ImportError:
        raise SystemExit(
            "error: --engine polars requires the 'polars' extra — "
            "install with `pip install exomol-headers[polars]`"
        ) from None
    return pl


def convert(
    data_path: Path,
    out_path: Path,
    compress: str,
    base_names: list,
    enrich: dict | None = None,
) -> int:
    """Stream .states/.trans to CSV via polars. Returns the row count.

    enrich, when given, is {"states_path": Path, "quanta_names": [str]}
    — quanta_names are the bare (unsuffixed) names of every .states
    column past the four fixed ones (i, E, g_tot, J). Mirrors cli.py's
    --enrich-quanta contract: joins upper/lower quanta onto a .trans
    conversion, matching on the trans file's first two columns
    (base_names[0]/[1], always "upper"/"lower").
    """
    pl = _import_polars()

    trans_df = pl.DataFrame(
        _read_records(data_path, len(base_names)),
        schema={n: pl.Utf8 for n in base_names},
        orient="row",
    )
    final_names = list(base_names)

    if enrich is not None:
        states_path = enrich["states_path"]
        quanta_names = enrich["quanta_names"]
        state_names = ["id", "E", "g_tot", "J"] + quanta_names
        states_df = pl.DataFrame(
            _read_records(states_path, len(state_names)),
            schema={n: pl.Utf8 for n in state_names},
            orient="row",
        )

        upper_cols = {q: f"{q}_upper" for q in quanta_names}
        lower_cols = {q: f"{q}_lower" for q in quanta_names}
        upper_df = states_df.select(["id"] + quanta_names).rename(upper_cols)
        lower_df = states_df.select(["id"] + quanta_names).rename(lower_cols)

        trans_df = trans_df.join(
            upper_df, left_on=base_names[0], right_on="id", how="left"
        )
        trans_df = trans_df.join(
            lower_df, left_on=base_names[1], right_on="id", how="left"
        )

        joined_cols = list(upper_cols.values()) + list(lower_cols.values())
        trans_df = trans_df.with_columns(
            [pl.col(c).fill_null("") for c in joined_cols]
        )
        final_names = base_names + joined_cols
        trans_df = trans_df.select(final_names)

    row_count = trans_df.height
    csv_text = trans_df.write_csv(include_header=True)
    with open_output(out_path, compress) as dst:
        dst.write(csv_text)
    print(f"{row_count:,} rows done -> {out_path}", file=sys.stderr)
    return row_count
