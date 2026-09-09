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

See [`DESIGN.md`](DESIGN.md) for the full design rationale.

## Install

```
pip install headers-for-ExoMol          # stdlib only, everything below works
pip install headers-for-ExoMol[polars]  # reserved for a faster convert backend — not wired up yet
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

## Status

Early scaffold, validated against real data. ExoMol has moved to a
structured `.def.json` format (confirmed against real CO and H2S
downloads) — that's the primary parser path now; the original
keyword-matching text parser is kept as a fallback for datasets that
haven't migrated. See `DESIGN.md` → Testing for what's been verified.

## Credit

Column-inventory reference: [`exomole`](https://github.com/hanicinecm/exomole)
(Hanicinec, MIT) — not forked; its positional `.def` parser is the thing
this tool deliberately does differently (label-driven, tolerant of format
drift), but its field list was useful as a starting reference.

## Licence

MIT — see `LICENSE`.
