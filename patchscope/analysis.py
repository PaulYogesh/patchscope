"""Task-paired descriptive analysis of the v0.2 run logs.

For n=1 task, do not report misleading non-parametric confidence intervals.
"""
from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict

CONTRASTS = (
    ("bm25", "native"),
    ("bm25", "placebo"),
    ("oracle", "native"),
    ("oracle", "bm25"),
    ("oracle", "placebo"),
    ("misleading", "native"),
    ("misleading", "placebo"),
    ("misleading", "oracle"),
)


def _verified(record: dict) -> int:
    return int(record.get("outcome", {}).get("repair_verified") is True)


def _evaluable(record: dict) -> bool:
    # Explicitly skipped verification must NOT be treated as a failed repair.
    # Model/protocol failures remain zero in an intention-to-treat comparison.
    return record.get("outcome", {}).get("status") != "proposal_requires_explicit_verification_opt_in"


def exact_mcnemar(b: int, c: int) -> float:
    """Exact two-sided binomial test for discordant matched binary outcomes."""
    n = b + c
    if n == 0:
        return 1.0
    smaller = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(smaller + 1)) / 2**n)


def paired_task_bootstrap(task_effects: list[float], *, n_boot=5000, seed=20261023) -> dict:
    """Cluster-resample tasks, never pretend repeated runs are independent tasks."""
    if not task_effects:
        return {"estimate": None, "ci_low": None, "ci_high": None}
    mean = statistics.mean(task_effects)
    if len(task_effects) == 1:
        return {"estimate": mean, "ci_low": None, "ci_high": None}
    rng = random.Random(seed)
    samples = sorted(statistics.mean(rng.choices(task_effects, k=len(task_effects)))
                     for _ in range(n_boot))
    return {"estimate": mean, "ci_low": samples[int(n_boot * .025)],
            "ci_high": samples[int(n_boot * .975)]}


def summarize(records: list[dict]) -> dict:
    seen = set()
    for record in records:
        key = (record["task_id"], record["condition"], record["repetition"])
        if key in seen:
            raise ValueError(f"Duplicate task-condition-repetition record: {key}")
        seen.add(key)
    by_condition = defaultdict(list)
    for record in records:
        by_condition[record["condition"]].append(record)
    conditions = {}
    for condition, runs in sorted(by_condition.items()):
        metrics = lambda key: [r.get("usage", {}).get(key, 0) for r in runs]
        conditions[condition] = {
            "runs": len(runs), "evaluated": sum(_evaluable(r) for r in runs),
            "verified_repairs": sum(_verified(r) for r in runs),
            "proposal_rejections": sum(
                not a.get("valid", False) for r in runs for a in r.get("proposal_attempts", [])),
            "contract_recovered_runs": sum(
                any(not a.get("valid", False) for a in r.get("proposal_attempts", []))
                and any(a.get("valid", False) for a in r.get("proposal_attempts", []))
                for r in runs),
            "repair_rate": (sum(_verified(r) for r in runs) / sum(_evaluable(r) for r in runs))
                           if any(_evaluable(r) for r in runs) else None,
            "median_tokens": statistics.median(metrics("total_tokens")),
            "median_tool_calls": statistics.median(metrics("tool_calls")),
            "median_repeated_reads": statistics.median(metrics("repeated_reads")),
            "median_retrieval_ms": statistics.median(metrics("retrieval_ms")),
            "median_wall_seconds": statistics.median(metrics("wall_seconds")),
            "protocol_errors": sum(r.get("outcome", {}).get("status") == "protocol_error" for r in runs),
            "unverified": sum(r.get("outcome", {}).get("status") == "proposal_requires_explicit_verification_opt_in" for r in runs),
        }
    pairs = {}
    index = {(r["task_id"], r["repetition"], r["condition"]): r for r in records}
    for a, b in CONTRASTS:
        common = sorted({(task, repetition)
                         for task, repetition, condition in index
                         if condition == a and (task, repetition, b) in index
                         and _evaluable(index[(task, repetition, a)])
                         and _evaluable(index[(task, repetition, b)])})
        by_task = defaultdict(list)
        aa_only = bb_only = both = neither = 0
        token_deltas = []
        for task, repetition in common:
            ra, rb = index[(task, repetition, a)], index[(task, repetition, b)]
            ya, yb = _verified(ra), _verified(rb)
            aa_only += ya == 1 and yb == 0
            bb_only += ya == 0 and yb == 1
            both += ya == 1 and yb == 1
            neither += ya == 0 and yb == 0
            by_task[task].append(ya - yb)
            token_deltas.append(ra["usage"]["total_tokens"] - rb["usage"]["total_tokens"])
        effects = [statistics.mean(values) for values in by_task.values()]
        # Exact McNemar requires independent matched pairs. Repetitions within
        # the same task share the defect and often the complete trajectory.
        # Report the discordances descriptively, but suppress its p-value.
        clustered_repetitions = any(len(values) > 1 for values in by_task.values())
        interval = paired_task_bootstrap(effects)
        pairs[f"{a} - {b}"] = {
            "matched_pairs": len(common), "tasks": len(by_task),
            "a_only": aa_only, "b_only": bb_only, "both": both, "neither": neither,
            "repair_risk_difference": interval["estimate"],
            "bootstrap_95_low": interval["ci_low"],
            "bootstrap_95_high": interval["ci_high"],
            "exact_mcnemar_p": (exact_mcnemar(aa_only, bb_only)
                                if common and not clustered_repetitions else None),
            "mcnemar_suppressed_due_to_repeated_tasks": clustered_repetitions,
            "median_token_difference": statistics.median(token_deltas) if common else None,
        }
    return {"conditions": conditions, "paired_contrasts": pairs,
            "task_count": len(set(r["task_id"] for r in records)),
            "total_runs": len(records)}
