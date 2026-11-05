"""Runs a deal step by step until it is paid. State is saved after every step, so a crash resumes where it stopped.
Every outward action goes through the ledger with a stable key, so a re-run can never send or pay twice."""
import threading
from math import ceil

from . import contract, db, llm, packages
from .config import FEE_BRAND, FEE_CREATOR, TIERS
from .crustdata import Unavailable
from .engine import settle
from .models import CANT, DealIn, LEFT, VERIFIED, Terms
from .scoring import gates
from . import service
from .verify import verify_sender

ORDER = ['verify', 'pitch', 'await_company', 'negotiate', 'contract', 'recheck', 'sign', 'fund', 'deliver', 'approve', 'release', 'invoice', 'done']
FINAL = {'done', 'blocked', 'no_deal'}
EXCLUSIVITY_STATES = {'contract', 'recheck', 'sign', 'fund', 'deliver', 'approve', 'release', 'invoice', 'done'}
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


class SimulatedCrash(Exception):
    pass


class Pause(Exception):
    """Waits on a person. question=None means waiting for a normal step, such as delivery."""
    def __init__(self, kind, question=None):
        self.kind, self.question = kind, question


class Stop(Exception):
    def __init__(self, state, reason):
        self.state, self.reason = state, reason


def start(data: DealIn) -> dict:
    d = {'id': db.new_id('deal'), 'state': 'verify', 'creator_ids': sorted(set(data.creator_ids)), 'company_id': data.company_id, 'terms': data.terms.model_dump(), 'non_standard_clause': data.non_standard_clause,
         'simulate_parties': data.simulate_parties, 'decisions': {}, 'paused': None, 'reasons': []}
    db.put('deal', d['id'], d)
    db.event(d['id'], 'deal_started', {'creators': d['creator_ids'], 'company': d['company_id']})
    return d


def public_deal(d: dict) -> dict:
    """Removes values that would let either side work out the other's limit beyond what the result itself shows."""
    out = {k: v for k, v in d.items() if k not in ('private_audit',)}
    if d.get('settlement'):
        out['settlement'] = {k: v for k, v in d['settlement'].items() if k not in ('surplus', 'options_considered')}
    return out


def _email(deal, step, to, subject, body):
    key = f"{deal['id']}:{step}:{to}"
    if db.act(key, deal['id'], 'mock_email', {'to': to, 'subject': subject, 'body': body, 'delivered': False, 'note': 'Mock outbox: nothing is sent to real people.'}):
        db.event(deal['id'], 'message_queued', {'to': to, 'subject': subject})


def _people(deal):
    return db.get('company', deal['company_id']), [db.get('creator', c) for c in deal['creator_ids']]


def _decided(deal, kind, question):
    """Asks once. A recorded answer means the deal carries on instead of asking again after a resume."""
    if kind not in deal['decisions']:
        raise Pause(kind, question)
    return deal['decisions'][kind]


def _conflict(deal, company, creator):
    """Exclusivity is checked per company group, so two names for one company still count as one."""
    for other in db.all_docs('deal'):
        if other['id'] == deal['id'] or creator['id'] not in other['creator_ids'] or other['state'] not in EXCLUSIVITY_STATES:
            continue
        terms = (other.get('settlement') or {}).get('terms') or {}
        if not terms.get('exclusivity_days'):
            continue
        rival = db.get('company', other['company_id'])
        same_group = rival.get('group') and rival['group'] == company.get('group')
        same_niche = rival.get('niche') and rival['niche'] == company.get('niche')
        if rival['id'] != company['id'] and (same_group or same_niche):
            return f"@{creator['handle']} has {terms['exclusivity_days']} days of exclusivity with {rival['name']}" + (', the same company group.' if same_group else ', a competitor in this niche.')
    return None


def step_verify(deal):
    company, creators = _people(deal)
    deal['reasons'] = list(company.get('reasons') or [])
    if company['status'] == 'blocked':
        raise Stop('blocked', ' '.join(company.get('reasons') or ['Company is blocked.']))
    for c in creators:
        failed = gates(c, company)
        if failed:
            raise Stop('blocked', ' '.join(failed))
        clash = _conflict(deal, company, c)
        if clash:
            raise Stop('blocked', clash)
    deal['tier'] = company.get('tier') or 'C'
    deal['tier_terms'] = TIERS.get(deal['tier'], TIERS['C'])
    if company.get('sender_status') == LEFT:
        _decided(deal, 'contact_left', f"{company.get('sender_name')} no longer appears to work at {company['name']}. Continue only with a new contact?")
    if deal['tier'] == 'C' and not _decided(deal, 'unverified_company', f"{company['name']} could not be verified. Continue with 100% held upfront and a low deal cap?"):
        raise Stop('no_deal', 'Declined after verification review.')


def step_pitch(deal):
    company, creators = _people(deal)
    to = company.get('sender_email') or f"contact@{company.get('domain') or company['id']}"
    _email(deal, 'pitch', to, f"Creator package for {company['name']}", llm.pitch_text({'name': company['name'], 'niche': company.get('niche')}, [{'handle': c['handle']} for c in creators], deal['terms']))


def step_await_company(deal):
    company, _ = _people(deal)
    response = deal.get('company_response')
    if response is None:
        if company.get('mode') == 'human':
            raise Pause('company_response')
        response = {'accept': True, 'simulated': True}
        deal['company_response'] = response
        db.event(deal['id'], 'simulated_company_replied', {'accept': True, 'is_mock': True})
    if not response.get('accept'):
        raise Stop('no_deal', 'The company declined.')
    clause = response.get('non_standard_clause') or deal.get('non_standard_clause')
    if clause and not _decided(deal, 'non_standard_clause', f'The company wants a non-standard clause: "{clause}". Accept it?'):
        raise Stop('no_deal', 'Non-standard clause declined.')


def _limits(deal, company, creators, base):
    lim = db.get('company_limits', company['id'])
    if lim:
        return lim
    return {'ceiling': packages.company_budget(company), 'simulated': True}


def step_negotiate(deal):
    company, creators = _people(deal)
    base = Terms(**deal['terms'])
    for c in creators:
        if deal['decisions'].get('new_floor') and c['id'] == deal['creator_ids'][0]:
            c['limits']['floor_reel'] = deal['decisions']['new_floor']
    opts = packages.options(creators, _limits(deal, company, creators, base), base, deal['tier'])
    result = settle(opts, FEE_CREATOR, FEE_BRAND) if opts else None
    if result is None:
        if deal['decisions'].get('no_overlap') is None:
            raise Pause('no_overlap', "No version of this deal fits both sides. The other side's limit stays private. Lower your floor to try again?")
        raise Stop('no_deal', 'No overlap between private limits.')
    deal['settlement'] = result.to_dict()
    db.event(deal['id'], 'terms_agreed', {'price': result.price, 'terms': result.terms, 'rule': result.rule})


def step_contract(deal):
    company, creators = _people(deal)
    text = contract.render(deal, company, creators)
    deal['contract_text'], deal['contract_hash'] = text, contract.contract_hash(text)
    db.act(f"{deal['id']}:contract", deal['id'], 'contract_issued', {'sha256': deal['contract_hash']})


def step_recheck(deal):
    """Facts must be right for the day they are used, so this skips the cache."""
    company, creators = _people(deal)
    changed = None
    if deal.get('simulate_contact_left'):
        changed = f"{company.get('sender_name')} left {company['name']} during this deal (simulated)."
    elif company.get('sender_status') == VERIFIED:
        r = verify_sender(service.cd, company.get('sender_name'), company.get('sender_email'), company.get('company_id'), company.get('domain'), company.get('sender_profile_url'), fresh=True)
        if r['status'] == CANT:
            changed = 'The sender could not be re-checked before signing, so this is unconfirmed: ' + ' '.join(r['reasons'])
        elif r['status'] != VERIFIED:
            changed = ' '.join(r['reasons'])
    deal['recheck'] = {'changed': bool(changed), 'detail': changed or 'No change found.', 'at': db.now()}
    if changed:
        if deal['decisions'].get('recheck_override'):
            deal['recheck']['changed'] = False
            deal['recheck']['detail'] += ' A person chose to continue.'
        elif 'recheck_override' in deal['decisions']:
            raise Stop('no_deal', 'Stopped at the pre-signing re-check: ' + changed)
        else:
            raise Pause('recheck_override', changed + ' Signing is paused. Continue with a new contact?')
    db.event(deal['id'], 'recheck_passed', deal['recheck'])


def step_sign(deal):
    company, creators = _people(deal)
    failures = contract.gate_failures(deal, company, creators)
    if failures:
        raise Stop('blocked', ' '.join(failures))
    excl = deal['settlement']['terms'].get('exclusivity_days')
    if excl:
        # Two companies racing for one creator: the first to sign holds it, atomically.
        for c in creators:
            key = f"exclusive:{c['id']}:{company.get('group') or company.get('niche') or company['id']}"
            if not db.act(key, deal['id'], 'exclusivity_reserved', {'creator': c['id'], 'days': excl}) and db.ledger_owner(key) != deal['id']:
                raise Stop('blocked', f"@{c['handle']} was reserved by another company that signed first.")
    for party in [company['id']] + deal['creator_ids']:
        db.act(f"{deal['id']}:sign:{party}", deal['id'], 'mock_signature', {'party': party, 'contract_sha256': deal['contract_hash'], 'is_mock': True})


def step_fund(deal):
    total = deal['settlement']['brand_pays']
    held = ceil(total * deal['tier_terms']['upfront_pct'] / 100)
    deal['held'] = held
    db.act(f"{deal['id']}:hold", deal['id'], 'mock_funds_held', {'amount': held, 'of': total, 'is_mock': True, 'note': 'A real launch needs a licensed payment partner.'})
    company, creators = _people(deal)
    for c in creators:
        _email(deal, 'start_work', '@' + c['handle'], 'Funds are held, please start', f"INR {held:,} is held. You can start work.")


def step_deliver(deal):
    if deal.get('delivery') is None:
        if not deal['simulate_parties']:
            raise Pause('delivery')
        deal['delivery'] = {'simulated': True, 'links': []}


def step_approve(deal):
    if deal.get('approval') is None:
        if not deal['simulate_parties']:
            raise Pause('approval')
        deal['approval'] = {'simulated': True}


def step_release(deal):
    s = deal['settlement']
    if s['brand_pays'] > deal.get('held', 0):
        db.act(f"{deal['id']}:balance", deal['id'], 'mock_balance_charged', {'amount': s['brand_pays'] - deal['held'], 'is_mock': True})
    for cid, net in sorted(s['creator_net'].items()):
        db.act(f"{deal['id']}:payout:{cid}", deal['id'], 'mock_payout', {'creator': cid, 'amount': net, 'is_mock': True})
    db.act(f"{deal['id']}:fee", deal['id'], 'mock_fee', {'amount': s['fee_brand'] + s['fee_creators'], 'is_mock': True})


def step_invoice(deal):
    company, _ = _people(deal)
    inv = contract.invoice(deal, company)
    deal['invoice'] = inv
    db.act(f"{deal['id']}:invoice", deal['id'], 'invoice', inv)
    _email(deal, 'invoice', company.get('sender_email') or f"contact@{company.get('domain') or company['id']}", f"Invoice {inv['number']}", f"Total INR {inv['total']:,}. Mock invoice.")


STEPS = {'verify': step_verify, 'pitch': step_pitch, 'await_company': step_await_company, 'negotiate': step_negotiate, 'contract': step_contract, 'recheck': step_recheck, 'sign': step_sign, 'fund': step_fund, 'deliver': step_deliver, 'approve': step_approve, 'release': step_release, 'invoice': step_invoice}


def run(deal_id: str, crash_after: str | None = None) -> dict:
    """Safe to call at any time and any number of times. crash_after is for the crash demo and tests."""
    with _guard:
        lock = _locks.setdefault(deal_id, threading.Lock())
    if not lock.acquire(blocking=False):
        return db.get('deal', deal_id)
    try:
        deal = db.get('deal', deal_id)
        while deal['state'] not in FINAL:
            state = deal['state']
            deal['paused'] = None
            try:
                STEPS[state](deal)
            except Pause as p:
                deal['paused'] = {'kind': p.kind, 'question': p.question}
                db.put('deal', deal_id, deal)
                db.event(deal_id, 'paused', deal['paused'])
                return deal
            except Stop as s:
                deal['state'], deal['final_reason'] = s.state, s.reason
                db.put('deal', deal_id, deal)
                db.event(deal_id, s.state, {'reason': s.reason})
                return deal
            except Unavailable as e:
                deal['paused'] = {'kind': 'tool_failure', 'question': f'A data source failed ({e}). The deal is saved and can resume.'}
                db.put('deal', deal_id, deal)
                db.event(deal_id, 'tool_failure', {'detail': str(e)})
                return deal
            if crash_after == state:      # Actions are done but state is not saved: the worst moment to crash.
                db.event(deal_id, 'crashed', {'after': state, 'is_simulation': True})
                raise SimulatedCrash(state)
            deal['state'] = ORDER[ORDER.index(state) + 1]
            db.put('deal', deal_id, deal)
            db.event(deal_id, 'step_done', {'step': state, 'next': deal['state']})
        return deal
    finally:
        lock.release()


def decide(deal_id: str, approve: bool, note: str = '', new_floor: int | None = None) -> dict:
    deal = db.get('deal', deal_id)
    p = deal.get('paused')
    if not p or not p.get('question'):
        return deal
    deal['decisions'][p['kind']] = approve
    if new_floor is not None:
        deal['decisions']['new_floor'] = new_floor
    db.put('deal', deal_id, deal)
    db.event(deal_id, 'person_decided', {'kind': p['kind'], 'approve': approve, 'note': note})
    return run(deal_id)


def set_field(deal_id: str, field: str, value) -> dict:
    deal = db.get('deal', deal_id)
    deal[field] = value
    db.put('deal', deal_id, deal)
    db.event(deal_id, field, {'received': True})
    return run(deal_id)
