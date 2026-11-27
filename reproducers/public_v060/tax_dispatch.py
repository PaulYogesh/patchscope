# Public reproduction uses only the documented service entry point.
from service import quote_total
assert quote_total(10.25, .1) == 11.28
