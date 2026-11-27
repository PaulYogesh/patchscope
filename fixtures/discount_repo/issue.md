# Bug: checkout increases price when applying a discount

A 20 percent discount on an item priced 100 should yield a final price
of 80, but final_price returns 120. A zero-percent discount should leave
the price unchanged. Preserve percent validation.
