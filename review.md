# Avuno: complete product overview for review

This document describes the product as built, including what is simulated and what is known to be weak. It is meant for a reviewer looking for edge cases, logic errors and security problems. Section 13 lists weaknesses we already know about, and section 14 lists where to look next. Please check claims against the code, because this document can be wrong.

## 1. What it is

Avuno does the work of an influencer-marketing or talent agency, for creators and brands of any size. It finds likely brands, builds media packs, verifies both parties, negotiates inside private limits, writes the contract and carries the deal through to a released payment and invoice. A person is asked only when the answer changes the result.

- **Service replaced:** talent managers (paid by commission) and influencer-marketing agencies (paid by retainer or campaign margin).
- **Position:** a neutral broker. One published rule for both sides, private limits, and a disclosed fee on closed deals only. Fee: 5% from each side.
- **Context:** built overnight for ContextCon 04, a hackathon judged on end-to-end execution (25), facts and verification (20), robustness (20), customer value (20) and demo (15). Facts must be right "for the day it is used". After a crash it must never send or pay twice. Agents may only talk to the team and organisers, never to real outside people.

## 2. What is real and what is simulated

| Real | Simulated |
|---|---|
| Crustdata company and people lookups | Payments, escrow, payouts (ledger rows only) |
| Reading public Instagram pages through Crustdata Web Fetch | E-signature (a button and a ledger row) |
| Negotiation maths, scoring, ranking, tiebreaks | Email: everything stays in a mock outbox |
| State machine, crash resume, action ledger | Replies from the other side in the email thread |
| Contract text and SHA-256 hash | "Day N" labels: fixed estimates in `config.MAIL_DAYS` |
| Offer review rules | GSTIN registry lookup (format check only) |
| | Delivery and approval, unless "Simulate delivery" is off |
| | Audience demographics: self-reported |
| | Sample creators in `data/mock_creators.json`, labelled mock |

There is **no login**. Anyone who can reach the server can act as anyone (see section 13).

## 3. Stack and files

Python, FastAPI, SQLite in one process, plain JavaScript and GSAP, no build step.

| File | Purpose |
|---|---|
| `app/engine.py` | Negotiation maths. Pure functions, no I/O |
| `app/orchestrator.py` | Deal state machine, crash resume, email thread, exclusivity reservation |
| `app/verify.py` | Domain cleaning, lookalike detection, brand and sender verification, risk tier |
| `app/scoring.py` | Likelihood, fit, confidence, gates, "why" lines |
| `app/niche.py` | Free-text niche vocabulary learned from search results |
| `app/packages.py` | Pricing, packs, tweak deltas, term variations |
| `app/applications.py` | Applications, offers, accept and decline, Auto Deal |
| `app/offers.py` | Review of a pasted offer against rules |
| `app/contract.py` | Contract text, gates, hash, invoice |
| `app/creators.py` | Instagram page parsing and engagement |
| `app/crustdata.py` | API client: cache, retries, key rotation, trace |
| `app/service.py` | Onboarding, company database, matching |
| `app/settings.py`, `app/config.py` | User settings; assumptions and limits |
| `app/llm.py` | Optional LLM helper with deterministic fallbacks |
| `app/db.py` | JSON documents, events, ledger, cache |
| `app/api.py`, `app/static/` | HTTP API and dashboard |
| `tests/`, `eval/` | Automated tests; pre-registered live tests and results |

## 4. Main flows

**Creator:** enter a handle and free-text niche; the app reads public stats in the background with progress; sees ranked brands with reasons; opens media packs; tweaks terms and sees estimated effects; applies, or turns on Auto Deal; or reviews an offer they received.

**Brand:** registers with name, niche, optional domain, sender, Instagram, GSTIN and budget; is verified; sees ranked offers with reasons; chooses one, which starts a deal; signs. A brand can also pick creators or a bundle directly.

**Registration merge:** registering a company whose Crustdata ID or domain already exists updates that record. So applications sent to a brand before it registers appear in its inbox afterwards.

## 5. Deal state machine (`orchestrator.py`)

Order: `verify, pitch, await_company, negotiate, contract, recheck, sign, fund, deliver, approve, release, invoice, done`. Final states: `done`, `blocked`, `no_deal`.

The state is saved after each step, so a crash re-runs the step in progress. Actions go through `db.act(key, ...)`, an `INSERT OR IGNORE` on a stable key, so repeats do nothing. A per-deal in-process lock prevents concurrent runs. At startup, every unfinished and unpaused deal resumes.

| Step | What happens | Can stop or pause on |
|---|---|---|
| verify | Checks company status, gates per creator and exclusivity conflict. Pulls company data and a lead (role only) from Crustdata | Blocked company, failed gate, conflict → blocked. Contact left, or tier C → question |
| pitch | Email to the sender, or to the lead's role in a mock inbox | |
| await_company | Simulated reply, or waits if the company is in human mode | Decline → no_deal. Non-standard clause → question |
| negotiate | Tries options meeting the requested terms; if none fits and allowed, tries lighter ones. Writes a quote, a counter and agreement to the thread | No overlap → question, which can lower the first creator's floor |
| contract | Renders the contract, or waits for the brand's own if "Write contracts" is off. Hashes it | Waits for own contract |
| recheck | Skips the cache. Domain still resolves, company re-enriched; if the sender was verified, re-verifies them | Any change or lookup failure → question |
| sign | Gate check; reserves exclusivity atomically; waits for a person if "Sign myself" is on | Gate failure or reservation lost → blocked |
| fund | Holds the tier's upfront percentage (mock) | |
| deliver, approve | Simulated, or waits | |
| release | Charges any balance, pays each creator, takes the fee, each with its own key | |
| invoice | Issues the invoice | |

**Questions:** `contact_left`, `unverified_company`, `non_standard_clause`, `no_overlap`, `recheck_override`, and a `tool_failure` pause when a data source fails.

## 6. Verification (`verify.py`)

Statuses: `verified`, `weak_match`, `partly_verified`, `cannot_verify`, `blocked`, plus `contact_left` for senders.

**Brand:**
1. A non-free-mail domain that resolves in Company Identify is `verified`. If the claimed name belongs to a different domain in the alias table, it's `blocked`.
2. A domain with no match is `blocked` if it contains a known brand's name from `data/aliases.json`, or if the claimed name resolves live (confidence ≥ 0.9) to a different real domain containing that name. Otherwise it's unmatched, not guilty.
3. A valid GSTIN format gives `partly_verified` (the registry lookup is mocked).
4. An Instagram page gives `weak_match`, or `partly_verified` with at least 10 posts and proof of ownership.
5. Otherwise `cannot_verify`. A lookup failure is reported as unchecked, never as a negative finding.

**Sender:** searches for that name at the company, current then past. Past only gives `contact_left`. No match gives `cannot_verify`. Any match starts at `weak_match`, because live testing found 4 same-name false matches. `verified` needs all of: an email on the company's domain, exactly one profile, and career history listing the company as current.

**Risk tier:**

| Tier | Condition | Held upfront | Deal cap |
|---|---|---|---|
| A | Brand and sender verified | 50% | None |
| B | Brand verified or partly verified | 100% | ₹25,000 |
| C | Anything else | 100%, after human review | ₹10,000 |
| Blocked | Either blocked | Deal stops | |

## 7. Negotiation (`engine.py`, proofs in `docs/proofs.txt`)

For an option with creator cost C, brand value V and fee rates fc, fb:

- r = ceil(C / (1 − fc)), summed per creator; c = floor(V / (1 + fb)). A deal is possible only if r ≤ c.
- The option with the largest surplus (c − r) wins. Ties go to fewer restrictions (exclusivity, usage, stories), then ID.
- Price = floor((r + c) / 2), the Nash bargaining solution.
- In a bundle, each creator gets their r plus an equal share of the surplus.
- Creator net = p − floor(p·fc); brand pays = p + ceil(p·fb).

Property tests on 20,000 random deals check: never outside limits, money adds up, order independence, the midpoint maximises the Nash product, and no listed option beats the winner for both sides.

**Options** come from `term_grid`: usage in {requested, 30, 60, 90}, exclusivity in {requested, 0}, stories in {requested, requested − 1}.

**Email thread:** the opening ask is max(sum of list prices, price × 1.1), and the counter is 2 × price − ask, so they're symmetric around the engine's price. They're presentation, not bargaining: the engine decides the price first.

## 8. Scoring (`scoring.py`, `niche.py`)

Weights are our judgement. Unknown factors score 0.5 and add no confidence.

- **Brand likelihood:** niche 25, influencer roles 25, influencer staff 15, funding 15, growth 10, news 10. Eligible if niche evidence ≥ 1 and score ≥ 45. If no brand matches the niche at all, brands hiring for influencer roles are shown, labelled "fit not proven".
- **Creator fit:** by default audience 35, content 25, attention 20, past sponsored 10, reliability 10. A brand's campaign goal (awareness, engagement, conversion, brand building) switches to other weights in `config.FIT_PROFILES`. Follower count isn't scored. Reliability has no data yet. Past sponsored comes from marked captions when at least 3 are read: none scores 0.5, up to 40% scores 1.0, up to 70% scores 0.6, above that 0.3. It can't see undisclosed sponsorships.
- **Confidence:** sum of weight × evidence strength, reported separately from fit.
- **Gates (fit):** under 18; brand's niche in the creator's blocked list; engagement under 0.1%.
- **Engagement:** (median likes + median comments) / followers, using the creator's own posts, skipping the first 3 when at least 6 exist (likely pinned). Above 50% is flagged as anomalous and not used.
- **Free-text niches:** the phrase is searched in Crustdata. Words appearing across several results become "learned" vocabulary. An own word counts 2, a learned word 0.5. Evidence = own × 2 + learned × 0.5, and the niche factor is min(evidence / 2, 1). Two niches are related if their vocabularies overlap by ≥ 20% of the smaller set. Being returned by a search doesn't count as evidence; only registered companies' stated niche does.

## 9. Pricing (`packages.py`, assumptions in `config.py`)

Estimates, not measurements. Views aren't readable, so they're estimated.

- Reel rate = max(₹1,500, likes × 15 views per like × ₹300 CPM / 1000), with likes capped at 25% of followers.
- Story = one third of a reel. Extra usage: +10% per 30 days beyond 30. Exclusivity: +20% per 30 days. Paid ads: +30%.
- Creator floor = their own, or 70% of the estimated rate.
- A simulated company values a reel at the larger of 1.4 × the rate and half its budget, split across creators and reels.
- Close estimate = 0.5 × likelihood + 30 × affordability + 0.2 × fit. A tweak is "improved" if expected earnings (net × close) rise.

## 10. Applications and Auto Deal (`applications.py`)

- One open application per creator and company. A new one is possible after a decline.
- Accepting creates one deal; accepting twice returns the same deal. By default the brand's other open applications are declined.
- **Auto Deal** sends a chosen pack to brands with likelihood ≥ 55, confidence ≥ 40 and an allowed status, up to 10. Skipped brands are returned with reasons. It only applies; it never signs.
- **Auto-accept** (off by default) accepts on fit ≥ 75.

## 11. Offer review (`offers.py`)

Regex extraction, then rules from `config.OFFER_RULES`: usage ≤ 180 days, exclusivity ≤ 90, payment ≤ 45 days, revisions ≤ 3, kill fee expected above ₹20,000.

Verdicts: `reject` (asks the creator to pay, asks for an OTP or password, asks to install software, private chat only or guaranteed income, hides ad disclosure, impersonation), `counter` (bad terms), `clarify` (missing details), `fair`.

## 12. Evidence so far

- **Automated tests:** `python -m pytest`. All pass, on a fake Crustdata that rejects unknown search fields. Covers crash at every step, no duplicates, limit privacy, and the main scenarios.
- **Browser run:** real Chrome clicking through packs, tweak, settings, choosing an offer, signing, and crash and resume, with no page errors. This was a one-off script and isn't in the repo.
- **Live tests:** `eval/REPORT.txt`, with cases committed before running:
  - Real domains resolved 23 of 24, and fake domains were rejected 12 of 12.
  - Likelihood backtest on 160 brands: 2.4× lift and AUC 0.623, but only 5 brands had the label. Weak evidence, and on an older score.
  - Labelled offers: 14 of 15 on the first run. The miss was fixed afterwards, so a re-run wouldn't be independent.
- **Not measured:** whether real brands respond, whether prices are right, or whether matches perform. There is no outcome data.

## 13. Known weaknesses

**Critical if this were real:**
1. **No authentication.** Anyone can read a creator's private limits at `GET /api/creators/{id}/limits`, change settings, accept offers, sign and approve deals.
2. **Company takeover by registration.** Registering with a known company's domain merges into its record, replacing budget and sender, and exposes its offers. Nothing proves control of the domain.
3. **Typed email is trusted.** A sender can become `verified` by typing a work email for a real employee. Mailbox ownership is never confirmed.
4. **Creator takeover.** Registering an existing handle overwrites that creator's limits and niche. The bio code isn't enforced before applying or dealing, and its check may fail because public pages can truncate bios.
5. **Anonymous credit spend.** Unauthenticated calls can trigger paid lookups. The limit is 60 a minute per client, kept in memory, and it trusts the connecting address.

**Logic gaps:**
6. Exclusivity has no end date. It blocks by deal state, not by whether the days have passed, and reservations aren't released when a deal stops.
7. There's no campaign object. Choosing one creator declines every open application to that brand, even for unrelated work.
8. The Auto Deal cap counts all past auto applications, not those per run, despite the setting's wording.
9. The Instagram route to `partly_verified` can't be reached through the API, because `bio_code_seen` is never set for companies.
10. Lowering the floor after "no overlap" applies to the first creator only and isn't saved to their limits. In a bundle this may not resolve the gap.
11. Gates aren't checked when applying, so a minor or low-engagement creator can apply and is only stopped when a deal starts. A creator still reading, or unreadable, can also apply.
12. Own contracts need only 200 characters and a word like "disclose", and don't have to contain the agreed price or terms.
13. The re-check tests that the domain still resolves and the sender is unchanged. It doesn't compare other facts such as funding or headcount.
14. The midpoint rule lets a party work out the other side's limit for that option from the final price. Limits can also be gamed: no efficient mechanism guarantees honest reporting.
15. Tier B and C caps can shrink value below costs, ending in "no overlap" with no explanation of why.

**Data and matching:**
16. Niche matching is lexical. English only, so Hindi or Hinglish captions score poorly, and learned words can be generic. Confidence is usually low.
17. Instagram parsing depends on page metadata and could break without warning. Followers are rounded. Reading this way may conflict with Instagram's terms.
18. The agency filter is a keyword list plus industry names, so it misses some agencies and may catch real brands.
19. Revenue estimates and some company records from Crustdata were wrong in testing. They are shown or used as signals only.
20. `/person/identify` is disabled on our key, so an email can't be resolved directly to a person.
21. Cached data can be up to 7 days old (24 hours for pages), and a failed refresh serves stale data with its old date. Score results are kept in memory with no expiry until restart.

**Reliability:**
22. The lock is in-process, and SQLite is one file, so running several workers is unsafe.
23. The event stream queries SQLite inside the async loop, and streams on paused deals poll for up to 15 minutes.
24. The ledger uses `synchronous=NORMAL`: safe for a process crash, but an OS crash could lose the latest rows. With real payments it would also need an outbox pattern, because an action could happen and crash before being recorded.
25. Startup resume runs inside server start, so paced deals delay startup.

**Legal:** the contract template has had no legal review. Consent, GST and TDS, stamp duty and escrow are mocked or noted, and minors are handled only through a self-reported flag.

## 14. Where a reviewer should look

1. **Money:** rounding, fees on bundles, tier caps, upfront plus balance, and any path that pays without funds held or holds without paying.
2. **State:** answering a question twice, answering after a state change, resuming during a pause, setting a field in the wrong state, or racing accept, decline and auto-accept.
3. **Idempotency:** any action whose key could collide or vary, and thread entries against ledger entries after a crash.
4. **Privacy:** any response, email, reason or ranking that leaks a floor, ceiling or budget, including through ordering, "why" lines or the estimated price shown.
5. **Verification bypass:** domain forms (subdomains, punycode, unicode lookalikes, trailing dots), names with unusual spacing or case, parent and child companies, and free-mail lists.
6. **Parsing:** budgets like "1.5 lakh", "2k-5k", "$500", or several numbers; relative dates; negated clauses ("no exclusivity", "not perpetual"); non-English offers; prompt injection in pasted text.
7. **Fairness:** the same case worded differently, whether tiebreak bands can be gamed, and whether scoring favours any group of creators or brands.
8. **Failure modes:** Crustdata timeouts, 402, 403 and malformed data at each step; a key running out mid-deal; an empty search; a company with missing fields.
9. **UI honesty:** anywhere the screen implies something real that's simulated, or a claim stronger than its evidence.

## 15. Running it

```
pip install -r requirements.txt
cp .env.example .env              # add CRUSTDATA_API_KEY, or CRUSTDATA_API_KEYS=key1,key2
uvicorn app.api:app --reload      # dashboard at localhost:8000, API docs at /docs
python -m pytest -q               # uses a fake Crustdata, spends no credits
python -m app.prewarm             # optional: warms the cache for known niches
```

`ANTHROPIC_API_KEY` is optional. The LLM layer has never been run live; without it, rules and templates are used. Other reference documents: `docs/spec.txt`, `docs/decisions.txt`, `docs/proofs.txt` and `eval/REPORT.txt`.
