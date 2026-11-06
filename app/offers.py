"""Reviews an offer a creator received: extracts its terms, compares them with published rules, proposes changes.
Rules live in config.OFFER_RULES and every finding cites one. Code decides; nothing here needs an LLM."""
import re

from . import config, llm
from .verify import verify_brand, verify_sender

R = config.OFFER_RULES
SCAMS = [
    (r'(registration|security|joining|processing|onboarding)\s+(fee|deposit|charge)|pay\s+(us|a\s+fee|first|upfront\s+to)|deposit\s+(of|first)', 'Asks the creator to pay money. Real brands pay creators.'),
    (r'\botp\b|password|login (details|credentials)|verify your (account|login)|share your (login|password)', 'Asks for a password, OTP or login. Never share these.'),
    (r'(click|open|download).{0,30}(apk|\.exe|\.zip|\.scr)|install (our|this) (app|tool|software)', 'Asks you to install software or open a file. This is a common account-theft trick.'),
    (r'(whatsapp|telegram) (only|me on)|only (on|via) (whatsapp|telegram)|guaranteed (income|earning)|earn .{0,12}daily', 'Moves the deal to private chat or promises guaranteed earnings.'),
]


def _days(text: str, *words) -> int | None:
    w = '|'.join(words)
    # A number only belongs to a word if no comma, full stop or other number sits between them.
    m = re.search(rf'(\d+)\s*[- ]?\s*(day|week|month|year)s?\b[^.,;\d\n]{{0,25}}\b(?:{w})', text) or re.search(rf'\b(?:{w})\b[^.,;\d\n]{{0,30}}?(\d+)\s*[- ]?\s*(day|week|month|year)s?', text)
    return int(m[1]) * {'day': 1, 'week': 7, 'month': 30, 'year': 365}[m[2]] if m else None


def extract(text: str) -> dict:
    t = text.lower().replace(',', '')
    b = llm.parse_brief_rules(text)
    perpetual = any(re.search(r'perpetu|forever|in perpetuity|lifetime (rights|usage)|unlimited usage|all rights|full ownership|buyout', s) and not re.search(r"\bnot\b|\bno\b|\bwithout\b|\bnever\b", s) for s in re.split(r'(?<=[.!?\n])\s*', t))
    pay = re.search(r'net\s*-?\s*(\d+)', t)
    pay_days = int(pay[1]) if pay else _days(t, 'payment', 'paid', 'pay', 'pays', 'paying', 'invoice')
    return {'budget': b['budget'], 'email': b['email'], 'brand': b['brand'], 'sender_name': b['sender_name'], 'reels': b['reels'], 'stories': b['stories'],
            'usage_days': None if perpetual else _days(t, 'usage', 'rights', 'licen[cs]e', 'reuse'), 'usage_perpetual': perpetual,
            'exclusivity_days': _days(t, 'exclusiv\\w*', 'non-compete'), 'payment_days': pay_days,
            'kill_fee': True if re.search(r'kill fee|cancellation fee', t) and not re.search(r'no (kill|cancellation) fee', t) else False if re.search(r'no (kill|cancellation) fee', t) else None,
            'unlimited_revisions': bool(re.search(r'unlimited (revision|edit|change)|as many (revision|edit|change)', t)), 'barter_only': bool(re.search(r'barter|free product|product only|gift(ed)? (only|in exchange)|exposure', t)) and not b['budget'],
            'no_disclosure': bool(re.search(r"(don't|do not|no need to|without) (disclos|tag\w* (as )?(ad|paid)|mention\w* (paid|sponsor|ad))|hide (that|the) (it|ad|sponsor)", t))}


def review(text: str, floor_reel: int | None = None, cd=None) -> dict:
    x, low = extract(text), text.lower()
    findings = []

    def add(severity, rule, problem, change):
        findings.append({'severity': severity, 'rule': rule, 'problem': problem, 'proposed_change': change})
    for pattern, why in SCAMS:
        if re.search(pattern, low):
            add('reject', 'scam_signal', why, 'Do not respond. Report it.')
    if x['usage_perpetual']:
        add('change', 'usage', 'Asks for usage rights forever.', f"Limit usage to {R['max_usage_days']} days, priced separately beyond that.")
    elif x['usage_days'] and x['usage_days'] > R['max_usage_days']:
        add('change', 'usage', f"{x['usage_days']} days of usage is above the {R['max_usage_days']}-day limit.", f"Reduce to {R['max_usage_days']} days or charge for the extra period.")
    if x['exclusivity_days'] and x['exclusivity_days'] > R['max_exclusivity_days']:
        add('change', 'exclusivity', f"{x['exclusivity_days']} days of exclusivity is above the {R['max_exclusivity_days']}-day limit.", f"Reduce to {R['max_exclusivity_days']} days and limit it to direct competitors, for a fee.")
    if x['payment_days'] and x['payment_days'] > R['max_payment_days']:
        add('change', 'payment_terms', f"Payment in {x['payment_days']} days is above the {R['max_payment_days']}-day limit.", 'Hold funds upfront and release them on approval.')
    if x['payment_days'] is None:
        add('ask', 'payment_terms', 'No payment date is stated.', 'Agree on a payment date, with funds held upfront.')
    if x['kill_fee'] is False or x['kill_fee'] is None and x['budget'] and x['budget'] >= R['kill_fee_above']:
        add('change' if x['kill_fee'] is False else 'ask', 'kill_fee', 'There is no fee if the brand cancels after work starts.', 'Add a kill fee: the creator keeps the amount held for work done.')
    if x['unlimited_revisions']:
        add('change', 'revisions', 'Asks for unlimited revisions.', f"Limit to {R['max_revisions']} rounds, charging for more.")
    if x['barter_only']:
        add('change', 'payment', 'Offers product or exposure, not money.', 'Ask for cash, or compare the product value with your floor before accepting.')
    if x['no_disclosure']:
        add('reject', 'ad_disclosure', 'Asks to hide that this is paid. ASCI guidelines require disclosure.', 'Decline unless the post is disclosed.')
    if floor_reel and x['budget'] and x['budget'] < floor_reel * (x['reels'] or 1):
        add('change', 'price', 'The offer is below your floor.', 'Counter at or above your floor.')
    if x['budget'] is None and not x['barter_only']:
        add('ask', 'price', 'No price is stated.', 'Ask for a budget before doing any work.')

    verification = None
    if cd and (x['email'] or x['brand']):
        v = verify_brand(cd, x['brand'], x['email'])
        s = verify_sender(cd, x['sender_name'], x['email'], v['company_id'], v['domain']) if x['sender_name'] else {'status': 'cannot_verify', 'reasons': ['No sender named.'], 'facts': []}
        verification = {'brand_status': v['status'], 'sender_status': s['status'], 'reasons': v['reasons'] + s['reasons'], 'facts': v['facts'] + s['facts']}
        if v['status'] == 'blocked':
            add('reject', 'identity', ' '.join(v['reasons']), 'Do not respond. This looks like impersonation.')
        elif s['status'] == 'contact_left':
            add('change', 'identity', ' '.join(s['reasons']), 'Confirm with the company through its official site before continuing.')
    sev = {f['severity'] for f in findings}
    verdict = 'reject' if 'reject' in sev else 'counter' if 'change' in sev else 'clarify' if 'ask' in sev else 'fair'
    return {'verdict': verdict, 'terms': x, 'findings': findings, 'verification': verification, 'note': 'Automated review from published rules. Not legal advice.'}
