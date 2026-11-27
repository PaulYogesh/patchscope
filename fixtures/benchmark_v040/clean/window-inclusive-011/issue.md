# Issue: window-inclusive-011

A streaming window is silently dropping samples exactly at its opening timestamp. Window bounds must be start-inclusive and stop-exclusive. Keep the gateway function contract unchanged.
