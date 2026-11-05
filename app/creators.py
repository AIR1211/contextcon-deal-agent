"""Reads public Instagram pages through Web Fetch. Fields must parse, because API success can't be trusted."""
import html
import re
import statistics

from .crustdata import Crustdata, Unavailable

def _og(body: str) -> str:
    m = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', body) or re.search(r'<meta[^>]+content="([^"]*)"[^>]+property="og:description"', body)
    return html.unescape(m[1]) if m else ''


def _num(s: str) -> float:
    s = s.replace(',', '')
    m = re.match(r'([\d.]+)\s*([KMB]?)', s)
    return float(m[1]) * {'': 1, 'K': 1e3, 'M': 1e6, 'B': 1e9}[m[2]]


def parse_profile(title: str, body: str, handle: str) -> dict | None:
    d = _og(body)
    m = re.search(r'([\d.,]+[KMB]?) Followers?, ([\d.,]+[KMB]?) Following, ([\d.,]+[KMB]?) Posts?', d)
    if not m or handle.lower() not in title.lower():
        return None
    bio = d.split(' - ', 1)[-1] if ' - ' in d else ''
    if bio.startswith('See Instagram photos and videos'):      # Instagram's default text, not something the creator wrote.
        bio = ''
    links = list(dict.fromkeys(re.findall(r'/(?:p|reel)/([\w-]{8,})/', body)))
    # Pages also link other people's posts that tag this creator. Links under the handle's own path are theirs.
    own = list(dict.fromkeys(re.findall(rf'/{re.escape(handle)}/(?:p|reel)/([\w-]{{8,}})/', body, re.I)))
    return {'followers': _num(m[1]), 'following': _num(m[2]), 'posts': _num(m[3]), 'bio': bio, 'post_ids': links[:12], 'own_post_ids': own}


def parse_reel(body: str) -> dict | None:
    d = _og(body)
    m = re.search(r'([\d.,]+[KMB]?) likes?, ([\d.,]+[KMB]?) comments? - ([\w.]+) on ([A-Za-z]+ \d+, \d{4})', d)
    if not m:
        return None
    caption = d.split(':', 1)[1].strip().strip('"') if ':' in d else ''
    return {'likes': _num(m[1]), 'comments': _num(m[2]), 'owner': m[3], 'date': m[4], 'caption': caption}


def read_profile(cd: Crustdata, handle: str, fresh=False) -> dict | None:
    url = f'https://www.instagram.com/{handle.strip().lstrip("@")}/'
    title, body, ts = cd.fetch_page(url, fresh=fresh)
    p = parse_profile(title, body, handle.strip().lstrip('@'))
    return p and {**p, 'as_of': ts, 'url': url}


ANOMALOUS_ENGAGEMENT = 0.5   # Above 50% of followers, the sampled posts are probably not typical.


def read_stats(cd: Crustdata, handle: str, max_reels=8) -> dict:
    """About 1 + max_reels credits. Only reels that really belong to this handle count.
    A profile's first posts are often pinned virals, so they are skipped when enough other posts exist."""
    handle = handle.strip().lstrip('@')
    p = read_profile(cd, handle)
    if not p:
        raise Unavailable('profile fields could not be read')
    reels = []
    own = p['own_post_ids'] or p['post_ids']
    ids = own[3:] + own[:3] if len(own) >= 6 else own      # Likely-pinned posts are only read last.
    for pid in ids[:max_reels]:
        if len(reels) >= max_reels:
            break
        try:
            _, body, _ = cd.fetch_page(f'https://www.instagram.com/reel/{pid}/')
        except Unavailable:
            continue
        r = parse_reel(body)
        if r and r['owner'].lower() == handle.lower():
            reels.append(r)
    stats = {'followers': p['followers'], 'following': p['following'], 'posts': p['posts'], 'bio': p['bio'], 'as_of': p['as_of'], 'url': p['url'], 'reels_read': len(reels), 'captions': [r['caption'] for r in reels], 'source': 'Crustdata Web Fetch, public Instagram page', 'strength': 0.7}
    return add_engagement(stats, [r['likes'] for r in reels], [r['comments'] for r in reels])


def add_engagement(stats: dict, likes: list, comments: list) -> dict:
    """Median, so one viral post doesn't inflate the score."""
    stats['median_likes'] = statistics.median(likes) if likes else None
    stats['median_comments'] = statistics.median(comments) if comments else None
    f = stats.get('followers')
    stats['engagement_rate'] = round((stats['median_likes'] + (stats['median_comments'] or 0)) / f, 4) if f and likes else None
    stats['engagement_anomalous'] = bool(stats['engagement_rate'] and stats['engagement_rate'] > ANOMALOUS_ENGAGEMENT)
    return stats
