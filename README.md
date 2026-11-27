# PatchScope

PatchScope traces a coding agent’s repair from the source lines it reads to the
patch it exports and the tests an independent grader runs. Use it to compare
two repair workflows on the same issue and investigate where their outcomes diverge.
When an export fails, replay the saved edit to see whether Git receives the
intended change.

## Try export replay

From a clean checkout with Python 3.11–3.13 and Git, run the demo from the
repository root. It uses the Python standard library and the bundled synthetic
calculator and edit cases in [fixtures/export_replay](fixtures/export_replay).
The calculator and both saved replacements deliberately end without a newline
to reproduce the legacy export bug.

```bash
python -m scripts.demo_export_replay
```

Git rejects the original export in both cases. Both corrected patches apply and
produce the intended repository snapshots. One edit passes the average check.
The other still fails because integer division rounds the result down.

To replay your own saved line-range edit, use a checkout containing the episode's
recorded base commit.

```bash
python -m scripts.replay_export --repo /path/to/checkout --episode /path/to/episode.json
```

The report includes the original Git rejection or resulting tree, the intended
tree, and the corrected tree. Use `--original-diff` if the original diff is
stored outside the episode, or `--write-patch` to save the corrected diff to a
new file. Use `--grader-dir` to check a grader archive containing `patch.diff`
and `report.json`. The command reports a grade when the archived patch matches
and the report records successful application for that task. It runs no grader
or model.

For an episode that includes an `expected_replay` object, pass
`--verify-expected` to check the original and corrected patch hashes, Git's
original rejection, the corrected tree, and the number of new model calls.
A mismatch exits with an error before writing a corrected patch.

## What happened on SQLFluff #2419

The agent saved a line-range edit to `src/sqlfluff/rules/L060.py`. The legacy
exporter produced a corrupt patch, which Git rejected before grading.
Replaying the **same saved edit** with the corrected exporter produced the
intended Git tree and reproduced the patch from the archived official grader
run. That run was **resolved**. The replay used zero new model calls.

| Evidence | Replay result |
|---|---|
| Original diff | Legacy renderer reproduced the archived bytes. Git reported a corrupt patch at line 14. |
| Corrected diff | Applied to base `f1dba0e1dd764ae72d67c3d5e1471cf14d3db030` and produced the intended tree `4d22474d275d09a33afcf71223974e105001b78f`. |
| Archived grade | Corrected patch matched the grader input. The official report recorded the issue as resolved. |

[Reproduce the SQLFluff replay](docs/cases/sqlfluff-2419.md)

## Compare proposal contracts

With Python and Git, run the paired demo from the repository root.

```bash
python -m scripts.demo_paired_repair --output "$(mktemp -d)/patchscope-demo"
```

The scripted demo tries the same calculator edit under two proposal contracts.
The exact-fragment contract rejects the edit because the text matches more than once.
The line-range contract identifies the intended occurrence and exports a patch. The paired
report shows **0 baseline exports and 1 candidate export**. The demo uses only
the Python standard library and Git. The generated episodes and diff are
available in the output directory. The report marks the prediction **ungraded**.

To run the full automated test suite:

```bash
python -m pip install -r requirements.txt
python -m pytest -q tests/
```

## What an unresolved grade can hide

On **pydicom #811**, the agent generated a repair for reading an empty file.
Its patch and the benchmark reference patch produced the **same Git tree**.
In separate grader runs, each passed the target test and 84 existing tests.
The same existing test, `testUTF8FileName`, failed in both runs. Both official
grades were **unresolved**.

The reference run changes how to interpret that result. The agent reproduced the
reference repair, and the filename-test failure also occurred with the reference
installed. The paired report preserves the official grade alongside that evidence.

[Read the case study](docs/cases/pydicom-811.md) · [Inspect the paired report](docs/cases/pydicom-811-paired-report.md)

## Diagnose archived runs

Use the [batch diagnostics report](docs/archive-diagnostics.md) to compare saved edits,
graded patches, and reference runs across a fixed set of cases. The report keeps the
official grade alongside the evidence, check timings, and suggested next action.

## How it works

The model explores a pinned repository through bounded, read-only tools. A separate proposal call requests one structured edit. PatchScope validates the edit against source the model actually saw, computes a hash of the original line range, runs static checks, and exports an applicable diff. In the SWE-bench development workflow, the official evaluator grades that diff separately.

- [Engineering guide](docs/ENGINEERING_GUIDE.md) covers the agent loop, architecture, trade-offs, and hands-on walkthrough.
- [Paired development protocol](SWE_BENCH_DEV_PAIRED_REPORT.md) explains how to rerun and report the 23 matched issues.
- [Historical v0.8 baseline](reports/swebench-lite-dev-v08-baseline.md) documents 8 exports from 23 assigned development issues.
- [v0.9 implementation notes](V0.9_IMPLEMENTATION.md) specify the observed line-range contract.

The development baseline measures exports. The current edit contract supports
a single observed Python range.
Versioned experiment manifests, fixtures, and reports record earlier protocols.

## License and citation

PatchScope is source-available under Apache License 2.0 with the Commons Clause
1.0. See [LICENSE](LICENSE) for the combined terms and [NOTICE](NOTICE) for
attribution and the original repository. For permission to sell PatchScope as
defined in the Commons Clause, contact [Yogesh Paul](https://github.com/PaulYogesh).

If you use PatchScope in research, cite the software using
[CITATION.cff](CITATION.cff).
