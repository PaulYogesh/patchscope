# PatchScope — Five-Day MVP Evaluation

## Experiment

- Task: `mini-average-001`
- Model: `qwen2.5-coder:7b`
- Benchmark: Small synthetic Python repository
- Conditions: Native exploration versus BM25-seeded exploration
- Study type: Exploratory development smoke test

## Results

| Metric | Native | BM25 |
|---|---:|---:|
| Repair verified | Yes | Yes |
| Tool calls | 5 | 6 |
| Repeated reads | 0 | 2 |
| Invalid tool requests | 0 | 2 |
| Prompt tokens | 3538 | 3254 |
| Completion tokens | 244 | 132 |
| Total reported tokens | 3782 | 3386 |
| Seed characters | 0 | 173 |
| Model calls | 7 | 7 |

BM25 used **396 fewer reported LLM tokens**
(10.5% relative to the native run).

## Interpretation

Both conditions generated a test-verified repair.

The BM25 condition used fewer reported LLM tokens, but
made more tool requests, including repeated reads and
invalid calls.

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
