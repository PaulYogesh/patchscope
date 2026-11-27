def f1_from_pr(precision, recall):
    """Compute F1 from precision and recall."""
    if precision + recall == 0:
        return 0.0
    return (precision + recall) / 2
