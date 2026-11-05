# Avuno

An AI agent that does the work of an influencer-marketing agency, for creators and brands of any size. It finds the other side, builds a media pack, negotiates, writes the contract and carries the deal to a paid invoice. A person is asked only when the answer changes the result.

Built at ContextCon 04, IIT Kanpur. **Work in progress:** the full judge-facing README is written last.

## Run it

```powershell
pip install -r requirements.txt
Copy-Item .env.example .env        # then add your key
uvicorn app.api:app --reload       # open http://localhost:8000, API docs at /docs
python -m pytest -q                # uses a fake Crustdata, spends no credits
```

To rotate between teammates' keys, set `CRUSTDATA_API_KEYS=key1,key2,key3,key4` in `.env`.
`ANTHROPIC_API_KEY` is optional. Without it, deterministic rules parse briefs and templates write the messages.

## How it's built

| Part | File | Job |
|---|---|---|
| Negotiation engine | `app/engine.py` | Picks terms and price. Pure maths, see `docs/proofs.txt` |
| Tiebreaks | `app/tiebreak.py` | Published chains with one guaranteed winner |
| Verification | `app/verify.py` | Verified, weak match, partly verified, can't verify, blocked |
| Creator reader | `app/creators.py` | Public Instagram stats through Crustdata Web Fetch |
| Scoring | `app/scoring.py` | Likelihood, fit, confidence, safety gates |
| Packs and pricing | `app/packages.py` | Media packs, tweak deltas, bundles |
| Orchestrator | `app/orchestrator.py` | Runs each deal, resumes after a crash, never acts twice |
| Crustdata client | `app/crustdata.py` | Cache, retries, key rotation, honest failure |
| Contract | `app/contract.py` | Contract, gates, hash, invoice |
| LLM layer | `app/llm.py` | Reads and writes only; code decides |
| API and UI | `app/api.py`, `app/static/` | Both dashboards |

State lives in SQLite. Every outward action goes through a ledger with a stable key.

## Where to read more

- `docs/spec.txt`: requirements, models, API
- `docs/decisions.txt`: options weighed and why
- `docs/proofs.txt`: what the maths guarantees and what it can't
- `eval/REPORT.txt`: pre-registered Crustdata tests with published failures
- `NOTES.md`: what we tried

## What's mocked

Payments and escrow, e-signature, GSTIN registry lookup, email delivery (a mock outbox only), and simulated companies. Nothing reaches real people. There is no login in this build. The contract template needs a lawyer's review before real use.
