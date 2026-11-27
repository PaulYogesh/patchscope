import argparse
import re
from pathlib import Path

def tokenize(text):
    """Split text into lowercase word and number tokens."""
    return re.findall(r"[a-z]+|\d+", text.lower())


def discover_files(repo_path):
    """Find source files, excluding tests and hidden folders."""
    repo_path = Path(repo_path)

    files = []
    for path in repo_path.rglob("*.py"):
        relative = path.relative_to(repo_path)

        if path.name.startswith("test_"):
            continue

        if any(part.startswith(".") or part == "__pycache__"
               for part in relative.parts):
            continue

        files.append(path)

    return sorted(files)


def search_repository(repo_path, query, top_k=3):
    """Rank repository source files against a text query."""
    from rank_bm25 import BM25Okapi

    repo_path = Path(repo_path)
    paths = discover_files(repo_path)

    if not paths:
        return []

    documents = []
    for path in paths:
        code = path.read_text(encoding="utf-8")
        text = path.stem + " " + code
        documents.append(tokenize(text))

    bm25 = BM25Okapi(documents)
    query_tokens = tokenize(query)

    scores = bm25.get_scores(query_tokens)

    results = [
        {
            "path": str(path.relative_to(repo_path)),
            "score": float(score),
        }
        for path, score in zip(paths, scores)
    ]

    results.sort(key=lambda item: (-item["score"], item["path"]))

    return results[:top_k]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    parser.add_argument("issue_file", type=Path)
    parser.add_argument("--top-k", type=int, default=3)

    args = parser.parse_args()

    query = args.issue_file.read_text(encoding="utf-8")
    results = search_repository(
        args.repository,
        query,
        top_k=args.top_k,
    )

    for rank, result in enumerate(results, start=1):
        print(
            f"{rank}. {result['path']} "
            f"(BM25 score: {result['score']:.3f})"
        )


if __name__ == "__main__":
    main()
