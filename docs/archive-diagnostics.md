# Diagnose archived runs

Run the batch report from the PatchScope repository root with Python and Git.

```bash
python -m scripts.report_archive_diagnostics --manifest /path/to/cases.json > report.json
```

The command reads saved inputs and grades. It compares patches using disposable
Git indexes and makes no model calls, runs no tests and downloads no repositories.

## Manifest

Give each assigned run a unique `id`, its evaluator `task_id`, a `group`
and its recorded `official_grade`. Paths can be absolute, start with `~/`,
or be relative to the command's working directory. Keep machine-local manifests
with the archive when they contain private paths.

```json
{
  "cases": [
    {
      "id": "sqlfluff-2419-baseline",
      "task_id": "sqlfluff__sqlfluff-2419",
      "group": "anchor",
      "official_grade": "no_prediction",
      "repo": "/path/to/pinned/sqlfluff",
      "episode": "fixtures/export_replay/sqlfluff-2419/episode.json"
    }
  ]
}
```

| Field | Accepted values |
|---|---|
| `group` | `anchor` for known cases, `archive` for runs in the fixed comparison, or `control` for deliberate missing or mismatched inputs |
| `official_grade` | `resolved`, `unresolved`, `no_prediction`, `grader_error`, `infrastructure_failure`, `ambiguous`, `ungraded`, or `unknown` |
| `repo`, `episode` | Local Git repository with the base commit and the saved episode JSON |
| `prediction`, `grader` | Single prediction record and the directory containing its `report.json` and `patch.diff` |
| `reference` | Optional object containing the reference `base_commit`, `prediction` and `grader` from a separate evaluation |

## Interpret the report

Every row preserves the supplied official grade and shows the action based on
that grade alone alongside the diagnostic action. Each check records its status,
verified evidence where available, and elapsed time. The case lists missing
inputs by role. A grade is bound to the submitted patch only when the grader's
saved patch and task match.

- For [SQLFluff #2419](cases/sqlfluff-2419.md), an exact reproduction of the
  corrupt export plus a corrected patch that produces the intended Git tree
  supports `retry_export`. The original grade is `no_prediction`. The
  recorded `resolved` grade belongs to the recovered patch.
- For [pydicom #811](cases/pydicom-811.md), the reference and submitted patches
  produced the same tree. Both archived grades were unresolved. The same
  target test passed and the same existing test failed in both runs. This
  supports `investigate_shared_test_failure`. The underlying cause is
  undetermined.
- A mismatch triggers `verify_archive_consistency`. A missing artifact limits
  the checks that can be performed. With no stronger evidence, the report keeps
  the grade-only action.

Fix the set of archive cases before reviewing the outputs. Read
`summary.groups.archive` for the number of cases assigned, the number and
fraction where the action changed, and evidence coverage. The denominator
includes cases with missing artifacts. The anchor and control groups have
separate summaries. Action changes measure how often this checklist changes its
recommendation within the selected set. Establishing that the changed actions
help requires follow-up verification.
