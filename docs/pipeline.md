# Building the catalogue in CI

Four commands do the work. GitHub Actions just arranges them.

```bash
storagegen schema              # every variable, as JSON
storagegen plan                # what the catalogue says to build
storagegen batch --chunk 0 --chunks 4 --out out
storagegen verify out          # re-read the files and check them
storagegen index out           # one INDEX.md over a merged batch
```

## Variables are discovered, not restated

`storagegen schema` prints every option of every generator, with its kind,
default, range, choices and help text, straight from the declaration the
generator already uses for CLI parsing and validation:

```bash
storagegen schema bin-shelf | jq '.generators["bin-shelf"].options[].name'
```

Nothing needs a second list of variables kept in step by hand, because there
is only one list. `catalogue.json` names the products worth building, not the
variables they are made of:

```json
{
  "items": [
    { "name": "fit-gauge_greenmade-mini", "generator": "fit-gauge" }
  ],
  "sweeps": [{
    "generator": "bin-shelf",
    "name": "bin-shelf_greenmade-mini_{columns}x{rows}_{pattern}",
    "options": { "bin": "greenmade-mini" },
    "axes": {
      "columns": [1, 2],
      "rows": [2, 3],
      "pattern": ["windows", "grid", "honeycomb", "diamond", "round", "triangle"]
    }
  }]
}
```

`items` are one variant each. `sweeps` expand their axes into every
combination. Every resulting variant is checked against its generator's
options the moment the catalogue is read, so a typo fails in the plan job in
about a second rather than in two hundred build jobs:

```
error: catalogue.json: bin-shelf_greenmade-mini_2x9_grid: rows: 9 is above the maximum 12
```

## One job per chunk, not one job per item

```bash
storagegen plan --chunk-size 8 --emit matrix
[{"chunk": 0, "chunks": 4, "count": 7}, {"chunk": 1, "chunks": 4, "count": 7}, ...]
```

That array feeds `strategy.matrix.include` through `fromJson()`. Each build job
then rebuilds the same plan and takes its own share:

```bash
storagegen batch --chunk 2 --chunks 4 --out out
```

Chunks are dealt out round robin rather than sliced contiguously, so jobs stay
about the same size even though a 2x3 rack costs several times a fit gauge. No
variant list travels through the matrix, so nothing has to survive shell
quoting, and the plan is deterministic: same catalogue and same arguments give
the same split in every job.

Two reasons to chunk rather than run one job per item. A matrix is capped at
256 jobs, and a job spends longer starting up than it does building a rack --
the whole 27-item catalogue builds in about a minute on one runner.

**Building a given number of items:** `--limit N`. By default the N are spread
evenly across the catalogue so a small run still covers the range of it;
`--pick first` takes the first N in catalogue order instead. The
`workflow_dispatch` form takes the limit as an input.

## Watertightness, and where it is checked

The generators build on manifold3d, which cannot produce a non-manifold solid.
Checking the in-memory object would therefore prove almost nothing. What can
still go wrong is everything after it: a truncated write, a wrong triangle
count in an STL header, an exporter dropping a vertex, a file mangled in
transit between jobs.

So `storagegen verify` reads the bytes back off disk and works out the
topology from scratch. Per mesh it reports, and fails on:

| Check | Why it matters |
|---|---|
| Header triangle count matches the file length | catches a truncated or padded write |
| Every edge belongs to exactly two triangles | a hole in the surface, or a non-manifold seam |
| Those two uses run in opposite directions | a triangle facing inward |
| Signed volume is positive | the whole surface is inside out |
| One connected component | the model would come off the bed in pieces |
| No NaN or infinite coordinates | silent corruption |
| 3MF declares millimetres, and its indices are in range | a model that imports at the wrong scale |
| Volume and bounding box match `manifest.json` | the described model is the delivered one |

Zero-area triangles are reported as a **warning**, not a failure. Booleans
leave a few wherever two coplanar faces meet; the surface is still closed and
every slicer skips them. `--strict` promotes warnings to failures if you would
rather not ship any.

STL carries no topology at all -- three unshared float32 corners per triangle
-- so any reader has to weld coincident vertices before it can say anything
about watertightness. That is exactly what a slicer does when it opens the
file, which is why welding here is the test rather than a workaround. The weld
snaps to a fixed 0.001 mm grid instead of a scale-dependent tolerance, so the
same file always gives the same verdict.

`batch` runs this on everything it writes and fails the job on a bad mesh, and
the collect job runs it again over the merged set, because what ships is that
directory rather than whatever any one job happened to have.

## Two things this pipeline deliberately does not do

**No mesh repair.** If a model fails validation, the geometry is wrong upstream
and that is where it gets fixed. Filling a hole automatically would ship a
model whose shape nobody chose, and would hide the bug that made the hole. The
check has already earned its keep this way: it caught four non-manifold edges
in one pattern variant, and following them back found a front stop meeting a
rail along exactly one line -- fine for manifold3d, which indexes those
vertices separately, but a pinch the moment anything welds by position. That
was a modelling bug worth fixing, not a mesh worth patching.

**No OpenSCAD, no `xvfb-run`, no virtual display.** Geometry comes from
manifold3d and previews from a small software rasteriser in this repo, both
pure Python and numpy. There is nothing to render on a screen, so there is no
display to fake and no segfault to work around. `pip install -e .` is the
whole setup step.

## The workflows

**`.github/workflows/ci.yml`** runs on every push: unit tests, then
`plan` to prove the catalogue still expands, then a four-item smoke build and
`verify`, with the output kept as an artifact.

**`.github/workflows/catalogue.yml`** builds the catalogue. Three jobs:

1. **plan** expands and validates, and emits the matrix.
2. **build** runs one job per chunk with `fail-fast: false`, so a single bad
   variant does not cancel the rest. Each job builds, verifies, and uploads
   its chunk.
3. **collect** downloads every chunk, re-indexes the merged set, verifies it
   again, uploads it as one artifact, and fails if any build job failed.

Trigger it from the Actions tab with a limit and, optionally, a release tag to
publish under. It also runs on a push that touches `catalogue.json`.

## Locally

```bash
make test        # 141 tests
make batch       # build the whole catalogue into out/
make verify      # check whatever is in out/
```
