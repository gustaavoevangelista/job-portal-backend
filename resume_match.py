"""
Resume-match scoring: how well does a job's description match YOUR
actual skills, not just "is this frontend" in general.

The skill profile below is built from your real CV/LinkedIn content
(Craftable, Atos, EnterTours, Retink Media) - not a generic frontend
checklist. Skills are tiered by how central they are to your actual
experience, so a strong match on your core stack (React/Next/TS)
counts for more than an incidental mention of something you've only
touched once.

This is a fit signal, not a gatekeeper - a low score doesn't mean
"don't apply", it means "this will likely need more upskilling or a
stronger cover-letter story to bridge the gap." Use it to prioritize
where to spend your first applications, not to filter anything out.
"""

import re

# --- Tier 1: core, load-bearing skills - heavy weight ---
# These are the things you've used across MULTIPLE roles/projects and
# would be expected to discuss fluently in an interview right now.
TIER_1_SKILLS = {
    "react": 10,
    "next.js": 10,
    "nextjs": 10,
    "typescript": 9,
    "javascript": 7,  # broader/older than TS, still core but slightly less weight
}

# --- Tier 2: solid, real experience but secondary to the above ---
TIER_2_SKILLS = {
    "tailwind": 6,
    "cypress": 6,
    "playwright": 6,
    "firebase": 6,
    "rest api": 5,
    "restful": 5,
    "html": 3,
    "css": 3,
    "shadcn": 5,
    "zustand": 5,
    "redux": 4,  # not in your CV explicitly, but adjacent state-mgmt experience transfers
    "prisma": 5,
    "mysql": 5,
    "sql server": 5,
    "next-auth": 5,
    # Process/methodology terms are real but generic - almost every job
    # mentions these regardless of stack fit, so they shouldn't inflate
    # a score the way an actual technology match should.
    "agile": 1,
    "scrum": 1,
}

# --- Tier 3: touched, but not your main strength - light weight ---
# Real experience (Atos health-system project, freelance work) but not
# what you'd lead with - still worth a small boost if mentioned, since
# it shows you're not purely frontend-only.
TIER_3_SKILLS = {
    "java": 3,
    "spring boot": 3,
    "microservices": 3,
    "jpa": 2,
    "hibernate": 2,
    "docker": 3,
    "jenkins": 2,
    "ci/cd": 3,
    "aws": 3,
    "domain-driven design": 3,
    "ddd": 3,
    # "node.js" is checked as a single pattern that also matches bare
    # "node" via regex, instead of two separate dict entries - avoids
    # double-counting the same skill when a description says "Node.js".
    "node(\\.js)?": 4,
    "express": 3,
    "postgresql": 3,
}

ALL_SKILL_WEIGHTS: dict[str, int] = {**TIER_1_SKILLS, **TIER_2_SKILLS, **TIER_3_SKILLS}
TIER_1_KEYS = set(TIER_1_SKILLS.keys())

# Phrases that mark a paragraph as "other roles we also staff for", not
# a description of THIS job - staffing marketplaces (Lemon.io, Proxify,
# etc) commonly include a giant stack list so any keyword search lights
# up regardless of the actual role. Real example: a Swift/SwiftUI
# listing's "NOT YOUR TECH STACK?" paragraph mentions "React & Node.js"
# among forty other combinations - none of which describe this job.
BOILERPLATE_MARKERS = [
    r"not your tech stack",
    r"if you have .{0,40}experience.{0,10}and are proficient in",
    r"we have a variety of projects",
]

# A title naming a specific non-Tier-1 primary language/framework is a
# strong signal the role is actually built around THAT, regardless of
# what else gets mentioned in the body - "Golang Developer" means Go is
# the job, even if React appears once as a thing the API "consumes."
TITLE_PRIMARY_LANGUAGE_OVERRIDE = [
    "golang", "go developer", "ruby", "python developer", "java developer",
    "c#", ".net developer", "php developer", "rust developer", "scala",
    "kotlin developer", "swift developer", "swiftui",
]


def _strip_boilerplate(text: str) -> str:
    """
    Cut off the description at the first staffing-marketplace boilerplate
    marker, so "other stacks we also place people in" paragraphs don't
    get scored as if they described this job.
    """
    earliest_cut = len(text)
    for marker in BOILERPLATE_MARKERS:
        match = re.search(marker, text)
        if match:
            earliest_cut = min(earliest_cut, match.start())
    return text[:earliest_cut]

# Maximum possible score, used to normalize to a 0-100 scale. Computed
# from a realistic "great match" job description rather than literally
# summing every skill (no real job mentions DDD + Jenkins + Firebase +
# Prisma all at once) - calibrated against your strongest real
# experience bullets (the Atos and Retink Media projects).
CALIBRATION_CAP = 45

# Without at least this many Tier-1 points (React/Next.js/TypeScript -
# your actual specialty), a job can't be a strong match for YOU
# specifically, no matter how many secondary/tertiary keywords it
# mentions. This is what stops a backend-heavy role that happens to
# mention TypeScript/React/Vue/Docker/PostgreSQL in passing from
# outscoring a role that's actually built around your core stack.
# Real example this fixes: "Senior Golang Developer (Fullstack,
# BE-Heavy)" mentioned enough Tier-2/3 terms to hit 93% before this cap
# existed, despite Go not being in your skillset at all and the
# frontend mention being about "consuming API contracts," not your work.
MIN_TIER1_FOR_FULL_SCORE = 9  # roughly one strong Tier-1 hit (react=10, typescript=9)

# Without ANY Tier-1 hit, cap the score hard regardless of how many
# Tier-2/3 terms appear - these almost never indicate a genuine fit on
# their own. Most staffing-marketplace job ads (Lemon.io, Proxify, etc)
# include large boilerplate paragraphs listing every stack they place
# people in ("React & Python, React & Golang, React & Java, ...") -
# without this cap, that boilerplate alone can fake a high score even
# when the actual role has nothing to do with your stack.
NO_TIER1_SCORE_CAP_PCT = 20


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def compute_resume_match(title: str, description: str) -> dict:
    """
    Returns a dict with:
      - raw_score: sum of weighted hits
      - match_pct: 0-100, normalized against CALIBRATION_CAP and gated
        on genuine Tier-1 (core stack) presence
      - matched_skills: list of (skill, weight) actually found, sorted by weight desc
      - tier1_score: how much of raw_score came from Tier-1 skills specifically
    """
    title_lower = (title or "").lower()
    body = _strip_html(description).lower()
    body = _strip_boilerplate(body)
    text = f"{title_lower} {body}"

    matched: list[tuple[str, int]] = []
    raw_score = 0
    tier1_score = 0

    for skill, weight in ALL_SKILL_WEIGHTS.items():
        # Word-boundary-ish matching - good enough for multi-word skills
        # like "next.js" or "spring boot", consistent with the lesson
        # learned in relevance.py about avoiding false substring matches.
        # Skills containing regex special chars beyond a literal period
        # (e.g. "node(\.js)?") are already valid patterns and shouldn't
        # be re.escape'd, or the pattern syntax itself gets escaped away.
        is_already_pattern = "(" in skill or "?" in skill
        skill_pattern = skill if is_already_pattern else re.escape(skill)
        pattern = r"\b" + skill_pattern + r"\b"
        if re.search(pattern, text):
            clean_label = skill.replace("(\\.js)?", ".js").replace("\\", "")
            matched.append((clean_label, weight))
            raw_score += weight
            if skill in TIER_1_KEYS:
                tier1_score += weight

    matched.sort(key=lambda x: -x[1])

    # Two views of fit, blended: overall keyword breadth (raw_score/cap)
    # and how strongly the CORE stack specifically is represented
    # (tier1_score against the max realistic Tier-1 total). A short job
    # ad that says "React, TypeScript, Node.js" and nothing else is a
    # genuinely strong match for you even though it won't accumulate
    # many keyword hits the way a long, detailed posting would - so
    # tier1 strength gets real weight here, not just a ceiling check.
    breadth_pct = min(100, round((raw_score / CALIBRATION_CAP) * 100))
    tier1_pct = min(100, round((tier1_score / (MIN_TIER1_FOR_FULL_SCORE * 2)) * 100))
    match_pct = round((breadth_pct * 0.4) + (tier1_pct * 0.6))
    match_pct = min(100, match_pct)

    # Gate: no real Tier-1 presence means this isn't actually a match
    # for your specialty, however many secondary keywords showed up.
    if tier1_score == 0:
        match_pct = min(match_pct, NO_TIER1_SCORE_CAP_PCT)
    elif tier1_score < MIN_TIER1_FOR_FULL_SCORE:
        # Partial Tier-1 presence (e.g. only a weak/incidental mention) -
        # scale the ceiling proportionally rather than an all-or-nothing cliff.
        ceiling = round(50 + (tier1_score / MIN_TIER1_FOR_FULL_SCORE) * 50)
        match_pct = min(match_pct, ceiling)

    # Title names a different primary language/framework as THE job,
    # not just a mentioned technology - cap hard regardless of body
    # keyword hits. Real example: "Senior Golang Developer (Fullstack,
    # BE-Heavy)" mentions React/TypeScript/Docker/PostgreSQL/DDD for
    # consuming APIs, but the job is Go - this stops that incidental
    # overlap from outranking a role actually built around your stack.
    if any(lang in title_lower for lang in TITLE_PRIMARY_LANGUAGE_OVERRIDE):
        match_pct = min(match_pct, NO_TIER1_SCORE_CAP_PCT + 15)

    return {
        "raw_score": raw_score,
        "match_pct": match_pct,
        "matched_skills": matched,
        "tier1_score": tier1_score,
    }