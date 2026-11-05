"""Free-text niches, with no fixed list. Any phrase works: its vocabulary is learned from the companies Crustdata returns
for that phrase (pseudo-relevance feedback). If Crustdata is down, matching falls back to the phrase's own words."""
import re
from collections import Counter

from functools import lru_cache

from . import config, db
from .crustdata import Unavailable

# Grammar and generic business words only. No domain knowledge lives here.
STOP = set("""the and for with from that this your our their are was were has have had not but you they its into over under about more most
some such than then them these those will would can could should may might also very just only each other all any both few own same out off
company companies brand brands business businesses india indian private limited ltd pvt llp inc group services service solutions products product
quality best new leading world global based offer offers offering provide provides providing make makes made help helps people customers customer
team years year online store shop range high across through while where which what when who how one two""".split())
_memo: dict[str, dict] = {}


def stem(w: str) -> str:
    if w.endswith('ies') and len(w) > 4:
        return w[:-3] + 'y'
    if w.endswith('es') and len(w) > 4 and w[-3] in 'sxz':
        return w[:-2]
    if w.endswith('s') and len(w) > 3 and not w.endswith('ss'):
        return w[:-1]
    return w


@lru_cache(maxsize=50000)
def _tokens(text: str) -> tuple:
    return tuple(stem(w) for w in re.findall(r"[a-z][a-z0-9]{2,}", text.lower()) if w not in STOP and stem(w) not in STOP)


def tokens(text: str) -> list[str]:
    return list(_tokens(text or ''))


def norm(niche: str) -> str:
    return ' '.join(tokens(niche)) or (niche or '').strip().lower()


def _client():
    from . import service      # Imported late, so tests can swap the client.
    return service.cd


def profile(niche: str) -> dict:
    """{'own': words in the phrase, 'learned': related words, 'source': where they came from}. Cached per niche."""
    key = norm(niche)
    if not key:
        return {'own': [], 'learned': [], 'source': 'empty'}
    memo = _memo.get((config.DB_PATH, key))
    if memo:
        return memo
    doc = db.get('niche', key)
    if doc:
        _memo[(config.DB_PATH, key)] = doc
        return doc
    own = sorted(set(tokens(niche)))
    learned, source = [], 'words only'
    try:
        rows, _ = _client().search_companies(niche, limit=15)
        df = Counter()
        for r in rows:
            b = r.get('basic_info') or {}
            df.update(set(tokens(' '.join([str(b.get('name') or ''), str(b.get('description') or ''), str((r.get('taxonomy') or {}).get('professional_network_industry') or '')]))))
        # A word must appear across several results to count as part of the niche, not one company's detail.
        learned = [w for w, n in df.most_common(40) if n >= max(2, len(rows) // 5) and w not in own][:10]
        source = 'Crustdata Company Search' if rows else source
    except Unavailable:
        return {'own': own, 'learned': [], 'source': 'words only, search unavailable'}    # Not saved, so it retries.
    _memo[(config.DB_PATH, key)] = db.put('niche', key, {'niche': niche, 'own': own, 'learned': learned, 'source': source})
    return _memo[(config.DB_PATH, key)]


def hits(niche: str, text: str) -> float:
    """Own words count fully and learned words count half, so a stray related word can't outweigh the niche itself."""
    p = profile(niche)
    t = set(tokens(text))
    return sum(w in t for w in p['own']) * 2 + sum(w in t for w in p['learned']) * 0.5


def share(texts: list[str], niche: str) -> float | None:
    texts = [t for t in texts if t]
    if not texts or not norm(niche):
        return None
    return sum(hits(niche, t) > 0 for t in texts) / len(texts)


def related(a: str, b: str) -> bool:
    """Are two free-text niches about the same thing? "home cooking" and "snack food" share learned vocabulary."""
    if not a or not b:
        return False
    if norm(a) == norm(b):
        return True
    pa, pb = profile(a), profile(b)
    sa, sb = set(pa['own'] + pa['learned']), set(pb['own'] + pb['learned'])
    if not sa or not sb:
        return False
    return len(sa & sb) / min(len(sa), len(sb)) >= 0.2
