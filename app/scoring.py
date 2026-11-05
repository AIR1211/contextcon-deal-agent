"""Likelihood, fit and confidence. Fit says how good a match looks; confidence says how much evidence backs that.
Weights are the team's judgement, not measurements. Unknown factors score 0.5 and lower confidence instead of the score."""
from datetime import date

from . import config
from . import niche as niches
from . import settings
from .creators import sponsored_posts

BRAND_WEIGHTS = {'niche': 25, 'influencer_roles': 25, 'influencer_staff': 15, 'funding': 15, 'growth': 10, 'news': 10}
FIT_WEIGHTS = config.FIT_PROFILES['balanced']
MIN_ENGAGEMENT = 0.001       # Assumption: below 0.1% suggests an inactive or inflated audience.


SMALL_SIZES = {'myself only', '2-10', '11-50'}


def _presence(n, base, step, small, none_small, none_large):
    """Small brands rarely advertise influencer roles, so having none counts against them less."""
    return min(base + step * n, 1.0) if n else (none_small if small else none_large)


def _combine(weights: dict, factors: dict) -> tuple[int, int]:
    """factors: name -> (score 0..1 or None, evidence strength 0..1)."""
    score = sum(w * (0.5 if factors[k][0] is None else factors[k][0]) for k, w in weights.items())
    conf = sum(w * (factors[k][1] if factors[k][0] is not None else 0) for k, w in weights.items())
    return round(score), round(conf)


def brand_signals(company: dict | None, roles: int | None, staff: int | None, niche_text: str = '') -> dict:
    """Turns Company Enrich data into signals. None means no evidence."""
    company = company or {}
    today = date.today()
    fund = company.get('funding') or {}
    last = str(fund.get('last_fundraise_date') or '')[:10]
    months = ((today - date.fromisoformat(last)).days / 30) if len(last) == 10 else None
    ts = (company.get('headcount') or {}).get('timeseries') or []
    growth = None
    if len(ts) >= 13 and ts[-13].get('employee_count'):
        growth = ts[-1]['employee_count'] / ts[-13]['employee_count'] - 1
    news = company.get('news') or []
    recent = sum(str(n.get('article_publish_date') or '')[:7] >= f'{today.year}-{max(today.month - 3, 1):02d}' for n in news) if news else None
    b = company.get('basic_info') or {}
    tax = company.get('taxonomy') or {}
    text = ' '.join(str(x) for x in [niche_text, b.get('name'), b.get('description'), b.get('industries'), tax])
    return {'months_since_funding': months, 'headcount_growth': growth, 'recent_news': recent, 'influencer_roles': roles, 'influencer_staff': staff, 'text': text.lower(), 'size_range': b.get('employee_count_range')}


def likelihood(sig: dict, niche: str, use_jobs: bool = True, open_niche: bool = False) -> dict:
    """How likely a brand is to buy creator marketing in this niche. use_jobs=False is for the backtest."""
    hits = niches.hits(niche, sig.get('text', ''))
    m = sig.get('months_since_funding')
    g = sig.get('headcount_growth')
    roles, staff, news = sig.get('influencer_roles'), sig.get('influencer_staff'), sig.get('recent_news')
    small = sig.get('size_range') in SMALL_SIZES
    f = {
        'niche': (min(hits / 2, 1.0), 0.7),
        'influencer_roles': (_presence(roles, 0.6, 0.15, small, 0.35, 0.2), 1.0 if roles else 0.5) if use_jobs and roles is not None else (None, 0),
        'influencer_staff': (_presence(staff, 0.5, 0.2, small, 0.4, 0.25), 0.8 if staff else 0.4) if staff is not None else (None, 0),
        'funding': (1.0 if m < 12 else 0.7 if m < 24 else 0.3, 0.9) if m is not None else (None, 0),
        'growth': (max(min(0.5 + g * 2, 1.0), 0.0), 0.8) if g is not None else (None, 0),
        'news': (min(news / 5, 1.0), 0.6) if news is not None else (None, 0),
    }
    score, conf = _combine(BRAND_WEIGHTS, f)
    reasons = []
    if hits >= 2: reasons.append(f'Its own description mentions {niche}.')
    elif hits >= 1: reasons.append(f'Its description uses words common in {niche}.')
    if roles: reasons.append(f'{roles} open influencer marketing role(s).')
    if staff: reasons.append(f'{staff} staff with influencer marketing in their profile.')
    if m is not None and m < 24: reasons.append(f'Raised funding {int(m)} months ago.')
    if g is not None and g > 0.05: reasons.append(f'Headcount grew {round(g * 100)}% in about a year.')
    if hits < 1 and open_niche: reasons.append(f'Hires for creator marketing across niches, so fit with {niche} is not proven.')
    elif hits < 1: reasons.append(f'No clear evidence this business fits {niche}.')
    return {'score': score, 'confidence': conf, 'reasons': reasons, 'factors': {k: v[0] for k, v in f.items()}, 'eligible': (hits >= 1 or open_niche) and score >= config.ASSUMPTIONS['match_threshold']}


def _sponsor_score(marked: int, read: int) -> float:
    """Some brand work shows experience. Too much suggests a saturated audience. None tells us little."""
    share = marked / read
    return 0.5 if share == 0 else 1.0 if share <= 0.4 else 0.6 if share <= 0.7 else 0.3


def gates(creator: dict, company: dict) -> list[str]:
    """Hard stops. Any failure removes the match, however good the score."""
    failed = []
    s = creator.get('stats') or {}
    lim = creator.get('limits') or {}
    if creator.get('is_minor'):
        failed.append('Creator is under 18, so a guardian must be added before contracting.')
    if company.get('niche') and any(niches.related(company['niche'], b) for b in (lim.get('blocked_categories') or [])):
        failed.append(f"Creator does not work with {company['niche']} brands.")
    er = s.get('engagement_rate')
    if er is not None and er < MIN_ENGAGEMENT:
        failed.append(f'Engagement of {round(er * 100 + 1e-9, 2)}% is below the {MIN_ENGAGEMENT:.1%} minimum.')
    return failed


def fit(creator: dict, company: dict) -> dict:
    """Follower count isn't scored. Creators of any size compete on engagement, content and audience."""
    s = creator.get('stats') or {}
    strength = s.get('strength', 0.3)
    marked, read = sponsored_posts(s.get('captions') or [])
    goal = settings.get('company', company['id'])['campaign_goal'] if company.get('id') else 'balanced'
    er = None if s.get('engagement_anomalous') else s.get('engagement_rate')
    aud = creator.get('audience_country_pct')
    niche = company.get('niche') or creator.get('niche')
    share = niches.share((s.get('captions') or []) + [s.get('bio') or ''], niche)
    if share is None and niches.related(niche, creator.get('niche')):
        share = 0.6
    f = {
        'audience': (aud / 100, 0.3) if aud is not None else (None, 0),
        'content': (share, strength) if share is not None else (None, 0),
        'attention': (min(er / 0.05, 1.0), strength) if er is not None else (None, 0),
        'past_sponsored': (_sponsor_score(marked, read), 0.5) if read >= 3 else (None, 0),
        'reliability': (None, 0),
    }
    score, conf = _combine(config.FIT_PROFILES[goal], f)
    failed = gates(creator, company)
    reasons = []
    if share: reasons.append(f'{round(share * 100)}% of checked content fits {niche}.')
    if er is not None: reasons.append(f'Engagement is {round(er * 100 + 1e-9, 1)}% of followers, from {s.get("reels_read", 0)} recent reels.')
    if aud is not None: reasons.append(f'{aud}% audience in target country, self-reported.')
    if read >= 3 and marked: reasons.append(f'{marked} of {read} recent posts are marked as sponsored.')
    elif read >= 3: reasons.append(f'None of {read} recent posts are marked as sponsored.')
    if goal != 'balanced': reasons.append(f"Scored for a {goal.replace('_', ' ')} campaign.")
    if s.get('engagement_anomalous'): reasons.append('Sampled posts look unusually viral for this account, so engagement is not used. Ask for analytics.')
    if not s.get('reels_read') and s.get('followers') is not None: reasons.append('No readable public posts, so engagement is unknown, not low.')
    if conf < 50: reasons.append('Low confidence: ask for analytics before relying on this score.')
    return {'score': score, 'confidence': conf, 'goal': goal, 'gates_failed': failed, 'passes': not failed, 'reasons': reasons, 'source': s.get('source'), 'factors': {k: v[0] for k, v in f.items()}}


def _sentence(subject: str, good: list[str], caution: str | None, empty: str) -> str:
    if not good:
        return empty + (f' {caution}' if caution else '')
    joined = good[0] if len(good) == 1 else ', '.join(good[:-1]) + ' and ' + good[-1]
    return f'{subject} {joined}.' + (f' {caution}' if caution else '')


def why_brand(name: str, s: dict | None, status: str) -> str:
    """One line for a creator: why this brand, built only from evidence we hold."""
    x = (s or {}).get('factors') or {}
    good = []
    if (x.get('niche') or 0) >= 1: good.append('works in your niche')
    elif (x.get('niche') or 0) >= 0.5: good.append('looks related to your niche')
    if (x.get('influencer_roles') or 0) >= 0.6: good.append('is hiring for influencer marketing')
    if (x.get('influencer_staff') or 0) >= 0.5: good.append('has staff running creator campaigns')
    if (x.get('funding') or 0) >= 0.7: good.append('raised funding recently')
    if (x.get('growth') or 0) >= 0.6: good.append('is growing')
    caution = {'weak_match': 'Its identity is only partly confirmed, so money is held upfront.', 'partly_verified': 'It has less public evidence so far, so money is held upfront.'}.get(status)
    return _sentence(name, good[:3], caution, f'Little public evidence about {name} so far.')


def why_creator(creator: dict, f: dict, company: dict) -> str:
    """One line for a brand: why this creator, built only from evidence we hold."""
    x = f.get('factors') or {}
    s = creator.get('stats') or {}
    good = []
    if (x.get('content') or 0) >= 0.4: good.append(f"posts about {company.get('niche') or creator.get('niche')}")
    if (x.get('attention') or 0) >= 0.4: good.append(f"has an engaged audience ({round(s.get('engagement_rate', 0) * 100 + 1e-9, 1)}%)")
    if (x.get('audience') or 0) >= 0.7: good.append('reaches your market, self-reported')
    caution = 'Based on public data only, so ask for analytics.' if f.get('confidence', 0) < 50 else None
    return _sentence('@' + creator['handle'], good[:3], caution, f"Little public evidence about @{creator['handle']} so far.")
