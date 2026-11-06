"""User settings, stored per creator, per company and for the app. Unknown keys are rejected, and types must match.
Core safety is deliberately not here: blocking impersonation, the re-check before signing, private limits, the action
ledger and the ad disclosure clause can't be switched off."""
from . import db

DEFAULTS = {
    'creator': {
        'auto_deal': False,              # Sends a media pack to every brand above the thresholds below.
        'auto_pack': 'Standard',
        'auto_min_likelihood': 55,       # Above the 45 needed just to show a brand, because this acts without asking.
        'auto_min_confidence': 40,       # Below this, the evidence is too thin to act on.
        'auto_max_per_run': 10,
        'auto_allow_partly_verified': True,
    },
    'company': {
        'campaign_goal': 'balanced',     # Changes what creator fit weighs. See config.FIT_PROFILES.
        'write_contracts': True,         # Off: the deal pauses for the brand's own contract.
        'clause_kill_fee': True,
        'clause_arbitration': True,
        'sign_myself': True,             # Pause for a person to sign, instead of a mock signature.
        'simulate_delivery': True,       # Delivery and approval happen automatically, labelled as mock.
        'allow_lighter_terms': True,     # Off: if the requested terms don't fit, ask instead of trying a lighter version.
        'decline_others_on_choose': True,
        'auto_accept': False,            # Accepts an application automatically when fit is high enough.
        'auto_accept_min_fit': 75,
        'offers_min_fit': 0,             # Hides weaker applications from the offers list. They stay under "hidden".
    },
    'app': {
        'motion': 'auto',                # auto follows the device's reduced motion setting.
        'watchable_pace': True,          # Slows steps so people can follow. The deal page says so when it is on.
        'pace_ms': 900,
        'show_data_calls': True,         # Lists every Crustdata lookup in the deal's activity.
        'show_fetching': True,
        'show_why': True,
        'show_evidence': True,
        'show_tiebreaks': True,
        'compact': False,
        'ai_pitch_polish': False,        # Needs Anthropic or OpenAI. Off by default, because the template pitch uses no tokens.
    },
}
CHOICES = {'auto_pack': ('Starter', 'Standard', 'Campaign'), 'motion': ('auto', 'full', 'off'), 'campaign_goal': ('balanced', 'awareness', 'engagement', 'conversion', 'brand_building')}


def get(scope: str, id_: str = 'global') -> dict:
    return {**DEFAULTS[scope], **(db.get('settings', f'{scope}:{id_}') or {})}


def update(scope: str, id_: str, changes: dict) -> dict:
    if scope not in DEFAULTS:
        raise ValueError('Unknown settings scope.')
    now = get(scope, id_)
    for k, v in changes.items():
        if k not in DEFAULTS[scope]:
            raise ValueError(f'Unknown setting: {k}')
        if isinstance(DEFAULTS[scope][k], bool) != isinstance(v, bool) or not isinstance(v, type(DEFAULTS[scope][k])):
            raise ValueError(f'Wrong type for {k}')
        if k in CHOICES and v not in CHOICES[k]:
            raise ValueError(f'{k} must be one of {", ".join(CHOICES[k])}')
        if isinstance(v, int) and not isinstance(v, bool) and not 0 <= v <= 5000:
            raise ValueError(f'{k} is out of range')
        now[k] = v
    db.put('settings', f'{scope}:{id_}', now)
    return now
