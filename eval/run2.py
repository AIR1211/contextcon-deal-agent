"""Suite 2. Run: python eval/run2.py [private_seed.json]   The seed holds earlier public handles and never enters the repo."""
import datetime as dt, hashlib, html, json, os, re, subprocess, sys, time, urllib.error as E, urllib.request as U

ROOT = os.path.dirname(os.path.abspath(__file__)); RAW = ROOT + '/raw2'; os.makedirs(RAW, exist_ok=True)
if subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', 'eval/cases2.json', 'eval/run2.py'], cwd=ROOT + '/..').returncode: sys.exit('Commit cases2.json and run2.py first.')
SHA = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT + '/..', text=True).strip()
C = json.load(open(ROOT + '/cases2.json', encoding='utf8'))
KEY = open(ROOT + '/../.env', encoding='utf-8-sig').read().strip().split('=', 1)[1].strip().strip('"')
GAP = {'/web/search/live': 6.2, '/web/enrich/live': 6.2}
st = {'prev': 'genesis', 'n': 0, 'cr': 0.0}; out = open(ROOT + '/results2.jsonl', 'w', encoding='utf8')


def call(path, body):
    q = U.Request('https://api.crustdata.com' + path, json.dumps(body).encode(), {'authorization': 'Bearer ' + KEY, 'x-api-version': '2025-11-01', 'content-type': 'application/json', 'user-agent': 'contextcon-eval'})
    t = time.time()
    try:
        with U.urlopen(q, timeout=90) as r: code, txt, h = r.status, r.read(), r.headers
    except E.HTTPError as e: code, txt, h = e.code, e.read(), e.headers
    except Exception as e: code, txt, h = 0, str(e).encode(), {}
    took = time.time() - t; cr = float(h.get('x-credits-used') or 0); st['cr'] += cr
    try: d = json.loads(txt)
    except Exception: d = None
    time.sleep(max(GAP.get(path, 2.1) - took, 0))
    return {'code': code, 'data': d, 'credits': cr, 's': round(took, 1), 'sha': hashlib.sha256(txt).hexdigest(), 'txt': txt}


def log(suite, case, expected, observed, ok, r=None):
    st['n'] += 1
    row = {'n': st['n'], 'ts': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'git': SHA, 'suite': suite, 'case': case, 'expected': expected, 'observed': observed, 'pass': ok, 'http': r and r['code'], 'credits': r and r['credits'], 'seconds': r and r['s'], 'response_sha256': r and r['sha']}
    row['row_sha256'] = st['prev'] = hashlib.sha256((st['prev'] + json.dumps(row, sort_keys=True)).encode()).hexdigest()
    out.write(json.dumps(row, ensure_ascii=False) + '\n'); out.flush()
    if r: open(f"{RAW}/{st['n']:04d}.json", 'wb').write(r['txt'])
    print(st['n'], suite, case, ok, round(st['cr'], 2), flush=True)


def room(): return st['cr'] < C['cap_credits']


# Brand discovery: do known brands appear, and is the country filter respected?
for c in C['company_search']:
    r = call('/company/search', {'search': {'query': c['query'], 'mode': 'hybrid'}, 'filters': {'field': 'locations.country', 'type': '=', 'value': 'India'}, 'fields': ['basic_info.name', 'basic_info.primary_domain', 'basic_info.employee_count_range'], 'limit': C['company_search_limit']})
    L = (r['data'] or {}).get('companies', []) if r['code'] == 200 else []
    names = [(x.get('basic_info') or {}).get('name', '').lower() for x in L]
    hits = [k for k in c['known'] if any(k in n for n in names)]
    log('company_search', c['query'], 'at least 1 known brand in results', {'returned': len(L), 'known_hit': hits, 'known_total': len(c['known']), 'with_domain': sum(bool((x.get('basic_info') or {}).get('primary_domain')) for x in L)}, bool(hits), r)

# Contact discovery: are returned people plausibly the right contact?
for d in C['contact_brands']:
    q, m = call('/company/identify', {'domains': [d]}), None
    m = q['data'][0]['matches'] if q['code'] == 200 and q['data'] else []
    if not m: log('contacts', d, 'company resolves', None, False, q); continue
    r = call('/person/search', {'filters': {'op': 'and', 'conditions': [{'field': 'experience.employment_details.current.company_id', 'type': '=', 'value': m[0]['company_data']['crustdata_company_id']}, {'field': 'basic_profile.headline', 'type': '[.]', 'value': 'influencer'}]}, 'fields': ['basic_profile.current_title'], 'limit': 5})
    T = [(p.get('basic_profile') or {}).get('current_title') or '' for p in ((r['data'] or {}).get('profiles', []) if r['code'] == 200 else [])]
    rel = sum(any(w in t.lower() for w in C['contact_title_words']) for t in T)
    log('contacts', d, 'most titles relevant', {'returned': len(T), 'relevant_titles': rel, 'total_matches': (r['data'] or {}).get('total_count')}, bool(T) and rel * 2 > len(T), r)


# Instagram: anonymised in the public log.
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


seed = json.load(open(sys.argv[1], encoding='utf8')) if len(sys.argv) > 1 else {'reels': [], 'handles': []}
reels, handles, attempts, nonempty = list(seed['reels']), list(seed['handles']), 0, 0
for q in C['ig_discovery_queries']:
    for _ in range(C['ig_discovery_attempts']):
        r = call('/web/search/live', {'query': q, 'sources': ['social']}); attempts += 1
        R = (r['data'] or {}).get('results', []) if r['code'] == 200 else []
        nonempty += bool(R)
        reels += [x['url'] for x in R if 'instagram.com/reel/' in (x.get('url') or '')]
        if R: break
reels = list(dict.fromkeys(reels))[:C['ig_max_reels']]
log('ig_discovery', 'retry until results', 'measured', {'attempts': attempts, 'nonempty': nonempty, 'reels': len(reels)}, None)
for i, u in enumerate(reels, 1):
    if not room(): break
    r, s, t, b = page(u); m = re.search(r'([\d.,]+[KMB]?) likes?, ([\d.,]+[KMB]?) comments? - ([\w.]+) on ([A-Za-z]+ \d+, \d{4})', og(b))
    if m: handles.append(m[3])
    log('ig_reel', f'reel_{i}', 'likes, comments, owner, date', {'parsed': bool(m), 'api_success': s, 'views_present': bool(re.search(r'"(play_count|video_view_count|view_count)":\d+', b))}, bool(m), r)
for i, h in enumerate(list(dict.fromkeys(handles))[:C['ig_max_profiles']], 1):
    if not room(): break
    r, s, t, b = page(f'https://www.instagram.com/{h}/'); m = re.search(r'([\d.,]+[KMB]?) Followers?, ([\d.,]+[KMB]?) Following, ([\d.,]+[KMB]?) Posts?', og(b))
    f = num(m[1]) if m else None; tier = None if f is None else '<10K' if f < 1e4 else '10K-100K' if f < 1e5 else '>100K'
    log('ig_profile', f'creator_{i}', 'followers, following, posts, right owner', {'tier': tier, 'owner_matches': h.lower() in t.lower(), 'api_success': s}, bool(m) and h.lower() in t.lower(), r)
out.close(); print('DONE', round(st['cr'], 2), flush=True)
