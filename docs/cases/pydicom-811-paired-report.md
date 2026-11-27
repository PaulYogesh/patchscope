# PatchScope paired development report

Assigned issues **4**. Pairs with matching recorded settings **4**.

The official grader supplies the resolution result. Successful export records a preflight applicability check. The applied count uses per-issue grader reports when available.

| Metric | Baseline | Candidate |
|---|---:|---:|
| exported | 2 | 1 |
| no_proposal | 2 | 2 |
| proposal_only | 0 | 1 |
| grader_error | 1 | 0 |
| no_prediction | 2 | 3 |
| unresolved | 1 | 1 |
| error | 1 | 1 |
| patch_range_not_fully_observed | 1 | 0 |
| patch_replacement_missing_final_newline | 0 | 1 |
| python_syntax_invalid | 0 | 1 |
| applied | 1 | 1 |
| application_unknown | 1 | 0 |
| Total tokens | 12575 (4/4 recorded) | 11169 (4/4 recorded) |
| Total seconds | 12.356 (4/4 recorded) | 6.465 (4/4 recorded) |

Paired resolution changes **0 gains**, **0 losses**, **1 unavailable**.

| Issue | Baseline export / grade | Candidate export / grade | Resolution change |
|---|---|---|---|
| pydicom__pydicom-811 | exported / unresolved | exported / unresolved | unchanged |
| sqlfluff__sqlfluff-3354 | no_proposal / no_prediction | proposal_only / no_prediction | unchanged |
| pydicom__pydicom-1720 | no_proposal / no_prediction | no_proposal / no_prediction | unchanged |
| sqlfluff__sqlfluff-1577 | exported / grader_error | no_proposal / no_prediction | — |

## Unresolved prediction diagnostics

### pydicom__pydicom-811 · baseline

Official grade **unresolved**. Target tests: 1 passed, 0 failed. Existing tests: 84 passed, 1 failed.

- Existing test failure: `pydicom/tests/test_filereader.py::ReaderTests::testUTF8FileName`

Reference run `ps_pydicom811_control_csmz3h_w`: **unresolved**. Model and reference trees: **identical**.
Reference target tests: 1 passed, 0 failed. Reference existing tests: 84 passed, 1 failed.
- Reference existing test failure: `pydicom/tests/test_filereader.py::ReaderTests::testUTF8FileName`

### pydicom__pydicom-811 · candidate

Official grade **unresolved**. Target tests: 1 passed, 0 failed. Existing tests: 84 passed, 1 failed.

- Existing test failure: `pydicom/tests/test_filereader.py::ReaderTests::testUTF8FileName`

Reference run `ps_pydicom811_control_csmz3h_w`: **unresolved**. Model and reference trees: **identical**.
Reference target tests: 1 passed, 0 failed. Reference existing tests: 84 passed, 1 failed.
- Reference existing test failure: `pydicom/tests/test_filereader.py::ReaderTests::testUTF8FileName`


