"""exomol-headers CLI.

Subcommands: inspect, sidecar, inject, convert. See DESIGN.md for the
rationale behind every choice below.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .def_parser import Schema, parse_def
from .io_utils import open_output, open_text, sniff_column_count

_DATA_SUFFIXES = (".states", ".trans")
_COMPRESSED_SUFFIXES = (".bz2", ".gz")


def discover_def_files(data_path: Path) -> list:
    """Find the .def(s) sharing a data file's naming stem.

    Exact stem match wins when present. Otherwise every .def in the same
    directory is a candidate — caller runs against all of them (never
    guesses, never blocks on ambiguity; see DESIGN.md CLI shape).
    """
    directory = data_path.parent
    stem = data_path.name
    for suffix in _COMPRESSED_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    for suffix in _DATA_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    for candidate_suffix in (".def.json", ".def"):
        exact = directory / f"{stem}{candidate_suffix}"
        if exact.exists():
            return [exact]
    return sorted(directory.glob("*.def.json")) + sorted(directory.glob("*.def"))


def resolve_def_files(data_path: Path, explicit_def) -> list:
    if explicit_def:
        return [Path(explicit_def)]
    found = discover_def_files(data_path)
    if not found:
        sys.exit(f"error: no .def found next to {data_path}; pass one explicitly")
    if len(found) > 1:
        print(
            f"multiple .def candidates found, running against all: "
            f"{', '.join(p.name for p in found)}",
            file=sys.stderr,
        )
    else:
        print(f"using {found[0].name}", file=sys.stderr)
    return found


def _is_trans(data_path: Path) -> bool:
    name = data_path.name
    for c in _COMPRESSED_SUFFIXES:
        name = name[: -len(c)] if name.endswith(c) else name
    return name.endswith(".trans")


def _resolved_columns(schema: Schema, data_path: Path):
    """states_columns() cross-checked against the actual file width.

    .def is a hint, the file is ground truth (Q10): on mismatch, warn and
    keep what matched, fall back to generic col_N names for the rest.
    """
    if _is_trans(data_path):
        n = sniff_column_count(data_path)
        names = ["upper", "lower", "A_coef"]
        if n >= 4:
            names.append("nu")
        for extra in range(len(names), n):
            names.append(f"col_{extra}")
        from .def_parser import Column

        return [Column(n_, "float64", None, "see ExoMol .trans spec") for n_ in names][
            :n
        ]

    columns = schema.states_columns()
    actual = sniff_column_count(data_path)
    if actual and actual != len(columns):
        print(
            f"warning: {data_path.name} has {actual} columns, "
            f".def implies {len(columns)} — using observed file as ground truth",
            file=sys.stderr,
        )
        from .def_parser import Column

        if actual > len(columns):
            columns = columns + [
                Column(f"col_{i}", "str", None, "unrecognized column")
                for i in range(len(columns), actual)
            ]
        else:
            columns = columns[:actual]
    return columns


def cmd_inspect(args):
    for def_path in resolve_def_files(Path(args.def_file), args.def_file):
        schema = parse_def(def_path)
        print(f"--- {def_path.name} ---")
        print(Schema.render_c(schema.states_columns()))
        if schema.extra_metadata:
            print("\n(unrecognized .def fields, kept as metadata:)")
            for k, v in schema.extra_metadata.items():
                print(f"  {k}: {v}")


def cmd_sidecar(args):
    data_path = Path(args.data_file)
    for def_path in resolve_def_files(data_path, args.def_file):
        schema = parse_def(def_path)
        columns = _resolved_columns(schema, data_path)

        header_path = data_path.with_suffix(data_path.suffix + ".header")
        header_path.write_text(Schema.render_c(columns) + "\n", encoding="utf-8")

        schema_path = data_path.with_suffix(data_path.suffix + ".schema.json")
        schema_path.write_text(
            json.dumps(
                [
                    {
                        "name": c.name,
                        "dtype": c.dtype,
                        "unit": c.unit,
                        "description": c.description,
                    }
                    for c in columns
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"wrote {header_path.name}, {schema_path.name}")


def cmd_inject(args):
    data_path = Path(args.data_file)
    def_files = resolve_def_files(data_path, args.def_file)
    schema = parse_def(def_files[0])
    columns = _resolved_columns(schema, data_path)

    out_path = data_path.with_name(data_path.name + ".headered")
    with open_text(data_path) as src, open(out_path, "wt", encoding="utf-8") as dst:
        dst.write(Schema.render_a(columns) + "\n")
        for line in src:
            dst.write(line)
    print(f"wrote {out_path} (copy; original untouched)")


def _quanta_lookup(states_path: Path, columns, suffix: str):
    """id -> {name+suffix: value} for every quantum-number column."""
    id_idx = 0  # 'i' is always column 0
    # everything past the 4 fixed base columns (i, E, g_tot, J): optional
    # flags (unc/tau/g_J) plus quanta — all joinable per-state properties.
    quanta_idx = [(i, c.name) for i, c in enumerate(columns) if i >= 4]
    lookup = {}
    with open_text(states_path) as f:
        for line in f:
            fields = line.split()
            if not fields:
                continue
            row_id = fields[id_idx]
            lookup[row_id] = {
                f"{name}{suffix}": (fields[i] if i < len(fields) else "")
                for i, name in quanta_idx
            }
    return lookup


def cmd_convert(args):
    data_path = Path(args.data_file)
    def_files = resolve_def_files(data_path, args.def_file)
    schema = parse_def(def_files[0])
    columns = _resolved_columns(schema, data_path)
    names = [c.name for c in columns]

    upper_lookup = lower_lookup = None
    if args.enrich_quanta:
        if not _is_trans(data_path):
            sys.exit("error: --enrich-quanta only applies to .trans conversion")
        states_path = Path(args.enrich_quanta)
        states_schema = parse_def(def_files[0])
        states_columns = _resolved_columns(states_schema, states_path)
        n_quanta = len(states_columns) - 4
        est = n_quanta * 2
        print(
            f"--enrich-quanta: adding ~{est} columns per row "
            f"(states file loaded into memory)",
            file=sys.stderr,
        )
        upper_lookup = _quanta_lookup(states_path, states_columns, "_upper")
        lower_lookup = _quanta_lookup(states_path, states_columns, "_lower")
        quanta_names = [c.name for c in states_columns[4:]]
        names = (
            names
            + [f"{n}_upper" for n in quanta_names]
            + [f"{n}_lower" for n in quanta_names]
        )
        # fallback for a trans row whose id isn't found in .states (data
        # error) — keeps column count aligned instead of silently
        # shifting every field after it.
        missing_upper = {f"{n}_upper": "" for n in quanta_names}
        missing_lower = {f"{n}_lower": "" for n in quanta_names}

    out_path = Path(args.out)
    with open_text(data_path) as src, open_output(out_path, args.compress) as dst:
        dst.write(",".join(names) + "\n")
        row_count = 0
        for line in src:
            fields = line.split()
            if not fields:
                continue
            row = fields
            if upper_lookup is not None:
                row = (
                    row
                    + list(upper_lookup.get(fields[0], missing_upper).values())
                    + list(lower_lookup.get(fields[1], missing_lower).values())
                )
            dst.write(",".join(row) + "\n")
            row_count += 1
            if row_count % 100_000 == 0:
                print(f"\r{row_count:,} rows...", end="", file=sys.stderr)
        print(f"\r{row_count:,} rows done -> {out_path}", file=sys.stderr)

    schema_path = out_path.with_suffix(out_path.suffix + ".schema.json")
    schema_path.write_text(
        json.dumps(
            [
                {"name": n, "dtype": "str", "unit": None, "description": ""}
                for n in names
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


def build_parser():
    p = argparse.ArgumentParser(prog="exomol-headers")
    sub = p.add_subparsers(dest="command", required=True)

    def add_def_arg(sp):
        sp.add_argument(
            "--def",
            dest="def_file",
            default=None,
            help="explicit .def path (auto-discovered by stem if omitted)",
        )

    p_inspect = sub.add_parser("inspect", help="print schema derived from a .def")
    p_inspect.add_argument("def_file")
    p_inspect.set_defaults(func=cmd_inspect)

    p_sidecar = sub.add_parser("sidecar", help="write .header + .schema.json sidecars")
    p_sidecar.add_argument("data_file")
    add_def_arg(p_sidecar)
    p_sidecar.set_defaults(func=cmd_sidecar)

    p_inject = sub.add_parser(
        "inject", help="write a copy with a bare header line prepended"
    )
    p_inject.add_argument("data_file")
    add_def_arg(p_inject)
    p_inject.set_defaults(func=cmd_inject)

    p_convert = sub.add_parser("convert", help="stream-convert .states/.trans to CSV")
    p_convert.add_argument("data_file")
    p_convert.add_argument("-o", "--out", required=True)
    p_convert.add_argument("--compress", choices=["none", "gz", "bz2"], default="none")
    p_convert.add_argument(
        "--enrich-quanta",
        default=None,
        help="path to .states file to join full quanta into a .trans convert",
    )
    add_def_arg(p_convert)
    p_convert.set_defaults(func=cmd_convert)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
