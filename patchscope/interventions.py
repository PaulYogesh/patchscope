"""Reproducible, model-visible repository evidence interventions.

Oracle labels and placebo pools are evaluator-only inputs. Never include task
metadata in the model prompt; only return seed_text from this module to it.
"""
from __future__ import annotations

import random
from pathlib import Path
from time import perf_counter

from patchscope.context import build_context_seed
from patchscope.tools import read_source_file

CONDITIONS = ("native", "bm25", "placebo", "oracle", "misleading")


def _render(path: str, code: str) -> str:
    # Keep the same evidence template as the v0.1 BM25 seed.
    return f"FILE: {path}\n````python\n{code}\n````"


def _source(repo: Path, path: str, *, remaining: int) -> dict:
    """Read a safe source file while respecting the TOTAL rendered-char budget."""
    overhead = len(_render(path, ""))
    if remaining <= overhead:
        raise ValueError(f"Seed budget too small to include {path}")
    item = read_source_file(repo, path, max_chars=remaining - overhead)
    return {
        "path": item["path"],
        "text": _render(item["path"], item["content"]),
        "chars": len(item["content"]),
        "truncated": item["truncated"],
    }


def _package(condition: str, start: float, chunks: list[dict], *, scores=None) -> dict:
    sources = []
    for i, chunk in enumerate(chunks):
        entry = {
            "path": chunk["path"],
            "selection": condition,
            "chars": chunk["chars"],
            "truncated": chunk["truncated"],
        }
        if scores is not None and i < len(scores):
            entry["bm25_score"] = scores[i]
        sources.append(entry)
    seed = "\n\n".join(chunk["text"] for chunk in chunks)
    return {
        "condition": condition,
        "seed_text": seed,
        "seed_chars": len(seed),
        "sources": sources,
        "retrieval_ms": round((perf_counter() - start) * 1000, 3),
    }


def build_intervention(
    condition: str,
    *,
    repo_path: Path,
    issue_text: str,
    oracle_paths: list[str],
    placebo_pool: list[str],
    rng: random.Random,
    misleading_pool: list[str] | None = None,
    top_k: int = 1,
    char_budget: int = 1600,
) -> dict:
    """Build an initial-context intervention from genuine repository code.

    The misleading condition draws only from curated *wrong-locus* source
    files: task-relevant implementations that are not on the tested execution
    path. Its files remain in the repository in every condition. The agent
    receives the same FILE/source syntax as BM25, placebo, and oracle; no
    fabricated source contents or hidden labels are placed in its prompt.
    """
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown intervention: {condition}")
    if char_budget < 40 or top_k < 1:
        raise ValueError("Invalid seed or retrieval budget")
    repo = Path(repo_path)
    start = perf_counter()
    if condition == "native":
        return _package(condition, start, [])

    if condition == "bm25":
        # Existing retrieval API bounds code chars PER FILE, not rendered seed.
        # Select files via the existing routine, then enforce a total budget.
        original = build_context_seed(repo, issue_text, top_k=top_k,
                                      max_chars_per_file=char_budget)
        chunks = []
        scores = []
        remaining = char_budget
        for candidate in original["sources"]:
            try:
                chunk = _source(repo, candidate["path"], remaining=remaining)
            except ValueError:
                break
            chunks.append(chunk)
            scores.append(candidate["bm25_score"])
            remaining -= len(chunk["text"]) + 2
            if remaining <= 0:
                break
        return _package(condition, start, chunks, scores=scores)

    if condition == "oracle":
        if not oracle_paths:
            raise ValueError("Oracle condition requires labeled source paths")
        if len(set(oracle_paths)) != len(oracle_paths):
            raise ValueError("Duplicate oracle paths")
        chunks = []
        remaining = char_budget
        for i, path in enumerate(oracle_paths):
            files_left = len(oracle_paths) - i
            allocation = remaining // files_left
            chunk = _source(repo, path, remaining=allocation)
            chunks.append(chunk)
            remaining -= len(chunk["text"]) + 2
        result = _package(condition, start, chunks)
        if result["seed_chars"] > char_budget:
            raise AssertionError("Oracle evidence exceeded seed budget")
        return result

    pool = placebo_pool if condition == "placebo" else misleading_pool
    if not pool:
        raise ValueError(f"{condition} requires curated source candidates")
    if len(set(pool)) != len(pool):
        raise ValueError(f"Duplicate {condition} paths")
    candidates = [p for p in pool if p not in set(oracle_paths)]
    if not candidates:
        raise ValueError(f"No {condition} candidate outside oracle paths")
    # Match BM25's displayed length, not merely the configured budget.
    bm25 = build_intervention(
        "bm25", repo_path=repo, issue_text=issue_text,
        oracle_paths=oracle_paths, placebo_pool=[], misleading_pool=[], rng=rng,
        top_k=top_k, char_budget=char_budget,
    )
    target_size = bm25["seed_chars"] or char_budget
    choices = []
    for path in sorted(candidates):
        chunk = _source(repo, path, remaining=char_budget)
        choices.append((abs(len(chunk["text"]) - target_size), path, chunk))
    best_distance = min(row[0] for row in choices)
    equally_good = [row[2] for row in choices if row[0] == best_distance]
    chosen = rng.choice(equally_good)
    result = _package(condition, start, [chosen])
    result[f"{condition}_length_gap"] = abs(result["seed_chars"] - target_size)
    return result
