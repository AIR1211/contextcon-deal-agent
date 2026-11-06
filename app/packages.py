"""Media packs, pricing and tweak deltas. List prices and close estimates are estimates, and are labelled as such."""
from math import ceil

from .config import ASSUMPTIONS as A, FEE_BRAND, FEE_CREATOR, TIERS
from .engine import Option
from .models import Terms

PACK_TIERS = {
    'Starter': Terms(reels=1, stories=0, usage_days=30),
    'Standard': Terms(reels=1, stories=2, usage_days=60),
    'Campaign': Terms(reels=2, stories=3, usage_days=90, exclusivity_days=30),
}
BUDGET_BY_SIZE = {'myself only': 8000, '2-10': 15000, '11-50': 30000, '51-200': 60000, '201-500': 100000}   # Assumption.
DEFAULT_BUDGET = 150000


def reel_rate(stats: dict) -> int:
    """Expected views x CPM. Public pages show likes, not views, so views are estimated from likes."""
    likes = stats.get('median_likes')
    if not likes:
        return A['minimum_reel_price_inr']
    if stats.get('followers'):
        likes = min(likes, stats['followers'] * A['max_likes_share_of_followers'])    # Stops one viral sample setting the price.
    return max(A['minimum_reel_price_inr'], round(likes * A['views_per_like'] * A['cpm_inr'] / 1000))


def priced(reel: int, story: int | None, t: Terms) -> int:
    story = story if story is not None else ceil(reel * A['story_share_of_reel'])
    base = reel * t.reels + story * t.stories
    extra_usage = max(t.usage_days - 30, 0) / 30 * float(A['usage_per_30_days_share'])
    excl = t.exclusivity_days / 30 * float(A['exclusivity_per_30_days_share'])
    ads = float(A['paid_ads_share']) if t.paid_ads else 0
    return ceil(base * (1 + extra_usage + excl + ads))


def list_price(creator: dict, t: Terms) -> int:
    return priced(reel_rate(creator.get('stats') or {}), None, t)


def creator_cost(creator: dict, t: Terms) -> int:
    """The creator's own floor. Without one, a default share of the estimated list price."""
    lim = creator.get('limits') or {}
    floor_reel = lim.get('floor_reel')
    if floor_reel is None:
        floor_reel = ceil(reel_rate(creator.get('stats') or {}) * A['default_floor_share_of_list'])
    return priced(floor_reel, lim.get('floor_story'), t)


def company_budget(company: dict) -> int:
    return company.get('budget') or BUDGET_BY_SIZE.get(company.get('size_range'), DEFAULT_BUDGET)


def brand_value(company_limits: dict, creators: list[dict], t: Terms) -> int:
    """What this deal is worth to the company, capped by its ceiling and tier."""
    total = 0
    for c in creators:
        per_reel = company_limits.get('value_per_reel') or ceil(reel_rate(c.get('stats') or {}) * 1.4)
        if company_limits.get('simulated') and not company_limits.get('value_per_reel'):
            # A simulated company puts up to half its budget behind the reels. Mock behaviour, labelled in the UI.
            per_reel = max(per_reel, ceil((company_limits.get('ceiling') or 0) / 2 / len(creators) / max(t.reels, 1)))
        per_story = company_limits.get('value_per_story') or ceil(per_reel / 3)
        total += per_reel * t.reels + per_story * t.stories
    total += max(t.usage_days - 30, 0) // 30 * company_limits.get('value_per_30_usage_days', 0)
    total += t.exclusivity_days // 30 * company_limits.get('value_per_30_exclusive_days', 0)
    total += company_limits.get('value_paid_ads', 0) if t.paid_ads else 0
    ceiling = company_limits.get('ceiling')
    return min(total, ceiling) if ceiling is not None else total


def within_limits(creator: dict, t: Terms) -> str | None:
    lim = creator.get('limits') or {}
    if t.exclusivity_days > lim.get('max_exclusivity_days', 90):
        return f"Exclusivity is above the creator's {lim.get('max_exclusivity_days', 90)}-day limit."
    if t.paid_ads and not lim.get('allow_paid_ads', True):
        return 'Creator does not allow paid ads.'
    return None


def term_grid(base: Terms) -> list[Terms]:
    """Variations around the proposed terms, so the engine can trade terms instead of only haggling on price."""
    out = {}
    for usage in sorted({base.usage_days, 30, 60, 90}):
        for excl in sorted({base.exclusivity_days, 0}):
            for stories in sorted({base.stories, max(base.stories - 1, 0)}):
                t = base.model_copy(update={'usage_days': usage, 'exclusivity_days': excl, 'stories': stories})
                out[f'r{t.reels}s{t.stories}u{t.usage_days}e{t.exclusivity_days}a{int(t.paid_ads)}'] = t
    return [v.model_copy() for _, v in sorted(out.items())]


def options(creators: list[dict], company_limits: dict, base: Terms, tier: str) -> list[Option]:
    cap = TIERS.get(tier, {}).get('deal_cap')
    limits = dict(company_limits)
    if cap:
        limits['ceiling'] = min(limits.get('ceiling') or cap, cap)
    out = []
    for t in term_grid(base):
        if any(within_limits(c, t) for c in creators):
            continue
        key = f'r{t.reels}s{t.stories}u{t.usage_days}e{t.exclusivity_days}a{int(t.paid_ads)}'
        costs = tuple(sorted((c['id'], creator_cost(c, t)) for c in creators))
        out.append(Option(key, costs, brand_value(limits, creators, t), t.model_dump()))
    return out


def evaluate(creator: dict, company: dict, t: Terms, likelihood_score: int, fit_score: int) -> dict:
    """Estimates only. A higher price can lower the chance of closing, so we compare expected earnings."""
    cost = creator_cost(creator, t)
    price = max(list_price(creator, t), ceil(cost / (1 - FEE_CREATOR)))
    budget = company_budget(company)
    brand_pays = ceil(price * (1 + FEE_BRAND))
    afford = max(min(1 - (brand_pays / budget - 0.6) / 0.6, 1.0), 0.0)
    close = round(0.5 * likelihood_score + 30 * afford + 0.2 * fit_score)
    net = price - int(price * FEE_CREATOR)
    return {'list_price': price, 'creator_floor': cost, 'creator_net_estimate': net, 'brand_pays_estimate': brand_pays, 'close_estimate': close,
            'expected_earnings': round(net * close / 100), 'fit': fit_score, 'is_estimate': True}


def packs_for(creator: dict, company: dict, likelihood_score: int, fit_score: int) -> list[dict]:
    out = []
    for name, t in PACK_TIERS.items():
        if within_limits(creator, t):
            t = t.model_copy(update={'exclusivity_days': 0})
        out.append({'name': name, 'terms': t.model_dump(), 'evaluation': evaluate(creator, company, t, likelihood_score, fit_score)})
    return out


def tweak(creator: dict, company: dict, before: Terms, after: Terms, likelihood_score: int, fit_score: int) -> dict:
    a, b = evaluate(creator, company, before, likelihood_score, fit_score), evaluate(creator, company, after, likelihood_score, fit_score)
    problem = within_limits(creator, after)
    delta = {k: b[k] - a[k] for k in ('list_price', 'close_estimate', 'expected_earnings')}
    verdict = 'blocked' if problem else 'improved' if delta['expected_earnings'] > 0 else 'worse' if delta['expected_earnings'] < 0 else 'unchanged'
    return {'before': a, 'after': b, 'delta': delta, 'verdict': verdict, 'problem': problem,
            'note': 'Estimate from our pricing assumptions, not a measured result. Assumptions are in app/config.py.'}
