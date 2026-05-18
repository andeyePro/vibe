# Audit — Mistral codestral public-docs probe + Green-AI vendor comparison vs GreenPT

**Date**: 2026-05-18
**Mode**: public docs only (no Mistral API key configured; unauthenticated reach confirmed)
**Triggered by**: TODO.md "Mistral `codestral` API probe (Green-AI vendor-comparison, parallels the GreenPT probe)" — last remaining For-Martin "Small bounded items I can ship without further input" entry, also referenced as sub-task (a) of the GreenPT continuation `## Open` entry
**Sister audit**: `.vs/audits/green-ai-probe.md` (2026-05-07) — same shape, GreenPT side
**Output**: research findings, no code change to vibe in this iter

## Executive summary

Mistral's API is **OpenAI-API-compatible**, **reachable from inside the vibe container without firewall changes** (`api.mistral.ai` responds with HTTP 401 on unauth — TCP and TLS layers pass), and ships a **code-specialist model (`codestral`)** at clear metered pricing ($0.30/$0.90 per 1M input/output tokens, 32K context, fill-in-the-middle support). **However Mistral does NOT expose per-request environmental impact data** — neither in response bodies nor in response headers. Per-token carbon, energy, and water consumption are published only in aggregated annual LCA reports (Mistral Large 2: 20.4 ktCO₂e cumulative training+18mo-inference, 281,000 m³ water; marginal-per-request: ~1.14 gCO₂e for a 400-token response). This is a sharp differentiator from GreenPT's `impact:` field returned on every response.

For vibe's Green-AI integration decision, Mistral is **best-in-class on training disclosure** (industry-first peer-reviewed LCA with ADEME + Carbone 4) but **structurally incompatible with vibe's per-request carbon-aware tooling story** as currently shaped by the GreenPT probe — there is no machine-readable per-request impact field to surface to the user. Mistral could still play a role in a **codestral-specific** integration (cost-competitive code model with strong sustainability narrative for the project page), but it cannot substitute for GreenPT in the "tell me the carbon cost of THIS request" use case.

## Probes attempted

### 1. Firewall reach — works

```
$ curl -fsS -o /dev/null -w "%{http_code}\n" -m 5 https://api.mistral.ai/v1/models
401
```

HTTP 401 (Unauthorized), not connection-refused or timeout. The vibe container's `init-firewall.sh` allowlist passes `api.mistral.ai` without changes. No firewall edit required to add a `--green-aux` Mistral path in future.

### 2. `GET /v1/models` (unauth) — 401

Same as #1; needs API key. No probing of available model IDs possible without auth.

### 3. API spec / OpenAPI discovery — partial

Mistral publishes API documentation at `docs.mistral.ai/api`. Documented endpoints (public docs):

- `/v1/chat/completions` (chat)
- `/v1/fim` (fill-in-the-middle, codestral-specific)
- `/v1/embeddings`
- `/v1/classifiers`
- `/v1/files`
- `/v1/models`
- `/v1/batch`
- `/v1/ocr`
- audio endpoints (speech, transcriptions, voices)

Response fields documented for `/v1/chat/completions`: `choices`, `created`, `id`, `model`, `object`, `usage`. **No environmental-impact field documented.** No `impact:`, no `carbon:`, no `energy:` field comparable to GreenPT's. No documented response headers for sustainability metrics either.

### 4. Codestral pricing + capabilities

- Input: **$0.30 per 1M tokens**
- Output: **$0.90 per 1M tokens**
- Context window: **32K tokens**
- Fill-in-the-middle: yes (the `/v1/fim` endpoint exists specifically for this; IDE-integration-tuned)
- Free tier: Mistral has a free experimentation tier (rate-limited) and paid plans; codestral-specific free-tier limits not documented in the public pricing page (need authenticated portal access to confirm)

For reference, GreenPT routes Mistral's `devstral-small-2505` and `devstral-2-123b-instruct-2512` aggregated through their own `/v1/chat/completions`; users who want Mistral's coding models can already access them through GreenPT with the `impact:` field attached, at the GreenPT credit tariff (which differs from direct-from-Mistral rates and the GreenPT probe was 402-blocked).

## Carbon disclosure schema — comparison table

| Dimension                          | GreenPT                                          | Mistral                                                       |
| ---------------------------------- | ------------------------------------------------ | ------------------------------------------------------------- |
| Per-request impact field in API    | **Yes** — `impact:{version, inferenceTime, energy, emissions}` on every successful response | **No** — no field, no header |
| Per-token cost in API response     | Yes — `usage.prompt_tokens`, etc. (OpenAI-shape) | Yes — `usage` (OpenAI-shape)                                  |
| Methodology versioning             | Yes — `impact.version: "20250922"`               | LCA report dated 2025-01, aligns with ADEME methodology       |
| Aggregated annual LCA              | Not published (no peer-reviewed LCA found)       | **Yes** — peer-reviewed, industry-first, ADEME + Carbone 4 collaboration |
| Training-emissions disclosure      | Not surfaced                                     | Yes — 20.4 ktCO₂e cumulative for Mistral Large 2 (training + 18mo inference) |
| Water-consumption disclosure       | Not in API; not in any docs surveyed             | Yes — 281,000 m³ for Mistral Large 2 lifecycle                |
| Marginal-per-request published     | Per-request from API                             | Aggregated estimate (1.14 gCO₂e per 400-token response)       |
| Database / third-party verification| None surveyed                                    | ADEME's Base Empreinte database                               |
| Renewable-energy hosting           | 100% (stated; not independently audited)         | EU-hosted; specifics not surveyed in this iter                |

The two vendors are **complementary, not competitive on disclosure**: GreenPT optimises for developer-facing per-request transparency; Mistral optimises for regulator-facing audited annual reporting. Neither shape replaces the other.

## Codestral-specific findings

`codestral` is positioned as Mistral's IDE-tuned code model with three differentiators:

1. **Fill-in-the-middle (FIM)** support via a dedicated `/v1/fim` endpoint — for inline code completion in editors. The standard `/v1/chat/completions` endpoint also accepts codestral.
2. **Lower cost than mistral-large** for code-shaped workloads ($0.30/$0.90 vs mistral-large's per-token rate, see Mistral pricing page).
3. **32K context window** — adequate for single-file edits but tighter than mistral-large-2's window.

No published per-request carbon data specific to codestral. The Mistral LCA report covers Mistral Large 2; whether codestral has its own LCA or shares an estimate by parameter-count scaling is not stated in the public materials surveyed.

## Gap analysis — what an authenticated probe would add

Provisioning a Mistral API key (paid; free tier might suffice for a probe) would resolve:

1. **Header inspection**: confirm whether Mistral returns any per-request environmental data in response headers (`x-carbon-emissions`, `x-energy`, `x-water`, `Carbon-Emissions-Scope-2`, etc.) — public docs surveyed do not list any, but an authenticated empirical probe is the definitive answer. The proposed HTTP header `Carbon-Emissions-Scope-2` (Hacker News 2023 discussion thread) might be in use by some providers; worth checking.
2. **`/v1/models` enumeration**: confirm the current 2026 codestral variants (e.g. `codestral-2405`, `codestral-latest`, any newer revisions). Mistral's model-naming convention puts date stamps on models; the public docs likely lag the actual `/v1/models` output.
3. **`usage` payload extensions**: confirm whether Mistral has extended OpenAI's `usage` field with any energy / carbon sub-objects (analogous to OpenAI's `prompt_tokens_details`).
4. **Free-tier limits for codestral**: confirm whether the experimentation tier covers codestral or restricts to general-chat models only. This affects whether vibe could ship a `--green-aux mistral` mode that works for an unauthenticated probing-via-Mistral user.
5. **OpenAPI / JSON schema**: Mistral may publish a machine-readable spec that confirms (1)–(3) without needing live probes.

Estimated cost: $1-2 in input/output tokens for a 5-call probe at codestral rates. Well under the GreenPT probe's metered-EUR exhaustion threshold.

## Implications for vibe Green-AI integration shape

The GreenPT audit recommended **Shape 2 (split-brain — chat on Anthropic Pro/Max, embeddings/rerank on GreenPT)** based on GreenPT's per-request `impact:` field on free-of-credit endpoints. This audit does not change that recommendation; Mistral's role would be **additive, not substitutive**:

- **Shape 2 stays**: GreenPT for embeddings/rerank (free, per-request carbon, vibe firewall already passes).
- **Optional Shape 2-bis: codestral for the coding inner loop**: if vibe ever wants a non-Anthropic coding model option (Green-AI charter), codestral via `/v1/fim` is the natural pick (price-competitive, Mistral's strongest training-disclosure narrative, EU-hosted). The tradeoff is **no per-request carbon surfacing** — users get the price/performance of codestral and the comfort of Mistral's annual LCA but cannot see "this commit cost N gCO₂e" in their terminal.
- **Shape 1 (full backend swap to Mistral) is unattractive** — vibe's defining feature is the Claude-Code agentic harness, which is Anthropic-API-shaped; swapping to Mistral loses the tool-call loop, the planner-subagent independence, and the `/vs` harness's existing model assignments (Opus/Sonnet/Haiku tiers).
- **Shape 3 (documentation-only)**: if neither audit moves the needle for users, vibe could ship a README section documenting "if you want the most carbon-transparent stack today, point your LiteLLM at GreenPT for embeddings/rerank and at Mistral codestral for coding completions; both endpoints are reachable from the vibe firewall without changes."

## What this audit does NOT recommend

- A `--mistral` flag in vibe core. Mistral's API is fully accessible via standard OpenAI-compatible clients (LiteLLM, Aider, Continue.dev); no vibe-side integration is required for a Mistral user. Document the path; don't ship code.
- Replacing GreenPT with Mistral. The per-request carbon data is unique to GreenPT; collapsing the audit to a single vendor would lose the developer-facing transparency that motivated this whole track.
- Treating Mistral's LCA report as a substitute for live per-request data. They serve different audiences (regulator vs developer) and both are needed for vibe's "carbon-aware AI tooling" pitch to land.

## Follow-up TODO entries

- [ ] **Authenticated Mistral codestral probe (header + `/v1/models` + free-tier-limits empirical check)** — needs a Mistral API key (free tier may suffice). Resolves the five gap-analysis items above. Estimated cost $1-2 in metered tokens; could be funded by Martin if free tier insufficient. ~30min probe. Lands as an appendix to this audit file.

- [ ] **Sketch the `vibe --green-aux` integration spec** (still gated on the GreenPT chat-`impact` schema confirmation per the sister audit's Remaining work) — but now with the codestral-specific addendum: if vibe wants the "non-Anthropic coding model option" sub-flag, add `--green-aux mistral` semantics to that spec. The two flags can coexist (`--green-aux greenpt-embeddings`, `--green-aux mistral-codestral`, both selectable independently).

## Sources

- [Mistral AI Pricing 2026 (DevTk.AI compendium)](https://devtk.ai/en/blog/mistral-api-pricing-guide-2026/)
- [Mistral codestral pricing (Helicone calculator)](https://www.helicone.ai/llm-cost/provider/mistral/model/codestral)
- [Mistral AI Pricing official (Le Chat focus; API tab not in fetch)](https://mistral.ai/pricing)
- [Mistral API documentation — endpoints + response fields](https://docs.mistral.ai/api)
- [Our contribution to a global environmental standard for AI — Mistral newsroom](https://mistral.ai/news/our-contribution-to-a-global-environmental-standard-for-ai)
- [Mistral environmental impact analysis — David Mytton, devsustainability](https://www.devsustainability.com/p/mistrals-environmental-impact)
- [Mistral report confirms AI is a hungry, thirsty beast — The Register](https://www.theregister.com/2025/07/24/mistral_environmental_report_ai_cost/)
- [French AI Startup Discloses Full Lifecycle Consumption — The Batch (DeepLearning.AI)](https://www.deeplearning.ai/the-batch/french-ai-startup-discloses-full-lifecycle-consumption-and-emissions-for-mistral-large-2/)
- [Mistral AI Reveals 2,200 Tons CO2 Emissions from Training Large Model — WebProNews](https://www.webpronews.com/mistral-ai-reveals-2200-tons-co2-emissions-from-training-large-model/)
- [HTTP Response Header Field: Carbon-Emissions-Scope-2 — Hacker News thread](https://news.ycombinator.com/item?id=35528651) (referenced as a candidate header to probe for in the authenticated follow-up)
