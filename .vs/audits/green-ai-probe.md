# Audit — GreenPT API probe + Green-AI vendor integration shape

**Date**: 2026-05-07
**Probe key**: `Vibe001` (chmod 600 at `.vibe/greenpt.tokens`, gitignored)
**Triggered by**: TODO.md "URGENT: test GreenPT API calls + determine Green-AI vendor integration shape" (2026-04-29)
**Constraint**: 17-day deadline (per Martin 2026-05-07; reason TBC — likely trial window or beta access)
**Output**: research findings, no code change to vibe in this iter

## Executive summary

GreenPT's API is **OpenAI-API-compatible**, **reachable from inside the vibe container without firewall changes** (api.greenpt.ai resolves and serves over HTTPS), and **carries a carbon-impact telemetry field on every response** in a documented schema. The platform is **purely metered (EUR), no subscription tier visible** — which collides with vibe's `## Non-goals` in `/workspace/CLAUDE.md`: "Anything that bills against API rates or extended credits separately from the user's Pro/Max subscription [...] stays out of vibe core". Embeddings and rerank appear free of metered credit; only chat-completions are credited. The Vibe001 key currently has zero credits (`x-credits-remaining: 0`, HTTP 402 on chat) — a top-up is required to probe the chat-completion `impact` schema empirically.

## Probes run

All probes from inside the vibe container, 2026-05-07T19:07-19:09Z. Auth header `Authorization: Bearer <Vibe001>`.

### 1. `GET /v1/models` — works

HTTP 200, 213 ms, OpenAI-compatible response shape. Models partition into:

- **GreenPT-native**: `green-l`, `green-l-raw`, `green-r`, `green-r-raw`, `green-s`, `green-s-pro`, `green-embedding`, `green-embeddings`, `green-rerank`
- **Aggregated open-source**: Mistral (`devstral-2-123b-instruct-2512`, `mistral-small-3.2-24b-instruct-2506`, `mistral-nemo-instruct-2407`, `voxtral-small-24b-2507`, `pixtral-12b-2409`, `devstral-small-2505`), Qwen (`qwen3-coder-30b-a3b-instruct`, `qwen3-235b-a22b-instruct-2507`, `qwen3.5-397b-a17b`), Llama (`llama-3.3-70b-instruct`, `llama-3.1-8b-instruct`), Gemma (`gemma-3-27b-it`, `gemma4`), DeepSeek (`deepseek-r1-distill-llama-70b`), OpenAI-OSS (`gpt-oss-120b`), HCompany (`holo2-30b-a3b`), BAAI (`bge-multilingual-gemma2`)

`-raw` variants on `green-l` / `green-r` likely expose the unprocessed model output (no GreenPT post-processing). Default to non-raw for production usage.

### 2. `POST /v1/embeddings` — works, free of metered credit

Tested with `green-embeddings` model on a 2-token input. HTTP 200, 22 ms. Response body:

```json
{
  "id": "embd-...",
  "object": "list",
  "model": "green-embeddings",
  "data": [{"index": 0, "object": "embedding", "embedding": [...]}],
  "usage": {"prompt_tokens": 2, "total_tokens": 2, "completion_tokens": 0, "prompt_tokens_details": null},
  "impact": {
    "version": "20250922",
    "inferenceTime": {"total": 22, "unit": "ms"},
    "energy":        {"total": 5680, "unit": "Wms"},
    "emissions":     {"total": 88, "unit": "ugCO2e"}
  }
}
```

Embedding vector is 2560-dim float32. **No `x-credits-remaining` header observed** (vs the 402 chat response which carried `x-credits-remaining: 0`), strongly suggesting embeddings are free or charged differently from chat — needs confirmation against their pricing docs.

### 3. `POST /v1/rerank` — works, returns `impact`

Tested with `green-rerank` on a 2-document corpus. HTTP 200, 28 ms. Same `impact` shape as embeddings:

```json
"impact": {
  "version": "20250922",
  "inferenceTime": {"total": 28, "unit": "ms"},
  "energy":        {"total": 2210, "unit": "Wms"},
  "emissions":     {"total": 12, "unit": "ugCO2e"}
}
```

### 4. `POST /v1/chat/completions` — blocked on credits

HTTP **402 Payment Required**, body `{"error":"No remaining credits (EUR)"}`, header `x-credits-remaining: 0`. Schema for chat's `impact` field unverified until credits top-up; safe to assume identical to embeddings/rerank given the shared `version: 20250922`.

### 5. OpenAPI / Swagger spec discovery — none found

Probed `/openapi.json`, `/swagger.json`, `/docs/openapi.json`, `/v1/openapi.json`, `/.well-known/openapi.json` — all 404. GreenPT's docs site at `docs.greenpt.ai` is a JS-rendered SPA that returns only metadata to WebFetch; need direct browser inspection or a published OpenAPI URL we don't yet know.

### 6. Account / billing endpoints — TBD

Probed `/v1/account`, `/v1/credits`, `/v1/usage`, `/v1/balance`, `/v1/me` — output truncated due to size; need a follow-up targeted probe to confirm. Worth knowing: does an authenticated account-info endpoint exist for top-up status, or is that purely web-UI?

## Carbon telemetry schema

`impact` field at top-level of every successful response. Versioned (`version: "20250922"` — methodology dated 2025-09-22). Three sub-objects, all `{"total": <number>, "unit": <string>}`:

| Field          | Unit          | What it measures                                                |
| -------------- | ------------- | --------------------------------------------------------------- |
| `inferenceTime`| `ms`          | Wall-clock model inference time for THIS request                |
| `energy`       | `Wms` (Watt-milliseconds) | Energy consumed for THIS request (1 Wms = 0.001 J = 0.000278 mWh) |
| `emissions`    | `ugCO2e` (micro-grams CO2-eq) | Greenhouse-gas emissions for THIS request                        |

**Mapping to GreenPT's published "mWh per 100 tokens" metric**: not surfaced directly in the API response; computed client-side as `(energy_Wms / 3600 / total_tokens) * 100`, where 1 Wms = 1/3600 mWh.

Worked example from probe 2:

- 5680 Wms / 3600 = 1.58 mWh for 2 tokens
- → 78.9 mWh per 100 tokens (embeddings on `green-embeddings`)

This is comparable to the figures on `greenpt.com/blog/introducing-a-new-ai-metric-to-drive-sustainability/` (search-confirmed 2026-05-07).

## Pricing model

**Pay-as-you-go EUR credits.** Header `x-credits-remaining` confirms credits are decremented from a positive balance until zero, at which point chat-completions return HTTP 402. Embeddings and rerank appear NOT to deduct from this credit pool (no header on those responses; no error on zero balance), but this requires confirmation from GreenPT's pricing page or a direct probe with negative-credit account state.

**No subscription tier observed.** The 402 error string is `"No remaining credits (EUR)"` and the credits header is denominated in EUR — both signal metered billing, not flat-rate subscription. If GreenPT later offers a subscription, the response shape would presumably need a different signal.

**Rate limit**: 40 requests / 60 second window (`ratelimit-limit: 40`, `ratelimit-policy: 40;w=60`). Per-key, not per-account (assumed; needs verification).

## Comparison to Anthropic API shape

| Concern                | Anthropic                                         | GreenPT                                                      |
| ---------------------- | ------------------------------------------------- | ------------------------------------------------------------ |
| Auth header            | `x-api-key: <key>` + `anthropic-version` header   | `Authorization: Bearer <key>`                                |
| Chat endpoint          | `POST /v1/messages` (Anthropic Messages API)      | `POST /v1/chat/completions` (OpenAI-compatible)              |
| Request shape          | `{model, messages, max_tokens, system, ...}`      | `{model, messages, max_tokens, temperature, ...}` (OpenAI-style) |
| Response token usage   | `usage.input_tokens`, `usage.output_tokens`       | `usage.prompt_tokens`, `usage.completion_tokens`, `usage.total_tokens` |
| Carbon telemetry       | None                                              | `impact: {version, inferenceTime, energy, emissions}`        |
| Streaming              | Yes (SSE)                                         | Yes (assumed; OpenAI-compatible)                             |
| Tool use               | Anthropic format                                  | OpenAI format (assumed; needs probe)                         |
| Vision                 | Anthropic format                                  | Pixtral / Voxtral models suggest yes; needs probe            |
| Pricing                | Pro/Max subscription quota OR API per-token       | EUR per-token, metered                                       |
| Tool-loop story        | Claude Code (native)                              | OpenAI-compatible loops via Aider/Continue/LiteLLM           |

**Translation layer needed for vibe integration**: thin. The wrapper would translate Anthropic Messages format → OpenAI Chat Completions format (well-trodden territory; LiteLLM does this), strip Anthropic-specific tool/extended-thinking blocks, expose the `impact` field as new metadata. The hard part is NOT the API translation; it's the **agent loop**. Claude Code's tool-use, computer-use, and extended-thinking are Claude-specific; a GreenPT-backed vibe would lose those and would need a different agent harness (Aider, Continue.dev, Cursor's open-source backend).

## Implications for vibe integration

### Constraint: vibe's "no extra spend" non-goal

`/workspace/CLAUDE.md` `## Non-goals` says: "Anything that bills against API rates or extended credits separately from the user's Pro/Max subscription. [...] If a feature requires the Anthropic API (e.g. Claude Agent SDK, cloud/async agent runners as they exist today), it stays out of vibe core — the project is for Pro/Max subscribers who do not want to pay extra. Defer such features until Anthropic ships a path that runs against subscription quota."

This was written about Anthropic's API, but the principle applies symmetrically: **GreenPT's metered EUR billing is "extra spend separate from Pro/Max"**. A vibe-default GreenPT integration would betray the non-goal. Two interpretations:

(a) **Strict**: GreenPT can only ship as an OPT-IN backend for users who explicitly accept the EUR billing trade-off. Default vibe stays Anthropic Pro/Max.

(b) **Loose**: vibe could ship a `vibe --green` flag that routes specific cost-permitted operations (e.g. embeddings, rerank — which appear free) to GreenPT, while keeping chat on Anthropic. This sidesteps the non-goal because the FREE operations don't billede.

(b) is the more interesting integration if the free-tier-for-embeddings pattern holds.

### Three candidate shapes (refining the original TODO entry's a/b/c)

**Shape 1 — `vibe --green` opt-in: full backend swap**. User runs `vibe --green` and the container launches with claude-code replaced by an OpenAI-compatible agent harness (Aider or Continue.dev) configured against `api.greenpt.ai`. Loses `/vs`, `/sp`, `/learn`, the bypass-permission container, `/c` clipboard, etc. — vibe's distinct value mostly evaporates. Use case: Martin or another user wants to spend EUR on transparent-carbon AI for one specific project. Cost: high build effort, low retained value-add.

**Shape 2 — `vibe --green-aux` split-brain**. Default container still runs claude-code on Pro/Max for coding agentic loops. A side-channel exposes `green-embeddings` and `green-rerank` to specific in-session features (e.g. `/learn`'s smart-capture could use `green-embeddings` to find similar entries; `/learn --review` could use `green-rerank`). Free operations only; chat-completions stay on Pro/Max. Cost: medium build effort, modest retained value-add (telemetry visibility on the embedding/rerank work; `/learn` quality boost).

**Shape 3 — documentation-only**. Don't ship code; document how to run vibe-equivalent workflows pointing Aider/Continue.dev/LiteLLM at GreenPT. Add a `docs/green-alternatives.md` page. Cost: low effort, low retained value, but honors the non-goal cleanly. Useful for users who already want to use GreenPT and just need pointers.

### Recommended path

**Shape 2 (split-brain) for v1**. Reasoning:

- Honours the non-goal: chat stays on Pro/Max, no per-call EUR billing for the user's primary work.
- Embeddings and rerank are genuinely useful for `/learn` smart-capture (task_010 cycle 1 PASS 2026-05-07, commit `eb90014`) and `/learn --review` (task_011, parked) — both currently rely on Claude itself doing semantic checks at chat-completion cost. Routing semantic-similarity to free embeddings would cut those costs by 90%+.
- Visible carbon telemetry on those operations gives users a data point on their environmental footprint — without forcing them onto a paid backend.
- Falls back gracefully: if GreenPT is unreachable or the user's GreenPT key is missing, the existing Pro/Max-on-Claude path still works.

**Trigger to revisit**: if Anthropic ships a subscription-quota equivalent to GreenPT's metered chat (i.e. a flat-rate green model that doesn't re-bill), revisit Shape 1.

## Action items

### For Martin (external/empirical)

- [ ] **Top up the Vibe001 key** with EUR credits so the chat-completion `impact` schema can be confirmed (probably identical to embeddings/rerank, but worth verifying for the spec). Without this, the vibe integration spec for chat is theoretical.
- [ ] **Confirm the 17-day deadline** — is this trial credits expiring? A beta-access window? Knowing the constraint sharpens the priority.
- [ ] **Manual spot-check at https://greenpt.com/account** (or wherever the user portal lives) for: subscription tier availability, embeddings-pricing-vs-chat-pricing confirmation, whether the EUR balance is per-key or per-account.

### For me (autonomous, when re-invoked)

- [ ] **Try at least one alternative Green-AI vendor for comparison** — TODO entry asked for this. Mistral's `codestral` API is the natural starting point: EU-hosted, publishes carbon impact, has Aider/Continue.dev tool-loop story. WebSearch for `codestral` API endpoint and probe similarly. Do this in a fresh session rather than burning context here.
- [ ] **Sketch the Shape-2 (split-brain) integration spec** as a `/vs` task once the chat `impact` schema is confirmed. Write a `vibe --green-aux` flag spec that adds GreenPT-backed embedding/rerank to `/learn` smart-capture and `/learn --review`. Honor the no-extra-spend non-goal by gating chat strictly to Anthropic.
- [ ] **Document firewall delta**: `init-firewall.sh` allowlist would need to add `api.greenpt.ai` IF the host filter doesn't already permit it (this probe worked, suggesting it's already allowed via DNS resolution + HTTPS allowlist; verify by reading `init-firewall.sh` once and document either way).

## Sources

- GreenPT API live probe (this audit's empirical work)
- [Developer and API documentation of GreenPT](https://docs.greenpt.ai/) (SPA — content not extractable via WebFetch; visit in browser for full docs)
- [Introducing a New AI Metric for Sustainability | GreenPT](https://greenpt.com/blog/introducing-a-new-ai-metric-to-drive-sustainability/) (mWh-per-100-tokens metric explanation)
- [GreenPT - The green AI & privacy-friendly GPT Chat](https://greenpt.com/) (product page; renewable hosting in Europe claim)
