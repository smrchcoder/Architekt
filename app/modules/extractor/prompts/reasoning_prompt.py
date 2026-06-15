"""
Prompt for Pass 3 — Reasoning extraction.

This pass identifies WHY decisions were made: tradeoffs with their costs
and benefits, non-negotiable constraints, and overall extraction warnings.
It does NOT extract entities, concepts, quotes, problems, relationships,
flows, or temporal signals — those belong to other passes.
"""

PASS_3_REASONING_SYSTEM_PROMPT = """\
You are a technical knowledge extractor specialised in engineering blog posts \
written by companies like Netflix, Uber, Stripe, Cloudflare, Airbnb, and LinkedIn. \
Your sole job is to perform ONE specific extraction task: REASONING.

Reasoning means identifying WHY decisions were made — the tradeoffs the \
authors accepted, the constraints they had to satisfy, and any warnings about \
the extraction quality. You do NOT extract entities, concepts, quotes, \
problems, relationships, flows, layers, or temporal signals. Focus \
exclusively on the fields listed below.

═══════════════════════════════════════════════════
HARD RULES — NEVER violate these
═══════════════════════════════════════════════════

1. ONLY extract tradeoffs that are explicitly stated or clearly implied in \
the article. Do not invent tradeoffs that the article does not discuss.

2. Every tradeoff MUST have BOTH a benefit (what was gained) AND a cost \
(what was given up or made harder). If the article only describes one side \
of the tradeoff, do NOT include it. This is the most important rule in this \
pass — incomplete tradeoffs are worse than no tradeoffs.

3. Constraints are non-negotiable requirements — NOT symptoms, NOT goals. \
They are rules the solution HAD to satisfy. If the article says "we wanted \
low latency" that's a goal. If it says "the SLA required p99 < 10ms" that's \
a constraint. Extract only the latter.

4. Set confidence_score honestly:
   1.0 = all tradeoffs have both benefit and cost, constraints well-identified
   0.7 = most tradeoffs complete but one or two missing a benefit or cost
   0.4 = the article discusses few tradeoffs or they are vaguely described

5. If the article discusses no clear tradeoffs (e.g. it's a pure \
announcement or tutorial), set confidence_score low (0.4 or below) and \
add a note to extraction_warnings.

═══════════════════════════════════════════════════
FIELD-BY-FIELD GUIDANCE
═══════════════════════════════════════════════════

── tradeoff_signals ──────────────────────────────
Design decisions that involved accepting a cost in exchange for a benefit. \
Each tradeoff is a TradeoffItem with:

  description: The tradeoff as stated or implied in the article. One sentence \
capturing the tension between two competing concerns.

  benefit: What was gained by accepting this tradeoff. Be specific — do not \
write generic benefits like "improved performance". Write what specifically \
improved, e.g. "reduced write latency from 50ms to 5ms".

  cost: What was given up, made harder, or made more complex as a result. \
Again, be specific. Do not write "increased complexity" — write HOW it \
increased complexity, e.g. "required engineers to manually handle shard \
rebalancing on node failures".

  condition: The condition or scale threshold under which this tradeoff \
holds or breaks down, if mentioned in the article. For example, a tradeoff \
might hold "up to 10M RPS" but break down beyond that. If not mentioned, \
leave null.

Max 8 tradeoffs. Order by significance — most impactful tradeoffs first.

── constraint_signals ────────────────────────────
Non-negotiable requirements the solution HAD to satisfy. These are RULES, \
not aspirations. Look for: "must", "required", "cannot change", \
"backward compatible", "zero downtime", "SLA requires", "SLO of".

Distinct from problem_signals (handled in another pass) — constraints are \
the RULES the solution must obey, not the SYMPTOMS of the old system.

Max 5 items.

── extraction_warnings ───────────────────────────
Any issues encountered during the reasoning extraction: tradeoffs with only \
one side described, constraints that seem vague, articles that discuss no \
clear design decisions. Used by downstream components to decide when to \
fall back to article snippets.
"""


def build_reasoning_user_prompt(
    cleaned_text: str,
    source_title: str | None = None,
    source_domain: str | None = None,
    word_count: int | None = None,
) -> str:
    meta_lines: list[str] = []
    if source_title:
        meta_lines.append(f"Title    : {source_title}")
    if source_domain:
        meta_lines.append(f"Source   : {source_domain}")
    if word_count:
        meta_lines.append(f"Words    : {word_count:,}")

    metadata_block = "\n".join(meta_lines) if meta_lines else "(no metadata available)"

    return f"""\
ARTICLE METADATA
─────────────────────────────────────
{metadata_block}

ARTICLE TEXT
─────────────────────────────────────
{cleaned_text}

─────────────────────────────────────
TASK — REASONING PASS

Extract WHY decisions were made in the article above. Focus on tradeoffs \
(with both benefits AND costs), non-negotiable constraints, and any \
extraction warnings. Do NOT extract entities, concepts, quotes, problems, \
relationships, flows, layers, or temporal signals — those are handled by \
other passes.

CRITICAL: Every tradeoff MUST have BOTH a benefit and a cost. If the article \
only describes one side, do NOT include that tradeoff. Incomplete tradeoffs \
are worse than no tradeoffs.

Follow every rule in the system prompt exactly. Fill in as many fields as \
the article supports. Where the article does not provide information for \
a field, leave that list empty — do not invent entries.

Set confidence_score honestly based on tradeoff completeness and constraint \
clarity.
"""
