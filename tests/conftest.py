"""Tests run on a fake Crustdata and a temporary database. They spend no credits."""
import httpx
import pytest

from app import config, service
from app.crustdata import Crustdata

COMPANIES = {'boat-lifestyle.com': (628835, 'boAt Lifestyle'), 'realbrand.in': (500, 'Real Brand'), 'otherbrand.in': (501, 'Other Brand')}
EMPLOYED = {('Priya Shah', 500): 'current', ('Ravi Rao', 500): 'past', ('Same Name', 500): 'many', ('Aman Gupta', 628835): 'current'}


def og(desc, title='Page'):
    return {'title': title, 'content': f'<meta property="og:description" content="{desc}" />', 'success': True}


class World:
    """A small programmable stand-in for the API."""
    def __init__(self):
        self.fail_paths, self.calls, self.people = {}, [], dict(EMPLOYED)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        import json
        path, body = request.url.path, json.loads(request.content or b'{}')
        self.calls.append(path)
        if path in self.fail_paths:
            return self.fail_paths[path](request)
        return httpx.Response(200, json=self.answer(path, body), headers={'x-credits-used': '1'})

    def answer(self, path, body):
        if path == '/company/identify':
            d = (body.get('domains') or [None])[0]
            if body.get('names') and body['names'][0] == 'Real Brand':
                d = 'realbrand.in'
            if d in COMPANIES:
                cid, name = COMPANIES[d]
                return [{'matches': [{'confidence_score': 1, 'company_data': {'crustdata_company_id': cid, 'basic_info': {'name': name, 'primary_domain': d}}}]}]
            return [{'matches': []}]
        if path == '/company/search':
            q = body.get('search', {}).get('query', '')
            if 'home cooking' in q or 'snack' in q:
                return {'companies': [{'crustdata_company_id': 900 + i, 'basic_info': {'name': f'Foodco {i}', 'description': 'tasty recipe kitchen food', 'industries': ['food']}} for i in range(5)]}
            return {'companies': []}
        if path == '/person/search':
            conds = body['filters']['conditions']
            cid = conds[0]['value']
            past = 'past' in conds[0]['field']
            name = conds[1]['value'] if conds[1]['field'] == 'basic_profile.name' else None
            state = self.people.get((name, cid))
            n = 2 if state == 'many' and not past else 1 if (state == 'past') == past and state else 0
            return {'profiles': [{'basic_profile': {'name': name}, 'social_handles': {'professional_network_identifier': {'profile_url': f'https://linkedin.example/in/p{i}'}}} for i in range(n)]}
        if path == '/person/enrich':
            return [{'matches': [{'person_data': {'experience': {'employment_details': {'current': [{'company_id': 500}]}}}}]}]
        if path == '/company/enrich':
            return [{'matches': [{'company_data': {'basic_info': {'name': 'x'}}}]}]
        if path == '/job/search':
            return {'job_listings': [], 'total_count': 2}
        if path == '/web/enrich/live':
            url = body['urls'][0]
            if '/reel/' in url:
                return {'results': [og('100 likes, 10 comments - tastyfood on October 2, 2026: &quot;Spicy food recipe&quot;')]}
            if 'tastyfood' in url:
                return {'results': [{**og('5K Followers, 100 Following, 120 Posts - Food recipes DEAL-ABC', 'Tasty (@tastyfood) • Instagram'), 'content': og('5K Followers, 100 Following, 120 Posts - Food recipes DEAL-ABC')['content'] + '/reel/AAAAAAAAAA/ /reel/BBBBBBBBBB/'}]}
            return {'results': [{'title': 'Instagram', 'content': '<html>nothing</html>', 'success': True}]}
        return {}


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DB_PATH', str(tmp_path / 'test.db'))
    w = World()
    monkeypatch.setattr(service, 'cd', Crustdata(keys=['k1'], transport=httpx.MockTransport(w), sleep=lambda s: None))
    return w
