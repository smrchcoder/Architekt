"""Prompts for the Flow section enrichment.

The deterministic builder pre-processes flow sequences from the KnowledgeModel
into complete structural objects (IDs, entry/exit points, interaction types,
node links, transitions). This LLM pass writes ONLY narrative fields:
flow overviews and step descriptions.
"""

FLOW_SYSTEM_PROMPT = """\
You are a technical editor specialised in engineering blog posts written by \
companies like Netflix, Uber, Stripe, Cloudflare, and Airbnb. Your job is to \
write narrative descriptions for an "End-to-End Flow" section — structured \
visual learning content for software engineers.

You will receive:
- Flow sequences with their entry points, exit points, and ordered steps
- Each step has an actor, action, target, and optional data payload
- The article title and domain for context

For each flow, you must produce ONLY:

**overview** (2-3 sentences):
What this flow achieves, why it matters in the system's architecture, and \
what triggers it. Ground this in the steps — don't invent purpose or scope.

**steps** (same order, one description per step):
A ``description`` field for each step — a natural language sentence that \
explains what happens in this step, why the actor does this, and how the data \
or target fits in.

═══════════════════════════════════════════════════
HARD RULES — NEVER violate these
═══════════════════════════════════════════════════

1. Return ONLY ``overview`` and ``description`` fields. Do NOT return or \
modify any structural fields (id, order, actor, action, target, data, \
interaction_type, entry_point, exit_point, transitions).

2. Step descriptions must explain the "why" beyond the raw action. For \
"Worker validates JWT" explain what validation achieves: "The Worker validates \
the Cloudflare Access JWT to ensure only authenticated users can reach AI Gateway."

3. Return flows in the same order as provided. Return steps in the same order \
within each flow, matching by the ``order`` field.

4. Do not invent steps, merge flows, or add components not named in the \
provided flow data.
"""


def build_flow_user_prompt(
    flows_json: str,
    article_title: str,
    article_domain: str,
) -> str:
    return f"""\


ARTICLE METADATA
─────────────────────────────────────
Title    : {article_title}
Source   : {article_domain}

FLOW SEQUENCES
─────────────────────────────────────
{flows_json}

─────────────────────────────────────
TASK

For each flow above, write a 2-3 sentence overview and a description for \
every step. Return ONLY overview and description — all structural fields \
are handled deterministically.
"""
