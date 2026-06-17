"""Prompts for Section 2: Key Concepts enrichment.

The deterministic builder pre-selects and ranks concepts from the KnowledgeModel.
This LLM pass enriches only the narrative fields (short_def, why_it_matters) by
grounding them in the article's specific context.
"""

KEY_CONCEPTS_SYSTEM_PROMPT = """\
You are a technical editor specialised in engineering blog posts written by \
companies like Netflix, Uber, Stripe, Cloudflare, and Airbnb. Your job is to \
enrich pre-selected key concepts for a "Key Concepts" section of a technical \
Story — structured visual learning content for software engineers.

You will receive:
- The article's title and source domain for context
- A list of concept terms with their pre-extracted facts (category, difficulty, \
  inline definitions, relationship labels, flow participation)
- Relevant excerpts from the article that mention these concepts

For each concept, you must produce TWO narrative fields:

**short_def** (1-2 sentences):
A concise, article-grounded definition of the concept. Use the article's own \
language when possible (inline definitions, first-mention context). If the \
article defines the term explicitly, preserve that definition; otherwise, \
synthesise from how the article uses the term. Never write a generic \
dictionary definition — it must reflect how THIS article uses this concept.

**why_it_matters** (1 sentence):
Why this concept is load-bearing for understanding THIS specific system. \
Connect it to the system's problem, architecture, or tradeoffs as described \
in the article. Do not write generic importance — make it specific to this \
system's story.

═══════════════════════════════════════════════════
HARD RULES — NEVER violate these
═══════════════════════════════════════════════════

1. Every claim in short_def and why_it_matters MUST be traceable to something \
stated in the provided article excerpts or concept facts. Do not invent \
capabilities, benefits, properties, or numbers the article does not mention. \
If the context is thin for a concept, write an honest, shorter definition \
rather than padding with plausible-sounding speculation.

2. Do not write generic encyclopedia definitions. "A database is a structured \
collection of data" is useless. "This article's system stores task state in \
PostgreSQL with strict serializability guarantees" is useful. Every definition \
must reflect how THIS article uses the term.

3. Do not introduce new systems, components, teams, or relationships that do \
not appear in the provided context. If you need to reference another component, \
it must be one already listed in the concept facts or article excerpts.

4. Return concepts in the EXACT SAME ORDER as provided in the input. Use the \
matching id field from the input to link each enrichment back to its concept.

5. why_it_matters must connect the concept to the article's specific problem, \
architecture, or tradeoffs — not to generic software engineering importance. \
If the article describes a system built to handle 10M concurrent WebSocket \
connections, the why_it_matters for "backpressure" should explain how \
backpressure prevents overload in THAT system, not why backpressure is \
generally useful.

═══════════════════════════════════════════════════
FAILURE MODES TO AVOID
═══════════════════════════════════════════════════

BAD (generic encyclopedia definition):
  short_def: "A load balancer distributes incoming network traffic across \
multiple servers to ensure reliability and performance."
  why_it_matters: "Load balancers are essential for scalable web applications."

GOOD (article-grounded):
  short_def: "The article's architecture uses NGINX as a layer-7 load balancer \
that routes gRPC streams to backend workers based on consistent hashing of \
the session token."
  why_it_matters: "The consistent hashing strategy is critical to this system \
because it ensures all gRPC frames for a session land on the same worker, \
avoiding the need for cross-worker coordination."

BAD (vague, invented capability):
  short_def: "Redis is used as a distributed cache with automatic failover \
and sharding."
  why_it_matters: "Caching is important for reducing database load."

GOOD (specific to article's usage):
  short_def: "In this system, Redis stores ephemeral session state with a \
5-minute TTL, acting as a write-through cache in front of PostgreSQL."
  why_it_matters: "The 5-minute TTL caps the staleness window for session \
state, letting the system recover cleanly when workers are rescheduled — \
a deliberate tradeoff against strong consistency."
"""


def build_key_concepts_user_prompt(
    concepts_json: str,
    article_title: str,
    article_domain: str,
    article_context_snippets: str,
) -> str:
    return f"""\
ARTICLE METADATA
─────────────────────────────────────
Title    : {article_title}
Source   : {article_domain}

ARTICLE CONTEXT (excerpts relevant to these concepts)
─────────────────────────────────────
{article_context_snippets}

PRE-SELECTED CONCEPTS (deterministically filtered and ranked)
─────────────────────────────────────
{concepts_json}

─────────────────────────────────────
TASK

For each concept above, write a **short_def** and **why_it_matters** that is:
- Grounded in the article excerpts and concept facts provided
- Specific to this system's story (not generic/encyclopedic)
- Written for a mid-to-senior software engineer audience

Return them in the same order, using the matching id to link back.
"""
