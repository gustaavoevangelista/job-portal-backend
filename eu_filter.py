"""
EU-remote compatibility classification.

The raw location data across sources is genuinely inconsistent in
*kind*, not just format - WWR gives company HQ city/country, Remotive
gives a candidate-location restriction, Working Nomads gives either a
timezone offset or a list of hiring continents, sometimes both phrased
differently in the same field. Trying to parse this into a single
clean "country" or "timezone" field isn't reliable, so instead we
derive the one thing that's actually decision-relevant: can someone
based in Portugal realistically apply to this?

Deliberately conservative design: a string like "Worldwide" technically
includes the EU, but gives zero actual confidence the company supports
EU payroll/tax/EOR arrangements (see the Germany-residency problem
flagged earlier in this project). Vague/broad signals get "unclear",
not "yes" - false positives here cost you wasted application time,
false "unclear"s just mean you eyeball it yourself, which is the safer
failure mode.

Returns one of: "yes", "no", "unclear"
"""

import re

# Strong, explicit EU/Europe signals - confident "yes"
EU_YES_PATTERNS = [
    r"\beu\b", r"\beu only\b", r"\beurope\b", r"\beuropean union\b",
    r"\bcet\b", r"\bcest\b",  # Central European Time - strong proxy for EU-compatible hours
    # Specific EU country names/cities seen in real data or commonly used
    r"\bportugal\b", r"\bgermany\b", r"\bnetherlands\b", r"\bspain\b",
    r"\bfrance\b", r"\bitaly\b", r"\bpoland\b", r"\bbulgaria\b", r"\bsofia\b",
    r"\bberlin\b", r"\bamsterdam\b",
    r"\bbelgium\b", r"\baustria\b", r"\bireland\b", r"\bgreece\b", r"\bathens\b",
]

# Explicit non-EU restrictions - confident "no". Checked first since a
# string can mention "US only" without any EU keyword conflicting, but
# we want this to win decisively when present.
EU_NO_PATTERNS = [
    r"\bus only\b", r"\busa only\b", r"\bunited states only\b",
    r"\bcanada only\b", r"\bcanada\b", r"\bapac only\b",
    r"\blatam only\b", r"\blatin america only\b",
    # Bare "USA"/"US" - in fields like Remotive's candidate_required_location,
    # this field is specifically a restriction by definition, so an
    # unqualified "USA" almost certainly means "must be US-based", not
    # incidental metadata. Word-boundary matched so this doesn't catch
    # "Australia" or similar.
    r"\busa\b", r"\bus\b",
    # US state/region-style strings seen in real WWR data, e.g.
    # "California, San Francisco, United States Of America",
    # "IL-CLIENT-STATE", "New York, NY"
    r"\bunited states of america\b", r"\bnew york\b", r"\bcalifornia\b",
    r"\bseattle\b", r"\bflorida\b", r"\bdenver\b",
    # Unambiguous non-EU countries seen in real data or clearly outside
    # any EU-adjacency question (unlike UK/Switzerland, which get their
    # own handling elsewhere because they're genuinely closer calls).
    # Word-boundary matched - "india" won't match inside "Indiana" etc.
    r"\bindia\b",
]

# Switzerland is geographically in Europe and often CET-aligned, but is
# NOT in the EU - relevant for actual payroll/tax/EOR reality, so it's
# excluded from EU_YES_PATTERNS deliberately and called out as its own
# case rather than silently grouped with EU member states.
SWITZERLAND_PATTERNS = [r"\bswitzerland\b", r"\bzuerich\b", r"\bzurich\b"]


def classify_eu_compatibility(raw_location: str) -> str:
    """
    Returns "yes", "no", or "unclear" based on the raw location/timezone
    string. Deliberately conservative - broad/ambiguous strings like
    "Worldwide" return "unclear", not "yes", since they carry no real
    signal about actual EU payroll/legal compatibility.
    """
    if not raw_location:
        return "unclear"

    text = raw_location.lower().strip()

    # Explicit non-EU restriction wins immediately if present
    if any(re.search(pattern, text) for pattern in EU_NO_PATTERNS):
        return "no"

    # Explicit EU/Europe signal
    if any(re.search(pattern, text) for pattern in EU_YES_PATTERNS):
        return "yes"

    # "Worldwide" / unqualified broad terms - technically includes EU,
    # but no real signal of actual compatibility. Deliberately "unclear",
    # not "yes" - see module docstring.
    return "unclear"


def is_switzerland(raw_location: str) -> bool:
    """
    Switzerland-specific flag, separate from the main EU classification
    since CH is geographically/culturally EU-adjacent (often CET,
    often appealing for remote EU candidates) but is NOT an EU member
    state, which matters for actual payroll/tax/EOR feasibility.
    """
    if not raw_location:
        return False
    text = raw_location.lower().strip()
    return any(re.search(pattern, text) for pattern in SWITZERLAND_PATTERNS)