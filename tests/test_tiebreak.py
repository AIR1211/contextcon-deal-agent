"""Tiebreak chains: always one winner, order independent, transitive, and each result is explained."""
import random
from fractions import Fraction as F

from app.engine import Option, settle
from app.tiebreak import rank_creators, rank_offers


def offer(cid, net=10000, tier='A', upfront=50, excl=0, usage=30, fit=70, at=100):
    return {'company_id': cid, 'net': net, 'tier': tier, 'upfront_pct': upfront, 'exclusivity_days': excl, 'usage_days': usage, 'fit': fit, 'offered_at': at}


def row(cid, fit=70, conf=60, price=5000, er=0.03, deals=0, followers=5000):
    return {'creator_id': cid, 'fit': fit, 'confidence': conf, 'list_price_estimate': price, 'engagement_rate': er, 'deals_done': deals, 'followers': followers}


def top(ranked):
    return ranked[0]['company_id'] if 'company_id' in ranked[0] else ranked[0]['creator_id']


def test_higher_pay_wins_outside_the_band():
    r = rank_offers([offer('a', net=10000), offer('b', net=11000)], 'x')
    assert top(r) == 'b' and r[0]['decided_by'] == 'Pays more'


def test_same_pay_goes_to_safer_payment():
    r = rank_offers([offer('a', tier='B', upfront=100), offer('b', tier='A')], 'x')
    assert top(r) == 'b' and 'Safer payment' in r[0]['decided_by']


def test_pay_within_two_percent_counts_as_a_tie():
    r = rank_offers([offer('a', net=10000), offer('b', net=9900, excl=0, usage=30, tier='A', upfront=100)], 'x')
    assert top(r) == 'b'


def test_same_pay_and_safety_goes_to_fewer_restrictions():
    r = rank_offers([offer('a', excl=30), offer('b')], 'x')
    assert top(r) == 'b' and 'restrictions' in r[0]['decided_by']


def test_then_earlier_offer():
    r = rank_offers([offer('a', at=200), offer('b', at=100)], 'x')
    assert top(r) == 'b' and 'first' in r[0]['decided_by']


def test_exact_tie_uses_a_fair_lot_that_is_repeatable():
    a = rank_offers([offer('a'), offer('b')], 'creator1')
    b = rank_offers([offer('b'), offer('a')], 'creator1')
    assert top(a) == top(b) and 'Fair lot' in a[0]['decided_by']


def test_lot_is_not_always_won_by_the_same_id():
    wins = {top(rank_offers([offer('a'), offer('b')], f'context{i}')) for i in range(30)}
    assert wins == {'a', 'b'}


def test_follower_count_never_decides_a_tie():
    r = rank_creators([row('big', followers=90000), row('small', followers=3000)], 'x')
    assert 'Fair lot' in r[0]['decided_by']


def test_creator_merit_comes_before_size():
    assert top(rank_creators([row('big', fit=90, followers=90000), row('small', fit=60, followers=3000)], 'x')) == 'big'


def test_creator_tie_spreads_income_to_those_with_fewer_deals():
    assert top(rank_creators([row('busy', deals=9, followers=100), row('new', deals=0, followers=9000)], 'x')) == 'new'


def test_any_input_order_gives_one_identical_ranking():
    rng = random.Random(5)
    for _ in range(2000):
        items = [offer(f'c{i}', net=rng.choice([10000, 10050, 12000]), tier=rng.choice('ABC'), upfront=rng.choice([50, 100]), excl=rng.choice([0, 30]), usage=rng.choice([30, 90]), fit=rng.randint(40, 90), at=rng.randint(1, 3)) for i in range(rng.randint(2, 6))]
        ids = [x['company_id'] for x in rank_offers(items, 'seed')]
        shuffled = items[:]
        rng.shuffle(shuffled)
        assert ids == [x['company_id'] for x in rank_offers(shuffled, 'seed')] and len(set(ids)) == len(ids)


def test_engine_prefers_lighter_terms_when_surplus_is_equal():
    heavy = Option('a_heavy', (('c', 1000),), 5000, {'exclusivity_days': 30, 'usage_days': 90})
    light = Option('z_light', (('c', 1000),), 5000, {'exclusivity_days': 0, 'usage_days': 30})
    fc, fb = F(5, 100), F(5, 100)
    assert settle([heavy, light], fc, fb).option_id == 'z_light' == settle([light, heavy], fc, fb).option_id
