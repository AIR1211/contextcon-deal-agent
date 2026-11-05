"""Finds real small Instagram creators for testing and records what we could read about them.
Reads public pages only and contacts nobody. Handles go to a git-ignored file, because these are private individuals.
Run: python eval/find_test_creators.py"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DEAL_DB', os.path.join(ROOT, 'deals_ui.db'))
from app.creators import add_engagement, parse_profile, parse_reel  # noqa: E402
from app import niche as niches                                     # noqa: E402
from app.crustdata import Crustdata, Unavailable                    # noqa: E402

OUT = os.path.join(ROOT, 'data', 'test_creators.local.json')
NICHES = ['home baking', 'millet recipes', 'regional home food', 'thrift fashion', 'handloom sarees', 'budget skincare', 'mens grooming', 'plant care',
          'pet parenting', 'womens strength training', 'hindi personal finance', 'college hostel life', 'himalayan budget travel', 'mehendi art', 'journaling stationery', 'diy home decor', 'sustainable living', 'indie book reviews']
MIN_F, MAX_F = 1000, 100000
NOT_HANDLES = {'explore', 'reel', 'reels', 'p', 'popular', 'accounts', 'stories', 'tv', 'instagram', 'about', 'developer', 'legal', 'directory', 'gmail', 'yahoo', 'hotmail', 'outlook'}
cd = Crustdata()
rows, seen = [], set()


def save():
    json.dump({'note': 'Private test list. Public pages only; nobody was contacted. Do not commit.', 'creators': rows}, open(OUT, 'w', encoding='utf8'), indent=1, ensure_ascii=False)


def candidates(res):
    found = []
    for x in res:
        text = ' '.join(str(x.get(k) or '') for k in ('url', 'title', 'snippet', 'author'))
        found += re.findall(r'instagram\.com/([a-zA-Z0-9._]{3,30})', text)
        found += re.findall(r'\(@([a-zA-Z0-9._]{3,30})\)', text)
        found += re.findall(r'(?<![\w.])@([a-zA-Z0-9._]{3,30})', text)
    return [h.rstrip('.').lower() for h in found if h.rstrip('.').lower() not in NOT_HANDLES]


for n in NICHES:
    kept = 0
    pool = []
    for q, src in ((f'{n} instagram creator India', 'web'), (f'site:instagram.com {n} India', 'web'), (f'{n} reel India', 'social')):
        try:
            res, _ = cd.web_search(q, src)
            pool += candidates(res)
        except Unavailable:
            pass
    tried = 0
    for h in dict.fromkeys(pool):
        if h in seen or kept >= 2 or tried >= 6:
            continue
        seen.add(h)
        tried += 1
        try:
            title, body, ts = cd.fetch_page(f'https://www.instagram.com/{h}/')
        except Unavailable:
            continue
        p = parse_profile(title, body, h)
        if not p or not MIN_F <= p['followers'] <= MAX_F or p['posts'] < 10:
            continue
        own = p['own_post_ids']
        ids = own[3:] + own[:3] if len(own) >= 6 else own
        likes, comments, captions = [], [], []
        for pid in ids[:3]:
            try:
                r = parse_reel(cd.fetch_page(f'https://www.instagram.com/reel/{pid}/')[1])
            except Unavailable:
                continue
            if r and r['owner'].lower() == h:
                likes.append(r['likes']); comments.append(r['comments']); captions.append(r['caption'])
        s = add_engagement({'followers': p['followers']}, likes, comments)
        share = niches.share(captions + [p['bio']], n)
        rows.append({'handle': h, 'searched_niche': n, 'followers': p['followers'], 'following': p['following'], 'posts': p['posts'], 'bio': p['bio'][:140], 'reels_read': len(likes), 'median_likes': s['median_likes'], 'engagement_rate': s['engagement_rate'], 'engagement_anomalous': s['engagement_anomalous'], 'niche_share': share, 'as_of': ts, 'needs_human_check': share in (None, 0)})
        kept += 1
        save()
        print(f'{n}: kept {len(rows)} total', flush=True)
    print(f'{n}: pool {len(set(pool))}, tried {tried}, kept {kept}', flush=True)
print('DONE', len(rows), flush=True)
