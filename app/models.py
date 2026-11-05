"""Shared models. Changes here must be announced to the team."""
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

VERIFIED, WEAK, PARTLY, CANT, BLOCKED, LEFT = 'verified', 'weak_match', 'partly_verified', 'cannot_verify', 'blocked', 'contact_left'


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Fact(BaseModel):
    subject: str
    field: str
    value: object = None
    source: str
    as_of: str = Field(default_factory=now)
    strength: str = VERIFIED
    url: Optional[str] = None
    is_mock: bool = False


class Terms(BaseModel):
    reels: int = Field(1, ge=0, le=20)
    stories: int = Field(0, ge=0, le=50)
    usage_days: int = Field(30, ge=0, le=365)
    exclusivity_days: int = Field(0, ge=0, le=365)
    paid_ads: bool = False
    revisions: int = Field(1, ge=0, le=5)


class CreatorLimits(BaseModel):
    floor_reel: Optional[int] = Field(None, ge=0)
    floor_story: Optional[int] = Field(None, ge=0)
    max_exclusivity_days: int = 90
    allow_paid_ads: bool = True
    blocked_categories: list[str] = []


class CreatorIn(BaseModel):
    handle: str
    niche: str
    limits: CreatorLimits = CreatorLimits()
    autopilot: bool = True
    audience_country_pct: Optional[int] = Field(None, ge=0, le=100)   # Self-reported or from analytics.
    is_minor: bool = False
    mock_stats: Optional[dict] = None                                 # Labelled mock profile, no API call.


class CompanyLimits(BaseModel):
    ceiling: int = Field(ge=0)
    value_per_reel: Optional[int] = None
    value_per_story: Optional[int] = None
    value_per_30_usage_days: int = 0
    value_per_30_exclusive_days: int = 0
    value_paid_ads: int = 0


class CompanyIn(BaseModel):
    name: str
    niche: str = ''
    domain: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    sender_profile_url: Optional[str] = None
    instagram: Optional[str] = None
    gstin: Optional[str] = None
    budget: int = Field(0, ge=0)
    limits: Optional[CompanyLimits] = None
    mode: str = Field('simulated', pattern='^(simulated|human)$')


class DealIn(BaseModel):
    creator_ids: list[str] = Field(min_length=1, max_length=10)
    company_id: str
    terms: Terms = Terms()
    non_standard_clause: Optional[str] = None
    simulate_parties: bool = True     # Delivery and approval happen automatically, labelled as mock.
    pace_ms: int = Field(0, ge=0, le=3000)


class CompanyResponse(BaseModel):
    accept: bool = True
    limits: Optional[CompanyLimits] = None
    non_standard_clause: Optional[str] = None


class Decision(BaseModel):
    approve: bool
    note: str = ''
    new_floor_reel: Optional[int] = Field(None, ge=0)
