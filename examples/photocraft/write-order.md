# Write order and batch-list format

This is the schedule excerpt for the write step. The run keeps no schedule file. It keeps a write order and one list of set names per batch and model.

## Write order

1. Audits before writing: every pinned cross-set signature is in the stubs; every registered component has a story owner.
2. Framework-side sets of all areas first (69 sets: 27 that touch the ui-contract contract, runtime or layout code or the behavior crate on Opus, 42 on Sonnet). One area at a time: write the batch, one Opus review, a fix round, combine on the integration branch, `check` and the crates' test binaries, a fix round, then the next area.
3. PhotoCraft sets (164) after the framework builds, written against the real framework code, in two build batches:
   1. panels, canvas-widgets and hub (48 sets)
   2. dialogs, tools and top (116 sets)

   Every set gets its review and fix round as it is written. The build steps (combine, compile, test binaries, run round) run once per batch, because a warm incremental build costs about the same for 20 sets or 60. If batch 1's compile shows plan-level errors (wrong contract, missing API) rather than typos, split batch 2 by area before it builds.

## Batch-list format

One text file per batch and model, one set name per line. The file name carries the area and the model (`batch-<area>-opus.txt`, `batch-<area>-sonnet.txt`). A rerun file lists the sets to write again. A combined file (`batch-fwcw.txt`) lists several batches.

Examples from the pilot's later batches:

`batch-dialogs-opus.txt`

```
dialogs-w1
dialogs-w11
dialogs-w13
dialogs-w4
dialogs-w5
```

`batch-dialogs-sonnet.txt`

```
dialogs-w10
dialogs-w12
dialogs-w14
dialogs-w15
dialogs-w16
dialogs-w17
dialogs-w18
dialogs-w2
dialogs-w3
dialogs-w6
dialogs-w7
dialogs-w8
dialogs-w9
```

`batch-top-opus.txt`

```
top-w2
top-w4
top-w7
```

`batch-top-sonnet.txt`

```
top-w1
top-w10
top-w3
top-w5
top-w6
```

`batch-fw01-rerun.txt` (one set written again after a failed write)

```
framework-01-w9
```

A set's model is decided from its sheet: Opus when the set changes a shared mechanism (pass, input routing, focus, layout, paint) or is a retry of a set a Sonnet writer failed, Sonnet otherwise.
