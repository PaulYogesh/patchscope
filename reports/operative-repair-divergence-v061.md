# PatchScope v0.6 — repair divergence

Post-hoc analysis of saved proposals. No model calls.

## retry-dynamic-dispatch-014

### off
Status: `resolved`
Verified: `True`

Patch file: `backoff_core.py`

```diff
--- a/backoff_core.py
+++ b/backoff_core.py
@@ -2,4 +2,4 @@
     """Capped exponential backoff, attempt counting starts at 1."""
     if attempt < 1:
         raise ValueError('attempt must be positive')
-    return min(maximum, base * attempt)
+    return min(maximum, base * (2 ** (attempt - 1)))
```

Reverified: PASS

### trace
Status: `repair_failed_tests`
Verified: `False`

Patch file: `backoff_core.py`

```diff
--- a/backoff_core.py
+++ b/backoff_core.py
@@ -2,4 +2,4 @@
     """Capped exponential backoff, attempt counting starts at 1."""
     if attempt < 1:
         raise ValueError('attempt must be positive')
-    return min(maximum, base * attempt)
+    return min(maximum, base ** attempt)
```

Reverified: FAIL

```text
.F..                                                                     [100%]
=================================== FAILURES ===================================
_______________________________ test_exponential _______________________________

    def test_exponential():
>       assert retry_delay(3, 3, 20) == 12
E       assert 20 == 12
E        +  where 20 = retry_delay(3, 3, 20)

test_contract.py:8: AssertionError
=========================== short test summary info ============================
FAILED test_contract.py::test_exponential - assert 20 == 12
1 failed, 3 passed in 0.01s

```

Same exact edit: `False`

## tax-dynamic-dispatch-013

### off
Status: `resolved`
Verified: `True`

Patch file: `tax_core.py`

```diff
--- a/tax_core.py
+++ b/tax_core.py
@@ -1,3 +1,3 @@
 def quote_total(amount, tax_rate):
     """Price including tax, rounded to two decimal places."""
-    return round(amount * (1 + tax_rate), 0)
+    return round(amount * (1 + tax_rate), 2)
```

Reverified: PASS

### trace
Status: `resolved`
Verified: `True`

Patch file: `tax_core.py`

```diff
--- a/tax_core.py
+++ b/tax_core.py
@@ -1,3 +1,3 @@
 def quote_total(amount, tax_rate):
     """Price including tax, rounded to two decimal places."""
-    return round(amount * (1 + tax_rate), 0)
+    return round(amount * (1 + tax_rate), 2)
```

Reverified: PASS

Same exact edit: `True`
