# Avuno

Paste a brand's request, in whatever words it came. Avuno checks who is asking, picks creators, negotiates, writes the contract, gets it signed, and carries each deal to a paid invoice. It asks a person only when the answer changes the result.

Built at ContextCon 04, IIT Kanpur. Theme: own idea, closest to Revenue and Trust and compliance. The demo video is linked on the submission form.

## The service

**What it replaces:** the job of an influencer-marketing or talent agency.

**Who does it today:** agencies and talent managers. They find the other side, check them, negotiate, handle the contract and chase payment over about two weeks of email.

**Who pays:** the brand, the creator, or both, usually as a commission on the deal. Small brands and small creators are often not worth an agency's time, so they go without or get bad terms. Larger clients pay for slow manual work. Avuno serves both sides at any size, for a disclosed 5% from each side on closed deals only.

**Why we picked it:** the work is mostly checking facts, applying rules and following up, which agents can do. The hard parts, trust and money, are also what the judging rewards.

## What it does now, end to end

1. **Takes the request.** An email, a chat message or a PDF brief goes in. Each detail is linked to the line it came from. Our test brief shows the current ₹5,00,000 cap being used and a superseded ₹6,00,000 being ignored.
2. **Pushes back.** Rights forever, payment in 90 days and unlimited revisions are flagged against published limits. A request to hide that a post is paid stops the job.
3. **Checks both parties on Crustdata.** Each fact shows its source and date. A person is only verified if their work email, a single matching profile and their career history all agree. Anything less is reported as "can't verify" and means stricter payment terms, not a guess.
4. **Chooses creators.** They are ranked on engagement, content and audience. Follower count isn't scored. Ties go through a published chain.
5. **Negotiates.** Each side's limit stays private. One published rule picks the best-value terms and the fee-adjusted midpoint price (`docs/proofs.txt`).
6. **Finishes the job.** Contract with a SHA-256 fingerprint, live re-check before signing, signatures, funds held, delivery, approval, payout, invoice.
7. **Shows its work.** Activity log, data lookups, email thread and an action ledger on every deal.

### Where it still needs a person

| Moment | Why |
|---|---|
| The message doesn't name the company, budget or niche | The result depends on it, so it asks instead of guessing |
| The company can't be verified | Continue with the strictest terms, or stop |
| A fact changes at the pre-signing re-check | Signing pauses |
| A source fails at the re-check | Facts stay unconfirmed, so a person decides |
| No price fits both sides | One side can lower its limit, or the deal ends |

### What is real and what is simulated

| Real | Simulated, and labelled |
|---|---|
| Crustdata lookups, cached and rate-limited | Email (mock outbox, nothing reaches anyone) |
| Parsing, scoring, the negotiation engine | Signatures, escrow and payments |
| Contract text and fingerprint | Replies, delivery and approval from the other side |
| Crash recovery and the action ledger | Creators in the demo (labelled mock accounts) |
| | GSTIN registry lookup (format check only) |

The rules forbid contacting real people, so a found contact is only ever named by role in the mock outbox.

## Whose side is it on?

Both. It is a neutral broker with a disclosed fee. Neither side can see the other's limit, and neither can move the price by haggling, because the rule is published in advance. Negotiating as a one-sided agent would have been easier, but each side would then have needed its own agency.

## How we tested it, and how we know it works

Crustdata was tested before we relied on it. Cases were committed before each run, and logs are hash-chained, so results can't be quietly edited (`eval/REPORT.txt`).

| Test | Result |
|---|---|
| Real brand domains resolve | 23 of 24 |
| Fake lookalike domains rejected | 12 of 12 |
| Labelled offers (fair, bad terms, fake), first run | 14 of 15, all 5 bad-term offers and all 6 fakes caught |
| Name resolves to the right company | 6 of 8 |
| Leaver not listed as current | 1 of 4, so a name match alone never verifies anyone |
| Brand-ranking backtest | Weak: 2.4× lift on only 5 positives, so we don't claim accuracy |
| Automated tests, using a fake Crustdata that rejects unknown fields | All pass (`python -m pytest -q`) |
| Full flows in real Chrome, using real clicks | Pass, with no page errors |

## The hardest case

**A crash in the middle of paying out.** The money has moved, but the step isn't saved. Every outward action has a stable key in a ledger, so a resume repeats the step and can't pay or send twice. The video shows this happening. Tests cover it at each step, along with pasting the same request twice and restarting a request after its deal has run.

**The hardest facts case:** someone claims to be from a real company using a personal email. The company checks out and the person doesn't. Avuno says so, holds 100% upfront with a lower cap, and addresses the deal to a marketing contact found at the company by role.

## Approaches we tried

| Approach | Result |
|---|---|
| LLM negotiating with itself | **Dropped.** Same case, different price. It also can't be proven fair |
| Multi-round concessions | **Dropped.** Slower, and invites gaming, with no better outcome |
| Sealed limits and one published rule | **Kept.** Repeatable and provable, with property tests on random deals |
| Agents and LLMs deciding each step | **Dropped.** Code decides. The LLM can only fill gaps and polish text, and is off by default. The demo uses 0 tokens |
| Name match means a verified person | **Dropped.** Our tests found different people with the same name |
| Creator data from Crustdata's person records | **Didn't work.** It is LinkedIn-based. Public Instagram pages through Web Fetch work, with limits |
| Finding brands by searching the niche word | **Weak.** It returned media peers. Hiring for influencer roles plus "consumer brand selling X products" was better |
| A fixed list of niches | **Dropped.** Vocabulary is now learned from search results for any phrase |
| Live lookups on each page view | **Too slow.** Now cache first, scoring in the background |
| Testing only against fake data | **Hid real bugs:** pinned viral posts (2,469% engagement), agencies listed as customers, and a wrong search field that broke all pre-loads. Live runs found these |

More in `docs/decisions.txt` and `NOTES.md`.

## What we left out to ship

Login, real email, real payments and e-sign, checks that delivered posts match the brief, multi-language parsing, scanned PDFs and lawyer-reviewed contracts.

## What it could do next, and why not now

| Next | Why not tonight |
|---|---|
| Check delivered posts against the brief | Needs real posts and platform access |
| Live email in both directions | The event rules forbid contacting real people |
| Licensed payment partner and e-sign | Needs a partner, KYC and legal review |
| Login and per-account access | The brand view is private by design, but not yet protected. This must come before real use |
| Learn pricing from real deals | Prices rest on stated assumptions until real deals exist |

## The future of this service

Once agents can do the whole job, an agency's commission stops paying for email and follow-up. What remains valuable is trust: a record of who delivered and who paid, which gets better with every deal. Small brands and creators get service they can't get today, and people handle only exceptions.

## How to run it

```powershell
pip install -r requirements.txt
Copy-Item .env.example .env        # add a Crustdata key. Rotate with CRUSTDATA_API_KEYS=key1,key2
uvicorn app.api:app --reload       # open http://localhost:8000, choose Brand, paste a request
python -m pytest -q                # uses a fake Crustdata and spends no credits
```

`ANTHROPIC_API_KEY` is optional. Without it, everything runs on rules and templates. The first request for a new company takes a minute or two because of API rate limits, and later ones come from the cache.

## How it's built

Diagram: [`docs/architecture.md`](docs/architecture.md)

| Part | File | Job |
|---|---|---|
| Request intake | `app/intake.py` | One message in, each stage saved and resumable |
| Brief reader | `app/campaign.py` | PDF and text to fields, flags and a creator brief with private parts removed |
| Verification | `app/verify.py` | Verified, weak match, partly verified, can't verify, blocked |
| Crustdata client | `app/crustdata.py` | Cache, retries, key rotation, honest failure |
| Scoring and tiebreaks | `app/scoring.py`, `app/tiebreak.py` | Fit, confidence, gates, published chains |
| Negotiation engine | `app/engine.py`, `app/packages.py` | Terms and price. Pure maths, see `docs/proofs.txt` |
| Orchestrator | `app/orchestrator.py` | Runs each deal, resumes after a crash, never acts twice |
| Contract | `app/contract.py` | Contract, gates, fingerprint, invoice |
| LLM layer | `app/llm.py` | Optional. Fills gaps and polishes text, never decides |
| API and UI | `app/api.py`, `app/static/` | FastAPI, plain JS, GSAP, no build step |

**Agents and models:** one rule-based service agent. There is no agent loop, so runs repeat exactly. Optional model: Claude, for gaps in parsing and for polishing a pitch. A changed number makes it discard the polish.

**Where it calls Crustdata:** Company Identify (who is this domain or name), Company Enrich (headcount, funding), Person Search and Enrich (sender and contact checks), Company Search and Job Search (brand discovery), Web Fetch and Search (public creator pages, niche evidence).

**Where state lives:** SQLite in WAL mode, one process. Saved after each step, with an append-only event log and a ledger keyed so each action happens once. A real launch would need a proper queue.

**Runs on:** one laptop, Python 3.12.
