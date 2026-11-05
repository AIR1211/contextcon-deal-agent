"""Verification ladder. Missing data never counts as guilt, and a name match never counts as identity."""
import json
import re

from . import config
from .creators import read_profile
from .crustdata import Crustdata, Unavailable
from .models import BLOCKED, CANT, Fact, LEFT, PARTLY, VERIFIED, WEAK, now

FREE_MAIL = {'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'proton.me', 'protonmail.com', 'icloud.com', 'rediffmail.com'}
GSTIN = re.compile(r'^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')
ALIASES = json.loads((config.DATA / 'aliases.json').read_text(encoding='utf8'))


def clean_domain(value: str | None) -> str | None:
    """Accepts a domain, URL or email in any messy form."""
    if not value:
        return None
    v = value.strip().lower().split('@')[-1]
    v = re.sub(r'^[a-z]+://', '', v).split('/')[0].split('?')[0]
    v = re.sub(r'^www\.', '', v).strip('. ')
    return v if '.' in v and ' ' not in v else None


def norm(name: str | None) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'\b(pvt|private|ltd|limited|llp|inc|the)\b|[^\w\s-]', ' ', (name or '').lower())).strip()


def group_of(name=None, domain=None) -> dict | None:
    """Resolves two names for one company to one record."""
    n, d = norm(name), clean_domain(domain)
    for a in ALIASES:
        if (d and d == a['domain']) or (n and n in a['names']):
            return a
    return None


def _lookalike(domain: str, name: str | None) -> dict | None:
    """A known brand's name inside a domain that is not its real domain."""
    stem = re.sub(r'[^a-z0-9]', '', domain.rsplit('.', 1)[0])
    for a in ALIASES:
        if a['domain'] == domain:
            continue
        real = re.sub(r'[^a-z0-9]', '', a['domain'].rsplit('.', 1)[0])
        tokens = {real} | {x.replace(' ', '').replace('-', '') for x in a['names'] if len(x) >= 4}
        if any(t in stem for t in tokens) or norm(name) in a['names']:
            return a
    return None


def _claimed_domain(cd: Crustdata, domain: str, name: str | None) -> dict | None:
    """Live check for brands not in the alias table: the claimed name resolves to a different real domain,
    and this domain contains that name."""
    token = re.sub(r'[^a-z0-9]', '', norm(name))
    if len(token) < 4 or token not in re.sub(r'[^a-z0-9]', '', domain):
        return None
    try:
        m, _ = cd.identify_name(name)
    except Unavailable:
        return None
    for x in m[:3]:
        real = clean_domain(x['company_data']['basic_info'].get('primary_domain'))
        if real and real != domain and x.get('confidence_score', 0) >= 0.9 and token in re.sub(r'[^a-z0-9]', '', real):
            return {'domain': real}
    return None


def verify_brand(cd: Crustdata, name=None, domain=None, instagram=None, gstin=None, bio_code_seen=False) -> dict:
    d = clean_domain(domain)
    subject = name or d or instagram or 'company'
    out = {'status': CANT, 'name': name, 'domain': d, 'company_id': None, 'group': None, 'facts': [], 'reasons': []}
    facts = out['facts']
    alias = group_of(name, d)
    if alias:
        out['group'] = alias['group']
        facts.append(Fact(subject=subject, field='group', value=alias['group'], source=alias['source']).model_dump())

    if d and d not in FREE_MAIL:
        try:
            m, ts = cd.identify_domain(d)
        except Unavailable as e:
            out['reasons'].append(f'Could not reach Crustdata ({e}), so the domain is unchecked.')
            m, ts = None, now()
        if m:
            b = m[0]['company_data']['basic_info']
            out.update(company_id=m[0]['company_data']['crustdata_company_id'], name=b.get('name') or name, status=VERIFIED)
            facts.append(Fact(subject=subject, field='company', value=b.get('name'), source='Crustdata Company Identify', as_of=ts, url=b.get('website')).model_dump())
            claimed = group_of(name)
            if claimed and claimed['domain'] != d:
                out['status'] = BLOCKED
                out['reasons'].append(f"Claims to be {name}, but {d} belongs to {b.get('name')}.")
                return out
            out['reasons'].append(f"{d} resolves to {b.get('name')}.")
            return out
        if m is not None:
            facts.append(Fact(subject=subject, field='domain', value='no match', source='Crustdata Company Identify', as_of=ts, strength=CANT).model_dump())
            real = _lookalike(d, name) or _claimed_domain(cd, d, name)
            if real:
                out['status'] = BLOCKED
                out['reasons'].append(f"{d} looks like {real['domain']} but is not that company's domain.")
                return out
            out['reasons'].append(f'{d} has no company record.')
    elif group_of(name):
        out['reasons'].append(f'Claims to be {name} without using that company\'s domain.')

    if gstin:
        ok = bool(GSTIN.match(gstin.strip().upper()))
        facts.append(Fact(subject=subject, field='gstin_format', value=ok, source='GSTIN format check; registry lookup is mocked', strength=PARTLY if ok else CANT, is_mock=True).model_dump())
        if ok:
            out['status'] = PARTLY
            out['reasons'].append('GSTIN format is valid. Registry lookup is mocked in this build.')
    if instagram:
        try:
            p = read_profile(cd, instagram)
        except Unavailable as e:
            p = None
            out['reasons'].append(f'Could not read Instagram ({e}).')
        if p:
            facts.append(Fact(subject=subject, field='instagram_followers', value=p['followers'], source='Crustdata Web Fetch, public Instagram page', as_of=p['as_of'], strength=PARTLY, url=p['url']).model_dump())
            if p['posts'] >= 10 and bio_code_seen:
                out['status'] = PARTLY
                out['reasons'].append(f"Instagram page has {int(p['posts'])} posts, and the owner proved control with a bio code.")
            elif out['status'] != PARTLY:
                out['status'] = WEAK
                out['reasons'].append('Instagram page exists, but ownership is not proven yet.')
    if out['status'] == CANT and not out['reasons']:
        out['reasons'].append('No evidence could be checked.')
    return out


def verify_sender(cd: Crustdata, name, email, company_id, company_domain, profile_url=None, fresh=False) -> dict:
    """Verified needs a work-domain email, exactly one matching profile, and career history that agrees."""
    out = {'status': CANT, 'reasons': [], 'facts': [], 'profiles_found': 0}
    subject = name or email or 'sender'
    if not name or not company_id:
        out['reasons'].append('Sender name or company is missing, so the sender is unchecked.')
        return out
    work_email = bool(email and company_domain and clean_domain(email) == company_domain)
    try:
        cur, ts = cd.person_at(name, company_id, fresh=fresh)
        past = cd.person_at(name, company_id, past=True, fresh=fresh)[0] if not cur else []
    except Unavailable as e:
        out['reasons'].append(f'Could not reach Crustdata ({e}).')
        return out
    out['profiles_found'] = len(cur)
    if not cur and past:
        out['status'] = LEFT
        out['reasons'].append(f'{name} is listed as a past employee, not a current one.')
        out['facts'].append(Fact(subject=subject, field='employment', value='past employee', source='Crustdata Person Search', as_of=ts, strength=LEFT).model_dump())
        return out
    if not cur:
        out['reasons'].append(f'No profile found for {name} at this company.')
        return out
    out['facts'].append(Fact(subject=subject, field='name_match', value=f'{len(cur)} profile(s)', source='Crustdata Person Search', as_of=ts, strength=WEAK).model_dump())
    out['status'] = WEAK
    if len(cur) > 1:
        out['reasons'].append(f'{len(cur)} profiles share this name here, so identity is unclear.')
        return out
    if not work_email:
        out['reasons'].append('Name matches a profile, but the email is not on the company domain. Same-name profiles are common.')
        return out
    url = profile_url or ((cur[0].get('social_handles') or {}).get('professional_network_identifier') or {}).get('profile_url')
    if not url:
        out['reasons'].append('Work email matches, but no profile link is available to check career history.')
        return out
    try:
        person, ets = cd.enrich_person(url, fresh=fresh)
    except Unavailable as e:
        out['reasons'].append(f'Career history could not be checked ({e}).')
        return out
    jobs = (((person or {}).get('experience') or {}).get('employment_details') or {}).get('current') or []
    if any(j.get('company_id') == company_id or j.get('crustdata_company_id') == company_id for j in jobs):
        out['status'] = VERIFIED
        out['reasons'].append('Work email, one matching profile, and current employment all agree.')
        out['facts'].append(Fact(subject=subject, field='current_employer', value=company_domain, source='Crustdata Person Enrich', as_of=ets, url=url).model_dump())
    else:
        out['reasons'].append('Career history does not confirm current employment here.')
    return out


def risk_tier(brand_status: str, sender_status: str) -> str:
    """Small is not the same as fake. Only blocked stops a deal outright."""
    if brand_status == BLOCKED or sender_status == BLOCKED:
        return 'blocked'
    if brand_status == VERIFIED and sender_status == VERIFIED:
        return 'A'
    if brand_status in (VERIFIED, PARTLY):
        return 'B'
    return 'C'
