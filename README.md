# study-data-vsk

A reproducible **parquet datalake** (Essential Tuple Normal Form) of the three V-Sekai
GitHub organizations — **V-Sekai**, **V-Sekai-fire**, **V-Sekai-multiplayer-fabric** — built
to answer one question:

> Which preexisting, long-haunting task can I **finish today**, completely and to a high
> level of polish, for the satisfaction of closing it out?

The pipeline pulls repos + open issues (public only) and the manuals' MADR decision records,
normalizes them into parquet, and ranks open issues by a **finish-it-today** score. The
payoff is [`reports/finishable_tasks.md`](reports/finishable_tasks.md).

## Quickstart

```sh
pixi run all          # ingest -> ingest-manuals -> normalize -> study
# then open reports/finishable_tasks.md
```

Individual steps:

```sh
pixi run ingest           # GitHub API  -> raw/*.parquet   (a dated snapshot)
pixi run ingest-manuals   # manuals repos MADRs -> raw/decisions.parquet
pixi run normalize        # raw/ -> lake/*.parquet (ETNF) + PK/FK integrity checks
pixi run study            # lake/ -> lake/joy_scores.parquet + reports/finishable_tasks.md
pixi run validate         # re-check PK uniqueness / FK integrity on the existing lake
pixi run lake             # DuckDB sanity queries over the parquet lake
pixi run clean            # remove lake/*.parquet and raw/*.parquet
```

Auth: the GitHub token comes from `GITHUB_TOKEN`, or falls back to your `gh auth token`
login. No secret is written to disk.

## Reproducibility

- **pixi** pins the whole environment (`pixi.lock`, conda-forge) across `win-64`/`linux-64`.
- **Parquet only** for persisted data. Ingest writes a dated snapshot to `raw/*.parquet` (raw
  API objects live verbatim in a `payload` JSON column). `normalize` and `study` read only
  from those parquet files, so re-running them on a fixed snapshot is deterministic.
- **Keys are deterministic UUIDv5** (namespaced hash of each row's natural key) — no random
  or time-based ids — so a given snapshot always yields identical keys. See
  [`SCHEMA.md`](SCHEMA.md).
- `raw/` is git-ignored (regenerate with `pixi run ingest`); `lake/` is committed as the
  study artifact.

## The datalake

Nine ETNF tables in `lake/` — entity relations (`orgs`, `repos`, `users`, `issues`, `labels`,
`decisions`, `snapshot`), all-key junctions (`issue_labels`, `repo_topics`), and a derived
`joy_scores`. Full schema and the ETNF argument are in [`SCHEMA.md`](SCHEMA.md).

## The finish-it-today score

Each open issue in a public, non-archived, non-fork repo is scored
`finishability + haunting + doability`:

- finishability: the repo has 1 open issue (+6), 2 (+4), 3 (+2), ≤5 (+1); closing it
  empties the repo, and a repo taken to zero open issues is a clean win.
- haunting: age >2y (+4), >1y (+3), >6mo (+2), >3mo (+1); +1 if untouched >1y.
- doability: ≤1 comment (+2)/≤3 (+1); short body (+1); a finishing-task title like
  "polish/cleanup/final" (+2); a good-first-issue/help-wanted/docs label (+2). Epics are
  pushed down: epic-ish title (−4), epic/needs-design label (−3).
- elixir: Elixir repo (+4); Elixir/BEAM keywords in the title (+3); a CLI-shaped task
  (+2), because any CLI can ship as a single Elixir binary via
  [Burrito](https://github.com/burrito-elixir/burrito). Ties break toward Elixir.

Issues labelled `blocked`/`wontfix`/`invalid`/`duplicate` are excluded. Weights live at the
top of [`src/study.py`](src/study.py) — tune them to your taste and re-run `pixi run study`.

The report also lists **haunting decisions** — MADRs in the manuals repos still marked
`proposed`/`draft`, i.e. documented intentions waiting to be finished and accepted.

## The Burrito-readiness study

"Which repo can I finish and ship as a downloadable binary?" is a repo-shape question, not an
issue question, so `pixi run ingest-packaging` probes each Elixir/C/C++/Python repo's build
manifest and `pixi run study-cli` ranks them by `burrito_readiness`. Three routes reach one
distributable Elixir binary:

- elixir — an escript / Mix release wrapped by Burrito (native).
- c — a C/C++ CLI wrapped via a NIF/port, then Burrito.
- python — a Python/ML app embedded via `pythonx`, distributed on hex.pm, then Burrito.

The framing is hexagonal (ports and adapters): each repo is a domain **core**; the escript is
the **driving adapter**; Burrito/hex.pm is the **distribution adapter**. A clean library core
just needs a CLI port attached; a web/MCP service is a core on the wrong driving adapter. The
probe also detects an Elixir/Unifex sub-project CLI (e.g. `cloth_fit_cli/`), so a C++ repo whose
CLI already lives in an Elixir subdir is scored on the native route. See
[`reports/burrito_candidates.md`](reports/burrito_candidates.md) for the ranked list and the
chosen primary/fallback finish-today tasks.

## Layout

```
src/ingest.py       GitHub API  -> raw/*.parquet
src/manuals.py      manuals MADRs (tarball, in-memory) -> raw/decisions.parquet
src/packaging.py    build manifests -> raw/packaging.parquet (Burrito-packaging shape)
src/normalize.py    raw/ -> lake/*.parquet (ETNF) + integrity checks
src/study.py        issue scoring -> lake/joy_scores.parquet + reports/finishable_tasks.md
src/study_cli.py    repo scoring  -> lake/cli_readiness.parquet + reports/burrito_candidates.md
src/lake_query.py   DuckDB sanity queries
src/common.py       config, paths, auth, UUIDv5 key helpers
```
