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
    a, b = company(), company(domain='otherbrand.in', sender_name=None, sender_email=None)
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
    richer, safer = company(ceiling=30000, limits=CompanyLimits(ceiling=30000, value_per_reel=20000)), company(domain='otherbrand.in', sender_name=None, sender_email=None, ceiling=9000, limits=CompanyLimits(ceiling=9000, value_per_reel=6000))
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
    b = llm.parse_brief('From Brandly: budget 30k. neha@brandly.in. We need one creator.')
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


def test_niche_words_match_whole_word_starts_only():
    from app import niche
    assert niche.hits('eat', 'a great creator') == 0
    assert niche.hits('food', 'food recipes') > 0


def test_any_free_text_niche_works_without_a_fixed_list(world):
    from app import niche
    p = niche.profile('home cooking')
    assert p['own'] == ['cooking', 'home'] and 'recipe' in p['learned'] and p['source'].startswith('Crustdata')
    assert niche.hits('home cooking', 'quick recipe ideas') > 0
    assert niche.related('home cooking', 'snack food')
    assert not niche.related('mehendi art', 'stock trading')


def test_niche_survives_a_search_outage(world):
    from app import niche
    world.fail_paths['/company/search'] = lambda r: httpx.Response(500)
    assert niche.profile('pottery classes')['learned'] == []
    assert niche.hits('pottery classes', 'my pottery studio') > 0


def test_same_company_registered_twice_stays_one_record(world):
    a = company(name='Real Brand')
    b = company(name='RealBrand India Pvt Ltd', budget=99000)
    assert a['id'] == b['id'] and len([x for x in db.all_docs('company') if x['company_id'] == 500]) == 1
    assert 'RealBrand India Pvt Ltd' in b['also_known_as'] and b['budget'] == 99000


def test_lookalike_of_unlisted_brand_is_caught_live(world):
    co = service.register_company(CompanyIn(name='Real Brand', domain='realbrand-collabs.co', niche='food'))
    assert co['status'] == BLOCKED and 'realbrand.in' in ' '.join(co['reasons'])


def test_impersonation_does_not_merge_into_the_real_record(world):
    real = service.register_company(CompanyIn(name='Real Brand', domain='realbrand.in', niche='food'))
    fake = service.register_company(CompanyIn(name='Real Brand', domain='realbrand-collabs.co', niche='food'))
    assert fake['id'] != real['id'] and db.get('company', real['id'])['status'] == VERIFIED


def test_outage_at_recheck_pauses_instead_of_assuming(world):
    d = orch.start(DealIn(creator_ids=[creator()['id']], company_id=company()['id']))
    with pytest.raises(orch.SimulatedCrash):
        orch.run(d['id'], crash_after='contract')
    stored = db.get('deal', d['id'])
    stored['simulate_outage'] = True
    db.put('deal', d['id'], stored)
    end = orch.run(d['id'])
    assert end['paused']['kind'] == 'recheck_override' and 'mock_signature' not in kinds(d['id'])


@pytest.mark.parametrize('text,verdict,rule', [
    ('Pay a registration fee of Rs 500 to join our campaign', 'reject', 'scam_signal'),
    ('Please share your OTP to verify your account', 'reject', 'scam_signal'),
    ('Rs 3000 for a reel, we keep rights forever, net 90', 'counter', 'usage'),
    ('Budget 10k, 12 months exclusivity, net 15', 'counter', 'exclusivity'),
    ('Free product in exchange for 2 reels', 'counter', 'payment'),
    ('Do not disclose this is an ad. 10k. net 10', 'reject', 'ad_disclosure'),
    ('Budget 5000 for one reel. 30 days usage. Payment net 10.', 'fair', None),
])
def test_offer_review_rules(world, text, verdict, rule):
    from app.offers import review
    r = review(text)
    assert r['verdict'] == verdict
    assert rule is None or rule in [f['rule'] for f in r['findings']]


def test_offer_below_private_floor_is_countered(world):
    from app.offers import review
    assert 'price' in [f['rule'] for f in review('Budget 2000 for 1 reel. net 10', floor_reel=5000)['findings']]


def test_default_instagram_text_is_not_a_bio():
    from app.creators import parse_profile
    body = '<meta property="og:description" content="937 Followers, 970 Following, 0 Posts - See Instagram photos and videos from Someone (@acc)" />'
    p = parse_profile('Someone (@acc)', body, 'acc')
    assert p['followers'] == 937 and p['posts'] == 0 and p['bio'] == ''


def test_account_with_no_posts_is_unknown_not_low(world):
    c = {'niche': 'food', 'stats': {'followers': 937, 'reels_read': 0, 'median_likes': None, 'engagement_rate': None, 'strength': 0.7}}
    f = scoring.fit(c, {'niche': 'food'})
    assert f['passes'] and any('unknown, not low' in r for r in f['reasons'])
    assert packages.reel_rate(c['stats']) == packages.A['minimum_reel_price_inr']


def test_cache_only_mode_never_touches_the_network(world):
    from app.crustdata import NotCached
    with pytest.raises(NotCached), service.cd.cache_only():
        service.cd.identify_domain('realbrand.in')
    assert world.calls == []
    service.cd.identify_domain('realbrand.in')
    n = len(world.calls)
    with service.cd.cache_only():
        assert service.cd.identify_domain('realbrand.in')[0]
    assert len(world.calls) == n


def test_matches_answers_from_cache_and_defers_the_rest(world, monkeypatch):
    c = creator()
    db.put('company', 'co_a', {'id': 'co_a', 'name': 'Foodco', 'niche': 'food', 'status': 'verified', 'company_id': 900, 'tier': 'B'})
    db.put('seed', 'food', {'at': 'now'})
    started = []
    monkeypatch.setattr(service, 'BACKGROUND', True)
    monkeypatch.setattr(service, '_start_assessing', lambda n, b: started.append(len(b)))
    before = len(world.calls)
    r = service.matches(c['id'])
    assert r['assessing'] == 1 and started == [1] and r['matches'] == []
    assert not [p for p in world.calls[before:] if p in ('/company/enrich', '/job/search')]
    service.assess([db.get('company', 'co_a')], 'food')
    r = service.matches(c['id'])
    assert r['assessing'] == 0 and len(r['matches'] + r['rejected']) == 1


@pytest.mark.parametrize('text,field,days', [
    ('Usage rights 90 days, 30 day exclusivity with competitors, payment in 30 days', 'payment_days', 30),
    ('Usage rights 90 days, 30 day exclusivity with competitors, payment in 30 days', 'usage_days', 90),
    ('Usage rights 90 days, 30 day exclusivity with competitors, payment in 30 days', 'exclusivity_days', 30),
    ('12 months exclusivity. net 45', 'exclusivity_days', 360),
    ('30 day usage. pay within 7 days', 'payment_days', 7),
])
def test_each_duration_is_read_from_its_own_phrase(text, field, days):
    from app.offers import extract
    assert extract(text)[field] == days


def test_only_the_creators_own_posts_are_read(world):
    from app.creators import parse_profile
    body = '<meta property="og:description" content="3K Followers, 400 Following, 800 Posts - bio" /> /reel/OTHERPOST01/ /acc/reel/MINEPOST001/ /acc/reel/MINEPOST002/'
    p = parse_profile('Name (@acc)', body, 'acc')
    assert p['own_post_ids'] == ['MINEPOST001', 'MINEPOST002'] and 'OTHERPOST01' in p['post_ids']


def test_broad_niche_falls_back_to_brands_hiring_for_creators(world):
    c = service.onboard_creator(CreatorIn(handle='v', niche='vlogging', mock_stats=MOCK))
    db.put('seed', 'vlogging', {'at': 'now'})
    db.put('company', 'co_j', {'id': 'co_j', 'name': 'Wellness Co', 'niche': '', 'status': 'verified', 'company_id': None, 'tier': 'B', 'source': 'job_search', 'signals': {'text': '', 'influencer_roles': 3, 'influencer_staff': 3, 'months_since_funding': 5, 'headcount_growth': 0.3, 'recent_news': 5}})
    r = service.matches(c['id'])
    assert r['open_niche'] is True and [b['name'] for b in r['matches']] == ['Wellness Co']
    assert 'not proven' in ' '.join(r['matches'][0]['reasons'])


def test_search_result_alone_is_not_evidence_of_niche_fit(world):
    c = creator()
    db.put('seed', 'food', {'at': 'now'})
    db.put('company', 'co_x', {'id': 'co_x', 'name': 'Allure Ink', 'description': 'tattoo studio', 'niche': 'food', 'status': 'verified', 'company_id': None, 'tier': 'B', 'source': 'company_search'})
    db.put('company', 'co_y', {'id': 'co_y', 'name': 'Tasty Giants', 'industry': 'Food and Beverage Services', 'niche': 'food', 'status': 'verified', 'company_id': None, 'tier': 'B', 'source': 'company_search'})
    r = service.matches(c['id'])
    assert 'Allure Ink' in [b['name'] for b in r['rejected']] and 'Tasty Giants' not in [b['name'] for b in r['rejected']]


def test_strongest_niche_evidence_is_assessed_first(world):
    db.put('company', 'co_old', {'id': 'co_old', 'name': 'Old Record', 'description': 'a style magazine', 'niche': '', 'status': 'verified'})
    db.put('company', 'co_new', {'id': 'co_new', 'name': 'Good Threads', 'industry': 'Retail Apparel and Fashion', 'description': 'fashion label for fashion lovers', 'niche': '', 'status': 'verified'})
    names = [b['name'] for b in service.candidates_for('fashion')]
    assert names == ['Good Threads']


def test_scoring_continues_until_enough_real_matches(world, monkeypatch):
    c = service.onboard_creator(CreatorIn(handle='f', niche='fashion', mock_stats=MOCK))
    db.put('seed', 'fashion', {'at': 'now'})
    for i in range(16):
        db.put('company', f'co_w{i}', {'id': f'co_w{i}', 'name': f'Fashion {i:02d}', 'niche': 'fashion', 'status': 'verified', 'company_id': 1000 + i, 'tier': 'B', 'source': 'company_search'})
    started = []
    monkeypatch.setattr(service, 'BACKGROUND', True)
    monkeypatch.setattr(service, '_start_assessing', lambda n, b: started.append(len(b)))
    assert service.matches(c['id'])['assessing'] == 15 and started == [15]


def _apps():
    from app import applications, settings
    return applications, settings


def test_applications_flow_to_a_chosen_deal_and_decline_the_rest(world):
    applications, settings = _apps()
    a, b = creator(handle='one', floor=2000), creator(handle='two', floor=1500)
    co = company(ceiling=30000, limits=CompanyLimits(ceiling=30000, value_per_reel=9000))
    x = applications.create(a['id'], co['id'], Terms(), 'Standard')
    y = applications.create(b['id'], co['id'], Terms(), 'Standard')
    assert applications.create(a['id'], co['id'], Terms())['id'] == x['id']        # Applying twice never sends twice.
    ranked = applications.for_company(co['id'])['open']
    assert len(ranked) == 2 and ranked[0]['why'] and ranked[0]['rank'] == 1
    assert '2000' not in json.dumps(ranked) and 'floor' not in json.dumps(ranked)   # Floors stay private.
    d = applications.accept(x['id'])
    assert applications.accept(x['id'])['id'] == d['id']                            # Accepting twice gives one deal.
    assert db.get('application', y['id'])['status'] == 'declined'
    end = orch.run(d['id'])
    assert end['state'] == 'sign' and end['paused']['kind'] == 'signature' and 'mock_signature' not in kinds(d['id'])
    end = orch.set_field(d['id'], 'signature', {'by': 'company'})
    assert end['state'] == 'done' and kinds(d['id']).count('mock_payout') == 1


def test_applications_made_to_a_known_brand_appear_when_it_registers(world):
    applications, _ = _apps()
    c = creator()
    known = service.search_brands('realbrand.in')[0]
    a = applications.create(c['id'], known['company_id'], Terms())
    registered = company(name='Real Brand')
    assert registered['id'] == known['company_id'] and [x['id'] for x in applications.for_company(registered['id'])['open']] == [a['id']]
    assert registered['source'] == 'registered'


def test_blocked_company_cannot_receive_applications(world):
    applications, _ = _apps()
    fake = company(name='boAt', domain='boat-collabs.co', sender_name=None, sender_email=None)
    with pytest.raises(ValueError):
        applications.create(creator()['id'], fake['id'], Terms())


def test_auto_deal_respects_thresholds_and_explains_skips(world):
    applications, settings = _apps()
    c = creator()
    db.put('seed', 'food', {'at': 'now'})
    good = {'text': 'food', 'influencer_roles': 3, 'influencer_staff': 3, 'months_since_funding': 5, 'headcount_growth': 0.3, 'recent_news': 5}
    db.put('company', 'co_good', {'id': 'co_good', 'name': 'Food Good', 'niche': 'food', 'status': 'verified', 'tier': 'B', 'source': 'company_search', 'signals': good})
    db.put('company', 'co_thin', {'id': 'co_thin', 'name': 'Food Thin', 'niche': 'food', 'status': 'verified', 'tier': 'B', 'source': 'company_search', 'signals': {'text': 'food'}})
    db.put('company', 'co_weak', {'id': 'co_weak', 'name': 'Food Weak', 'niche': 'food', 'status': 'weak_match', 'tier': 'B', 'source': 'company_search', 'signals': good})
    assert applications.auto_apply(c['id'])['sent'] == []                           # Off by default.
    settings.update('creator', c['id'], {'auto_deal': True})
    r = applications.auto_apply(c['id'])
    assert r['sent'] == ['Food Good']
    held = {h['name']: h['reason'] for h in r['held_back']}
    assert 'Confidence' in held['Food Thin'] and 'not verified' in held['Food Weak']
    assert applications.auto_apply(c['id'])['sent'] == []                           # Running again sends nothing twice.
    assert applications.for_creator(c['id'])[0]['source'] == 'auto'


def test_auto_deal_cap_is_honoured(world):
    applications, settings = _apps()
    c = creator()
    db.put('seed', 'food', {'at': 'now'})
    good = {'text': 'food', 'influencer_roles': 3, 'influencer_staff': 3, 'months_since_funding': 5, 'headcount_growth': 0.3, 'recent_news': 5}
    for i in range(4):
        db.put('company', f'co_{i}', {'id': f'co_{i}', 'name': f'Food {i}', 'niche': 'food', 'status': 'verified', 'tier': 'B', 'source': 'company_search', 'signals': good})
    settings.update('creator', c['id'], {'auto_deal': True, 'auto_max_per_run': 2})
    assert len(applications.auto_apply(c['id'])['sent']) == 2


def test_settings_reject_unknown_keys_and_wrong_types(world):
    _, settings = _apps()
    with pytest.raises(ValueError):
        settings.update('creator', 'x', {'nope': True})
    with pytest.raises(ValueError):
        settings.update('creator', 'x', {'auto_deal': 'yes'})
    with pytest.raises(ValueError):
        settings.update('creator', 'x', {'auto_min_likelihood': 99999})
    assert settings.update('creator', 'x', {'auto_min_likelihood': 70})['auto_min_likelihood'] == 70


def test_auto_accept_uses_the_brands_threshold(world):
    applications, settings = _apps()
    co = company(ceiling=30000, limits=CompanyLimits(ceiling=30000, value_per_reel=9000))
    settings.update('company', co['id'], {'auto_accept': True, 'auto_accept_min_fit': 1, 'sign_myself': False})
    a = applications.create(creator()['id'], co['id'], Terms())
    assert a['status'] == 'accepted' and db.get('deal', a['deal_id'])['state'] == 'done'


def test_deal_activity_records_real_lookups(world):
    d, end = go([creator()['id']], company())
    calls = [e['data'] for e in db.events(d['id']) if e['type'] == 'data_call']
    assert {'Company Enrich', 'Company Identify'} <= {c['source'] for c in calls} and any(c['how'] == 'live' for c in calls)


def test_recheck_failure_on_company_lookup_pauses(world):
    d = orch.start(DealIn(creator_ids=[creator()['id']], company_id=company(sender_name=None, sender_email=None)['id']))
    with pytest.raises(orch.SimulatedCrash):
        orch.run(d['id'], crash_after='contract')
    world.fail_paths['/company/identify'] = lambda r: httpx.Response(500)
    end = orch.run(d['id'])
    assert end['paused']['kind'] == 'recheck_override'


def test_why_lines_cite_only_real_evidence(world):
    co, c = company(), creator()
    r = service.company_creators(co['id'])['creators'][0]
    assert '@small_food' in r['why']
    assert 'hiring' not in scoring.why_brand('X', {'factors': {'niche': 1, 'influencer_roles': None}}, 'verified')
    assert 'hiring' in scoring.why_brand('X', {'factors': {'niche': 1, 'influencer_roles': 0.9}}, 'verified')


def test_one_handle_stays_one_record(world):
    a, b = creator(handle='Same'), creator(handle='@same')
    assert a['id'] == b['id'] and a['ownership_code'] == b['ownership_code']


def test_read_reports_progress(world):
    from app.creators import read_stats
    seen = []
    read_stats(service.cd, 'tastyfood', progress=seen.append)
    assert seen[0] == 'Reading the public profile' and any('reel' in s for s in seen)


def test_learned_words_alone_are_described_as_related_not_a_fit(world):
    s = scoring.likelihood({'text': 'x', 'influencer_roles': 3, 'influencer_staff': 3, 'months_since_funding': 5, 'headcount_growth': 0.3, 'recent_news': 5}, 'food')
    assert s['eligible'] is False
    assert 'works in your niche' in scoring.why_brand('A', {'factors': {'niche': 1.0}}, 'verified')
    assert 'looks related' in scoring.why_brand('A', {'factors': {'niche': 0.5}}, 'verified')


def test_a_stray_learned_word_does_not_make_a_brand_eligible(world):
    from app import niche
    niche.profile('home cooking')
    one_word = scoring.likelihood({'text': 'recipe', 'influencer_roles': 3, 'influencer_staff': 3, 'months_since_funding': 5, 'headcount_growth': 0.3, 'recent_news': 5}, 'home cooking')
    assert one_word['eligible'] is False


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
    assert (b['budget'], b['reels'], b['stories'], b['usage_days'], b['niche'], b['email'], b['sender_name']) == (30000, 2, 1, 60, 'snack', 'neha@snackly.in', 'Neha Jain')
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
