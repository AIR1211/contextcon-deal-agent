"""Creators apply to brands with a media pack, and brands choose. Auto Deal applies on a creator's behalf above set thresholds.
Applying never commits anyone: nothing is signed until the brand accepts and the deal runs."""
from . import campaign, db, llm, orchestrator as orch, packages, scoring, service, settings, tiebreak
from .models import DealIn, Terms


def _company_contact(company: dict) -> str:
    return company.get('sender_email') or f"contact@{company.get('domain') or company['id']}"


def _open_for(creator_id: str, company_id: str):
    return next((a for a in db.all_docs('application') if a['creator_id'] == creator_id and a['company_id'] == company_id and a['status'] == 'sent'), None)


def create(creator_id: str, company_id: str, terms: Terms, pack: str = 'Standard', source: str = 'manual') -> dict:
    existing = _open_for(creator_id, company_id)
    if existing:
        return existing                  # Applying twice never sends twice.
    creator, company = db.get('creator', creator_id), db.get('company', company_id)
    if company['status'] == 'blocked':
        raise ValueError('This company is blocked.')
    problem = packages.within_limits(creator, terms)
    if problem:
        raise ValueError(problem)
    s = service._brand_score(company, creator['niche'], True)      # Looks up the brand if needed, so the reason is real.
    f = scoring.fit(creator, company)
    a = {'id': db.new_id('app'), 'creator_id': creator_id, 'handle': creator['handle'], 'company_id': company_id, 'company_name': company['name'], 'terms': terms.model_dump(), 'pack': pack, 'status': 'sent', 'source': source, 'brief_sha': (company.get('brief') or {}).get('sha'),
         'sent_at': db.now(), 'deal_id': None, 'is_mock': creator.get('is_mock', False), 'why_brand': scoring.why_brand(company['name'], s, company['status']), 'why_creator': scoring.why_creator(creator, f, company)}
    db.put('application', a['id'], a)
    body = llm.pitch_text({'name': company['name'], 'niche': company.get('niche')}, [{'handle': creator['handle']}], a['terms'])
    db.act(f"{a['id']}:sent", a['id'], 'mock_email', {'to': _company_contact(company), 'subject': f"@{creator['handle']} applied with a {pack} pack", 'body': body, 'delivered': False, 'note': 'Mock outbox: nothing is sent to real people.'})
    cs = settings.get('company', company_id)
    if cs['auto_accept'] and f['passes'] and f['score'] >= cs['auto_accept_min_fit']:
        deal = accept(a['id'], decline_others=False)
        orch.run(deal['id'])
        return db.get('application', a['id'])
    return a


def for_creator(creator_id: str) -> list[dict]:
    return sorted([a for a in db.all_docs('application') if a['creator_id'] == creator_id], key=lambda a: a['sent_at'], reverse=True)


def for_company(company_id: str) -> dict:
    """Open applications ranked by the published chain. Shows estimates only, never a creator's floor."""
    apps = [a for a in db.all_docs('application') if a['company_id'] == company_id]
    company = db.get('company', company_id)
    done = {}
    for d in db.all_docs('deal'):
        if d['state'] == 'done':
            for x in d['creator_ids']:
                done[x] = done.get(x, 0) + 1
    rows = []
    for a in [x for x in apps if x['status'] == 'sent']:
        c = db.get('creator', a['creator_id'])
        f = scoring.fit(c, company)
        s = c.get('stats') or {}
        rows.append({**a, 'creator_id': c['id'], 'niche': c['niche'], 'followers': s.get('followers'), 'engagement_rate': s.get('engagement_rate'), 'fit': f['score'], 'confidence': f['confidence'], 'gates_failed': f['gates_failed'],
                     'reasons': f['reasons'], 'list_price_estimate': packages.list_price(c, Terms(**a['terms'])), 'deals_done': done.get(c['id'], 0), 'why': scoring.why_creator(c, f, company), 'brief_checks': campaign.check_creator(company.get('brief'), c)})
    floor = settings.get('company', company_id)['offers_min_fit']
    shown, hidden = [r for r in rows if r['fit'] >= floor], [r for r in rows if r['fit'] < floor]
    return {'open': tiebreak.rank_creators(shown, company_id), 'hidden': len(hidden), 'closed': [x for x in apps if x['status'] != 'sent']}


def accept(app_id: str, decline_others: bool | None = None) -> dict:
    """Starts the deal. The caller runs it. Accepting twice returns the same deal."""
    a = db.get('application', app_id)
    if a['deal_id']:
        return db.get('deal', a['deal_id'])
    if a['status'] != 'sent':
        raise ValueError('This application is closed.')
    if not db.get('company', a['company_id']).get('brief'):
        raise ValueError('Add your campaign brief before choosing a creator. Creators need something to read.')
    cs, app = settings.get('company', a['company_id']), settings.get('app')
    d = orch.start(DealIn(creator_ids=[a['creator_id']], company_id=a['company_id'], terms=Terms(**a['terms']), simulate_parties=cs['simulate_delivery'], pace_ms=app['pace_ms'] if app['watchable_pace'] else 0))
    d.update(company_response={'accept': True}, human_sign=cs['sign_myself'], application_id=app_id)
    db.put('deal', d['id'], d)
    a.update(status='accepted', deal_id=d['id'])
    db.put('application', app_id, a)
    if cs['decline_others_on_choose'] if decline_others is None else decline_others:
        for o in db.all_docs('application'):
            if o['company_id'] == a['company_id'] and o['status'] == 'sent':
                decline(o['id'], 'The brand chose another creator for this campaign.')
    return d


def decline(app_id: str, note: str = 'The brand passed on this application.') -> dict:
    a = db.get('application', app_id)
    if a['status'] == 'sent':
        a.update(status='declined', note=note)
        db.put('application', app_id, a)
        db.act(f'{app_id}:declined', app_id, 'mock_email', {'to': '@' + a['handle'], 'subject': f"{a['company_name']} passed this time", 'body': note, 'delivered': False, 'note': 'Mock outbox: nothing is sent to real people.'})
    return a


def auto_apply(creator_id: str) -> dict:
    """Sends the Standard pack to each eligible brand. Returns who was skipped and why, so nothing happens unexplained."""
    st = settings.get('creator', creator_id)
    if not st['auto_deal']:
        return {'sent': [], 'held_back': [], 'assessing': 0}
    creator = db.get('creator', creator_id)
    m = service.matches(creator_id)
    pack = st['auto_pack']
    terms = packages.PACK_TIERS[pack]
    allowed = ('verified', 'partly_verified') if st['auto_allow_partly_verified'] else ('verified',)
    if packages.within_limits(creator, terms):
        terms = terms.model_copy(update={'exclusivity_days': 0})
    used = len([a for a in for_creator(creator_id) if a['source'] == 'auto'])
    sent, held = [], []
    for b in m['matches']:
        name = b['name']
        if _open_for(creator_id, b['company_id']):
            continue
        if b['likelihood'] < st['auto_min_likelihood']:
            held.append({'name': name, 'reason': f"Likelihood {b['likelihood']} is below your {st['auto_min_likelihood']}."})
        elif b['confidence'] < st['auto_min_confidence']:
            held.append({'name': name, 'reason': f"Confidence {b['confidence']} is below your {st['auto_min_confidence']}."})
        elif b['status'] not in allowed:
            held.append({'name': name, 'reason': 'The company is not verified enough to approach automatically.'})
        elif used + len(sent) >= st['auto_max_per_run']:
            held.append({'name': name, 'reason': f"Reached your limit of {st['auto_max_per_run']} applications."})
        else:
            create(creator_id, b['company_id'], terms, pack, 'auto')
            sent.append(name)
    return {'sent': sent, 'held_back': held, 'assessing': m['assessing']}
