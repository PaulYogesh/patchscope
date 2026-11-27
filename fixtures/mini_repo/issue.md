
# Bug: Average calculation loses fractional values

The average function returns an incorrect result
when the arithmetic mean is not an integer.

Example:
- Input: [1, 2]
- Expected: 1.5
- Actual: 1

Fix the implementation without modifying tests.
