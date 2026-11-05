"""The negotiation engine. Pure maths: no I/O, no LLM. Claims and proofs are in docs/proofs.txt.

Each option is a set of terms with a cost per creator and a value to the brand, in whole rupees. The engine picks the
option with the highest surplus and settles at the fee-adjusted midpoint, the Nash bargaining solution.
"""
from dataclasses import dataclass, field, asdict
from fractions import Fraction
from itertools import combinations
from math import ceil, floor


@dataclass(frozen=True)
class Option:
    id: str
    creator_costs: tuple   # ((creator_id, whole-rupee cost), ...)
    brand_value: int
    terms: dict = field(default_factory=dict, hash=False, compare=False)


@dataclass
class Settlement:
    option_id: str
    terms: dict
    price: int
    creator_prices: dict
    creator_net: dict
    brand_pays: int
    fee_creators: int
    fee_brand: int
    surplus: int
    options_considered: int
    rule: str = 'The option with the largest joint gain, settled at the midpoint of both private limits after fees (Nash bargaining solution).'

    def to_dict(self):
        return asdict(self)


def creator_min(cost: int, fee: Fraction) -> int:
    return ceil(Fraction(cost) / (1 - fee))


def brand_max(value: int, fee: Fraction) -> int:
    return floor(Fraction(value) / (1 + fee))


def bounds(o: Option, fc: Fraction, fb: Fraction):
    return sum(creator_min(c, fc) for _, c in o.creator_costs), brand_max(o.brand_value, fb)


def burden(o: Option) -> tuple:
    """Tiebreak between options with equal surplus: fewer restrictions on the creator."""
    t = o.terms or {}
    return (t.get('exclusivity_days', 0), t.get('usage_days', 0), t.get('stories', 0))


def settle(options: list[Option], fc: Fraction, fb: Fraction) -> Settlement | None:
    """Returns the settlement, or None when no option has overlapping limits. Input order never affects the result."""
    feasible = [(*bounds(o, fc, fb), o) for o in options]
    feasible = [x for x in feasible if x[0] <= x[1]]
    if not feasible:
        return None
    r, c, o = min(feasible, key=lambda x: (x[0] - x[1], burden(x[2]), x[2].id))    # Largest surplus, then lightest terms.
    price = (r + c) // 2
    extra, members = price - r, sorted(o.creator_costs)
    share, rest = divmod(extra, len(members))
    prices = {}
    for i, (cid, cost) in enumerate(members):
        prices[cid] = creator_min(cost, fc) + share + (1 if i < rest else 0)
    net = {cid: p - floor(p * fc) for cid, p in prices.items()}
    fee_b = ceil(price * fb)
    return Settlement(o.id, o.terms, price, prices, net, price + fee_b, sum(prices.values()) - sum(net.values()), fee_b, c - r, len(options))


def bundle_options(candidates: list[dict], budget: int, max_size: int = 5) -> list[Option]:
    """candidates: {id, cost, value, terms}. Every subset's value is capped at the budget."""
    out = []
    for size in range(1, min(max_size, len(candidates)) + 1):
        for group in combinations(sorted(candidates, key=lambda x: x['id']), size):
            value = min(budget, sum(g['value'] for g in group))
            out.append(Option('+'.join(g['id'] for g in group), tuple((g['id'], g['cost']) for g in group), value, {'bundle': [g['id'] for g in group]}))
    return out
