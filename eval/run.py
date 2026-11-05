"""Crustdata test suite. Run: python eval/run.py   Check the log: python eval/run.py --verify
Writes eval/results.jsonl (hash-chained, public) and eval/raw/ (full responses, private, git-ignored)."""
import concurrent.futures as cf, datetime as dt, hashlib, html, json, os, re, subprocess, sys, time, urllib.error as E, urllib.request as U

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT, RAW = ROOT + '/results.jsonl', ROOT + '/raw'
API = 'https://api.crustdata.com'
GAP = {'/company/enrich': 4.2, '/person/enrich': 4.2, '/web/search/live': 6.2, '/web/enrich/live': 6.2, '/person/search': 2.1, '/job/search': 2.1, '/social_post/search': 2.1, '/company/identify': 2.1}
CUR, PAST = 'experience.employment_details.current.company_id', 'experience.employment_details.past.company_id'


def row_hash(prev, row):
    return hashlib.sha256((prev + json.dumps(row, sort_keys=True)).encode()).hexdigest()


def verify():
    prev = 'genesis'
    for n, line in enumerate(open(OUT, encoding='utf8'), 1):
        r = json.loads(line); h = r.pop('row_sha256')
        if row_hash(prev, r) != h: sys.exit(f'TAMPERED at row {n}')
        prev = h
    print(f'OK: {n} rows, chain intact, last hash {prev}')


if '--verify' in sys.argv: verify(); sys.exit()

if subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', 'eval/cases.json'], cwd=ROOT + '/..').returncode:
    sys.exit('cases.json has uncommitted changes. Commit and push it first.')
SHA = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT + '/..', text=True).strip()
C = json.load(open(ROOT + '/cases.json', encoding='utf8'))
KEY = open(ROOT + '/../.env', encoding='utf-8-sig').read().strip().split('=', 1)[1].strip().strip('"')
os.makedirs(RAW, exist_ok=True)
state = {'prev': 'genesis', 'n': 0, 'credits': 0.0}
outf = open(OUT, 'w', encoding='utf8')
NOW = dt.datetime.now(dt.timezone.utc)


def call(path, body=None, key=KEY, wait=True):
    req = U.Request(API + path, data=None if body is None else json.dumps(body).encode(), method='GET' if body is None else 'POST',
                    headers={'authorization': 'Bearer ' + key, 'x-api-version': '2025-11-01', 'content-type': 'application/json', 'user-agent': 'contextcon-eval'})
    t = time.time()
    try:
        with U.urlopen(req, timeout=90) as r: code, txt, h = r.status, r.read(), r.headers
    except E.HTTPError as e: code, txt, h = e.code, e.read(), e.headers
    except Exception as e: code, txt, h = 0, str(e).encode(), {}
    took = time.time() - t
    try: cr = float(h.get('x-credits-used') or 0)
    except Exception: cr = 0.0
    state['credits'] += cr
    try: data = json.loads(txt)
    except Exception: data = None
    if wait: time.sleep(max(GAP.get(path, 1) - took, 0))
    return {'code': code, 'data': data, 'credits': cr, 's': round(took, 1), 'sha': hashlib.sha256(txt).hexdigest(), 'txt': txt, 'headers': h}


def log(suite, case, expected, observed, ok, r=None):
    """ok: True, False, or None for measurement-only rows."""
    state['n'] += 1
    row = {'n': state['n'], 'ts': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'git': SHA, 'suite': suite, 'case': case, 'expected': expected, 'observed': observed, 'pass': ok,
           'http': r and r['code'], 'credits': r and r['credits'], 'seconds': r and r['s'], 'response_sha256': r and r['sha']}
    state['prev'] = row['row_sha256'] = row_hash(state['prev'], row)
    outf.write(json.dumps(row, ensure_ascii=False) + '\n'); outf.flush()
    if r: open(f"{RAW}/{state['n']:04d}.json", 'wb').write(r['txt'])
    print(state['n'], suite, case, ok, round(state['credits'], 2), flush=True)


def room(): return state['credits'] < C['cap_credits']
def host(d): return (d or '').lower().replace('www.', '')


def identify(**kw):
    r = call('/company/identify', kw)
    m = r['data'][0]['matches'] if r['code'] == 200 and r['data'] else []
    return r, m


IDS = {}
def cid(domain):
    if domain not in IDS:
        _, m = identify(domains=[domain]); IDS[domain] = m[0]['company_data']['crustdata_company_id'] if m else None
    return IDS[domain]


def people(conds, limit=3, fields=('basic_profile.name', 'basic_profile.current_title', 'social_handles.professional_network_identifier.profile_url')):
    r = call('/person/search', {'filters': {'op': 'and', 'conditions': conds}, 'fields': list(fields), 'limit': limit})
    return r, (r['data'] or {}).get('profiles', []) if r['code'] == 200 else []


def name_at(name, company, field=CUR):
    return people([{'field': field, 'type': '=', 'value': company}, {'field': 'basic_profile.name', 'type': '=', 'value': name}])


# 1. Is the company real?
for d in C['identify_real']:
    r, m = identify(domains=[d]); got = host(m[0]['company_data']['basic_info'].get('primary_domain')) if m else None
    if m: IDS[d] = m[0]['company_data']['crustdata_company_id']
    log('identify_real', d, 'returns this domain', got, got == d, r)
for d in C['identify_fake']:
    r, m = identify(domains=[d]); log('identify_fake', d, 'no match', len(m), not m, r)
for c in C['identify_format']:
    r, m = identify(domains=[c['input']]); same = bool(m) and m[0]['company_data']['crustdata_company_id'] == cid(c['same_as'])
    log('identify_format', c['input'], 'same company as ' + c['same_as'], m[0]['company_data']['basic_info']['name'] if m else None, same, r)
for c in C['identify_name']:
    r, m = identify(names=[c['name']]); top = host(m[0]['company_data']['basic_info'].get('primary_domain')) if m else None
    log('identify_parent' if c.get('kind') == 'parent' else 'identify_name', c['name'], 'top result is ' + c['domain'], top, top == c['domain'], r)
a = [identify(names=['Plum Goodness'])[1] for _ in range(3)]; ids = [[x['company_data']['crustdata_company_id'] for x in m] for m in a]
log('determinism', 'identify x3', 'same ranked IDs', 'same' if ids[0] == ids[1] == ids[2] else 'differs', ids[0] == ids[1] == ids[2])

# 2. Are company facts right today?
G = ['basic_info', 'headcount', 'funding', 'revenue', 'seo', 'web_traffic', 'people', 'news', 'hiring', 'taxonomy']
for c in C['enrich']:
    if not room(): break
    r = call('/company/enrich', {'crustdata_company_ids': [cid(c['domain'])], 'fields': G})
    x = r['data'][0]['matches'][0]['company_data'] if r['code'] == 200 and r['data'] and r['data'][0].get('matches') else {}
    b, h = x.get('basic_info') or {}, x.get('headcount') or {}
    log('enrich_founded', c['domain'], c['founded'], b.get('year_founded'), b.get('year_founded') == c['founded'], r)
    if c.get('name_must_not_contain'): log('enrich_record', c['domain'], 'name without ' + c['name_must_not_contain'], b.get('name'), c['name_must_not_contain'] not in (b.get('name') or ''))
    ts = h.get('timeseries') or []
    age = (NOW.date() - dt.date.fromisoformat(ts[-1]['date'][:10])).days if ts else None
    log('enrich_fresh', c['domain'], f"<= {C['freshness_max_age_days']} days", age, age is not None and age <= C['freshness_max_age_days'])
    low = (((x.get('revenue') or {}).get('estimated') or {}).get('lower_bound_usd')); per = round(low / h['total']) if low and h.get('total') else None
    log('enrich_revenue_sane', c['domain'], f"<= ${C['revenue_per_employee_max_usd']} per employee", per, per is not None and per <= C['revenue_per_employee_max_usd'])
    log('enrich_coverage', c['domain'], 'measured', {g: bool(x.get(g)) for g in G}, None)
    seo = x.get('seo') or {}
    log('enrich_ads_budget', c['domain'], 'measured', {k: v for k, v in seo.items() if 'ad' in k.lower() or 'budget' in k.lower()} if isinstance(seo, dict) else None, None)

# 3. Is the sender who they say they are?
found = {}
for c in C['person_current']:
    if not room(): break
    r, p = name_at(c['name'], cid(c['domain'])); found[c['name']] = p
    log('person_current', f"{c['name']} @ {c['domain']}", 'found', len(p), bool(p), r)
for c in C['person_wrong_company']:
    r, p = name_at(c['name'], cid(c['domain'])); log('person_wrong_company', f"{c['name']} @ {c['domain']}", 'not found', len(p), not p, r)
for c in C['person_left']:
    co = cid(c['domain'])
    r, p = name_at(c['name'], co); log('person_left_current', f"{c['name']} @ {c['domain']}", 'not current', len(p), not p, r)
    r, q = name_at(c['name'], co, PAST); log('person_left_past', f"{c['name']} @ {c['domain']}", 'found as past', len(q), bool(q), r); found.setdefault(c['name'], q)
for c in C['person_messy']:
    r, p = name_at(c['variant'], cid(c['domain'])); log('person_messy', c['variant'], 'found' if c['expect_found'] else 'not found', len(p), bool(p) == c['expect_found'], r)

# 4. Does career history back the claim?
for c in C['person_enrich']:
    if not room(): break
    p = found.get(c['name']) or []
    u = ((p[0].get('social_handles') or {}).get('professional_network_identifier') or {}).get('profile_url') if p else None
    if not u: log('person_enrich', c['name'], 'history lists ' + c['employer'], 'no profile URL from search', False); continue
    r = call('/person/enrich', {'professional_network_profile_urls': [u], 'fields': ['basic_profile', 'experience', 'education', 'skills']})
    m = r['data'][0].get('matches') if r['code'] == 200 and isinstance(r['data'], list) and r['data'] else []
    x = (m[0].get('person_data') or m[0]) if m else {}
    e = (x.get('experience') or {}).get('employment_details') or {}
    nm = lambda L: [str(i.get('company_name') or i.get('name')) for i in (L or [])]
    cur, past = nm(e.get('current')), nm(e.get('past')); want = c['employer'].lower()
    inn = lambda L: any(want in s.lower() for s in L)
    ok = inn(past) and not inn(cur) if c.get('past') else inn(cur)
    log('person_enrich', c['name'], ('past: ' if c.get('past') else 'current: ') + c['employer'], {'current': cur[:3], 'past_count': len(past), 'updated_at': x.get('updated_at') or m and m[0].get('updated_at')}, ok, r)

# 5. Is the brand spending on creators?
for d in C['jobs_brand']:
    r = call('/job/search', {'filters': {'op': 'and', 'conditions': [{'field': 'company.basic_info.company_id', 'type': '=', 'value': cid(d)}, {'field': 'job_details.title', 'type': '[.]', 'value': 'influencer'}]}, 'fields': ['job_details.title'], 'limit': 3})
    log('jobs_brand', d, 'measured', {'total': (r['data'] or {}).get('total_count'), 'titles': [j['job_details'].get('title') for j in (r['data'] or {}).get('job_listings', [])]}, None, r)
for t in C['jobs_india_terms']:
    r = call('/job/search', {'filters': {'op': 'and', 'conditions': [{'field': 'job_details.title', 'type': '[.]', 'value': t}, {'field': 'location.country', 'type': '=', 'value': 'India'}]}, 'fields': ['job_details.title', 'location', 'company.basic_info.name'], 'limit': 10})
    J = (r['data'] or {}).get('job_listings', []) if r['code'] == 200 else []
    india = sum('india' in json.dumps(j.get('location') or {}).lower() for j in J)
    log('jobs_india', t, 'all located in India', {'returned': len(J), 'india': india, 'total': (r['data'] or {}).get('total_count')}, bool(J) and india == len(J), r)
for c in C['posts']:
    f = {'field': 'mentions.company_id', 'type': '=', 'value': cid(c['domain'])} if c.get('domain') else {'op': 'and', 'conditions': [{'field': 'text', 'type': '[.]', 'value': c['text']}, {'field': 'actor.location.country', 'type': '=', 'value': 'India'}]}
    r = call('/social_post/search', {'filters': f, 'sorts': [{'field': 'date_posted', 'order': 'desc'}], 'fields': ['share_url', 'date_posted'], 'limit': 5})
    P = (r['data'] or {}).get('posts', []) if r['code'] == 200 else []
    newest = P[0]['date_posted'][:10] if P else None; age = (NOW.date() - dt.date.fromisoformat(newest)).days if newest else None
    log('posts', c['label'], f"<= {C['freshness_max_age_days']} days old", {'n': len(P), 'newest_age_days': age, 'hosts': sorted({re.sub(r'https?://(www\.)?([^/]+).*', r'\2', x.get('share_url') or '') for x in P})}, age is not None and age <= C['freshness_max_age_days'], r)

# 6. Can web search confirm a fact, and is social search dependable?
for c in C['web_truth']:
    r = call('/web/search/live', {'query': c['query'], 'sources': [c['source']]})
    txt = json.dumps((r['data'] or {}).get('results', []))
    log('web_truth', c['query'], 'mentions ' + c['must_mention'], c['must_mention'].lower() in txt.lower(), c['must_mention'].lower() in txt.lower(), r)
for q in C['web_social_repeat']:
    counts = []
    for _ in range(C['web_social_runs']):
        r = call('/web/search/live', {'query': q, 'sources': ['social']}); counts.append(len((r['data'] or {}).get('results', [])))
    log('web_social_repeat', q, 'results on every run', counts, all(counts), r)


# 7. Can public Instagram pages be read? Accounts are found by a fixed procedure and anonymised in the public log.
def og(b):
    m = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', b) or re.search(r'<meta[^>]+content="([^"]*)"[^>]+property="og:description"', b)
    return html.unescape(m[1]) if m else ''


def num(s):
    s = s.replace(',', ''); m = re.match(r'([\d.]+)\s*([KMB]?)', s)
    return float(m[1]) * {'': 1, 'K': 1e3, 'M': 1e6, 'B': 1e9}[m[2]]


def page(u):
    r = call('/web/enrich/live', {'urls': [u]}); d = r['data']
    L = d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), []) if isinstance(d, dict) else []
    x = L[0] if L else {}
    return r, x.get('success'), x.get('title') or '', x.get('content') or ''


reels = []
for q in C['ig_discovery_queries']:
    r = call('/web/search/live', {'query': q, 'sources': ['social']})
    reels += re.findall(r'https://www\.instagram\.com/reel/[\w-]+/', json.dumps((r['data'] or {}).get('results', [])).replace('\\/', '/'))
reels = list(dict.fromkeys(reels))[:C['ig_max_reels']]
log('ig_discovery', 'fixed queries', 'measured', {'reels_found': len(reels)}, None)
owners, likes = [], {}
for i, u in enumerate(reels, 1):
    if not room(): break
    r, s, t, b = page(u); m = re.search(r'([\d.,]+[KMB]?) likes?, ([\d.,]+[KMB]?) comments? - ([\w.]+) on ([A-Za-z]+ \d+, \d{4})', og(b))
    if m: owners.append(m[3]); likes.setdefault(m[3], []).append(num(m[1]))
    log('ig_reel', f'reel_{i}', 'likes, comments, owner, date', {'parsed': bool(m), 'api_success': s, 'views_present': bool(re.search(r'"(play_count|video_view_count|view_count)":\d+', b))}, bool(m), r)
for i, h in enumerate(dict.fromkeys(owners), 1):
    if not room(): break
    r, s, t, b = page(f'https://www.instagram.com/{h}/'); d = og(b); m = re.search(r'([\d.,]+[KMB]?) Followers?, ([\d.,]+[KMB]?) Following, ([\d.,]+[KMB]?) Posts?', d)
    f = num(m[1]) if m else None
    tier = None if f is None else '<10K' if f < 1e4 else '10K-100K' if f < 1e5 else '>100K'
    log('ig_profile', f'creator_{i}', 'followers, following, posts, right owner', {'tier': tier, 'owner_matches': h.lower() in t.lower(), 'api_success': s, 'grid_posts': len(set(re.findall(r'/(?:p|reel)/([\w-]{8,})/', b)))}, bool(m) and h.lower() in t.lower(), r)
for h in C['ig_fake']:
    r, s, t, b = page(f'https://www.instagram.com/{h}/'); parsed = bool(re.search(r'Followers?,', og(b)))
    log('ig_fake', h, 'no stats returned', {'api_success': s, 'parsed': parsed}, not parsed, r)

# 8. Do failures behave predictably?
for lab, path, body, key, want in [('unknown filter field', '/company/search', {'filters': {'field': 'not.a.field', 'type': '=', 'value': 'x'}, 'limit': 1}, KEY, 400),
                                   ('empty identify body', '/company/identify', {}, KEY, 400), ('invalid key', '/company/identify', {'domains': ['nike.com']}, 'invalid', 401),
                                   ('disabled endpoint', '/person/identify', {'emails': ['nobody@unknown-domain.com']}, KEY, 403), ('denied field', '/person/enrich', {'professional_network_profile_urls': ['https://www.linkedin.com/in/x'], 'fields': ['assessment']}, KEY, 403)]:
    r = call(path, body, key); log('errors', lab, want, r['code'], r['code'] == want, r)
r = call('/company/enrich', {'domains': ['zzqx-brand-deals.io']}); log('errors', 'enrich unknown domain', 'no charge, no invented data', {'credits': r['credits'], 'matches': sum(len(i.get('matches') or []) for i in r['data']) if isinstance(r['data'], list) else None}, r['credits'] == 0, r)
r = call('/watch/company'); log('access', 'watcher list', 'measured', r['code'], None, r)
r = call('/agent/query', {'query': 'Who leads marketing at boAt Lifestyle?'}); log('access', 'agent query', 'measured', {'code': r['code'], 'credits': r['credits']}, None, r)
r = call('/company/search/autocomplete', {'field': 'basic_info.industries', 'query': 'cosmetic', 'limit': 3}); log('access', 'autocomplete', 'returns values', r['code'], r['code'] == 200, r)
with cf.ThreadPoolExecutor(8) as ex: burst = list(ex.map(lambda _: call('/company/identify', {'domains': ['nike.com']}, wait=False), range(45)))
n429 = [b for b in burst if b['code'] == 429]
reset = n429[0]['headers'].get('x-ratelimit-reset') if n429 else None
log('rate_limit', '45 quick free calls', 'over-limit calls get 429 with reset header', {'429s': len(n429), 'other_errors': sum(b['code'] not in (200, 429) for b in burst), 'reset_header': bool(reset)}, bool(n429) and bool(reset))
time.sleep(62)
r = call('/company/identify', {'domains': ['nike.com']}); log('rate_limit', 'retry after waiting', 200, r['code'], r['code'] == 200, r)
outf.close(); print('DONE', round(state['credits'], 2), flush=True)
