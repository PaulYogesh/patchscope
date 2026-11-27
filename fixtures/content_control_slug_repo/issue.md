# Bug: slug builder does not normalize repeated whitespace

Creating a URL slug from '  Hello   World  ' gives 'hello---world'
instead of 'hello-world'. Spaces, tabs and newlines should be collapsed
into one hyphen between words. Keep the result lowercase.
