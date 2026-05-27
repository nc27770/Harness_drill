# common/ — Shared Building Blocks

> **Curriculum:** Cross-layer shared primitives. See [`docs/curriculum.md`](../docs/curriculum.md#code-organization--three-layers).

**Status:** placeholder. Shared primitives migrate here once a pattern has
been proven in two or more modules and the duplication is real overhead,
not a useful diff.

## The migration rule

The curriculum's per-module isolation is deliberate — *the diff between
Module N and Module N-1 is the lesson*. Premature DRY collapses the diff
and destroys the lesson. So shared primitives must earn their place:

1. **Pattern stabilizes** — the same code appears in ≥2 modules with
   non-trivial overlap.
2. **The duplication adds no pedagogical value** — the modules are not
   teaching a new lesson at this seam; they are just re-using a solved
   primitive.
3. **The interface is unlikely to churn** — moving it doesn't lock-in a
   premature abstraction.

When all three hold, the primitive moves here and the modules import from
`common/`. Until then, the duplication stays.

## Candidates for migration (when ready)

These are stable patterns that already appear in ≥2 modules and would
reasonably move here next:

- **`assets.py`** — S3 / URL / local-path fetcher with ETag caching.
  Currently lives at `level_1_modules/module_01d_modality/assets.py` and
  is imported across 1d, 1e, 1f, 1k, 1l. **The clearest current candidate
  for migration.**
- **The async-job state machine** — submit / poll / terminal-state
  primitive currently inside `module_01j_video_out/bilateral_j.py` and
  reused in 1l. Per 1j's own README, *"`common/async_job.py` not yet
  extracted. The poll-and-terminal state machine lives inside
  `bilateral_j.py`. When a second module needs it ... the pattern earns
  extraction into `common/`."* That second use happened in 1l; extraction
  is now reasonable.
- **The `--baseline` / `--all` sweep harness** — argparse + comparison
  table appears across most bilateral modules. Lower priority; the
  surface is small and the duplication is largely cosmetic.

## When NOT to put something here

- Anything specific to one module's lesson.
- Anything still being figured out (let it churn in the module first).
- Anything whose presence here would obscure a pedagogical diff.
