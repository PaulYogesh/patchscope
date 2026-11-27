import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_run(condition):
    path = ROOT / "runs" / f"experiment_{condition}.json"

    if not path.exists():
        raise FileNotFoundError(f"Missing run: {path}")

    record = json.loads(path.read_text(encoding="utf-8"))

    if record["condition"] != condition:
        raise ValueError("Condition mismatch in run log")

    return record


def total_tokens(record):
    return record["prompt_tokens"] + record["completion_tokens"]


def invalid_calls(record):
    return sum(
        bool(event.get("result_error"))
        for event in record["events"]
    )


def status(value):
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Not evaluated"


def main():
    native = load_run("native")
    bm25 = load_run("bm25")

    if native["model"] != bm25["model"]:
        raise ValueError("Model mismatch between conditions")

    if native["task_id"] != bm25["task_id"]:
        raise ValueError("Task mismatch between conditions")

    native_tokens = total_tokens(native)
    bm25_tokens = total_tokens(bm25)

    difference = native_tokens - bm25_tokens

    percentage = (
        100 * difference / native_tokens
        if native_tokens else 0.0
    )

    report = f"""# PatchScope — Five-Day MVP Evaluation

## Experiment

- Task: `{native["task_id"]}`
- Model: `{native["model"]}`
- Benchmark: Small synthetic Python repository
- Conditions: Native exploration versus BM25-seeded exploration
- Study type: Exploratory development smoke test

## Results

| Metric | Native | BM25 |
|---|---:|---:|
| Repair verified | {status(native["repair_verified"])} | {status(bm25["repair_verified"])} |
| Tool calls | {native["tool_calls"]} | {bm25["tool_calls"]} |
| Repeated reads | {native["repeated_reads"]} | {bm25["repeated_reads"]} |
| Invalid tool requests | {invalid_calls(native)} | {invalid_calls(bm25)} |
| Prompt tokens | {native["prompt_tokens"]} | {bm25["prompt_tokens"]} |
| Completion tokens | {native["completion_tokens"]} | {bm25["completion_tokens"]} |
| Total reported tokens | {native_tokens} | {bm25_tokens} |
| Seed characters | {native["seed_chars"]} | {bm25["seed_chars"]} |
| Model calls | {native["model_calls"]} | {bm25["model_calls"]} |

## Interpretation

The native-minus-BM25 token difference was **{difference:+d}**
({percentage:+.1f}% of the native token count).
Verified repair in the native run was **{status(native["repair_verified"])}**.
Verified repair in the BM25 run was **{status(bm25["repair_verified"])}**.

These are observations from individual development runs,
not estimates of general coding-agent performance.

## Methodological limitations

1. Only one synthetic bug-fixing task was evaluated.
2. The benchmark and prompts were used during development.
3. Runs were not repeated under a frozen protocol.
4. The same model and tool interface were used, but a
   strict cumulative token budget was not enforced.
5. The agent uses a separate repair-proposal model call.
6. Tool calling included a validated text fallback rather
   than relying exclusively on native structured calls.
7. Wall-clock measurements include human approval and
   therefore cannot support a speed comparison.
8. The temporary directory is not a security sandbox.
9. The retrieval corpus is tiny and the bug is simple.
10. The run logs do not yet capture every reproducibility
    parameter, such as model digest and runtime version.

## Conclusion

The five-day MVP demonstrates a working end-to-end
pipeline for repository retrieval, agent investigation,
patch proposal, and test verification.

It does not yet establish that BM25 improves agent
repair success, reliability, efficiency, or cost.
"""

    output = ROOT / "reports" / "day5_mvp.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nReport saved to: {output}")


if __name__ == "__main__":
    main()
