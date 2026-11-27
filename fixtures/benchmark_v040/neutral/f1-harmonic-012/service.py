"""Public integration surface for the metrics subsystem."""
from scores import f1_from_pr

def report_f1(precision, recall):
    return f1_from_pr(precision, recall)
