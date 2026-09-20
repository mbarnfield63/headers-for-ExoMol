# headers-for-ExoMol

Labelled headers, CSV conversion, and schema sidecars for [ExoMol](https://www.exomol.com)
`.states`/`.trans` files — derived from their `.def` file, without changing
the originals.

Package name is `headers-for-ExoMol`; the installed CLI command is
`exomol-headers` (shorter to type, unrelated to the PyPI/repo name).

ExoMol's canonical data files carry no in-file column headers; column
meaning lives only in the `.def` file, in a format not everyone wants to
parse by hand. This tool reads a `.def` and gives you the column labels
back in whichever shape suits your workflow.

Repo: https://github.com/mbarnfield63/headers-for-ExoMol

See [`DESIGN.md`](DESIGN.md) for the full design rationale.

## Install

Not on PyPI yet. For now:

```
git clone https://github.com/mbarnfield63/headers-for-ExoMol
pip install -e headers-for-ExoMol
```

Once published:

```
pip install headers-for-ExoMol          # stdlib only, everything below works
pip install headers-for-ExoMol[polars]  # faster `convert --engine polars` (see Usage)
pip install headers-for-ExoMol[parquet] # reserved for Parquet output — not wired up yet
```

## Usage

Real dataset names (CO `4thplus`, diatomic; H2S `AYT2`, triatomic) — both
verified end to end, see `DESIGN.md` → Testing:

```
exomol-headers inspect  12C-16O__4thplus.def.json
exomol-headers sidecar  12C-16O__4thplus.states.bz2
exomol-headers convert  12C-16O__4thplus.states.bz2 -o co.csv
exomol-headers convert  12C-16O__4thplus.trans.bz2  -o co_trans.csv \
    --enrich-quanta 12C-16O__4thplus.states.bz2
exomol-headers inject   12C-16O__4thplus.states.bz2   # writes a *copy*, never in-place
```

`inspect` takes a `.def`/`.def.json` path directly. The other subcommands
take the `.states`/`.trans` file and auto-discover its `.def`/`.def.json`
next to it by filename stem; pass `--def path/to/file.def.json` to
override, or when auto-discovery finds more than one candidate.

`convert` defaults to a pure-stdlib engine. Add `--engine polars` (needs
the `[polars]` extra) for a faster `--enrich-quanta` join on large
files — verified byte-identical output, ~1.6× faster on a real 7.2M-row
H2S chunk, see `DESIGN.md` → Testing:

```
exomol-headers convert  1H2-32S__AYT2__00000-01000.trans.bz2 -o h2s_trans.csv \
    --enrich-quanta 1H2-32S__AYT2.states.bz2 --engine polars
```

Point `convert` at a **directory** instead of a file to batch-convert every
`.trans` chunk in it (large linelists are split across many chunk files
sharing one `.def.json`/`.states` file, e.g. H2S/AYT2's 35 chunks) — `-o`
then names the output directory, and each chunk gets its own
`<chunk-stem>.csv` + `.schema.json`. With `--enrich-quanta`, the `.states`
file is loaded into memory once and shared across every chunk, not
rebuilt per file:

```
exomol-headers convert  1H2-32S__AYT2_trans_chunks/ -o h2s_csvs/ \
    --enrich-quanta 1H2-32S__AYT2.states.bz2 --engine polars
```

## Status

Early scaffold, validated against real data. ExoMol's whole database has
moved to a structured `.def.json` format (confirmed against real CO and
H2S downloads); this tool only supports that format now — legacy
line-based `.def` is not parsed. See `DESIGN.md` → Testing for what's
been verified.

## Credit

Column-inventory reference: [`exomole`](https://github.com/hanicinecm/exomole)
(Hanicinec, MIT) — not forked; its positional `.def` parser is the thing
this tool deliberately does differently (label-driven, tolerant of format
drift), but its field list was useful as a starting reference.

## Licence

MIT — see `LICENSE`.
