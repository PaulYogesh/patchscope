# A reference-equivalent repair received an unresolved grade

**Case:** `pydicom__pydicom-811` · SWE-bench development split · PatchScope native editor · `qwen3.5:9b`

PatchScope reproduced the benchmark's empty-file fix. Both editor runs and the independent reference run passed the target test. All three received an unresolved grade because an existing filename test failed.

## What the code changed

The file reader peeks at the next byte and seeks backwards so the parser can read it again. At end of file, the peek returns an empty byte string and consumes zero bytes. The repair makes the backward seek conditional on having read a byte.

The two editor runs produced identical predictions. Applying that prediction and applying the benchmark reference patch to base commit `7d0889e7143f5d4773fa74606efa816ed4e54c9f` produced the same Git tree, `ff3d100a23eb71ba1e2bdd5d2b78c2ad8bf8fd30`. Tree equality checks the resulting tracked contents and file modes even when two submitted diff strings use different headers.

## What the grader observed

| Official test group or outcome | Saved-window baseline | Traceback-window candidate | Reference control |
|---|---:|---:|---:|
| Patch applied | Yes | Yes | Yes |
| FAIL_TO_PASS passed / failed | 1 / 0 | 1 / 0 | 1 / 0 |
| PASS_TO_PASS passed / failed | 84 / 1 | 84 / 1 | 84 / 1 |
| Official resolution | Unresolved | Unresolved | Unresolved |

The target test was `ReaderTests::test_empty_file`. The sole failing test was `ReaderTests::testUTF8FileName`. The captured pytest output for the whole test file reported 86 passed, 1 failed and 1 skipped. The table uses the grader's designated test groups.

## Why the filename test failed

The test tried to copy an existing fixture to a temporary filename containing Cyrillic characters. During `shutil.copyfile`, Python 3.6.13 called `os.stat` on the destination path and raised `UnicodeEncodeError` because ASCII could not encode those characters. The exception occurred during fixture setup, before that test exercised the repaired reader. The log establishes the failed operation and codec. It does not record the effective locale settings or a controlled rerun under UTF-8.

## Engineering decision

Keep the official grade in the paired trial. Alongside it, record that the resulting tree matched the reference, the target test passed, and the same existing test failed on the reference. Close this case for editor tuning. Both editing conditions produced the same patch, so this case supplies no repair gain attributable to traceback-guided selection.

For future unresolved predictions with a passing target test, an evaluator can compare the predicted and reference Git trees and run the reference separately when needed. Keep reference code and test outcomes on the evaluator side. Show the official grade and the diagnostic evidence together. One case establishes the value of this check here. Estimating how often it changes the interpretation of a grade requires additional independent cases.

## Evidence identifiers

| Artifact | Identifier |
|---|---|
| Baseline grader run | `ps_trace_trial_essxce_baseline` |
| Candidate grader run | `ps_trace_trial_essxce_candidate` |
| Independent reference grader run | `ps_pydicom811_control_csmz3h_w` |
| Reference prediction patch SHA-256 | `da10fa36749a9928a81b3d7bfd647d58e91f9da654178dc0f7704a8c8be7aa72` |

The per-instance grader reports supply the outcomes above. The reference-control report records the base and resulting tree. The raw test output identifies the failing operation.
