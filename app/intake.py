"""Takes a request in the customer's own words and runs the whole job: read it, check who is asking, choose creators, then run each
deal to a paid invoice. Each stage is saved, so a crash resumes where it stopped. A person is asked only when an answer changes the result.
Rules only: the same text always reads the same way, and the text is data, so nothing in it can instruct the agent."""
import hashlib
import re
import threading
import time

from . import applications, campaign, config, db, llm, offers, orchestrator as orch, packages, service, settings
from . import niche as niches
from .config import FEE_BRAND, FEE_CREATOR, OFFER_RULES as R
from .crustdata import Unavailable
from .engine import settle
from .models import CompanyIn, Terms, now
from .verify import FREE_MAIL, clean_domain

EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
DOMAIN = re.compile(r'(?<![@\w.-])(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+(?:com|in|co|io|ai|org|net|store|shop|club|app|life|care))\b(?:/\S*)?', re.I)
KIND = r'(?:creators?|influencers?|bloggers?|vloggers?|youtubers?|reviewers?)'
CAP = r"[A-Z][\w&'’-]*(?:[ 	]+(?:&[ 	]+)?[A-Z][\w&'’-]*){0,4}"
COUNTS = {'one': 1, 'a': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'couple': 2, 'pair': 2, 'few': 3}
WANT = re.compile(rf'\b(\d+|one|two|three|four|five|couple(?: of)?|pair of|few)(?:\s*(?:-|–|to|or)\s*(\d+|two|three|four|five))?\s+(?:[\w-]+\s+){{0,3}}?{KIND}\b', re.I)
KIND_WORD = re.compile(rf"\b((?:[\w'-]+\s+){{1,3}}?){KIND}\b", re.I)
VAGUE = set('a an the some few couple pair of good great right nice decent relevant micro nano mid small big large top popular local indian desi new our your any more one two three four five six need needs want wants get find and or for with like who looking us to do'.split())
PRODUCT = re.compile(r"\b(?:launching|launch of|launch|selling|sell|sells|make|makes|making|promote|promoting|promotion of)\s+(?:(?:a|an|our|the|new|first|next|latest|brand new)\s+)*([\w'’ -]{3,40}?)(?=\s+(?:next|this|in|on|at|for|and|by|before|from|with|soon|which|that|to|range)\b|[,.;:!?(\n]|$)", re.I)
OPENERS = (r"(?i:called|named)\s+", r"(?i:greetings from)\s+", r"(?i:brand|company|client)\s*(?:name)?\s*[:=-]\s*", r"(?i:we(?:'|’)?re|we are|this is|i(?:'|’)?m from|i am from|writing from|calling from|team at|team|on behalf of|founder of|co-?founder of|ceo of|cmo of|marketing (?:lead |manager |head )?(?:at|for)|head of marketing at|work(?:ing)? (?:at|for|with)|running|i run|we run)\s+", r"\bat\s+", r"\bfrom\s+")
TITLE_WORDS = re.compile(r'\b(founder|co-?founder|ceo|cmo|coo|cto|head|lead|manager|marketing|growth|brand|director|partnerships?|executive|intern|associate|team|vp)\b', re.I)
CLOSING = re.compile(r"^\s*[-–—~]?\s*(?:thanks|thank you|thx|ty|regards|best|best regards|kind regards|warm regards|cheers|sincerely|yours)\b[\s,.!:-]*(.*)$", re.I)
NAME = re.compile(r"^[A-Z][a-zA-Z'’.-]+(?:\s+[A-Z][a-zA-Z'’.-]+){0,2}$")
QUESTIONS = {'company': 'Which company is this request for?', 'budget': 'What budget should the agent work within? It stays private.', 'niche': 'What does the brand sell, or what kind of creators does it want?'}
STOP_STAGES = {'stopped', 'duplicate'}
SHOWN_LIMIT = 6
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _sender(lines: list[str], email: str | None) -> tuple[str | None, str | None, int | None]:
    """Who sent it, and the company in the signature if there is one. Reads the sign-off first, then 'I'm X'."""
    for i, line in enumerate(lines):
        m = CLOSING.match(line)
        if m:
            below = next((n for n in range(i + 1, min(i + 4, len(lines))) if lines[n].strip()), None)
            for text, at in ((m[1], i), (lines[below] if below is not None else '', below)):
                head, _, tail = re.sub(r'^[-–—~\s]+', '', text).partition(next((s for s in (',', ' | ', ' - ', ' – ', ' @ ', ' at ') if s in text), '\0'))
                if NAME.match(head.strip()) and not TITLE_WORDS.fullmatch(head.strip()):
                    return head.strip(), tail.strip() or None, at
    for i, line in enumerate(lines):
        m = re.search(r"(?i:i(?:'|’)?m|i am|this is|my name is|name's)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)(?=\s*(?:,|\.|from|here|at|and|\band\b|$))", line)
        if m and m[1].lower() not in ('from',):
            return m[1], None, i
    if email:
        for i, line in enumerate(lines):
            if email in line:
                above = next((n for n in range(i - 1, -1, -1) if lines[n].strip()), None)
                if above is not None and NAME.match(lines[above].strip()):
                    return lines[above].strip(), None, above
                head = line.replace(email, '').strip(' ,-–—|<>()')
                if NAME.match(head):
                    return head, None, i
    return None, None, None


def _company_candidates(text: str, signature: str | None, label: str | None) -> list[str]:
    """Possible company names, best first. One that agrees with the website wins; anything else gets checked, not trusted."""
    found = []
    if signature:
        parts = [p.strip() for p in re.split(r',|\||@|\s+at\s+|\s+-\s+', signature) if p.strip()]
        found += [p for p in reversed(parts) if re.match(r'[A-Z]', p) and not TITLE_WORDS.search(p)]
    for opener in OPENERS:
        found += [m[1].rstrip(".’'") for m in re.finditer(opener + rf'({CAP})', text)]
    seen, out = set(), []
    for name in found:
        key = re.sub(r'[^a-z0-9]', '', name.lower())
        if key and key not in seen:
            seen.add(key)
            out.append(name)
    if label:
        out.sort(key=lambda n: label not in re.sub(r'[^a-z0-9]', '', n.lower()) and re.sub(r'[^a-z0-9]', '', n.lower()) not in label)
    return out


def _budget(text: str) -> int | None:
    clean = re.sub(r'\d[\d,.]*\s*(?:k|l|lakh|lac)?\+?\s*(?:followers?|subs\b|subscribers?|views?|sign-?ups?|likes?)', ' ', text, flags=re.I)
    for sentence in re.split(r'(?<=[.!?\n])\s*', clean):
        if re.search(r'budget|spend|all in|all-in|in total|pay\b|paying|fee\b|₹|\brs\b|\binr\b|rupees?|lakh', sentence, re.I):
            found = llm._money(sentence)
            bare = re.search(r'(\d{1,3}(?:,\d{2,3})+|\d{4,})', sentence)
            if found or bare:
                return found or int(bare[1].replace(',', ''))
    return llm._money(clean)


def _wanted(text: str) -> int:
    m = WANT.search(text)
    if not m:
        return 1
    top = m[2] or m[1]
    word = top.lower().split()[0]
    n = int(word) if word.isdigit() else COUNTS.get(word, 1)
    return max(1, min(n, 5))


def _niche(text: str, brief: dict, rules: dict) -> tuple[str | None, str | None]:
    """(the kind of creator wanted, the product). Either can match creators."""
    kind = None
    for m in KIND_WORD.finditer(text):
        words = [w for w in m[1].lower().split() if w not in VAGUE and not w.isdigit()]
        if words:
            kind = ' '.join(words)
            break
    product = next((f['value'] for f in brief['fields'] if f['key'] == 'product' and f['lines'] and '—' in f['value']), None)
    product = product.split(';')[0].split('—')[-1].split('(')[0].strip() if product else None
    if not product:
        m = PRODUCT.search(text)
        words = [w for w in m[1].split() if w.lower() not in VAGUE] if m else []
        product = ' '.join(words) or None
    return kind, product or rules.get('niche')


def read(text: str, answers: dict | None = None) -> dict:
    """What the message says. Every value carries the line it came from. Missing means missing: nothing is guessed."""
    a = answers or {}
    lines = text.replace('\r', '').split('\n')
    brief = campaign.parse(text)
    rules = llm.parse_brief_rules(text)
    by = {f['key']: f for f in brief['fields']}

    def line_of(value):
        return next((i for i, l in enumerate(lines) if value and value.lower() in l.lower()), None)

    email_m = EMAIL.search(text)
    email = email_m[0] if email_m else None
    email_domain = clean_domain(email) if email else None
    site = next((clean_domain(m[1]) for m in DOMAIN.finditer(text) if clean_domain(m[1]) != email_domain), None)
    domain = a.get('domain') or site or (email_domain if email_domain and email_domain not in FREE_MAIL else None)
    label = re.sub(r'[^a-z0-9]', '', domain.split('.')[0]) if domain else None
    sender, signature, sender_line = _sender(lines, email)
    candidates = [a['company']] if a.get('company') else [re.sub(r'\s*\(.*?\)\s*', ' ', by['client']['value']).strip()] if 'client' in by else _company_candidates(text, signature, label)
    candidates = [c for c in candidates if not sender or c.lower() != sender.lower()]
    agrees = lambda n: label and (label in re.sub(r'[^a-z0-9]', '', n.lower()) or re.sub(r'[^a-z0-9]', '', n.lower()) in label)
    name = next((c for c in candidates if agrees(c)), None) or (candidates[0] if candidates and not label else (label.title() if label else None))
    kind, product = _niche(text, brief, rules)
    niche = a.get('niche') or kind or product
    budget = int(a['budget']) if a.get('budget') else (brief.get('budget') or {}).get('cap') or _budget(text)
    wanted = (brief.get('budget') or {}).get('creators_target') or _wanted(text)
    want_line = next((i for i, l in enumerate(lines) if WANT.search(l)), None)
    x = offers.extract(text)
    usage = R['max_usage_days'] if x['usage_perpetual'] else min(x['usage_days'] or packages.PACK_TIERS['Standard'].usage_days, R['max_usage_days'])
    stated = brief.get('reels') or brief.get('stories')
    terms = Terms(reels=brief.get('reels') or 1, stories=(brief.get('stories') or 0) if stated else packages.PACK_TIERS['Standard'].stories, usage_days=usage, exclusivity_days=min(x['exclusivity_days'] or 0, R['max_exclusivity_days']))

    def row(key, label_, value, line, private=False):
        return {'key': key, 'label': label_, 'value': str(value), 'lines': [line] if line is not None else [], 'private': private}

    identity = []
    if name:
        identity.append(row('company', 'Company', name, line_of(name) if line_of(name) is not None else line_of(domain)))
    if domain:
        identity.append(row('website', 'Website', domain, line_of(domain)))
    if sender:
        identity.append(row('sender', 'From', sender, sender_line))
    if email:
        identity.append(row('email', 'Email', email, line_of(email)))
    if product:
        identity.append(row('product', 'Product', product, line_of(product)))
    if kind:
        identity.append(row('kind', 'Creators wanted', f"{wanted} × {kind}", want_line if want_line is not None else line_of(kind)))
    elif wanted > 1:
        identity.append(row('kind', 'Creators wanted', wanted, want_line))
    if budget:
        identity.append(row('budget', 'Budget', f'₹{budget:,}', next((i for i, l in enumerate(lines) if _budget(l) == budget), None), True))
    skip = {'title', 'client', 'budget', 'product'}
    fields = identity + [f for f in brief['fields'] if f['key'] not in skip]
    needs = [k for k, ok in (('company', name or domain), ('budget', budget), ('niche', niche)) if not ok]
    return {'name': name, 'candidates': candidates, 'domain': domain, 'sender_name': sender, 'sender_email': email, 'niche': niche, 'product': product, 'budget': budget, 'wanted': wanted, 'terms': terms.model_dump(), 'fields': fields, 'flags': brief['flags'], 'missing': brief['missing'], 'sha': brief['sha'], 'text': text, 'needs': needs,
            'usage_asked_forever': x['usage_perpetual']}


def _log(case: dict, text: str) -> None:
    case.setdefault('log', []).append({'at': now(), 'text': text})


def _reply(case: dict, key: str, to: str, subject: str, body: str) -> None:
    if db.act(f"{case['id']}:{key}", case['id'], 'mock_email', {'to': to, 'subject': subject, 'body': body, 'delivered': False, 'note': 'Mock outbox: nothing is sent to real people.'}):
        case.setdefault('replies', []).append({'to': to, 'subject': subject, 'body': body})
        return True
    return False


def _requester(case: dict, r: dict, co: dict | None = None) -> str:
    return r.get('sender_email') or (co and f"Marketing team at {co['name']} (mock inbox)") or 'The requester (mock inbox)'


def stage_read(case: dict) -> None:
    r = read(case['text'], case.get('answers'))
    case['read'] = r
    _log(case, f"Read the request: {len(r['fields'])} details found")
    if 'company' in r['needs']:
        _ask(case, ['company'])


def _ask(case: dict, needs: list[str]) -> None:
    case['paused'] = {'needs': needs, 'question': ' '.join(QUESTIONS[k] for k in needs)}
    _log(case, 'Asked a person: ' + case['paused']['question'])
    raise orch.Pause('request_details')


def _resolve_by_name(r: dict) -> None:
    """No website in the message: look the name up. A weak match doesn't count, so the check below reports it as unverified."""
    if r['domain']:
        return
    for name in r['candidates'][:3]:
        try:
            m = service.cd.identify_name(name)[0]
        except Unavailable:
            return
        top = m[0] if m else None
        if top and top.get('confidence_score', 0) >= 0.9 and top['company_data']['basic_info'].get('primary_domain'):
            r.update(domain=clean_domain(top['company_data']['basic_info']['primary_domain']), name=name)
            return


def stage_company(case: dict) -> None:
    r = case['read'] = read(case['text'], case.get('answers'))
    _resolve_by_name(r)
    before = next((d for d in db.all_docs('company') if r['domain'] and d.get('domain') == clean_domain(r['domain'])), None)
    co = service.register_company(CompanyIn(name=r['name'] or r['domain'], niche=r['niche'] or '', domain=r['domain'], sender_name=r['sender_name'], sender_email=r['sender_email'], budget=r['budget'] or 0))
    case.update(company_id=co['id'], company_name=co['name'])
    _log(case, f"Checked {co['name']} on Crustdata: {co['status'].replace('_', ' ')}")
    if r['sender_name']:
        _log(case, f"Checked {r['sender_name']}: {co['sender_status'].replace('_', ' ')}")
    if co['status'] == 'blocked':
        _reply(case, 'blocked', _requester(case, r), 'We can\'t take this request', ' '.join(co.get('reasons') or []))
        raise orch.Stop('stopped', ' '.join(co.get('reasons') or ['This company failed verification.']))
    twin = next((o for o in db.all_docs('request') if o['id'] != case['id'] and o.get('company_id') == co['id'] and o.get('stage') not in STOP_STAGES and (not r['niche'] or niches.related((o.get('read') or {}).get('niche'), r['niche']))), None)
    if twin:
        case['duplicate_of'] = twin['id']
        if before:      # A second message adds a name to the record. It can't replace the contact or budget on a running job.
            db.put('company', co['id'], {**before, 'also_known_as': co.get('also_known_as') or []})
        _reply(case, 'duplicate', _requester(case, r), f"Already in progress for {co['name']}", 'This looks like the same campaign as a request we are already running, so no second deal was started.')
        names = co.get('also_known_as') or []
        raise orch.Stop('duplicate', f"This is the same company as an earlier request{' (also known as ' + ', '.join(names) + ')' if names else ''}, asking for the same campaign. It stays one record, and no second contract or payment was started.")
    # Asked only now, so a duplicate or a fake never costs anyone a question.
    if r['needs']:
        _ask(case, r['needs'])
    brief = service.set_brief(co['id'], case['text'])
    blocks = [f['text'] for f in brief['flags'] if f['severity'] == 'block']
    if blocks:
        _reply(case, 'blocked', _requester(case, r), 'We can\'t take this request', ' '.join(blocks))
        raise orch.Stop('stopped', ' '.join(blocks))
    stored = db.get('company', co['id'])
    per = r['budget'] // r['wanted']
    stored['brief']['budget'].update(cap=r['budget'], pool=r['budget'], creators_target=r['wanted'], per_creator=per)
    stored['brief']['creator_brief'].update(title=stored['brief']['creator_brief']['title'] if stored['brief']['creator_brief']['title'] != 'Campaign brief' else f"{co['name']} creator campaign", client=co['name'])
    db.put('company', co['id'], stored)
    settings.update('company', co['id'], {'sign_myself': False})      # The customer asked for the job to be done, and signatures are mocks.
    facts = orch._company_facts(stored)
    lead = orch._find_lead(stored)
    if lead:
        facts.append(orch.Fact(subject=co['name'], field='lead', value=lead['title'], source=lead['source'], as_of=lead['as_of']).model_dump())
    case.update(facts=facts, tier=stored.get('tier'), tier_terms=config.TIERS.get(stored.get('tier')))
    pushback = [f['text'] for f in r['flags'] if f['severity'] == 'warn' and not f.get('private')]
    _reply(case, 'ack', _requester(case, r), f"Your request for {co['name']}", 'We have started on this. ' + (' '.join(pushback) if pushback else 'Nothing needs your attention right now.'))
    _log(case, 'Replied to the requester (mock outbox)')


def stage_creators(case: dict) -> None:
    r, co = case['read'], db.get('company', case['company_id'])
    ranked = service.company_creators(co['id'], Terms(**r['terms']))
    tier, per = co.get('tier') or 'C', r['budget'] // r['wanted']
    rows, chosen = [], []
    for row in ranked['creators']:
        creator = db.get('creator', row['creator_id'])
        row = {**row, 'brief_checks': campaign.check_creator(co.get('brief'), creator)}
        if len(chosen) < r['wanted']:
            options = packages.options([creator], {'ceiling': per, 'simulated': True}, Terms(**r['terms']), tier)
            if settle(options, FEE_CREATOR, FEE_BRAND) and not packages.within_limits(creator, Terms(**r['terms'])):
                chosen.append(row['creator_id'])
                row['outcome'] = 'chosen'
            else:
                row['outcome'] = 'no_overlap'
        else:
            row['outcome'] = 'not_needed'
        rows.append(row)
    case.update(creators=rows[:SHOWN_LIMIT], chosen=chosen, ranked_total=len(rows), failed_gates=len(ranked['failed_gates']))
    _log(case, f"Ranked {len(rows)} matching creators, chose {len(chosen)}")
    if chosen and len(chosen) < r['wanted']:
        case['shortfall'] = f"Asked for {r['wanted']} creators. Only {len(chosen)} fit on the evidence and budget, so we didn't pad the list."
        _log(case, case['shortfall'])
    if not chosen:
        _reply(case, 'no_match', _requester(case, r), f"No creators yet for {co['name']}", 'No creator we can verify fits this niche and budget, so nothing was started and nothing was charged.')
        raise orch.Stop('stopped', 'No creator fits this niche and budget right now, so nothing was started and nothing was charged.')


def stage_deals(case: dict) -> None:
    r, deals = case['read'], list(case.get('deal_ids') or [])
    terms = Terms(**r['terms'])
    for cid in case['chosen']:
        # Stable per request and creator, so a crash and resume can't start a second deal.
        app_doc = next((a for a in db.all_docs('application') if a.get('request_id') == case['id'] and a['creator_id'] == cid), None)
        if not app_doc:
            app_doc = applications.create(cid, case['company_id'], terms, 'Standard', 'agent')
            app_doc['request_id'] = case['id']
            db.put('application', app_doc['id'], app_doc)
        deal = applications.accept(app_doc['id'], decline_others=False)
        if deal['id'] not in deals:
            deals.append(deal['id'])
            case['deal_ids'] = deals
            _log(case, f"Started a deal with @{app_doc['handle']}")
            db.put('request', case['id'], case)
        orch.run(deal['id'])
    finished = [db.get('deal', d) for d in deals]
    if all(d['state'] in orch.FINAL for d in finished):
        done = [d for d in finished if d['state'] == 'done']
        total = sum(d['settlement']['brand_pays'] for d in done)
        if _reply(case, 'finished', _requester(case, r), f"Finished: {len(done)} of {len(finished)} deals paid", f"{len(done)} contract(s) signed, content approved and INR {total:,} settled. Contracts and invoices are attached."):
            _log(case, f'All deals closed: {len(done)} of {len(finished)} paid')


STAGES = {'read': stage_read, 'company': stage_company, 'creators': stage_creators, 'deals': stage_deals}
ORDER = list(STAGES)


def submit(text: str) -> dict:
    """The same text is one request. Pasting it again returns the first one, and nothing happens twice."""
    clean = re.sub(r'\s+', ' ', text).strip()
    rid = 'req_' + hashlib.sha256(clean.encode('utf8')).hexdigest()[:12]
    existing = db.get('request', rid)
    if existing:
        return existing
    return db.put('request', rid, {'id': rid, 'text': text.strip(), 'stage': 'read', 'received_at': now(), 'log': [{'at': now(), 'text': 'Request received'}]})


def advance(rid: str) -> dict:
    """Safe to call any time and any number of times. Saves after each stage."""
    with _guard:
        lock = _locks.setdefault(rid, threading.Lock())
    if not lock.acquire(blocking=False):
        return db.get('request', rid)
    try:
        case = db.get('request', rid)
        app = settings.get('app')
        pace = app['pace_ms'] / 1000 if app['watchable_pace'] else 0
        while case['stage'] in STAGES and not case.get('paused'):
            stage = case['stage']
            service.cd.set_trace(lambda source, how, seconds, credits: case.setdefault('calls', []).append({'source': source, 'how': how, 'seconds': seconds}))
            try:
                STAGES[stage](case)
            except orch.Pause:
                db.put('request', rid, case)
                return case
            except orch.Stop as s:
                case.update(stage=s.state, reason=s.reason)
                _log(case, s.reason)
                db.put('request', rid, case)
                return case
            except Unavailable as e:
                case['paused'] = {'needs': [], 'question': f'A data source failed ({e}). The request is saved and can resume.', 'retry': True}
                _log(case, f'A data source failed ({e}). Saved, so it can resume.')
                db.put('request', rid, case)
                return case
            finally:
                service.cd.set_trace(None)
            if stage == 'deals':
                db.put('request', rid, case)
                return case
            case['stage'] = ORDER[ORDER.index(stage) + 1]
            db.put('request', rid, case)
            if pace:
                time.sleep(pace)
        return case
    finally:
        lock.release()


def start(rid: str) -> None:
    if service.BACKGROUND:
        threading.Thread(target=advance, args=(rid,), daemon=True).start()
    else:
        advance(rid)


def answer(rid: str, values: dict) -> dict:
    case = db.get('request', rid)
    case['answers'] = {**(case.get('answers') or {}), **{k: v for k, v in values.items() if v not in (None, '')}}
    case['paused'] = None
    case['stage'] = 'read' if case['stage'] == 'read' else case['stage']
    _log(case, 'A person answered')
    db.put('request', rid, case)
    start(rid)
    return public(case)


def public(case: dict) -> dict:
    """The request room's view, with each deal's current state. This is the customer's own record of the job."""
    out = dict(case)
    deals = []
    for did in case.get('deal_ids') or []:
        d = db.get('deal', did)
        creator = db.get('creator', d['creator_ids'][0])
        s = d.get('settlement') or {}
        deals.append({'id': did, 'handle': creator['handle'], 'state': d['state'], 'price': s.get('price'), 'brand_pays': s.get('brand_pays'), 'creator_net': (s.get('creator_net') or {}).get(creator['id']), 'contract_hash': d.get('contract_hash'), 'invoice': d.get('invoice'), 'paused': d.get('paused'), 'tracking_code': d.get('tracking_code'), 'reason': d.get('final_reason')})
    out['deals'] = deals
    out['finished'] = bool(deals) and all(d['state'] in orch.FINAL for d in deals) and any(d['state'] == 'done' for d in deals)
    if case.get('company_id'):
        co = db.get('company', case['company_id'])
        out['company'] = {k: co.get(k) for k in ('id', 'name', 'domain', 'status', 'sender_status', 'reasons', 'facts', 'also_known_as', 'tier')}
    return out
