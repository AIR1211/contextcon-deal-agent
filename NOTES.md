# Notes

Append what we tried, whether it worked, and why.

## Night of 5-6 Nov

- Pre-registered three Crustdata test suites before running them. Results and failures are in eval/.
- Assumed a name match at a company meant the same person. Test showed 4 same-name false matches. Name match is now weak evidence.
- Plain Company Search found known brands on 1 of 4 queries. Size filter returns small brands, so we use it for small-brand discovery.
- Social search returned results on few attempts, so creators register themselves instead of being discovered that way.
- First pricing test: a simulated company valued a small creator below their floor, so nothing closed. Fixed the simulated company's valuation.
- Crash at every step test passes: no action is ever repeated.
- First live run exposed bugs fake data hid: a profile's first posts were pinned virals (2,469% engagement); brands with no data outranked enriched ones; the engine shrank requested terms when the budget was binding; agencies appeared as customers. All fixed with tests.
- Made the LLM lean: rules first, model only for missing fields, cached, no loops.
- Live test on a real small creator: half the links on a profile are other people's posts tagging them. Now reads only the creator's own posts (reels read went from 1 to 5).
- Mistake: requested a Company Search field that does not exist. Tests missed it because the fake API accepted any field; the fake now rejects unknown fields. The pre-load exposed it by failing on all 40 niches.
