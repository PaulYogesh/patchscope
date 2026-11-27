# Public reproduction uses only the documented service entry point.
from service import retry_delay
assert retry_delay(4, 3, 20) == 20
