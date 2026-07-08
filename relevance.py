"""
Relevance categorization for frontend-adjacent roles.

Replaces a flat true/false with four categories, because a single
boolean can't represent "this is mobile, not web" or "this is
full-stack but heavily React-driven" without losing information you
actually want to see.

This is a heuristic, not a guarantee. Keyword scoring will always have
edge cases. Treat categories as "worth a look," not "definitely apply."
"""

import re

# --- Mobile detection (checked first - mobile roles should never land
# in web_frontend). NOTE: this category is "mobile_dev", not
# "react_native" specifically - it also catches Swift/SwiftUI, Flutter,
# and plain Android/iOS titles, since none of those are your web React
# stack either. Grouped together because the action (skip, not web
# frontend) is the same for all of them. ---
MOBILE_KEYWORDS = [
    "react native", "ios developer", "android developer",
    "mobile engineer", "mobile developer", "flutter",
    "swift developer", "swiftui", "kotlin developer",
]

# --- Strong web-frontend title signal ---
# Word-boundary regex instead of plain substring checks - plain "in"
# checks let "ui developer" match inside "swiftUI Developer", which
# was a real false positive caught in production data. Word boundaries
# fix that whole class of bug.
WEB_FRONTEND_TITLE_PATTERNS = [
    r"\bfrontend\b", r"\bfront-end\b", r"\bfront end\b",
    r"\breact\b", r"\bvue\b", r"\bangular\b",
    r"\bnext\.js\b", r"\bnextjs\b",
    r"\bui engineer\b", r"\bui developer\b",
    r"\bjavascript developer\b", r"\btypescript developer\b",
]

# --- Title terms suggesting full-stack/product-engineer framing
# (not auto-excluded - these get a second check against description
# strength before being categorized) ---
FULLSTACK_TITLE_PATTERNS = [
    r"\bfull stack\b", r"\bfull-stack\b", r"\bfullstack\b", r"\bfounding engineer\b",
]

# --- Description-level signal, used both as supporting evidence for
# web_frontend and as the deciding factor for full_stack_react ---
REACT_DESCRIPTION_KEYWORDS = [
    "react", "next.js", "nextjs", "typescript", "redux", "zustand",
    "tailwind", "jsx", "react.js", "reactjs",
]

# --- Title terms that strongly suggest this isn't frontend-relevant at
# all, even if description happens to mention React in passing ---
NEGATIVE_TITLE_KEYWORDS = [
    ".net", "qa engineer", "sdet", "site reliability", "devops",
    "data engineer", "data scientist", "backend", "back-end", "back end",
    "designer", "sales", "marketing", "recruiter", "accountant",
    "support engineer", "python", "java developer", "ruby", ".net developer",
]

WEB_TITLE_SCORE = 10
NEGATIVE_TITLE_SCORE = -8
DESCRIPTION_MATCH_SCORE = 1

# Full-stack titles need a meaningfully strong React signal in the
# description (not just one stray mention) to be surfaced - this is
# the threshold that addresses the "Full Stack Product Engineer with
# zero React mentions" false-miss problem without reopening the
# ".NET dev mentions React once" false-positive problem.
FULLSTACK_REACT_SIGNAL_THRESHOLD = 3


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in text)


def _count_pattern_hits(text: str, patterns: list[str]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text))


def categorize_job(title: str, description: str) -> tuple[str, int]:
    """
    Returns (category, score).
    category is one of: web_frontend, mobile_dev, full_stack_react, not_relevant
    """
    title_lower = (title or "").lower()
    desc_lower = _strip_html(description).lower()

    # 1. Mobile check first - takes priority regardless of other signals
    if any(kw in title_lower for kw in MOBILE_KEYWORDS):
        return "mobile_dev", WEB_TITLE_SCORE

    # 2. Strong negative signal - likely not relevant unless overridden
    #    by an explicit web-frontend title match (rare but possible,
    #    e.g. a title mentioning both "backend" and "frontend")
    negative_hits = _count_keyword_hits(title_lower, NEGATIVE_TITLE_KEYWORDS)
    web_title_hits = _count_pattern_hits(title_lower, WEB_FRONTEND_TITLE_PATTERNS)

    if web_title_hits > 0:
        score = (web_title_hits * WEB_TITLE_SCORE) + (negative_hits * NEGATIVE_TITLE_SCORE)
        score += _count_keyword_hits(desc_lower, REACT_DESCRIPTION_KEYWORDS) * DESCRIPTION_MATCH_SCORE
        if score > 0:
            return "web_frontend", score
        # Negative signal overpowered the web match - fall through to not_relevant
        return "not_relevant", score

    if negative_hits > 0:
        return "not_relevant", negative_hits * NEGATIVE_TITLE_SCORE

    # 3. Full-stack / generic titles - only surfaced if description
    #    carries a real React signal, not just one passing mention
    fullstack_title_hits = _count_pattern_hits(title_lower, FULLSTACK_TITLE_PATTERNS)
    react_signal = _count_keyword_hits(desc_lower, REACT_DESCRIPTION_KEYWORDS)

    if fullstack_title_hits > 0 and react_signal >= FULLSTACK_REACT_SIGNAL_THRESHOLD:
        score = (fullstack_title_hits * 2) + react_signal
        return "full_stack_react", score

    # 4. No strong title signal either way - weak description-only
    #    matches don't qualify on their own (this is what filters out
    #    the ".NET dev mentions React once" case)
    return "not_relevant", react_signal


def extract_headquarters(description: str) -> str:
    """
    Pull the 'Headquarters: X' line out of WWR-style descriptions.
    Returns '' if not found - not every source/posting has this field.
    """
    if not description:
        return ""
    match = re.search(r"Headquarters:</strong>\s*([^<\n]+)", description)
    if match:
        return match.group(1).strip()
    return ""