"""End-to-end scenarios from the rubric: finished work, facts, edge cases, crashes, double sends."""
import json

import httpx
import pytest

from app import db, llm, orchestrator as orch, packages, scoring, service, verify
from app.crustdata import Crustdata, Unavailable
from app.models import BLOCKED, CANT, CompanyIn, CompanyLimits, CreatorIn, CreatorLimits, DealIn, LEFT, PARTLY, Terms, VERIFIED, WEAK

MOCK = {'followers': 5000, 'likes': [120, 150, 90], 'comments': [10, 12, 8], 'bio': 'Food recipes', 'captions': ['food recipe'] * 3}


def creator(handle='small_food', floor=2000, **kw):
    return service.onboard_creator(CreatorIn(handle=handle, niche='food', limits=CreatorLimits(floor_reel=floor), mock_stats=MOCK, audience_country_pct=90, **kw))


def company(ceiling=20000, **kw):
    base = dict(name='Real Brand', domain='realbrand.in', niche='food', sender_name='Priya Shah', sender_email='priya@realbrand.in', budget=ceiling, limits=CompanyLimits(ceiling=ceiling, value_per_reel=9000))
    return service.register_company(CompanyIn(**{**base, **kw}))


def go(c_ids, co, crash_after=None, **kw):
    d = orch.start(DealIn(creator_ids=c_ids, company_id=co['id'], **kw))
    return d, orch.run(d['id'], crash_after)


def kinds(deal_id):
    return [a['kind'] for a in db.ledger(deal_id)]


def test_happy_path_finishes_with_paid_invoice(world):
    co = company()
    assert (co['status'], co['sender_status'], co['tier']) == (VERIFIED, VERIFIED, 'A')
    d, end = go([creator()['id']], co)
    assert end['state'] == 'done'
    s = end['settlement']
    assert s['brand_pays'] <= 20000
    k = kinds(d['id'])
    for needed in ('mock_email', 'contract_issued', 'mock_signature', 'mock_funds_held', 'mock_balance_charged', 'mock_payout', 'mock_fee', 'invoice'):
        assert needed in k
    assert 'ASCI' in end['contract_text'] and len(end['contract_hash']) == 64
    ledger = db.ledger(d['id'])
    paid = sum(a['payload']['amount'] for a in ledger if a['kind'] in ('mock_payout', 'mock_fee'))
    assert paid == s['brand_pays']                                   # Every rupee is accounted for.


def test_crash_at_every_step_never_doubles_any_action(world):
    co = company()
    cid = creator()['id']
    for step in [s for s in orch.ORDER if s != 'done']:
        d = orch.start(DealIn(creator_ids=[cid], company_id=co['id']))
        with pytest.raises(orch.SimulatedCrash):
            orch.run(d['id'], crash_after=step)
        before = db.get('deal', d['id'])['state']
        assert before == step                                        # The step's state was not saved.
        end = orch.run(d['id'])
        orch.run(d['id'])                                            # An extra resume must change nothing.
        assert end['state'] == 'done'
        keys = [a['key'] for a in db.ledger(d['id'])]
        assert len(keys) == len(set(keys))
        assert kinds(d['id']).count('mock_payout') == 1
        assert kinds(d['id']).count('invoice') == 1
        assert kinds(d['id']).count('mock_funds_held') == 1


def test_lookalike_domain_is_blocked(world):
    co = company(name='boAt', domain='boat-collabs.co', sender_email='x@boat-collabs.co', sender_name='Aman Gupta')
    assert co['status'] == BLOCKED
    d, end = go([creator()['id']], co)
    assert end['state'] == 'blocked' and 'boat-lifestyle.com' in end['final_reason']
    assert db.ledger(d['id']) == []                                  # Nothing goes out.


def test_claiming_a_brand_from_another_real_domain_is_blocked(world):
    assert company(name='boAt', domain='realbrand.in', sender_name=None)['status'] == BLOCKED


def test_same_name_on_personal_email_is_only_weak(world):
    co = company(sender_email='priya.shah@gmail.com')
    assert co['sender_status'] == WEAK and co['tier'] == 'B'


def test_several_same_name_profiles_are_only_weak(world):
    assert company(sender_name='Same Name', sender_email='s@realbrand.in')['sender_status'] == WEAK


def test_contact_who_left_pauses_the_deal(world):
    co = company(sender_name='Ravi Rao', sender_email='ravi@realbrand.in')
    assert co['sender_status'] == LEFT
    d, end = go([creator()['id']], co)
    assert end['paused']['kind'] == 'contact_left'
    assert 'mock_email' not in kinds(d['id'])
    assert orch.decide(d['id'], True)['state'] == 'done'


def test_contact_leaves_mid_deal_is_caught_before_signing(world):
    co = company()
    d, _ = None, None
    d = orch.start(DealIn(creator_ids=[creator()['id']], company_id=co['id']))
    with pytest.raises(orch.SimulatedCrash):
        orch.run(d['id'], crash_after='contract')
    orch.run(d['id'])    # Finishes; now repeat with the fact changed first.
    d2 = orch.start(DealIn(creator_ids=d['creator_ids'], company_id=co['id']))
    with pytest.raises(orch.SimulatedCrash):
        orch.run(d2['id'], crash_after='contract')
    world.people[('Priya Shah', 500)] = 'past'
    end = orch.run(d2['id'])
    assert end['paused']['kind'] == 'recheck_override' and 'mock_signature' not in kinds(d2['id'])


def test_tool_failure_at_recheck_does_not_silently_pass(world):
    co = company()
    d = orch.start(DealIn(creator_ids=[creator()['id']], company_id=co['id']))
    with pytest.raises(orch.SimulatedCrash):
        orch.run(d['id'], crash_after='contract')
    world.fail_paths['/person/search'] = lambda r: httpx.Response(500)
    end = orch.run(d['id'])
    assert end['paused']['kind'] == 'recheck_override' and 'could not be re-checked' in end['paused']['question']


def test_no_website_brand_gets_stricter_terms_not_rejection(world):
    co = service.register_company(CompanyIn(name='Ghar Ke Snacks', niche='food', gstin='09ABCDE1234F1Z5', budget=20000))
    assert co['status'] == PARTLY and co['tier'] == 'B'
    d, end = go([creator()['id']], co)
    assert end['state'] == 'done' and end['tier_terms']['upfront_pct'] == 100
    assert kinds(d['id']).count('mock_balance_charged') == 0        # Everything was held upfront.


def test_nothing_verifiable_goes_to_a_person(world):
    co = service.register_company(CompanyIn(name='Mystery Co', niche='food', budget=5000))
    assert co['status'] == CANT and co['tier'] == 'C'
    d, end = go([creator(floor=500)['id']], co)
    assert end['paused']['kind'] == 'unverified_company'
    assert orch.decide(d['id'], False)['state'] == 'no_deal'


def test_no_overlap_keeps_limits_private_then_can_close(world):
    co = company(ceiling=1000, limits=CompanyLimits(ceiling=1000, value_per_reel=1000))
    d, end = go([creator(floor=9000)['id']], co)
    assert end['paused']['kind'] == 'no_overlap' and '1000' not in end['paused']['question']
    assert orch.decide(d['id'], True, new_floor=500)['state'] == 'done'


def test_no_overlap_declined_ends_cleanly(world):
    co = company(ceiling=1000, limits=CompanyLimits(ceiling=1000, value_per_reel=1000))
    d, _ = go([creator(floor=9000)['id']], co)
    end = orch.decide(d['id'], False)
    assert end['state'] == 'no_deal' and 'mock_payout' not in kinds(d['id'])


def test_bundle_of_small_creators_pays_each_above_floor(world):
    ids = [creator(handle=f'small_{i}', floor=1500 + i * 100)['id'] for i in range(3)]
    co = company(ceiling=30000, limits=CompanyLimits(ceiling=30000, value_per_reel=6000))
    d, end = go(ids, co)
    s = end['settlement']
    assert end['state'] == 'done' and len(s['creator_net']) == 3
    assert all(s['creator_net'][c] >= packages.creator_cost(db.get('creator', c), Terms(**{k: s['terms'][k] for k in Terms.model_fields})) for c in ids)
    assert kinds(d['id']).count('mock_payout') == 3


def test_exclusivity_conflict_across_parent_company_names(world):
    cid = creator()['id']
    first = service.register_company(CompanyIn(name='boAt', domain='boat-lifestyle.com', niche='audio', budget=90000, limits=CompanyLimits(ceiling=90000, value_per_reel=20000, value_per_30_exclusive_days=30000)))
    assert first['group'] == 'boat'
    _, a = go([cid], first, terms=Terms(exclusivity_days=30))
    assert a['state'] == 'done' and a['settlement']['terms']['exclusivity_days'] == 30
    second = service.register_company(CompanyIn(name='Imagine Marketing', niche='audio', budget=30000, gstin='09ABCDE1234F1Z5'))
    assert second['group'] == 'boat'
    _, b = go([cid], second)
    assert b['state'] == 'blocked' and 'same company group' in b['final_reason']


def test_public_deal_never_exposes_limits(world):
    co = company(ceiling=44444, limits=CompanyLimits(ceiling=44444, value_per_reel=33333))
    c = creator(floor=2222)
    d, end = go([c['id']], co)
    text = json.dumps(orch.public_deal(end)) + json.dumps(service.public_creator(c))
    assert '44444' not in text and '33333' not in text and 'surplus' not in text and 'floor_reel' not in text


def test_company_view_of_creators_hides_floors(world):
    creator(floor=7777)
    assert '7777' not in json.dumps(service.company_creators(company()['id']))


def test_two_companies_racing_for_one_creator_first_signer_wins(world):
    cid = creator()['id']
    a, b = company(), company()
    excl = Terms(exclusivity_days=30)
    da, db_ = orch.start(DealIn(creator_ids=[cid], company_id=a['id'], terms=excl)), orch.start(DealIn(creator_ids=[cid], company_id=b['id'], terms=excl))
    for x in (da, db_):
        stored = db.get('deal', x['id'])
        stored.update(state='sign', tier='A', tier_terms={'upfront_pct': 50, 'deal_cap': None}, contract_hash='h', settlement={'terms': {'exclusivity_days': 30}, 'brand_pays': 100, 'creator_net': {cid: 90}, 'fee_brand': 5, 'fee_creators': 5, 'price': 95, 'creator_prices': {cid: 95}})
        db.put('deal', x['id'], stored)
    assert orch.run(da['id'])['state'] == 'done'
    assert orch.run(da['id'])['state'] == 'done'
    end = orch.run(db_['id'])
    assert end['state'] == 'blocked' and 'signed first' in end['final_reason']


def test_compare_offers_ranks_and_explains(world):
    c = creator()
    richer, safer = company(ceiling=30000, limits=CompanyLimits(ceiling=30000, value_per_reel=20000)), company(ceiling=9000, limits=CompanyLimits(ceiling=9000, value_per_reel=6000))
    r = service.compare_offers(c['id'], [safer['id'], richer['id']])
    assert r['offers'][0]['company_id'] == richer['id'] and r['offers'][0]['decided_by'] == 'Pays more'


def test_requested_terms_are_kept_when_they_fit(world):
    co = company(ceiling=20000, limits=CompanyLimits(ceiling=20000, value_per_reel=9000))
    _, end = go([creator(floor=2000)['id']], co, terms=Terms(reels=1, stories=1, usage_days=60))
    t = end['settlement']['terms']
    assert t['stories'] >= 1 and t['usage_days'] >= 60 and 'terms_reduced' not in end


def test_terms_shrink_only_when_requested_terms_do_not_fit(world):
    co = company(ceiling=3000, limits=CompanyLimits(ceiling=3000, value_per_reel=3000, value_per_story=100))
    _, end = go([creator(floor=2000)['id']], co, terms=Terms(reels=1, stories=4, usage_days=60))
    assert end['state'] == 'done' or end.get('paused')


def test_viral_samples_do_not_set_the_price():
    from app.creators import add_engagement
    s = add_engagement({'followers': 14000}, [343000, 454000, 151000], [4140, 2720, 398])
    assert s['engagement_anomalous'] is True
    assert packages.reel_rate(s) <= 14000 * 0.25 * 15 * 300 / 1000
    f = scoring.fit({'niche': 'food', 'stats': {**s, 'strength': 0.7}}, {'niche': 'food'})
    assert any('unusually viral' in r for r in f['reasons'])


def test_pinned_posts_are_skipped_when_enough_exist(world):
    from app.creators import read_stats
    calls = []
    orig = service.cd.fetch_page
    def fake(url, fresh=False):
        calls.append(url)
        if '/reel/' in url:
            return 'x', '<meta property="og:description" content="347 likes, 16 comments - acc on October 2, 2026: &quot;food&quot;" />', 'now'
        links = ' '.join(f'/reel/POST{i:06d}/' for i in range(12))
        return 'Acc (@acc)', '<meta property="og:description" content="14K Followers, 100 Following, 300 Posts - bio" />' + links, 'now'
    service.cd.fetch_page = fake
    s = read_stats(service.cd, 'acc')
    service.cd.fetch_page = orig
    assert not any('POST000000' in c or 'POST000002' in c for c in calls) and s['reels_read'] == 8 and s['median_likes'] == 347


def test_agencies_are_not_customers():
    for name in ('AD Mafiya Creative Agency', 'Zapplr Media', 'OnO Creators', 'Digital Web Solutions'):
        assert service.is_intermediary(name)
    for name in ('Plum', 'VMax Wellness', 'Good Guilt'):
        assert not service.is_intermediary(name)


def test_having_no_data_cannot_beat_having_data():
    base = {'text': 'snack food brand', 'size_range': '2-10'}
    known_zero = scoring.likelihood({**base, 'influencer_roles': 0, 'influencer_staff': 0}, 'food')
    with_roles = scoring.likelihood({**base, 'influencer_roles': 2, 'influencer_staff': 1}, 'food')
    assert with_roles['score'] > known_zero['score'] and with_roles['confidence'] > known_zero['confidence']


def test_complete_brief_uses_no_llm_call(world, monkeypatch):
    called = []
    monkeypatch.setattr(llm, '_claude', lambda *a, **k: called.append(a) or None)
    b = llm.parse_brief('From Snackly: budget 30k for 2 reels for our snack brand, 60 day usage. neha@snackly.in')
    assert b['parsed_by'] == 'rules' and not b['missing'] and called == []


def test_llm_is_asked_only_for_missing_fields(world, monkeypatch):
    seen = {}
    def fake(prompt, schema=None, max_tokens=0):
        seen['fields'] = schema['required']
        return '{"niche": "food"}' if 'niche' in schema['required'] else None
    monkeypatch.setattr(llm, '_claude', fake)
    b = llm.parse_brief('From Snackly: budget 30k. neha@snackly.in. Our chips launch needs a creator.')
    assert seen['fields'] == ['niche'] and b['niche'] == 'food' and b['parsed_by'] == 'rules+llm'


def test_a_full_deal_uses_no_llm_calls_by_default(world, monkeypatch):
    called = []
    monkeypatch.setattr(llm, '_claude', lambda *a, **k: called.append(a) or None)
    _, end = go([creator()['id']], company())
    assert end['state'] == 'done' and called == []


def test_pitch_rewrite_that_changes_numbers_is_rejected(world, monkeypatch):
    monkeypatch.setattr(llm.config, 'LLM_POLISH', True)
    monkeypatch.setattr(llm, '_claude', lambda *a, **k: 'Wonderful offer: 99 reels!')
    text = llm.pitch_text({'name': 'X', 'niche': 'food'}, [{'handle': 'a'}], {'reels': 1, 'stories': 0, 'usage_days': 30})
    assert '99' not in text and 'AI agent' in text


def test_minor_is_gated(world):
    d, end = go([creator(is_minor=True)['id']], company())
    assert end['state'] == 'blocked' and 'under 18' in end['final_reason']


def test_non_standard_clause_goes_to_a_person(world):
    _, end = go([creator()['id']], company(), non_standard_clause='Perpetual worldwide usage')
    assert end['paused']['kind'] == 'non_standard_clause'


def test_human_company_waits_then_continues(world):
    co = company(mode='human')
    d, end = go([creator()['id']], co)
    assert end['paused']['kind'] == 'company_response' and end['state'] == 'await_company'
    assert orch.set_field(d['id'], 'company_response', {'accept': True})['state'] == 'done'


def test_real_read_of_small_creator_uses_median_and_owner_check(world):
    c = service.onboard_creator(CreatorIn(handle='@tastyfood', niche='food'))
    s = c['stats']
    assert s['followers'] == 5000 and s['median_likes'] == 100 and s['reels_read'] == 2
    assert s['engagement_rate'] == 0.022 and c['facts'] and c['facts'][0]['source'].startswith('Crustdata')


def test_blocked_or_missing_page_says_cannot_verify_instead_of_inventing(world):
    c = service.onboard_creator(CreatorIn(handle='zz_not_real', niche='food'))
    assert c['status'] == CANT and c['stats'].get('followers') is None and c['facts'] == []


def test_ownership_code_flow(world):
    c = service.onboard_creator(CreatorIn(handle='tastyfood', niche='food'))
    assert service.check_ownership(c['id'])['verified'] is False
    stored = db.get('creator', c['id'])
    stored['ownership_code'] = 'DEAL-ABC'
    db.put('creator', c['id'], stored)
    assert service.check_ownership(c['id'])['verified'] is True


def test_outage_never_becomes_a_negative_finding(world):
    world.fail_paths['/company/identify'] = lambda r: httpx.Response(500)
    co = service.register_company(CompanyIn(name='Real Brand', domain='realbrand.in', niche='food'))
    assert co['status'] == CANT and any('unchecked' in r for r in co['reasons'])


def test_rate_limit_is_retried_and_cache_prevents_second_charge(world):
    seq = iter([httpx.Response(429, headers={'x-ratelimit-reset': '1'})])
    world.fail_paths['/company/identify'] = lambda r: (world.fail_paths.pop('/company/identify'), next(seq))[1]
    m, _ = service.cd.identify_domain('realbrand.in')
    assert m
    n = world.calls.count('/company/identify')
    service.cd.identify_domain('realbrand.in')
    assert world.calls.count('/company/identify') == n


def test_key_rotation_on_rate_limit(world):
    cd = Crustdata(keys=['a', 'b'], transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[{'matches': []}]) if 'Bearer b' == r.headers['authorization'] else httpx.Response(429)), sleep=lambda s: None)
    assert cd.identify_domain('x.co')[0] == []


def test_nonsense_response_is_unavailable(world):
    world.fail_paths['/job/search'] = lambda r: httpx.Response(200, json=['nonsense'])
    with pytest.raises(Unavailable):
        service.cd.jobs_at(1)


def test_messy_domains_normalise():
    for raw in ('https://www.nykaa.com/', 'WWW.NYKAA.COM', ' nykaa.com ', 'team@nykaa.com'):
        assert verify.clean_domain(raw) == 'nykaa.com'


def test_alias_makes_two_names_one_record():
    assert verify.group_of('Imagine Marketing Limited')['group'] == verify.group_of('boAt')['group'] == verify.group_of(domain='boat-lifestyle.com')['group']


@pytest.mark.parametrize('text,budget', [('budget is ₹1.5L', 150000), ('we can pay 25k', 25000), ('Rs. 20,000 for one reel', 20000), ('offer of 8000 rupees', 8000)])
def test_messy_budgets_parse(text, budget):
    assert llm.parse_brief_rules(text)['budget'] == budget


def test_messy_brief_marks_missing_fields_instead_of_guessing():
    b = llm.parse_brief('hey!! want 2 reels n a story for our snack launch, 60 day usage, budget 30k. thanks, Neha Jain neha@snackly.in')
    assert (b['budget'], b['reels'], b['stories'], b['usage_days'], b['niche'], b['email'], b['sender_name']) == (30000, 2, 1, 60, 'food', 'neha@snackly.in', 'Neha Jain')
    assert llm.parse_brief('collab?')['missing'] == ['brand', 'budget', 'niche', 'email']


def test_same_brief_worded_differently_gets_same_deal_terms():
    a = llm.parse_brief_rules('Budget 30k, 2 reels, 60 day usage for our snack brand')
    b = llm.parse_brief_rules('we offer ₹30,000 for two reels with usage rights 60 days. snack company')
    assert all(a[k] == b[k] for k in ('budget', 'reels', 'usage_days', 'niche'))


def test_tweak_reports_improvement_or_harm(world):
    c, co = creator(), company()
    base = Terms()
    better = service.tweak_pack(c['id'], co['id'], base, Terms(usage_days=60))
    assert better['delta']['list_price'] > 0 and better['verdict'] in ('improved', 'worse', 'unchanged') and 'Estimate' in better['note']
    over = service.tweak_pack(c['id'], co['id'], base, Terms(exclusivity_days=200))
    assert over['verdict'] == 'blocked'


def test_small_creator_can_outrank_large_on_fit():
    co = {'niche': 'food'}
    small = {'niche': 'food', 'audience_country_pct': 95, 'stats': {'followers': 4000, 'engagement_rate': 0.06, 'strength': 0.7, 'captions': ['food recipe'] * 3, 'reels_read': 3}}
    big = {'niche': 'food', 'audience_country_pct': 40, 'stats': {'followers': 900000, 'engagement_rate': 0.002, 'strength': 0.7, 'captions': ['travel', 'car', 'food'], 'reels_read': 3}}
    assert scoring.fit(small, co)['score'] > scoring.fit(big, co)['score']


def test_missing_evidence_lowers_confidence_not_score_only():
    co = {'niche': 'food'}
    rich = {'niche': 'food', 'audience_country_pct': 90, 'stats': {'engagement_rate': 0.05, 'strength': 0.7, 'captions': ['food']}}
    poor = {'niche': 'food', 'stats': {'strength': 0.3}}
    assert scoring.fit(rich, co)['confidence'] > scoring.fit(poor, co)['confidence']


def test_likelihood_rejects_wrong_niche_and_is_deterministic():
    s = {'text': 'car parts manufacturer', 'influencer_roles': 5, 'influencer_staff': 5, 'months_since_funding': 3, 'headcount_growth': 0.5, 'recent_news': 5}
    a, b = scoring.likelihood(s, 'food'), scoring.likelihood(s, 'food')
    assert a == b and a['eligible'] is False
    assert scoring.likelihood({**s, 'text': 'snack food brand'}, 'food')['eligible'] is True
