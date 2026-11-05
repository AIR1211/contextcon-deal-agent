"""Settings and every assumption in the pricing and scoring maths, in one reviewable place."""
import os
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'

for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines() if (ROOT / '.env').exists() else []:
    if '=' in line and not line.lstrip().startswith('#'):
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))

DB_PATH = os.environ.get('DEAL_DB', str(ROOT / 'deals.db'))
CRUSTDATA_KEYS = [k.strip() for k in (os.environ.get('CRUSTDATA_API_KEYS') or os.environ.get('CRUSTDATA_API_KEY') or '').split(',') if k.strip()]
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
LLM_MODEL = os.environ.get('LLM_MODEL', 'claude-opus-5-5')
LLM_POLISH = os.environ.get('LLM_POLISH', '0') == '1'     # Off by default: the template pitch needs no tokens.
CACHE_TTL_HOURS = 24 * 7

# Fees are a disclosed percentage of the agreed price, charged to each side only on closed deals.
FEE_CREATOR = Fraction(5, 100)
FEE_BRAND = Fraction(5, 100)

# ASSUMPTIONS, not measurements. All are labelled as estimates in the product and replaced by real deal data later.
ASSUMPTIONS = {
    'views_per_like': 15,            # Public pages show likes but not views.
    'cpm_inr': 300,                  # Rupees per 1,000 expected views.
    'max_likes_share_of_followers': 0.25,
    'story_share_of_reel': Fraction(1, 3),
    'usage_per_30_days_share': Fraction(1, 10),
    'exclusivity_per_30_days_share': Fraction(1, 5),
    'paid_ads_share': Fraction(3, 10),
    'minimum_reel_price_inr': 1500,
    'match_threshold': 45,
    'default_floor_share_of_list': Fraction(7, 10),
}

# Risk tier terms. Cap of None means no cap.
TIERS = {
    'A': {'label': 'Verified', 'upfront_pct': 50, 'deal_cap': None},
    'B': {'label': 'Partly verified', 'upfront_pct': 100, 'deal_cap': 25000},
    'C': {'label': 'Unverified', 'upfront_pct': 100, 'deal_cap': 10000},
}
