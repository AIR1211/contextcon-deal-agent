"""Scores the offer review on the labelled set, using live Crustdata identity checks. Run: python eval/run_labelled.py"""
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ROOT))
os.environ['DEAL_DB'] = os.path.join(ROOT, '..', 'deals_eval2.db')
from app.crustdata import Crustdata      # noqa: E402
from app.offers import review            # noqa: E402

if subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', 'eval/labelled_offers.json'], cwd=ROOT + '/..').returncode:
    sys.exit('Commit labelled_offers.json first.')
SHA = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT + '/..', text=True).strip()
cases = json.load(open(ROOT + '/labelled_offers.json', encoding='utf8'))['cases']
cd = Crustdata()
prev, ok = 'genesis', 0
conf = Counter()
with open(ROOT + '/labelled_results.jsonl', 'w', encoding='utf8') as out:
    for c in cases:
        r = review(c['text'], cd=cd)
        got = 'fair' if r['verdict'] in ('fair', 'clarify') else r['verdict']
        hit = got == c['label']
        ok += hit
        conf[(c['label'], got)] += 1
        row = {'git': SHA, 'id': c['id'], 'label': c['label'], 'got': r['verdict'], 'pass': hit, 'rules': [f['rule'] for f in r['findings']], 'brand_status': (r['verification'] or {}).get('brand_status')}
        row['row_sha256'] = prev = hashlib.sha256((prev + json.dumps(row, sort_keys=True)).encode()).hexdigest()
        out.write(json.dumps(row) + '\n')
        print(c['id'], c['label'], '=>', r['verdict'], 'OK' if hit else 'MISS', row['rules'])
print(f'{ok}/{len(cases)}', dict(conf))
