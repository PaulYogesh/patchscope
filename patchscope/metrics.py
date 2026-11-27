def recall_at_k(retrieved_paths, relevant_paths, k):
    """Fraction of relevant files found in the top K results."""

    if k < 1:
        raise ValueError("k must be at least 1")

    relevant = set(relevant_paths)

    if not relevant:
        raise ValueError("At least one relevant file is required")

    retrieved = set(retrieved_paths[:k])
    found = retrieved.intersection(relevant)

    return len(found) / len(relevant)
