# exomol-headers — Design Doc

## Problem

ExoMol `.states` and `.trans` files carry no in-file column headers. Column
meaning is defined only in the companion `.def` file, in a format most users
never parse. This tool derives labelled headers from `.def` and offers them
back to users in whatever shape they need, without requiring changes to the
canonical ExoMol database files themselves.

## Non-goals

- Not a full ExoMol client (that's `exomole` / RADIS / PyExoCross).
- Not a replacement for the `.def` format or a proposal to change it.
- Not a `.def` parser that aims for exhaustive semantic understanding of
  every field — only what's needed to label `.states`/`.trans` columns.

## Prior art

- **`exomole`** (github.com/hanicinecm/exomole, PyPI, MIT) — the closest
  existing tool. Parses `.def`/`.states`/`.trans` for ExoMol
  maintainers/server-side use. Its `.def` parser (`read_def.py`) is
  **positional**: it expects a fixed, hardcoded line order and only uses
  comments as validation hints. It halts after the "High Energy Complete"
  line. Not forked — reused only as a reference for the field inventory and
  the `get_states_header()` shape. Credit in README.

## Repo & distribution

- Standalone repo, MIT licence, structured so it could later be donated to
  `github.com/exomol` if it proves useful — not built inside that org from
  day one.
- GitHub repo and PyPI package: `headers-for-ExoMol`. Import name stays
  `exomol_headers` (PyPI/repo display name and Python import name don't
  have to match — hyphens aren't valid in import names anyway), console
  script stays `exomol-headers` (shorter to type than the full package
  name). PyPI name availability check deferred to actual publish time.
- Repo is live: https://github.com/mbarnfield63/headers-for-ExoMol
  (public, pushed from the initial scaffold commit). Local clone folder
  is still named `ExoMol_headers`, not `headers-for-ExoMol` — an
  in-session rename attempt was blocked by an OS-level lock on the
  working directory (something holds it open for the session's
  lifetime), not worth fighting; doesn't affect the remote name either
  way. Three names now exist by design, each for its own context: repo/
  PyPI (`headers-for-ExoMol`), CLI command (`exomol-headers`), local
  folder (`ExoMol_headers`, cosmetic only, rename whenever convenient
  outside an active session).
- Core dependency footprint: **stdlib only** (`csv`, `gzip`, `bz2`, `pathlib`,
  `argparse`). Python 3.9+.
- Optional extras, guarded imports:
  - `exomol-headers[polars]` — faster streaming convert backend.
  - `exomol-headers[parquet]` — Parquet output via `pyarrow`.
- No pandas dependency in core.

## `.def` parsing strategy

**Update (validated against real data, 2026-09):** ExoMol has moved to a
structured **`.def.json`** format — this turned out to be the actual
"recent change" that motivated this whole project. It gives an explicit,
ordered `dataset.states.states_file_fields` list: `name`, `desc`, `ffmt`
(Fortran format), `cfmt` (C/Python format) per column. No comment-text
guessing needed, and optional-column order (`unc`/`tau`/`g_J` vs quanta)
is stated directly, not inferred.

**Decision (2026-09-18): legacy text `.def` support dropped, not just
deferred.** The old line-based parser (label-driven keyword matching on
`value # comment` lines) was kept for a while as a fallback for datasets
that hadn't migrated to `.def.json`. The whole ExoMol database has since
moved to `.def.json`, so the fallback path was removed entirely —
`parse_def` now only accepts `.def.json` (detected by leading `{`,
still not by trusting the file extension) and raises clearly on anything
else. `discover_def_files` in `cli.py` only looks for `*.def.json`.

Both real files pulled for testing (CO `4thplus`, H2S `AYT2`) are
`.def.json`, as is everything else in the current database.

Consequences of this choice:

- **Self-contained.** Building the schema from `.def.json` never touches
  `.states`/`.trans`. `inspect` works with only a `.def.json` file present.
- **Unrecognized/unmodelled fields never fail the parse or vanish.** The
  top-level sections not turned into `Column`s (`isotopologue`, `atoms`,
  `irreducible_representations`, `partition_function`, `broad`) are kept
  verbatim in `extra_metadata` — not because they're unrecognized (they're
  well-defined), just not schema-relevant for header generation. Visible
  on the `Schema` object, not lost, not specially typed.
- **Multiple quantum-number "cases"** (rare, mostly Duo-produced diatomics
  with e.g. Hund's case (a)/(b) alternative labellings): auto-pick the
  `.def`-declared default case, silently. No `--case` flag until real
  demand appears (YAGNI) — states/trans column *data* is identical either
  way, only the label set changes.

## Schema object

Per column: `name`, `dtype`, `unit`, `description`. `dtype` is derived
from `.def.json`'s `ffmt` (Fortran format code — `I*`→`int64`,
`F`/`E`/`D`/`G*`→`float64`, `A*`→`str`). The raw `ffmt`/`cfmt` strings
themselves are **not** carried on `Column` — no round-trip-to-fixed-width
use case in scope, only the derived dtype.

Two renderings, chosen by where the output has to stay machine-parseable
vs. where it's purely advisory:

| Rendering | Contains | Used for |
|---|---|---|
| **A — bare names** | column names only, one line | `inject` header line, every `convert` output's header row |
| **C — full schema** | name + dtype + unit + description | `stdout` (`inspect`), `.header` sidecar, `.schema.json` sidecar (auto-emitted alongside every `convert` output) |

Rule: *anything that must stay tabular/parseable gets A; anything
advisory/human-facing gets C.* Applied consistently across every output
mode below.

## Cross-validation: `.def` vs actual file

`.def` is a hint; the file on disk is ground truth. Applies everywhere:

- **`.trans` column count** (3 cols vs 4 with wavenumber) is **sniffed**
  from the first data line, not trusted from any `.def` flag. If `.def`
  disagrees, warn — sniffed value wins.
- **Total column count mismatch** between `.def`'s declared count and the
  actual file: never a hard error. Warn on stderr, keep whatever columns
  matched, fall back to generic `col_N` names for the unexplained
  extra/missing ones.
- Never silent, never a hard block on structural drift.

## Output modes (v1)

- `sidecar` — writes `<file>.header` (rendering C, plain text) and
  `<file>.schema.json` (rendering C, structured) next to the original.
  Original file untouched. Default mode.
- `inspect` — prints rendering C to stdout. No file I/O beyond `.def`.
- `convert` — streams `.states`/`.trans` to `.csv`/`.tsv`
  (`[parquet]`/`[polars]` optional) with rendering-A header row, plus an
  auto-emitted `.schema.json` sidecar (rendering C) alongside it.
- `inject` — writes a **copy** of `.states`/`.trans` with a bare (A)
  header line prepended. **Never mutates the original file, never the
  default mode.** Rejected as a default because rewriting a multi-GB
  canonical data file for one header line risks checksums/reproducibility
  for near-zero benefit.

## `.trans`-specific handling

- Column count: sniffed (see above), not declared.
- **Both `.states` and `.trans` are parsed by whitespace-splitting**
  (`line.split()`), not fixed-width slicing from `.def`'s format strings.
  The original plan was format-driven fixed-width parsing for `.states`
  (quantum columns can, in principle, abut without a separating space) —
  simplified to whitespace-split for v1 since every real column so far
  (CO, H2S — including string fields like `+/-`, `e/f`, `X(1Sigma+)`,
  `Ma`/`Ca`) has split cleanly on whitespace. ponytail: revisit fixed-width
  slicing only if a real file turns up where it doesn't (a value with an
  internal space, or truly abutting fields) — not before.
- **Chunked `.trans` files** (large linelists split by wavenumber range,
  sharing one `.def`, e.g. H2S/AYT2's 35 files): each file is one
  `convert` invocation today — **not yet auto-batched**. Calling `convert`
  once per chunk naturally gives "one output per chunk" (see Testing), but
  there's no directory/glob mode yet that discovers and runs all chunks in
  one command; see Open/Deferred.
- **`--enrich-quanta <states-file>`** (opt-in, off by default, `convert`
  on a `.trans` file only): joins each transition row with its upper/lower
  state's full quantum numbers, not just IDs. Implementation: builds an
  `id -> quanta` dict from `.states` once (orders of magnitude smaller
  than `.trans`, fits in memory even for the largest linelists), streams
  `.trans`, looks up both ids per row; a row whose id isn't found gets
  empty-string quanta rather than a shifted/misaligned row. Column naming:
  **suffix style** (`J_upper`, `J_lower`), not prefix. Prints a cost
  estimate (extra-columns-per-row) before running, since this measurably
  inflates output size and runtime — the exact tradeoff that motivated
  making it opt-in (see Testing for real timing numbers).

## CLI shape

Actual argparse signatures (`exomol_headers/cli.py`):

```
exomol-headers inspect  <mol>.def|.def.json
exomol-headers sidecar  <mol>.states|.trans  [--def <path>]
exomol-headers inject   <mol>.states|.trans  [--def <path>]
exomol-headers convert  <mol>.states|.trans  -o <out>
                         [--def <path>] [--compress none|gz|bz2]
                         [--enrich-quanta <mol>.states]
                         [--engine python|polars]
```

- Subcommands (verbs), not one command with mode flags.
- `inspect` takes a `.def`/`.def.json` path directly — no auto-discovery
  (there's no data file to derive a stem from).
- `sidecar`/`inject`/`convert` take the data file as the required
  positional and auto-discover its `.def`/`.def.json` **by filename stem**
  when `--def` is omitted (ExoMol's own naming convention:
  `<Molecule>__<Dataset>.def(.json)` alongside
  `<Molecule>__<Dataset>.states`/`.trans`). Always prints which file it
  used to stderr.
- If auto-discovery matches **more than one** `.def`/`.def.json`
  candidate: don't error, don't guess — print all matches and run the
  operation against all of them.
- **`--engine polars` (2026-09-18, pulled forward from deferred):**
  implemented in `engines.py`, guarded import — `polars` stays an
  optional extra (`exomol-headers[polars]`), never a core dependency.
  Scoped deliberately narrow: it targets the one bottleneck the Testing
  section's real numbers actually identified (the `--enrich-quanta`
  join), not a general rewrite of row parsing. Rows are still
  whitespace-split the same way as the `python` engine (`line.split()`)
  — polars can't safely be pointed at these files as a native
  ragged-whitespace CSV source — and every column is read/joined/written
  as `Utf8`, never inferred to a numeric dtype, so values pass through
  unmodified (no risk of `polars` reformatting `"1.050000"` or `"Inf"`).
  The join itself (`.states` id → quanta, both upper and lower) is a
  single vectorized `DataFrame.join`, replacing two per-row Python dict
  lookups. `pyarrow`/Parquet output remains undone — see Open/Deferred.

## I/O details

- **Input** compression (`.gz`/`.bz2`/plain) always transparently
  detected and decompressed — stdlib `gzip`/`bz2` drop-in `open()`, not
  optional.
- **Output** defaults to plain text; `--compress gz|bz2|none` is opt-in.
  Default plain because the point of `convert` is removing a decompress
  step before the data reaches pandas/Excel/etc.
- Progress feedback on long streaming runs: stdlib-only row-count/percent
  line to stderr, updated every ~100k rows or 1%. No `tqdm` dependency
  (violates the stdlib-core rule for a cosmetic feature).

## Testing

**Real fixtures now in hand** (in `./data`, gitignored — not committed,
large binary downloads):

- **CO** (`12C-16O__4thplus`) — diatomic. 11,264 states, 609,470
  transitions (single `.trans` file, 4 columns incl. wavenumber).
- **H2S** (`1H2-32S__AYT2`) — triatomic, C2v. 220,630 states; 115M
  transitions split across 35 chunk files (only chunk `00000-01000`
  downloaded, 3 columns, no wavenumber).

All four subcommands run end-to-end against both and were verified
against real numbers (row counts match each `.def.json`'s declared
`number_of_states`/`number_of_transitions`; column counts match exactly,
zero mismatch warnings on either dataset). Confirms, with real data:

- `.trans` column-count sniffing (Q7) — CO sniffs to 4 cols, H2S chunk to
  3, correctly, from two differently-shaped real files.
- `--enrich-quanta` join (Q8) — ran full H2S chunk (7.2M transitions) in
  ~52s pure Python/stdlib; ~14s without enrichment. Gives a real number
  for the "polars would meaningfully help at full-database scale" claim
  from Q3 — 35 chunks × ~52s ≈ 30 min pure-Python for one dataset's full
  enrichment run, not disqualifying but a real candidate for a polars
  backend.
- **`--engine polars` validated against the same H2S chunk (2026-09-18,
  in an isolated `uv`-managed venv — polars isn't installed by the
  stdlib-only core):** the enrich-quanta join dropped from ~48s to
  ~30.6s (~1.6×) on this machine, and output was **byte-identical** to
  the `python` engine's — same run, same file, `diff` clean, both with
  and without `--enrich-quanta`. Confirms the join was in fact the
  bottleneck (not I/O or the whitespace-split itself, which the polars
  engine also still does in Python) and that reading/joining/writing
  every column as `Utf8` doesn't reformat any value in practice, not
  just in theory.
- Real quantum-number columns are messier than the synthetic fixture
  assumed: names carry namespacing (`hunda:Lambda`, `Herzberg:v1`,
  `Auxiliary:SourceType`), and values include `Inf`/`NaN` (CO's ground
  state has no measured lifetime). Nothing in the tool special-cases
  these — they pass through as opaque strings, which is correct: it's
  not this tool's job to interpret physics, only to label columns.

The synthetic fixtures that previously lived at `tests/fixtures/` existed
only to exercise the legacy text-`.def` code path; they were removed
along with that parser (2026-09-18 — see "`.def` parsing strategy"
above). Test coverage for `.def.json` parsing now runs entirely against
the real `./data` fixtures and is skipped (not failed) when that
directory isn't present.

## Open / deferred (explicitly out of scope for v1)

- `--case <n>` flag for multi-case `.def` files — add only on real demand.
- `--engine polars` for `convert` is implemented (2026-09-18 — see CLI
  shape and Testing above); `--format parquet` via `pyarrow` is still
  undone — `pyarrow` stays a declared-but-unused extra until CSV-only
  output turns out to be an actual limitation.
- Directory/glob batch mode (discover and convert every `.trans` chunk in
  a directory in one command) — today it's one `convert` call per chunk
  file. Fine for the two-dataset scale tested so far; revisit if running
  35 commands by hand for one full H2S conversion turns out to be annoying
  in practice rather than theoretically annoying.
- Fixed-width `.states`/`.trans` parsing driven by `.def`'s Fortran format
  strings — simplified to whitespace-split for v1; every real column
  tested so far splits cleanly. Revisit only if a real file doesn't.
- PyPI name availability check — deferred to publish time.
- Contribution/donation to `github.com/exomol` — deferred until the tool
  has proven itself standalone.
