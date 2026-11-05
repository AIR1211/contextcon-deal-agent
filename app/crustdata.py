"""Crustdata client: cache, retries, key rotation. Failures raise Unavailable so callers can say "can't verify"."""
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import config, db
from .models import now

BASE = 'https://api.crustdata.com'
CURRENT = 'experience.employment_details.current.company_id'
PAST = 'experience.employment_details.past.company_id'
PERSON_FIELDS = ['basic_profile.name', 'basic_profile.current_title', 'basic_profile.headline', 'social_handles.professional_network_identifier.profile_url']


class Unavailable(Exception):
    """The source could not answer. Never treat this as a negative finding."""


class Crustdata:
    def __init__(self, keys=None, transport=None, sleep=time.sleep):
        self.keys = list(keys if keys is not None else config.CRUSTDATA_KEYS)
        self.i = 0
        self.http = httpx.Client(timeout=45, transport=transport)
        self.sleep = sleep

    def _request(self, method: str, path: str, body=None):
        if not self.keys:
            raise Unavailable('no API key configured')
        last = 'unknown'
        for attempt in range(4):
            headers = {'authorization': f'Bearer {self.keys[self.i]}', 'x-api-version': '2025-11-01', 'content-type': 'application/json'}
            try:
                r = self.http.request(method, BASE + path, headers=headers, json=body)
            except httpx.HTTPError as e:
                last = f'network: {type(e).__name__}'
                self.sleep(min(2 ** attempt, 8))
                continue
            if r.status_code == 200 or r.status_code == 202:
                try:
                    return r.json(), float(r.headers.get('x-credits-used') or 0)
                except ValueError:
                    last = 'response was not JSON'
                    continue
            if r.status_code == 429:
                last = 'rate limited'
                if len(self.keys) > 1:
                    self.i = (self.i + 1) % len(self.keys)
                    continue
                try:
                    wait = float(r.headers.get('x-ratelimit-reset') or 2)
                except ValueError:
                    wait = 2
                wait = wait if wait < 90 else max(wait - time.time(), 1)
                self.sleep(min(wait, 60))
                continue
            if r.status_code == 402 and len(self.keys) > 1 and attempt < len(self.keys) - 1:
                self.i = (self.i + 1) % len(self.keys)
                last = 'out of credits'
                continue
            if r.status_code >= 500:
                last = f'server error {r.status_code}'
                self.sleep(min(2 ** attempt, 8))
                continue
            raise Unavailable(f'HTTP {r.status_code}')
        raise Unavailable(last)

    def post(self, path: str, body: dict, ttl_hours: float = config.CACHE_TTL_HOURS, fresh: bool = False):
        """Returns (data, as_of). fresh=True skips the cache, for checks right before signing."""
        key = hashlib.sha256((path + json.dumps(body, sort_keys=True)).encode()).hexdigest()
        hit = db.cache_get(key)
        if hit and not fresh:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(hit[1])
            if age < timedelta(hours=ttl_hours):
                return hit
        try:
            data, cr = self._request('POST', path, body)
        except Unavailable:
            if hit and not fresh:      # Stale data carries its old date, which the UI shows.
                return hit
            raise
        ts = now()
        db.cache_put(key, data, ts, cr)
        return data, ts

    def identify_domain(self, domain: str):
        d, ts = self.post('/company/identify', {'domains': [domain]})
        return _matches(d), ts

    def identify_name(self, name: str):
        d, ts = self.post('/company/identify', {'names': [name]})
        return _matches(d), ts

    def enrich_company(self, company_id: int, fresh=False):
        groups = ['basic_info', 'headcount', 'funding', 'revenue', 'web_traffic', 'people', 'news', 'hiring', 'taxonomy']
        d, ts = self.post('/company/enrich', {'crustdata_company_ids': [company_id], 'fields': groups}, fresh=fresh)
        m = _matches(d)
        return m[0]['company_data'] if m else None, ts

    def person_at(self, name: str, company_id: int, past=False, fresh=False):
        body = {'filters': {'op': 'and', 'conditions': [{'field': PAST if past else CURRENT, 'type': '=', 'value': company_id}, {'field': 'basic_profile.name', 'type': '=', 'value': name}]}, 'fields': PERSON_FIELDS, 'limit': 5}
        d, ts = self.post('/person/search', body, fresh=fresh)
        return _dict(d).get('profiles') or [], ts

    def contacts(self, company_id: int, limit=5):
        body = {'filters': {'op': 'and', 'conditions': [{'field': CURRENT, 'type': '=', 'value': company_id}, {'field': 'basic_profile.headline', 'type': '[.]', 'value': 'influencer'}]}, 'fields': PERSON_FIELDS, 'limit': limit}
        d, ts = self.post('/person/search', body)
        return _dict(d).get('profiles') or [], ts

    def enrich_person(self, profile_url: str, fresh=False):
        d, ts = self.post('/person/enrich', {'professional_network_profile_urls': [profile_url], 'fields': ['basic_profile', 'experience']}, fresh=fresh)
        m = _matches(d)
        return (m[0].get('person_data') or m[0]) if m else None, ts

    def influencer_jobs(self, limit=50, cursor=None):
        body = {'filters': {'op': 'and', 'conditions': [{'field': 'job_details.title', 'type': '[.]', 'value': 'influencer'}, {'field': 'location.country', 'type': '=', 'value': 'India'}]}, 'fields': ['job_details.title', 'company.basic_info.crustdata_company_id', 'company.basic_info.name', 'company.basic_info.primary_domain'], 'limit': limit}
        if cursor:
            body['cursor'] = cursor
        d, ts = self.post('/job/search', body)
        return _dict(d).get('job_listings') or [], ts, _dict(d).get('next_cursor')

    def jobs_at(self, company_id: int):
        body = {'filters': {'op': 'and', 'conditions': [{'field': 'company.basic_info.company_id', 'type': '=', 'value': company_id}, {'field': 'job_details.title', 'type': '[.]', 'value': 'influencer'}]}, 'fields': ['job_details.title'], 'limit': 5}
        d, ts = self.post('/job/search', body)
        return _dict(d).get('total_count') or 0, ts

    def small_brands(self, query: str, size='2-10', limit=25):
        body = {'search': {'query': query, 'mode': 'hybrid'}, 'filters': {'op': 'and', 'conditions': [{'field': 'locations.country', 'type': '=', 'value': 'India'}, {'field': 'basic_info.employee_count_range', 'type': '=', 'value': size}]}, 'fields': ['basic_info.name', 'basic_info.primary_domain', 'basic_info.employee_count_range', 'basic_info.description'], 'limit': limit}
        d, ts = self.post('/company/search', body)
        return _dict(d).get('companies') or [], ts

    def web_search(self, query: str, source='web'):
        d, ts = self.post('/web/search/live', {'query': query, 'sources': [source]})
        return _dict(d).get('results') or [], ts

    def fetch_page(self, url: str, fresh=False):
        """Returns (title, content, as_of). API success is not trusted: callers must check the fields they need."""
        d, ts = self.post('/web/enrich/live', {'urls': [url]}, ttl_hours=24, fresh=fresh)
        L = d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), []) if isinstance(d, dict) else []
        x = L[0] if L and isinstance(L[0], dict) else {}
        return x.get('title') or '', x.get('content') or '', ts

    def credits(self):
        return self._request('GET', '/account/credits')[0]['account']['credits']


def _dict(d):
    if not isinstance(d, dict):
        raise Unavailable('unexpected response shape')
    return d


def _matches(d):
    if not isinstance(d, list):
        raise Unavailable('unexpected response shape')
    return (d[0].get('matches') or []) if d and isinstance(d[0], dict) else []
