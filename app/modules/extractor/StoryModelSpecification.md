Section 1 — Overview

The first thing a user reads. Answers: what is this article about, what system is being discussed, and why does this article exist. Must orient a reader who has never heard of the company or system before.

AI extraction intent: Write the summary as if explaining to a smart engineer unfamiliar with the company. Avoid jargon not defined in Section 2. one_line_summary is the most important field — it is used as the card preview text in listing pages.

"overview": {

  "one_line_summary": "Netflix replaced a centralized ML routing service with a per-caller sidecar architecture to eliminate shared failure modes across 40+ ML use cases.",

  "system_name": "Lightbulb",

  "company": "Netflix",

  "domain": ["ML Infrastructure", "Distributed Systems"],

  "full_summary": "Netflix's ML platform routes inference requests from product surfaces to the right model cluster. As the number of ML use cases grew, their centralized router (Switchboard) became a single point of failure and a shared blast radius for all tenants. This article documents the evolution to Lightbulb, a per-caller sidecar that decouples model selection from request routing.",

  "why_it_exists": "To allow ML researchers to ship new model versions without coordinating with client app teams, and to eliminate the risk of one bad tenant degrading all others.",

  "reading_time_min": 8

}

Section 2 — Key Concepts

An array of technical terms the reader needs before the architecture section makes sense. Each concept is self-contained. The AI should extract only concepts that are load-bearing for this specific article — not a generic glossary.

AI extraction intent: Extract 3–6 concepts. Prioritise terms used without definition in the article body. Skip terms like REST or API that a target reader already knows.

Array constraint: Min 2 items, max 8. The frontend renders concepts as a card grid — more than 8 causes layout degradation.

"concepts": [

  {

    "id": "objective",

    "name": "Objective",

    "short_def": "A named use case contract between a client app and the ML platform.",

    "why_it_matters": "It is the stable API surface that never changes even when models underneath are swapped.",

    "category": "data_model",

    "difficulty": "intermediate"

  },

  {

    "id": "routing-key",

    "name": "Routing Key",

    "short_def": "A token placed in request headers that maps a request to the correct model cluster.",

    "why_it_matters": "Enables low-overhead routing — Envoy reads headers without parsing the request body.",

    "category": "protocol",

    "difficulty": "intermediate"

  },

  {

    "id": "envoy-proxy",

    "name": "Envoy Proxy",

    "short_def": "An open-source edge proxy that performs the actual traffic forwarding.",

    "why_it_matters": "Keeps routing logic entirely out of application code by acting on header metadata.",

    "category": "infrastructure",

    "difficulty": "foundational"

  }

]

Section 3 — Problem Statement

Explains the pain the company was experiencing before this system existed. A well-formed problem section is the difference between a reader understanding why a complex architecture was chosen versus thinking the engineers over-engineered a simple problem.

AI extraction intent: The problem is almost never stated explicitly in one place. Synthesise it from scattered context: the introduction, motivation sections, and challenges described before the solution. Extract constraints separately from pain points — they are architecturally different.

"problem": {

  "headline": "A single routing cluster became a systemic failure point across all ML use cases.",

  "context": "Netflix built Switchboard as a centralized routing service for all member-facing ML inference. As the number of tenants grew beyond a handful of use cases, the shared cluster began to exhibit cross-tenant failure modes that were difficult to isolate or mitigate.",

  "pain_points": [

    "Switchboard was a single point of failure — any outage cut off all ML serving simultaneously.",

    "A surge of bad requests from one tenant could cascade errors to completely unrelated use cases.",

    "Different ML use cases had incompatible latency requirements that a shared cluster could not satisfy simultaneously."

  ],

  "constraints": [

    "Client apps must integrate with the ML platform only once — model updates must not require client changes.",

    "The solution must preserve context-aware routing and model ID abstraction from Switchboard."

  ],

  "scale_context": "Across 40+ ML use cases serving hundreds of millions of members globally.",

  "prior_approach": "Switchboard"

}


Section 4 — Architecture Overview

The most technically dense section. Defines the major components and their relationships. The nodes and edges arrays are the direct input to the React Flow diagram renderer — their structure must be exact.

Renderer contract: nodes[] and edges[] are passed directly to React Flow. Any schema violation breaks the diagram. The backend must validate against the Pydantic schema before storing.

AI extraction intent: Extract only components that appear as distinct named systems in the article. Do not invent components. Each node represents one system boundary. Relationships should be directional and labelled with the type of interaction.

"architecture": {

  "summary": "Lightbulb splits the work Switchboard did as one unit into two isolated components: a per-caller sidecar that handles model selection, and Envoy proxy that handles the actual network routing based on a header token.",

  "diagram_hint": "top_down",



  "layers": [

    { "id": "client-layer",  "label": "Client layer",        "order": 0 },

    { "id": "routing-layer", "label": "Routing layer",       "order": 1 },

    { "id": "model-layer",   "label": "Model serving layer", "order": 2 }

  ],



  "nodes": [

    {

      "id": "domain-service",

      "label": "Domain microservice",

      "type": "client",

      "description": "Product surface calling the ML platform, e.g. recommendations or artwork service.",

      "layer_id": "client-layer",

      "is_new": false,

      "concept_ref": null

    },

    {

      "id": "lightbulb",

      "label": "Lightbulb sidecar",

      "type": "service",

      "description": "Per-caller process that reads the Objective config and picks the model version to serve.",

      "layer_id": "routing-layer",

      "is_new": true,

      "concept_ref": null

    },

    {

      "id": "envoy-proxy",

      "label": "Envoy proxy",

      "type": "proxy",

      "description": "Reads the routingKey header and forwards the request to the correct cluster VIP.",

      "layer_id": "routing-layer",

      "is_new": false,

      "concept_ref": "envoy-proxy"

    },

    {

      "id": "model-cluster",

      "label": "Model cluster",

      "type": "model",

      "description": "The actual ML model cluster that runs inference and returns a response.",

      "layer_id": "model-layer",

      "is_new": false,

      "concept_ref": null

    }

  ],



  "edges": [

    {

      "id": "edge-domain-lightbulb",

      "source": "domain-service",

      "target": "lightbulb",

      "label": "sends Objective name + context",

      "edge_type": "sync"

    },

    {

      "id": "edge-lightbulb-envoy",

      "source": "lightbulb",

      "target": "envoy-proxy",

      "label": "writes routingKey to header",

      "edge_type": "sync"

    },

    {

      "id": "edge-envoy-model",

      "source": "envoy-proxy",

      "target": "model-cluster",

      "label": "forwards inference request",

      "edge_type": "sync"

    }

  ]

}

Section 5:
Form the end to end flow on how request comes into the system end to end , each indiviudal possible steps

Section 6:
TradeOff and KeyLearnings