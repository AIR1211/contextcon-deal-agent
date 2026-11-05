"""Suite 3: likelihood backtest and small-account read test. Run: python eval/run3.py  Writes eval/results3.jsonl.
Lookups are cached in a private local database. Brand names are public; creator handles are not logged."""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ROOT))
os.environ['DEAL_DB'] = os.path.join(ROOT, '..', 'deals_eval.db')

from app.creators import parse_profile, parse_reel       # noqa: E402
from app.crustdata import Crustdata, Unavailable         # noqa: E402
from app import scoring                                  # noqa: E402

if subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', 'eval/cases3.json', 'eval/run3.py'], cwd=ROOT + '/..').returncode:
    sys.exit('Commit cases3.json and run3.py first.')
SHA = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT + '/..', text=True).strip()
C = json.load(open(ROOT + '/cases3.json', encoding='utf8'))
cd = Crustdata()
out = open(ROOT + '/results3.jsonl', 'a', encoding='utf8')
prev = ['genesis']


def log(suite, case, observed, ok=None):
    row = {'ts': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'git': SHA, 'suite': suite, 'case': case, 'observed': observed, 'pass': ok}
    row['row_sha256'] = prev[0] = hashlib.sha256((prev[0] + json.dumps(row, sort_keys=True)).encode()).hexdigest()
    out.write(json.dumps(row, ensure_ascii=False) + '\n')
    out.flush()
    print(suite, case, ok, flush=True)


def backtest():
    B, rows, seen = C['backtest'], [], set()
    for niche, query in B['niches'].items():
        for size in B['sizes']:
            try:
                found, _ = cd.small_brands(query, size=size, limit=B['per_cell'])
            except Unavailable as e:
                log('backtest_sample', f'{niche}/{size}', {'error': str(e)}); continue
            for r in found:
                cid = r.get('crustdata_company_id')
                if not cid or cid in seen:
                    continue
                seen.add(cid)
                try:
                    co, _ = cd.enrich_company(cid)
                    roles = cd.jobs_at(cid)[0]
                except Unavailable as e:
                    log('backtest_lookup', str(cid), {'error': str(e)}); continue
                sig = scoring.brand_signals(co, None, None, '')
                s = scoring.likelihood(sig, niche, use_jobs=False)
                rows.append({'company': (r.get('basic_info') or {}).get('name'), 'niche': niche, 'size': size, 'score': s['score'], 'confidence': s['confidence'], 'has_role': roles > 0})
                log('backtest_row', rows[-1]['company'] or str(cid), rows[-1])
    rows.sort(key=lambda r: -r['score'])
    n = len(rows)
    base = sum(r['has_role'] for r in rows) / n if n else 0
    top = rows[:max(n // 4, 1)]
    bottom = rows[-max(n // 4, 1):]
    precision = sum(r['has_role'] for r in top) / len(top) if n else 0
    low = sum(r['has_role'] for r in bottom) / len(bottom) if n else 0
    # Rank-sum AUC: chance that a brand with a role outranks one without. Ties count half.
    pos, neg = [r['score'] for r in rows if r['has_role']], [r['score'] for r in rows if not r['has_role']]
    auc = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg)) if pos and neg else None
    lift = precision / base if base else None
    log('backtest_summary', 'all', {'brands': n, 'base_rate': round(base, 3), 'top_quarter_precision': round(precision, 3), 'bottom_quarter_rate': round(low, 3), 'lift': lift and round(lift, 2), 'auc': auc and round(auc, 3)}, bool(lift and lift >= 1.5))


def ig_small():
    I, reels = C['ig_small'], []
    tried = nonempty = 0
    for q in I['queries']:
        for _ in range(I['attempts_per_query']):
            tried += 1
            try:
                res, _ = cd.post('/web/search/live', {'query': q, 'sources': ['social']}, ttl_hours=0)
            except Unavailable:
                continue
            found = [x['url'] for x in (res.get('results') or []) if 'instagram.com/reel/' in (x.get('url') or '')]
            nonempty += bool(found)
            reels += found
            if found:
                break
    reels = list(dict.fromkeys(reels))[:I['max_reels']]
    log('ig_discovery', 'social search', {'attempts': tried, 'with_reels': nonempty, 'unique_reels': len(reels)})
    owners, reel_ok = {}, 0
    for u in reels:
        try:
            _, body, _ = cd.fetch_page(u)
        except Unavailable:
            continue
        r = parse_reel(body)
        reel_ok += bool(r)
        if r:
            owners.setdefault(r['owner'], []).append(r['likes'])
    log('ig_reels', 'parsed', {'parsed': reel_ok, 'of': len(reels)}, None)
    tiers = {}
    for h in list(owners)[:I['max_profiles']]:
        try:
            title, body, _ = cd.fetch_page(f'https://www.instagram.com/{h}/')
        except Unavailable:
            tiers.setdefault('fetch_failed', [0, 0])[1] += 1
            continue
        p = parse_profile(title, body, h)
        f = p['followers'] if p else None
        tier = 'unreadable' if f is None else '<1K' if f < 1e3 else '1K-10K' if f < 1e4 else '10K-100K' if f < 1e5 else '>100K'
        t = tiers.setdefault(tier, [0, 0])
        t[0] += bool(p)
        t[1] += 1
    log('ig_profiles', 'by follower tier', {k: {'readable': v[0], 'of': v[1]} for k, v in tiers.items()}, bool(tiers.get('<1K', [0])[0] or tiers.get('1K-10K', [0])[0]))


if __name__ == '__main__':
    start = cd.credits()
    ig_small()
    backtest()
    log('credits', 'used', {'start': start, 'end': cd.credits()})
    print('DONE', flush=True)
