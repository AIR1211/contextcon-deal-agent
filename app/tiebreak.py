"""Published tiebreak chains. Each candidate gets a tuple of keys compared left to right, so there is always exactly one
winner, the order is transitive, and input order never matters. See docs/proofs.txt, claim 6.

"Similar" is handled with bands anchored to the best value in the set, so close values tie and the next key decides.
The last key is a SHA-256 lot, so an exact tie can't be won by registering first in the database or by a lucky ID.
"""
import hashlib

PAY_BAND = 0.02         # Offers within 2% of each other count as equal pay.
SCORE_BAND = 3          # Scores within a 3-point band count as equal.
TIER_RANK = {'A': 2, 'B': 1, 'C': 0}


def lot(context: str, item_id: str) -> str:
    return hashlib.sha256(f'{context}:{item_id}'.encode()).hexdigest()


def _pay_band(value, best):
    """0 is the top band. Whole bands below the best value, so the grid is the same for everyone in the set."""
    step = max(best * PAY_BAND, 1)
    return -int((best - value) // step)


def _rank(items: list[dict], keys: list[tuple], context: str, id_field: str) -> list[dict]:
    """keys: (label, function), larger is better. Adds rank and decided_by, the reason it beat the next candidate."""
    scored = []
    for it in items:
        scored.append((tuple(k[1](it) for k in keys), lot(context, it[id_field]), it))
    scored.sort(key=lambda s: (tuple(-x if isinstance(x, (int, float)) else x for x in s[0]), s[1]))
    out = []
    for i, (vals, _, it) in enumerate(scored):
        reason = None
        if i + 1 < len(scored):
            nxt = scored[i + 1][0]
            reason = next((keys[j][0] for j in range(len(keys)) if vals[j] != nxt[j]), 'Fair lot: every published criterion tied.')
        out.append({**it, 'rank': i + 1, 'decided_by': reason})
    return out


def rank_offers(offers: list[dict], context: str) -> list[dict]:
    """A creator choosing between companies. Offer: company_id, net, tier, upfront_pct, exclusivity_days, usage_days, fit, offered_at."""
    best = max((o['net'] for o in offers), default=0)
    return _rank(offers, [
        ('Pays more', lambda o: _pay_band(o['net'], best)),
        ('Safer payment: better verified, more held upfront', lambda o: TIER_RANK.get(o.get('tier'), 0) * 1000 + o.get('upfront_pct', 0)),
        ('Fewer restrictions on the creator', lambda o: -(o.get('exclusivity_days', 0) * 2 + o.get('usage_days', 0))),
        ('Better fit with the creator\'s niche', lambda o: o.get('fit', 0) // SCORE_BAND),
        ('Made the offer first', lambda o: -o['offered_at'] if isinstance(o.get('offered_at'), (int, float)) else 0),
    ], context, 'company_id')


def rank_creators(rows: list[dict], context: str) -> list[dict]:
    """A company choosing between creators. Merit first, then evidence, then the choice that spreads income to smaller creators."""
    return _rank(rows, [
        ('Better fit', lambda r: r.get('fit', 0) // SCORE_BAND),
        ('Stronger evidence', lambda r: r.get('confidence', 0) // SCORE_BAND),
        ('Lower estimated price', lambda r: _pay_band(-r.get('list_price_estimate', 0), 0)),
        ('Higher engagement', lambda r: round((r.get('engagement_rate') or 0) * 200)),
        ('Fewer paid deals so far', lambda r: -r.get('deals_done', 0)),
        ('Smaller creator', lambda r: -(r.get('followers') or 0)),
    ], context, 'creator_id')


def rank_brands(rows: list[dict], context: str) -> list[dict]:
    """Brands suggested to a creator."""
    return _rank(rows, [
        ('More likely to buy', lambda r: r.get('likelihood', 0) // SCORE_BAND),
        ('Better verified', lambda r: TIER_RANK.get(r.get('tier'), 0)),
        ('Stronger evidence', lambda r: r.get('confidence', 0) // SCORE_BAND),
    ], context, 'company_id')
