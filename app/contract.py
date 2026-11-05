"""Contract and invoice generation. A template with cited clauses, reviewed by a person before any real use."""
import hashlib
from datetime import date

from .config import FEE_BRAND, FEE_CREATOR

NOTICE = 'DRAFT FOR A HACKATHON DEMO. Not legal advice. E-signature and escrow are mocked.'


def gate_failures(deal: dict, company: dict, creators: list[dict]) -> list[str]:
    """Nothing is signed until each of these holds."""
    f = []
    if company.get('status') == 'blocked':
        f.append('Company is blocked.')
    if deal.get('recheck', {}).get('changed'):
        f.append('A fact changed at the pre-signing re-check.')
    if not deal.get('settlement'):
        f.append('No agreed terms.')
    if any(c.get('is_minor') for c in creators):
        f.append('A creator is under 18 and no guardian is on file.')
    return f


def render(deal: dict, company: dict, creators: list[dict]) -> str:
    s = deal['settlement']
    t = s['terms']
    tier = deal['tier_terms']
    names = {c['id']: c['handle'] for c in creators}
    pay = '\n'.join(f"  - @{names[c]}: INR {s['creator_prices'][c]:,} gross, INR {s['creator_net'][c]:,} after the {FEE_CREATOR * 100}% fee" for c in sorted(s['creator_prices']))
    usage = t.get('usage_days', 30)
    excl = t.get('exclusivity_days', 0)
    return f"""INFLUENCER SERVICES AGREEMENT
{NOTICE}
Date: {date.today().isoformat()}   Deal: {deal['id']}

PARTIES
Brand: {company.get('name')} ({company.get('domain') or 'no website; identity evidence on file'})
Creator(s): {', '.join('@' + c['handle'] for c in creators)}
Broker: ContextCon Deal Agent, an AI agent acting as a disclosed neutral broker. The broker is not a party to the services.

1. DELIVERABLES
{t.get('reels', 0)} reel(s) and {t.get('stories', 0)} story/stories per creator, with up to {t.get('revisions', 1)} revision round(s).

2. FEES
Agreed price: INR {s['price']:,}. Brand pays INR {s['brand_pays']:,}, including a {FEE_BRAND * 100}% broker fee.
{pay}

3. PAYMENT
{tier['upfront_pct']}% of the brand payment is held before work starts. The balance is due on delivery approval.
Held funds are released to the creator when the brand approves, or automatically 7 days after delivery with no objection.
If the brand cancels after work starts, the creator keeps the amount already held for work done (kill fee).

4. USAGE RIGHTS
The brand may reuse the content for {usage} days from first posting{', including paid advertising' if t.get('paid_ads') else ', organic use only'}.
The creator keeps ownership of the content.

5. EXCLUSIVITY
{f'The creator will not promote direct competitors for {excl} days.' if excl else 'None.'}

6. AD DISCLOSURE
All posts must clearly disclose the paid partnership, following ASCI influencer guidelines.

7. TAX
Each party is responsible for its own taxes. GST and TDS details are shown on the invoice.

8. DATA AND CONSENT
Each party consents to the processing of its data for this deal, and evidence is kept in the audit log.

9. DISPUTES
Disputes go first to the broker's human review, then to online arbitration under the Arbitration and Conciliation Act, 1996.

10. ELECTRONIC RECORD
This agreement is an electronic record under the Information Technology Act, 2000. Stamp duty, where applicable, is handled by the e-sign provider.
"""


def contract_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf8')).hexdigest()


def invoice(deal: dict, company: dict) -> dict:
    s = deal['settlement']
    return {'number': f"INV-{deal['id'][-8:].upper()}", 'bill_to': company.get('name'), 'gstin': company.get('gstin') or 'not provided', 'services': s['price'], 'broker_fee': s['fee_brand'],
            'total': s['brand_pays'], 'currency': 'INR', 'tax_note': 'GST and TDS are not calculated in this build.', 'is_mock': True}
