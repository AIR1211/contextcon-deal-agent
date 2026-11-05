# CLAUDE.md — ContextCon 04 team context

Read this before writing code. It holds the event's rules, how we're judged, the Crustdata API,
our idea at a high level, and who owns what. The product design is ours to decide as we build —
don't invent architecture beyond what the owner of a module asks for.

---

## 1. The event

**ContextCon 04: IIT Kanpur — the Agentic Services Hackathon.** Overnight, Thu 5 → Fri 6 Nov 2026,
DJAC 206, IIT Kanpur. Hosted by Techkriti, with Crustdata (YC F24), in partnership with Y Combinator.

**Theme: "Services, Replaced."** Take a job people or firms are paid to do and build agents that do
*all* of it. Bring in a human only for exceptions, make every decision cite its reasons.
A tool stops when it has found something; a service carries on until the work is done
(parts delivered, invoices paid, fraud caught, offers signed — not just listed or flagged).

The 10 themes: Hiring · Investing · Research and markets · Insurance · Trust and compliance ·
Buying and paying · Agents that spend · Supply chain · Revenue · Infrastructure for agents.
**Own ideas are allowed** — "any service people are paid to do is fair game." Shape can be a single
agent, a multi-agent system, an MCP server or a CLI.

### Schedule
| Time | What |
|---|---|
| 11:00 PM | Building begins (Crustdata team on the floor all night) |
| 12:30 AM | Snacks + lightning talks |
| 3:00 AM | Optional mentor checkpoint (not judged) — bring your hardest case and what breaks |
| 6:30 AM | Last call |
| **7:00 AM** | **Code freeze — the one hard deadline. Repo + demo video due on the submission form** |
| 7:15 AM | Judges review every submission (video review). CTF runs 7:15–8:00 |
| 8:30 AM | Ten finalists + running order announced |
| 8:45 AM | Finals live: **2-min demo + 1 min questions**. Finalists at the front by 8:40, laptop charged |
| 9:15 AM | Last call for People's Choice vote |
| 9:20 AM | Winners |

Suggested pace: ~12:30 one real request runs end to end · ~3:00 hardest case tried · ~6:30 README + video done.

### Rules (breaking these = not judged)
- Coding starts 11:00 PM in a **new repo whose commit history starts at 11:00 PM on 5 Nov**. Repo must be **public**.
- Any model, framework, tool, open-source library or AI coding tool is allowed.
- **Agents talk only to our own team and the organisers — never to real people outside.** No real emails/DMs/payments; use a mock outbox.
- Commit as you go (judges look at how it came together). Keep notes of what we tried and what worked.
- Crustdata use is encouraged (15,000 credits each) but optional; judged on the same criteria either way.

---

## 2. How we're judged (score as the customer who'd buy the service)

Each criterion scored 1–5, weighted to 100. Average of judges' totals decides.
**Ties → End-to-end execution, then Facts and verification.**

| Criterion | Pts | What judges look for |
|---|---|---|
| End-to-end execution | 25 | A real request goes in, a finished result comes out (offer drafted, claim settled, invoice paid, case file written). No one steps in. Asks a person only when the answer changes the result. |
| Facts and verification | 20 | Every person, company, number and date is right *for the day it's used*. Each decision has reasons and sources. One person/company under two names stays one record. When it can't check a fact, it says so instead of guessing. |
| Robustness and edge cases | 20 | Handles messy text, missing fields, unusual cases, a tool that times out or returns nonsense. After a crash/retry it continues where it stopped and **never sends or pays twice**. |
| Customer value and idea | 20 | A job businesses pay people/firms to do today; a non-obvious approach. Does the work itself — more than a chat UI on a model. |
| Demo and understanding | 15 | Clear demo; team can explain approaches weighed and why, what worked/didn't, hardest case, what's next. |

**What judges want to hear** (video + README + live demo): the service and who pays for it today; approaches
we considered and why we chose ours; what worked and what didn't; the hardest case and how we handle it;
how we tested it and know it works; what we left out to ship; what we'd improve next and why not now.

Design questions the handbook says to answer at each step of a service:
take the request (vague request?) · plan (crash halfway?) · gather facts (sources disagree, tool fails?) ·
decide (same case worded differently → same answer?) · act or hand over (never twice?) · show its work (trustworthy without watching?).

**People's Choice:** every builder votes once (not own project) for the one they'd pay for, scoring the same five criteria.

### Prizes
1st $8,000 · 2nd $3,000 · 3rd $1,000 (all in Crustdata credits). Top 3: 1-on-1 office hours with Jon Xu (YC Partner).
Standout builders from any team: pre-placement interview at Crustdata. People's Choice award.

---

## 3. Submission (one person submits; resubmit any time before 7:00, latest counts; same team name each time)

Form asks: team name · one-line (the job it does) · theme (or own idea) · public GitHub repo ·
demo video (one Loom / unlisted YouTube / Drive link, ~2 min, anyone-with-link) ·
how it works (service replaced, what it does today, engineering approach + models, what's next) ·
high-level diagram link (open to anyone) · per member (up to 4): name + email exactly as on YC registration,
IITK email, roll number, personal email, GitHub username.

Checklist: repo public, history from 11 PM · README in repo · video is one link and plays in a private window ·
diagram link opens for anyone · names/emails match YC registration · everyone used @iitk.ac.in for credits.

**README** (judges start here): the service, who does it today, who pays · what it does now end to end and
where it still needs a person · future · how to run · how it's built (agents, models, tools, data, where it
calls Crustdata, where state lives) · approaches tried, what worked and what didn't.

**Demo video:** our product taking a request it has never seen all the way to finished work. Start with the
request going in, end with finished work coming out, show where each fact came from, one-sentence intro.
It's how finalists are picked and our backup if the live demo breaks. In finals, ideally show it handling more
than the prepared request: a duplicate record, a changed fact, or a call that fails.

---

## 4. Crustdata API

Canonical identity graph for people and company data. Credits: sign up at app.crustdata.com with your own
@iitk.ac.in email + the promo code in the handbook (or redeem at app.crustdata.com/billing/credits).
**One account per teammate**, each gets 15,000 credits. Dashboard code is in the handbook.

- Base `https://api.crustdata.com`; headers `authorization: Bearer YOUR_API_KEY` and `x-api-version: 2025-11-01`.
- Docs: docs.crustdata.com (API reference with "Try it", guides, MCP, CLI, `llms.txt` for agents).
  **Only the two endpoint paths below are confirmed — check the docs/llms.txt for the others; don't invent fields.**
- MCP: `claude mcp add --transport http crustdata https://install.crustdata.com/mcp`
  (other clients: streamable-http, same URL, header `Authorization: Bearer YOUR_API_KEY`).

| API | Gives | Req/min |
|---|---|---|
| Person Search | People by title, current/past employer, skills, education, location | 30 |
| Person Enrich | Full career history with dates, education, skills | 15 |
| Company Search | Companies by industry, size, growth, funding, location | 30 |
| Company Identify | Resolve a name or domain to one company — **free** | 30 |
| Company Enrich | Headcount over time, funding, leadership, web traffic | 15 |
| Job Search | Job postings by company, role, location | 30 |
| Web Search and Fetch | Web, news, academic search; fetch any page | 10 |
| Watcher | Webhook when a watched person/company/job changes | 10 |

Each key: 200 req/min across all endpoints. Cost e.g. company search 0.03 credits/result + premium field groups
(docs.crustdata.com/general/pricing). Balance: dashboard Credits, `crustdata account credits` (CLI), or `GET /account/credits` (free).

```bash
curl -X POST https://api.crustdata.com/company/identify \
  -H 'authorization: Bearer YOUR_API_KEY' -H 'content-type: application/json' -H 'x-api-version: 2025-11-01' \
  -d '{ "domains": ["crustdata.com"] }'
# → [{ "matched_on":"crustdata.com","match_type":"domain","matches":[{ "confidence_score":1,
#      "company_data":{ "crustdata_company_id":6036032,"basic_info":{"name":"Crustdata (YC F24)","year_founded":2024},
#      "headcount":{"total":47} } }] }]

curl -X POST https://api.crustdata.com/person/search \
  -H 'authorization: Bearer YOUR_API_KEY' -H 'content-type: application/json' -H 'x-api-version: 2025-11-01' \
  -d '{ "filters": { "field":"education.schools.school","type":"=","value":"Indian Institute of Technology, Kanpur" }, "limit":1 }'
```

Errors: **401** key not reaching them (send as `authorization: Bearer ...`) · **402** out of credits, retry won't help ·
**403** key not allowed for endpoint (check dashboard Endpoints page) · **429** over limit — wait `x-ratelimit-reset`, build retries in ·
**no results** — loosen one filter at a time, get exact values via the Autocomplete API.

Suggested routes: Trust and compliance = Company Identify → Person Enrich → Web Search and Fetch ·
Revenue = Job Search → Person Search → Watcher · Infrastructure = MCP → Watcher.

---

## 5. Our idea (high level — details decided as we build)

**An AI agency for influencer–brand deals.** It does the job an influencer-marketing / talent-management
agency is paid to do (typically a commission on the deal): take a brand deal, check both sides, work out terms
against a set of rules, and execute the contract end to end — not just recommend.

Things to keep in mind (from the rubric):
- Decide clearly whose side the agent is on, or how it stays fair to both; judges will ask.
- Verify the parties (is the brand/company real, does the person contacting actually work there) and cite sources.
- Finish the job: a contract/term sheet and the outgoing message — sent to a **mock** outbox, never real people.
- Never act twice after a crash; say "can't verify" rather than guess.
- Build a small labelled test set (fair deals, bad terms, fakes) and report results in the README.

---

## 6. Division of labour

| Person | Owns | Responsible for |
|---|---|---|
| **P1 — Intake & terms** | parsing + contract/terms logic | Turn a messy request/offer/contract into structured terms; compare against the rules; produce proposed changes |
| **P2 — Verification & Crustdata** | Crustdata client + verification | API client (cache, retries on 429, key rotation across teammates' keys); checks on the brand and the people involved, each fact with source + time |
| **P3 — Orchestrator & state** | shared data models, state/DB, decisions, actions | Defines the shared models first so everyone can work in parallel; runs the job step by step and resumes after a crash; decision rules; idempotent actions (mock outbox, payment milestones) |
| **P4 — UI, eval & demo** | UI, report, fixtures, eval, docs | Sample requests + test set; UI; final report; README, diagram, demo video, submission form |

Working rules:
- Only edit what you own; ask the owner for changes. Changes to shared models are announced to everyone.
- Branch per person, merge to `main` at least hourly; commit small and often.
- Everyone appends to `NOTES.md`: what we tried, whether it worked, why. It feeds the README and Q&A.
- Team checkpoints: 12:45 one request end to end (stubs OK) · 3:00 hardest case to mentor · 5:00 feature freeze ·
  ~6:00 video recorded and first submission in.
- Never commit API keys (`.env` gitignored).

## 7. Contacts
Techkriti team: venue, Wi-Fi, food, activities. Crustdata team on the floor: credits, promo code, APIs, MCP, your idea and build
(Maharnav, Ainesh, Tanvi, Yash). Submissions/form: WhatsApp group. Urgent: Ayush Kumar Singh (Techkriti).
