# Bug: numeric clamping returns the wrong boundary

The clamp function returns an incorrect value for an input inside a valid
interval. For example, clamp(5, 0, 10) should return 5, but returns 10.
Correct the implementation while retaining validation of reversed bounds.
