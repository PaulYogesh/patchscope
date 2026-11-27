from time import perf_counter

from patchscope.retrieval import search_repository
from patchscope.tools import read_source_file


def build_context_seed(
    repo_path,
    issue_text,
    top_k=1,
    max_chars_per_file=1600,
):
    """Build a bounded source-code context seed using BM25."""

    if top_k < 1:
        raise ValueError("top_k must be positive")

    if max_chars_per_file < 1:
        raise ValueError("Character limit must be positive")

    start = perf_counter()

    ranked = search_repository(
        repo_path,
        issue_text,
        top_k=top_k,
    )

    chunks = []
    sources = []

    for candidate in ranked:
        # A non-positive score provides no positive
        # lexical evidence for this query.
        if candidate["score"] <= 0:
            continue

        result = read_source_file(
            repo_path,
            candidate["path"],
            max_chars=max_chars_per_file,
        )

        chunks.append(
            f"FILE: {result['path']}\n"
            f"````python\n{result['content']}\n````"
        )

        sources.append({
            "path": result["path"],
            "bm25_score": candidate["score"],
            "truncated": result["truncated"],
        })

    seed_text = "\n\n".join(chunks)
    elapsed_ms = (perf_counter() - start) * 1000

    return {
        "seed_text": seed_text,
        "sources": sources,
        "seed_chars": len(seed_text),
        "retrieval_ms": round(elapsed_ms, 3),
    }
