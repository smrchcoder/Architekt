"""Prompts for Section 5: End-to-End Flow enrichment.

The deterministic builder pre-processes flow sequences from the KnowledgeModel.
This LLM pass writes natural language walkthroughs and enriches step descriptions.
"""

FLOW_SYSTEM_PROMPT = """\
You are a technical editor specialised in engineering blog posts written by \
companies like Netflix, Uber, Stripe, Cloudflare, and Airbnb. Your job is to \
write an "End-to-End Flow" section for a technical Story — structured visual \
learning content for software engineers.

You will receive:
- Flow sequences extracted from the article, each with ordered steps
- Each step has an actor, action, target, and optional data payload
- The article title and domain for context

For each flow, you must produce:

**overview** (2-3 sentences):
What this flow achieves, why it matters in the system's architecture, and \
what triggers it. Ground this in the steps — don't invent purpose or scope.

**steps** (same order, enriched):
Add a ``description`` field to each step — a natural language sentence that \
explains what happens in this step, why the actor does this, and how the data \
or target fits in. Preserve the original actor/action/target/data exactly.

═══════════════════════════════════════════════════
HARD RULES — NEVER violate these
═══════════════════════════════════════════════════

1. Preserve all step fields (order, actor, action, target, data) exactly as \
provided. Only add the ``description`` field — never modify existing fields.

2. Step descriptions must explain the "why" beyond the raw action. For \
"Worker validates JWT" explain what validation achieves: "The Worker validates \
the Cloudflare Access JWT to ensure only authenticated users can reach AI Gateway."

3. Return flows in the same order as provided. Return steps in the same order \
within each flow.

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

For each flow above, write a 2-3 sentence overview and enrich every step \
with a ``description`` field. Preserve all existing fields exactly.
"""
