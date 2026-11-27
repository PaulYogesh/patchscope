# Issue: one-index-pages-008

The listing API treats page=1 as the second page. The API is one-indexed: page=1 size=2 should return the first two elements, page=2 the next two. Preserve the wrapper API.
