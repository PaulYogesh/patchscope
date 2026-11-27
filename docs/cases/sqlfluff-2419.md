# Reproduce the SQLFluff #2419 export replay

The [saved episode](../../fixtures/export_replay/sqlfluff-2419/episode.json)
contains the line-range edit for rule L060, the malformed diff from the first
export, and the expected replay results. The edit adds separate lint messages
for `IFNULL` and `NVL`. Its final line has no newline. The legacy renderer
failed to mark that line correctly, so Git rejected the diff before grading.

## Run the replay

From the PatchScope root, use Git and your existing Python 3.11–3.13
`.venv`. If you need a virtual environment, create one with
`python3 -m venv .venv`. The replay uses the Python standard library.

```bash
base=f1dba0e1dd764ae72d67c3d5e1471cf14d3db030
sqlfluff_repo="$(mktemp -d)"

git init --quiet --bare "$sqlfluff_repo" &&
git -C "$sqlfluff_repo" fetch --depth=1 https://github.com/sqlfluff/sqlfluff.git \
  "$base:refs/heads/replay-base" &&
git -C "$sqlfluff_repo" symbolic-ref HEAD refs/heads/replay-base &&
.venv/bin/python -m scripts.replay_export \
  --repo "$sqlfluff_repo" \
  --episode fixtures/export_replay/sqlfluff-2419/episode.json \
  --verify-expected
```

The command reports `expected_replay_verified: true` when these checks pass.

| Check | Expected result |
|---|---|
| Original export | Legacy renderer reproduces the saved diff byte for byte. Git reports a corrupt patch. |
| Corrected export SHA-256 | `330a2119df33565a876e814270fcbdabbf7376ab2f2a5e2940f6843388cdf807` |
| Intended and corrected Git tree | `4d22474d275d09a33afcf71223974e105001b78f` |
| New model calls | 0 |

The fixture's `archived_grader_result` records that the official SWE-bench
grader applied the patch with the corrected SHA-256 and marked the task as
resolved. The local replay checks the patch and resulting Git tree. Its
`archived_grade` field is null because this command supplies no grader archive.

SQLFluff excerpts in the fixture retain the pinned upstream
[MIT license and copyright notice](../../fixtures/export_replay/sqlfluff-2419/LICENSE.upstream.md).
