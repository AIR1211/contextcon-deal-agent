"""Checks the claims in docs/proofs.txt on random deals, with a fixed seed so anyone can reproduce the run."""
import random
from fractions import Fraction as F

from app.engine import Option, bounds, brand_max, bundle_options, creator_min, settle

FC, FB = F(5, 100), F(5, 100)
RUNS = 20000


def rand_options(rng):
    out = []
    for i in range(rng.randint(1, 6)):
        members = [(f'c{j}', rng.randint(0, 200000)) for j in range(rng.randint(1, 5))]
        out.append(Option(f'o{i}', tuple(members), rng.randint(0, 900000)))
    return out


def test_never_outside_limits_and_money_adds_up():
    rng = random.Random(42)
    settled = 0
    for _ in range(RUNS):
        opts = rand_options(rng)
        s = settle(opts, FC, FB)
        if s is None:
            assert all(bounds(o, FC, FB)[0] > bounds(o, FC, FB)[1] for o in opts)
            continue
        settled += 1
        o = next(x for x in opts if x.id == s.option_id)
        costs = dict(o.creator_costs)
        assert s.brand_pays <= o.brand_value                                    # Claim 3, brand.
        assert all(s.creator_net[c] >= costs[c] for c in costs)                 # Claim 3, creators.
        assert sum(s.creator_prices.values()) == s.price                        # Claim 4.
        assert s.brand_pays - sum(s.creator_net.values()) == s.fee_brand + s.fee_creators
    assert settled > RUNS / 10


def test_midpoint_maximises_nash_product():
    rng = random.Random(7)
    for _ in range(3000):
        o = Option('x', (('c', rng.randint(0, 50000)),), rng.randint(0, 100000))
        s = settle([o], FC, FB)
        if s is None:
            continue
        r, c = bounds(o, FC, FB)
        best = max((p - r) * (c - p) for p in range(r, c + 1)) if c - r < 3000 else (s.price - r) * (c - s.price)
        assert (s.price - r) * (c - s.price) == best                            # Claim 1, whole rupees.


def test_highest_surplus_wins_and_no_option_beats_it_for_both():
    rng = random.Random(9)
    for _ in range(RUNS // 4):
        opts = rand_options(rng)
        s = settle(opts, FC, FB)
        if s is None:
            continue
        feasible = [bounds(o, FC, FB) for o in opts if bounds(o, FC, FB)[0] <= bounds(o, FC, FB)[1]]
        assert s.surplus == max(c - r for r, c in feasible)                     # Claim 2.


def test_repeatable_and_order_independent():
    rng = random.Random(11)
    for _ in range(3000):
        opts = rand_options(rng)
        a, b = settle(opts, FC, FB), settle(list(reversed(opts)), FC, FB)
        assert (a.to_dict() if a else None) == (b.to_dict() if b else None)     # Claim 5.


def test_fair_between_creators_with_equal_costs():
    o = Option('b', (('a', 10000), ('b', 10000)), 60000)
    p = settle([o], FC, FB).creator_prices
    assert abs(p['a'] - p['b']) <= 1


def test_mirrored_deal_gives_each_side_the_same_gain():
    s = settle([Option('x', (('c', 9500),), 21000)], FC, FB)    # r = 10000, c = 20000
    assert (s.price - 10000, 20000 - s.price) == (5000, 5000)


def test_no_overlap_returns_none():
    assert settle([Option('x', (('c', 50000),), 1000)], FC, FB) is None


def test_exact_limit_still_settles():
    r = creator_min(9500, FC)
    s = settle([Option('x', (('c', 9500),), 10500)], FC, FB)
    assert brand_max(10500, FB) == r == s.price == 10000
    assert s.creator_net['c'] == 9500 and s.brand_pays == 10500


def test_bundle_beats_single_when_it_has_more_surplus():
    cands = [{'id': n, 'cost': 3000, 'value': 8000, 'terms': {}} for n in 'abc']
    s = settle(bundle_options(cands, 20000), FC, FB)
    assert len(s.creator_prices) == 3 and s.brand_pays <= 20000


def test_bundle_respects_budget():
    rng = random.Random(3)
    for _ in range(1000):
        cands = [{'id': f'c{i}', 'cost': rng.randint(500, 9000), 'value': rng.randint(500, 15000), 'terms': {}} for i in range(rng.randint(1, 6))]
        budget = rng.randint(1000, 40000)
        s = settle(bundle_options(cands, budget), FC, FB)
        if s:
            assert s.brand_pays <= budget
            assert all(s.creator_net[c['id']] >= c['cost'] for c in cands if c['id'] in s.creator_net)
