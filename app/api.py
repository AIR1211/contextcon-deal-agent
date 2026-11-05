"""HTTP API for both dashboards. Run: uvicorn app.api:app --reload  Interactive docs are at /docs. No login in this build."""
import asyncio
import json
import re
import time
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import applications, config, db, llm, offers, orchestrator as orch, service, settings
from .crustdata import Unavailable
from .models import CompanyIn, CompanyLimits, CompanyResponse, CreatorIn, CreatorLimits, DealIn, Decision, Terms

app = FastAPI(title='Avuno')
STATIC = Path(__file__).parent / 'static'


class FreshStatic(StaticFiles):
    """Browsers must check for changes, so a refresh always gets the current interface."""
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers['Cache-Control'] = 'no-cache'
        return response


app.mount('/static', FreshStatic(directory=STATIC), name='static')


def need(kind: str, id_: str) -> dict:
    d = db.get(kind, id_)
    if not d:
        raise HTTPException(404, f'{kind} not found')
    return d


def safe_run(deal_id: str, crash_after: str | None = None) -> None:
    try:
        orch.run(deal_id, crash_after)
    except orch.SimulatedCrash:
        pass


@app.on_event('startup')
def resume_interrupted():
    """A restart picks up every deal that was mid-step."""
    for d in db.all_docs('deal'):
        if d['state'] not in orch.FINAL and not d.get('paused'):
            safe_run(d['id'])


@app.get('/')
def home():
    return FileResponse(STATIC / 'index.html', headers={'Cache-Control': 'no-cache'})


@app.post('/api/creators')
def create_creator(data: CreatorIn, background: BackgroundTasks):
    """Answers at once. The read continues in the background; poll the creator for its progress."""
    c = service.begin_creator(data)
    background.add_task(service.finish_creator, c['id'], data)
    return {**service.public_creator(c), 'ownership_code': c['ownership_code'], 'limits': c['limits']}


@app.get('/api/creators')
def list_creators():
    return [service.public_creator(c) for c in db.all_docs('creator')]


@app.get('/api/creators/{cid}')
def get_creator(cid: str):
    return service.public_creator(need('creator', cid))


@app.post('/api/creators/{cid}/check-ownership')
def check_ownership(cid: str):
    need('creator', cid)
    return service.check_ownership(cid)


@app.get('/api/creators/{cid}/limits')
def read_limits(cid: str):
    """The creator's own private limits, for their Settings page. There is no login in this build."""
    return need('creator', cid)['limits']


@app.post('/api/creators/{cid}/limits')
def write_limits(cid: str, x: CreatorLimits):
    c = need('creator', cid)
    c['limits'] = x.model_dump()
    db.put('creator', cid, c)
    return c['limits']


@app.get('/api/creators/{cid}/matches')
def creator_matches(cid: str):
    need('creator', cid)
    return service.matches(cid)


@app.get('/api/brands/search')
def brand_search(q: str):
    return service.search_brands(q)


class ApplyIn(BaseModel):
    creator_id: str
    company_id: str
    terms: Terms
    pack: str = 'Standard'


@app.post('/api/applications')
def apply_to_brand(x: ApplyIn):
    need('creator', x.creator_id), need('company', x.company_id)
    try:
        return applications.create(x.creator_id, x.company_id, x.terms, x.pack)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get('/api/creators/{cid}/applications')
def creator_applications(cid: str):
    return applications.for_creator(cid)


@app.get('/api/companies/{cid}/applications')
def company_applications(cid: str):
    need('company', cid)
    return applications.for_company(cid)


@app.post('/api/applications/{aid}/accept')
def accept_application(aid: str, background: BackgroundTasks):
    need('application', aid)
    try:
        d = applications.accept(aid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    background.add_task(safe_run, d['id'])
    return orch.public_deal(d)


@app.post('/api/applications/{aid}/decline')
def decline_application(aid: str):
    need('application', aid)
    return applications.decline(aid)


def _auto_loop(cid: str) -> None:
    """Keeps applying as background scoring finishes. Stops when the toggle goes off."""
    for _ in range(30):
        r = applications.auto_apply(cid)
        if not r['assessing'] or not settings.get('creator', cid)['auto_deal']:
            return
        time.sleep(6)


@app.get('/api/settings/{scope}/{sid}')
def read_settings(scope: str, sid: str):
    if scope not in settings.DEFAULTS:
        raise HTTPException(404, 'Unknown settings scope')
    return settings.get(scope, sid)


@app.post('/api/settings/{scope}/{sid}')
def write_settings(scope: str, sid: str, changes: dict, background: BackgroundTasks):
    try:
        out = settings.update(scope, sid, changes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if scope == 'creator' and out['auto_deal'] and db.get('creator', sid):
        background.add_task(_auto_loop, sid)
    return out


@app.get('/api/creators/{cid}/packs/{company_id}')
def creator_packs(cid: str, company_id: str):
    need('creator', cid), need('company', company_id)
    return service.packs(cid, company_id)


class TweakIn(BaseModel):
    before: Terms
    after: Terms


@app.post('/api/creators/{cid}/packs/{company_id}/tweak')
def tweak(cid: str, company_id: str, t: TweakIn):
    need('creator', cid), need('company', company_id)
    return service.tweak_pack(cid, company_id, t.before, t.after)


class CompareIn(BaseModel):
    company_ids: list[str]
    terms: Terms = Terms()


@app.post('/api/creators/{cid}/compare-offers')
def compare_offers(cid: str, x: CompareIn):
    need('creator', cid)
    return service.compare_offers(cid, x.company_ids, x.terms)


@app.post('/api/companies')
def create_company(data: CompanyIn):
    return service.register_company(data)


@app.get('/api/companies')
def list_companies():
    return db.all_docs('company')


@app.get('/api/companies/{cid}')
def get_company(cid: str):
    return need('company', cid)


@app.get('/api/companies/{cid}/creators')
def company_creators(cid: str):
    need('company', cid)
    return service.company_creators(cid)


@app.post('/api/companies/seed')
def seed(niche: str | None = None, max_jobs: int = 300):
    try:
        return service.seed_brands(niche, max_jobs)
    except Unavailable as e:
        raise HTTPException(503, f"Crustdata unavailable: {e}")


class OfferIn(BaseModel):
    text: str = Field(max_length=8000)
    creator_id: str | None = None


@app.post('/api/offers/review')
def review_offer(x: OfferIn):
    c = db.get('creator', x.creator_id) if x.creator_id else None
    return offers.review(x.text, ((c or {}).get('limits') or {}).get('floor_reel'), service.cd)


class BriefIn(BaseModel):
    text: str = Field(max_length=8000)


@app.post('/api/briefs')
def brief(b: BriefIn):
    return llm.parse_brief(b.text)


@app.post('/api/deals')
def create_deal(data: DealIn, background: BackgroundTasks, crash_after: str | None = None):
    need('company', data.company_id)
    for c in data.creator_ids:
        need('creator', c)
    d = orch.start(data)
    background.add_task(safe_run, d['id'], crash_after)
    return orch.public_deal(d)


@app.get('/api/deals')
def list_deals():
    return [orch.public_deal(d) for d in db.all_docs('deal')]


@app.get('/api/deals/{did}')
def get_deal(did: str):
    return {**orch.public_deal(need('deal', did)), 'actions': db.ledger(did)}


@app.get('/api/deals/{did}/events')
async def deal_events(did: str):
    need('deal', did)

    async def stream():
        seq = 0
        for _ in range(1800):
            for e in db.events(did, seq):
                seq = e['seq']
                yield f'data: {json.dumps(e)}\n\n'
            if db.get('deal', did)['state'] in orch.FINAL and not db.events(did, seq):
                return
            await asyncio.sleep(0.5)
    return StreamingResponse(stream(), media_type='text/event-stream')


@app.post('/api/deals/{did}/company-response')
def company_response(did: str, r: CompanyResponse):
    d = need('deal', did)
    if r.limits:
        db.put('company_limits', d['company_id'], r.limits.model_dump())
    return orch.public_deal(orch.set_field(did, 'company_response', {'accept': r.accept, 'non_standard_clause': r.non_standard_clause}))


@app.post('/api/deals/{did}/decide')
def decide(did: str, x: Decision):
    need('deal', did)
    return orch.public_deal(orch.decide(did, x.approve, x.note, x.new_floor_reel))


class OwnContract(BaseModel):
    text: str = Field(min_length=200, max_length=60000)


@app.post('/api/deals/{did}/own-contract')
def own_contract(did: str, x: OwnContract):
    """A brand's own contract replaces ours, but must still cover ad disclosure."""
    need('deal', did)
    if not re.search(r'disclos|ASCI|paid partnership', x.text, re.I):
        raise HTTPException(400, 'The contract must include an ad disclosure clause, as ASCI guidelines require.')
    return orch.public_deal(orch.set_field(did, 'own_contract', x.text))


@app.post('/api/deals/{did}/sign')
def sign(did: str):
    need('deal', did)
    return orch.public_deal(orch.set_field(did, 'signature', {'by': 'company', 'is_mock': True}))


@app.post('/api/deals/{did}/deliver')
def deliver(did: str, links: list[str] = []):
    need('deal', did)
    return orch.public_deal(orch.set_field(did, 'delivery', {'links': links}))


@app.post('/api/deals/{did}/approve')
def approve(did: str):
    need('deal', did)
    return orch.public_deal(orch.set_field(did, 'approval', {'by': 'company'}))


@app.post('/api/deals/{did}/resume')
def resume(did: str):
    need('deal', did)
    return orch.public_deal(orch.run(did))


@app.post('/api/demo/sample-creators')
def sample_creators():
    """Adds labelled mock creators once, so the company side has someone to rank before real sign-ups."""
    have = {c['handle'] for c in db.all_docs('creator')}
    rows = json.loads((config.DATA / 'mock_creators.json').read_text(encoding='utf8'))
    added = [service.onboard_creator(CreatorIn(**r))['handle'] for r in rows if r['handle'] not in have]
    return {'added': added}


@app.post('/api/demo/deals/{did}/contact-left')
def simulate_contact_left(did: str):
    """Demo control, labelled as a simulation: set before the pre-signing re-check runs."""
    d = need('deal', did)
    d['simulate_contact_left'] = True
    db.put('deal', did, d)
    return {'simulated': True}


@app.post('/api/demo/deals/{did}/outage')
def simulate_outage(did: str):
    d = need('deal', did)
    d['simulate_outage'] = True
    db.put('deal', did, d)
    return {'simulated': True}


@app.get('/api/outbox')
def outbox():
    return db.ledger()


@app.get('/api/status')
def status():
    try:
        balance = service.cd.credits()
    except (Unavailable, KeyError, TypeError):
        balance = None
    return {'llm_enabled': bool(llm.config.ANTHROPIC_KEY), 'llm_usage': db.get('llm_usage', 'total') or {'calls': 0}, 'crustdata_keys': len(service.cd.keys), 'credits_used_cached': db.credits_used(), 'credit_balance': balance}
