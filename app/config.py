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
OPENAI_KEY = os.environ.get('OPENAI_API_KEY', '')
# auto | anthropic | openai. auto uses Anthropic when both keys are set (existing default).
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'auto').strip().lower() or 'auto'
_LLM_MODEL_ENV = os.environ.get('LLM_MODEL', '').strip()
LLM_POLISH = os.environ.get('LLM_POLISH', '0') == '1'     # Off by default: the template pitch needs no tokens.
CACHE_TTL_HOURS = 24 * 7
MARKET_COUNTRY = os.environ.get('MARKET_COUNTRY', 'India')

_DEFAULT_MODELS = {'anthropic': 'claude-opus-5-5', 'openai': 'gpt-4o-mini'}
# Kept for callers that read the name; the live model comes from resolve_llm().
LLM_MODEL = _LLM_MODEL_ENV or _DEFAULT_MODELS['anthropic']


def resolve_llm() -> tuple[str | None, str | None, str | None]:
    """Pick (provider, api_key, model). Returns (None, None, None) when no usable key is set."""
    want = LLM_PROVIDER
    if want not in ('auto', 'anthropic', 'openai'):
        want = 'auto'
    if want == 'auto':
        hint = (_LLM_MODEL_ENV or '').lower()
        openai_hint = hint.startswith(('gpt-', 'o1', 'o3', 'o4'))
        # Prefer the provider that matches LLM_MODEL when that key exists; else Anthropic, else OpenAI.
        if openai_hint and OPENAI_KEY:
            want = 'openai'
        elif (not openai_hint) and ANTHROPIC_KEY:
            want = 'anthropic'
        elif OPENAI_KEY:
            want = 'openai'
        elif ANTHROPIC_KEY:
            want = 'anthropic'
        else:
            return None, None, None
    key = ANTHROPIC_KEY if want == 'anthropic' else OPENAI_KEY
    if not key:
        return None, None, None
    model = _LLM_MODEL_ENV or _DEFAULT_MODELS[want]
    return want, key, model

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

# Our estimate of when each email would happen in a real deal, in days from the first pitch. Shown as an estimate.
MAIL_DAYS = {'pitch': 0, 'reply': 2, 'quote': 2, 'counter': 3, 'agreed': 4, 'contract': 5, 'signed': 6, 'funded': 6, 'delivered': 13, 'approved': 14, 'paid': 14, 'invoice': 14}

# Fit weights by campaign goal. Our judgement, adapted from the idea of goal-specific scoring profiles.
FIT_PROFILES = {
    'balanced': {'audience': 35, 'content': 25, 'attention': 20, 'past_sponsored': 10, 'reliability': 10},
    'awareness': {'audience': 35, 'content': 15, 'attention': 30, 'past_sponsored': 10, 'reliability': 10},
    'engagement': {'audience': 20, 'content': 25, 'attention': 40, 'past_sponsored': 5, 'reliability': 10},
    'conversion': {'audience': 40, 'content': 20, 'attention': 15, 'past_sponsored': 15, 'reliability': 10},
    'brand_building': {'audience': 25, 'content': 40, 'attention': 10, 'past_sponsored': 10, 'reliability': 15},
}

# Offer review limits. Each finding in app/offers.py cites one of these.
OFFER_RULES = {'max_usage_days': 180, 'max_exclusivity_days': 90, 'max_payment_days': 45, 'max_revisions': 3, 'kill_fee_above': 20000}

# Risk tier terms. Cap of None means no cap.
TIERS = {
    'A': {'label': 'Verified', 'upfront_pct': 50, 'deal_cap': None},
    'B': {'label': 'Partly verified', 'upfront_pct': 100, 'deal_cap': 25000},
    'C': {'label': 'Unverified', 'upfront_pct': 100, 'deal_cap': 10000},
}
