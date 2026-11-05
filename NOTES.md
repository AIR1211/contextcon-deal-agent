# Notes

Append what we tried, whether it worked, and why.

## Night of 5-6 Nov

- Pre-registered three Crustdata test suites before running them. Results and failures are in eval/.
- Assumed a name match at a company meant the same person. Test showed 4 same-name false matches. Name match is now weak evidence.
- Plain Company Search found known brands on 1 of 4 queries. Size filter returns small brands, so we use it for small-brand discovery.
- Social search returned results on few attempts, so creators register themselves instead of being discovered that way.
- First pricing test: a simulated company valued a small creator below their floor, so nothing closed. Fixed the simulated company's valuation.
- Crash at every step test passes: no action is ever repeated.
