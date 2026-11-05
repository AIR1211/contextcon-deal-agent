"""Onboarding and matching for both dashboards. Private limits live in separate documents and never leave through public views."""
import re
import secrets
import threading

from . import db, packages, scoring, tiebreak
from .config import FEE_BRAND, FEE_CREATOR
from .engine import settle
from . import niche as niches
from .creators import read_profile, read_stats, add_engagement
from .crustdata import Crustdata, NotCached, Unavailable
from .models import CANT, CompanyIn, CreatorIn, Fact, Terms
from .verify import group_of, risk_tier, verify_brand, verify_sender

cd = Crustdata()
BACKGROUND = True
_running: set[str] = set()
_guard = threading.Lock()
SEARCH_SIZES = ('2-10', '11-50', '51-200')      # Small brands first: the customers agencies skip.


def public_creator(c: dict) -> dict:
    return {k: v for k, v in c.items() if k not in ('limits', 'ownership_code')}


def onboard_creator(data: CreatorIn) -> dict:
    handle = data.handle.strip().lstrip('@')
    c = {'id': db.new_id('cr'), 'handle': handle, 'niche': data.niche, 'limits': data.limits.model_dump(), 'autopilot': data.autopilot, 'is_minor': data.is_minor,
         'audience_country_pct': data.audience_country_pct, 'ownership_code': 'DEAL-' + secrets.token_hex(3).upper(), 'ownership_verified': False, 'facts': [], 'status': 'read', 'is_mock': bool(data.mock_stats)}
    if data.mock_stats:
        m = dict(data.mock_stats)
        likes, comments = m.pop('likes', []), m.pop('comments', [])
        c['stats'] = add_engagement({**m, 'source': 'Labelled mock profile', 'strength': 0.3, 'reels_read': len(likes)}, likes, comments)
    else:
        try:
            c['stats'] = read_stats(cd, handle)
        except Unavailable as e:
            c.update(stats={'source': None, 'strength': 0}, status=CANT, read_error=str(e))
    s = c['stats']
    for field in ('followers', 'engagement_rate', 'median_likes', 'median_comments'):
        if s.get(field) is not None:
            c['facts'].append(Fact(subject='@' + handle, field=field, value=s[field], source=s['source'], url=s.get('url'), as_of=s.get('as_of') or c.get('as_of') or db.now(), strength='partly_verified', is_mock=c['is_mock']).model_dump())
    return db.put('creator', c['id'], c)


def check_ownership(creator_id: str) -> dict:
    c = db.get('creator', creator_id)
    try:
        p = read_profile(cd, c['handle'], fresh=True)
    except Unavailable as e:
        return {'verified': False, 'reason': f'Could not read the profile ({e}).'}
    ok = bool(p and c['ownership_code'] in (p.get('bio') or ''))
    c['ownership_verified'] = ok
    db.put('creator', creator_id, c)
    return {'verified': ok, 'reason': 'Code found in bio.' if ok else 'Code not found. Bio text from public pages can be cut short, so try placing it first.'}


def register_company(data: CompanyIn, bio_code_seen: bool = False) -> dict:
    v = verify_brand(cd, data.name, data.domain or data.sender_email, data.instagram, data.gstin, bio_code_seen)
    sender = verify_sender(cd, data.sender_name, data.sender_email, v['company_id'], v['domain'], data.sender_profile_url) if data.sender_name else {'status': CANT, 'reasons': ['No sender named.'], 'facts': []}
    tier = risk_tier(v['status'], sender['status'])
    if v['status'] == 'blocked':      # No point reporting on a sender at a company that failed.
        sender = {'status': CANT, 'reasons': [], 'facts': []}
    twin = next((x for x in db.all_docs('company') if v['status'] != 'blocked' and ((v['company_id'] and x.get('company_id') == v['company_id']) or (v['domain'] and x.get('domain') == v['domain']))), None)
    names = sorted({n for n in (twin or {}).get('also_known_as', []) + [(twin or {}).get('name'), data.name] if n and n != (v['name'] or data.name)})
    c = {'id': twin['id'] if twin else db.new_id('co'), 'also_known_as': names, 'name': v['name'] or data.name, 'niche': data.niche, 'domain': v['domain'], 'company_id': v['company_id'], 'group': v['group'], 'status': v['status'], 'sender_status': sender['status'],
         'sender_name': data.sender_name, 'sender_email': data.sender_email, 'sender_profile_url': data.sender_profile_url, 'tier': tier, 'facts': v['facts'] + sender['facts'], 'reasons': v['reasons'] + sender['reasons'],
         'budget': data.budget, 'gstin': data.gstin, 'instagram': data.instagram, 'mode': data.mode, 'source': 'registered'}
    if data.limits:
        db.put('company_limits', c['id'], data.limits.model_dump())
    elif data.budget and data.mode == 'simulated':
        db.put('company_limits', c['id'], {'ceiling': data.budget, 'simulated': True})
    return db.put('company', c['id'], c)


INTERMEDIARY = re.compile(r'\b(agency|agencies|advertis\w*|media|digital|marketing|consult\w*|staffing|recruit\w*|talent|resource\w*|infosol\w*|solutions|semantics|creators?|creative|studios?|influencer\w*|\bpr\b|hr)\b', re.I)


def is_intermediary(name: str | None, industries=None) -> bool:
    """An agency hiring for influencer roles is a rival, not a customer. Names are a rough filter, so this can miss some."""
    if name and INTERMEDIARY.search(name):
        return True
    return any(x in str(industries or '').lower() for x in ('advertising', 'staffing', 'recruiting', 'marketing services', 'public relations', 'media production', 'movies, videos', 'online audio and video media'))


def seed_brands(niche: str | None = None, max_jobs=300, per_size=15) -> dict:
    """Builds the company database live: brands hiring for influencer roles, plus companies matching any free-text niche."""
    seen = {b.get('company_id') for b in db.all_docs('company')}
    added = {'from_jobs': 0, 'from_search': 0, 'agencies_skipped': 0}
    if not db.get('seed', 'jobs'):
        jobs, ts, cursor = [], db.now(), None
        while len(jobs) < max_jobs:
            page, ts, cursor = cd.influencer_jobs(min(100, max_jobs - len(jobs)), cursor)
            jobs += page
            if not page or not cursor:
                break
        counts = {}
        for j in jobs:
            b = ((j.get('company') or {}).get('basic_info') or {})
            if is_intermediary(b.get('name')):
                added['agencies_skipped'] += 1
                continue
            cid = b.get('crustdata_company_id')
            if not cid and b.get('primary_domain'):
                try:
                    m, _ = cd.identify_domain(b['primary_domain'])
                    cid = m[0]['company_data']['crustdata_company_id'] if m else None
                except Unavailable:
                    cid = None
            if cid:
                counts.setdefault(cid, {'b': b, 'n': 0})['n'] += 1
        for cid, x in counts.items():
            if cid not in seen:
                seen.add(cid)
                d = db.new_id('co')
                db.put('company', d, {'id': d, 'name': x['b'].get('name'), 'domain': x['b'].get('primary_domain'), 'company_id': cid, 'status': 'verified', 'sender_status': CANT, 'tier': 'B', 'niche': '', 'mode': 'simulated', 'source': 'job_search', 'influencer_roles_seen': x['n'], 'as_of': ts,
                                       'facts': [Fact(subject=x['b'].get('name') or str(cid), field='influencer_roles', value=x['n'], source='Crustdata Job Search', as_of=ts).model_dump()]})
                added['from_jobs'] += 1
        db.put('seed', 'jobs', {'at': db.now()})
    if niche:
        for size in SEARCH_SIZES:
            # Tested against alternatives: this phrasing finds consumer brands, not companies with "brand" in their name.
            rows, ts = cd.search_companies(f'consumer brand selling {niche} products', size=size, limit=per_size)
            for r in rows:
                cid, b = r.get('crustdata_company_id'), r.get('basic_info') or {}
                if cid and cid not in seen and not is_intermediary(b.get('name'), (r.get('taxonomy') or {}).get('professional_network_industry')):
                    seen.add(cid)
                    d = db.new_id('co')
                    db.put('company', d, {'id': d, 'name': b.get('name'), 'domain': b.get('primary_domain') or None, 'company_id': cid, 'status': 'verified' if b.get('primary_domain') else 'weak_match', 'sender_status': CANT, 'tier': 'B', 'niche': niche, 'mode': 'simulated', 'source': 'company_search', 'size_range': b.get('employee_count_range'), 'description': b.get('description'), 'industry': (r.get('taxonomy') or {}).get('professional_network_industry'), 'as_of': ts,
                                           'facts': [Fact(subject=b.get('name') or str(cid), field='company', value=b.get('name'), source=f'Crustdata Company Search for "{niche}"', as_of=ts).model_dump()]})
                    added['from_search'] += 1
        db.put('seed', niches.norm(niche), {'at': db.now()})
    return added


def _brand_score(company: dict, niche: str, deep: bool, cached_only: bool = False, open_niche: bool = False) -> dict | None:
    """deep=True uses enrichment. cached_only returns None if this brand hasn't been looked up yet."""
    enriched, roles, staff = None, company.get('influencer_roles_seen'), None
    if deep and company.get('company_id'):
        try:
            if cached_only:
                with cd.cache_only():
                    enriched, _ = cd.enrich_company(company['company_id'])
                    roles = cd.jobs_at(company['company_id'])[0]
                    staff = len(cd.contacts(company['company_id'])[0])
            else:
                enriched, _ = cd.enrich_company(company['company_id'])
                roles = cd.jobs_at(company['company_id'])[0]
                staff = len(cd.contacts(company['company_id'])[0])
        except NotCached:
            return None
        except Unavailable:
            pass
    # A niche only counts as evidence if the company stated it. Being returned by a search proves nothing.
    fields = ('name', 'description', 'industry', 'niche') if company.get('source') == 'registered' else ('name', 'description', 'industry')
    text = ' '.join(str(company.get(k) or '') for k in fields)
    return scoring.likelihood(company.get('signals') or scoring.brand_signals(enriched, roles, staff, text), niche, open_niche=open_niche)


def candidates_for(niche: str) -> list[dict]:
    brands = [b for b in db.all_docs('company') if b['status'] != 'blocked' and not is_intermediary(b.get('name'))]
    return [b for b in brands if niches.related(b.get('niche'), niche) or niches.hits(niche, ' '.join(str(b.get(k) or '') for k in ('name', 'description', 'industry')))]


def assess(brands: list[dict], niche: str) -> None:
    """Paced to the enrich rate limit. Results land in the cache, where the next page load finds them."""
    for b in brands:
        try:
            _brand_score(b, niche, True)
        except Exception:      # One bad record must not stop the rest.
            continue


def _start_assessing(niche: str, brands: list[dict]) -> None:
    key = niches.norm(niche)
    with _guard:
        if key in _running:
            return
        _running.add(key)

    def work():
        try:
            assess(brands, niche)
        finally:
            _running.discard(key)
    threading.Thread(target=work, daemon=True).start()


def matches(creator_id: str, limit: int = 15) -> dict:
    """Answers at once from the cache, and scores the rest in the background. Only brands with the same evidence are
    compared, so missing data can't beat real data. The page refreshes as results arrive."""
    creator = db.get('creator', creator_id)
    niche = creator['niche']
    if not db.get('seed', niches.norm(niche)):
        try:
            seed_brands(niche)
        except Unavailable:
            pass      # Ranks whatever is already known.
    niches.profile(niche)      # The creator's own niche may need one live lookup. Everything below is cache only.
    with cd.cache_only():
        candidates = candidates_for(niche)
    # Broad niches such as "vlogging" return media peers, not buyers. Brands hiring for creator marketing buy across niches.
    open_niche = not candidates
    if open_niche:
        candidates = [b for b in db.all_docs('company') if b.get('source') == 'job_search' and b['status'] != 'blocked' and not is_intermediary(b.get('name'))]
    ranked, rejected, pending = [], [], []
    for b in candidates:
        with cd.cache_only():
            s = _brand_score(b, niche, True, cached_only=True, open_niche=open_niche)
        if s is None:
            pending.append(b)
            continue
        row = {'company_id': b['id'], 'name': b['name'], 'domain': b.get('domain'), 'status': b['status'], 'tier': b.get('tier'), 'likelihood': s['score'], 'confidence': s['confidence'], 'reasons': s['reasons'], 'size_range': b.get('size_range'), 'source': b.get('source')}
        (ranked if s['eligible'] else rejected).append(row)
    # Enough already scored means no background work is needed for this page.
    todo = pending[:max(limit - len(ranked) - len(rejected), 0)]
    if todo and BACKGROUND:
        _start_assessing(niche, todo)
    elif todo:
        assess(todo, niche)
        return matches(creator_id, limit)
    ranked = tiebreak.rank_brands(ranked, creator_id)
    return {'matches': ranked[:20], 'rejected': rejected[:20], 'threshold': packages.A['match_threshold'], 'open_niche': open_niche, 'assessing': len(todo), 'not_assessed': max(len(pending) - len(todo), 0), 'note': 'Likelihood weights are our judgement until real deals exist.'}


def _scores(creator: dict, company: dict) -> tuple[int, int]:
    return _brand_score(company, creator['niche'], False)['score'], scoring.fit(creator, company)['score']


def packs(creator_id: str, company_id: str) -> dict:
    c, co = db.get('creator', creator_id), db.get('company', company_id)
    like, fit_ = _scores(c, co)
    return {'packs': packages.packs_for(c, co, like, fit_), 'likelihood': like, 'fit': fit_, 'is_estimate': True}


def tweak_pack(creator_id: str, company_id: str, before: Terms, after: Terms) -> dict:
    c, co = db.get('creator', creator_id), db.get('company', company_id)
    like, fit_ = _scores(c, co)
    return packages.tweak(c, co, before, after, like, fit_)


def company_creators(company_id: str, base: Terms = Terms()) -> dict:
    """Ranks creators with a suggested bundle within budget. Scores never reveal a creator's floor."""
    co = db.get('company', company_id)
    rows, failed = [], []
    done = {}
    for d in db.all_docs('deal'):
        if d['state'] == 'done':
            for x in d['creator_ids']:
                done[x] = done.get(x, 0) + 1
    for c in db.all_docs('creator'):
        if co.get('niche') and not niches.related(c.get('niche'), co['niche']):
            continue
        f = scoring.fit(c, co)
        row = {'creator_id': c['id'], 'handle': c['handle'], 'niche': c['niche'], 'followers': (c.get('stats') or {}).get('followers'), 'engagement_rate': (c.get('stats') or {}).get('engagement_rate'), 'fit': f['score'], 'confidence': f['confidence'], 'reasons': f['reasons'], 'list_price_estimate': packages.list_price(c, base), 'is_mock': c.get('is_mock'), 'deals_done': done.get(c['id'], 0)}
        if f['passes']:
            rows.append(row)
        else:
            failed.append({**row, 'gates_failed': f['gates_failed']})
    rows = tiebreak.rank_creators(rows, company_id)
    budget, used, bundle = packages.company_budget(co), 0, []
    for r in rows:
        cost = r['list_price_estimate']
        if used + cost <= budget and len(bundle) < 5:
            bundle.append(r['creator_id'])
            used += cost
    return {'creators': rows, 'failed_gates': failed, 'suggested_bundle': bundle, 'bundle_list_price_estimate': used, 'budget': budget}


def compare_offers(creator_id: str, company_ids: list[str], base: Terms = Terms()) -> dict:
    """A creator with offers from several companies. Each is settled by the engine, then ranked by the published chain."""
    c = db.get('creator', creator_id)
    offers, none = [], []
    for i, cid in enumerate(company_ids):
        co = db.get('company', cid)
        if not co or co['status'] == 'blocked':
            none.append({'company_id': cid, 'reason': 'Unknown or blocked company.'})
            continue
        lim = db.get('company_limits', cid) or {'ceiling': packages.company_budget(co), 'simulated': True}
        tier = co.get('tier') or 'C'
        s = settle(packages.options([c], lim, base, tier), FEE_CREATOR, FEE_BRAND)
        if not s:
            none.append({'company_id': cid, 'name': co['name'], 'reason': 'No overlap between private limits.'})
            continue
        offers.append({'company_id': cid, 'name': co['name'], 'net': s.creator_net[creator_id], 'tier': tier, 'upfront_pct': packages.TIERS[tier]['upfront_pct'], 'exclusivity_days': s.terms.get('exclusivity_days', 0), 'usage_days': s.terms.get('usage_days', 30), 'fit': scoring.fit(c, co)['score'], 'offered_at': i, 'terms': s.terms})
    return {'offers': tiebreak.rank_offers(offers, creator_id), 'no_offer': none}
