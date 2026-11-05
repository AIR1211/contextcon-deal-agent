"""User settings, stored per creator, per company and for the app. Unknown keys are rejected, and types must match."""
from . import db

DEFAULTS = {
    'creator': {
        'auto_deal': False,              # Sends the Standard pack to every brand above the thresholds below.
        'auto_min_likelihood': 55,       # Above the 45 needed just to show a brand, because this acts without asking.
        'auto_min_confidence': 40,       # Below this, the evidence is too thin to act on.
        'auto_max_per_run': 10,
    },
    'company': {
        'auto_accept': False,            # Accepts an application automatically when fit is high enough.
        'auto_accept_min_fit': 75,
        'sign_myself': True,             # Pause for a person to sign, instead of a mock signature.
        'simulate_delivery': True,       # Delivery and approval happen automatically, labelled as mock.
    },
    'app': {
        'watchable_pace': True,          # Slows steps so people can follow. The deal page says so when it is on.
        'pace_ms': 900,
        'show_data_calls': True,         # Lists every Crustdata lookup in the deal's activity.
    },
}


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
        if isinstance(v, int) and not isinstance(v, bool) and not 0 <= v <= 5000:
            raise ValueError(f'{k} is out of range')
        now[k] = v
    db.put('settings', f'{scope}:{id_}', now)
    return now
