# Issue: backoff-ceiling-006

Background request retries wait too long even on the first retry. With base=1, attempt=0 and ceiling=8, the delay should be 1 second. Delays should increase exponentially but never exceed the ceiling.
