# GreenPT API smoke test

Standalone Mac-side test app to confirm the Vibe001 GreenPT key works
outside the vibe container. Single Python file, stdlib only — no
`pip install` needed.

## What it does

Runs three probes against `https://api.greenpt.ai`:

1. `GET /v1/models` — sanity-check auth + connectivity, list available models.
2. `POST /v1/embeddings` — confirm the carbon-impact telemetry shape (this
   call appears free of metered EUR credit, so it proves the API works
   regardless of your chat-credit balance).
3. `POST /v1/chat/completions` — the real query/response round-trip. This
   is the metered endpoint; if your key has zero credits, it returns
   HTTP 402 and the script tells you to top up.

## Setup

The script needs the API key. Two equivalent options:

**Option A — environment variable (preferred):**

```bash
export GREENPT_API_KEY="sk-..."
python3 main.py
```

**Option B — local file:**

```bash
echo "sk-..." > greenpt.key
python3 main.py
```

The `.gitignore` in this folder excludes `greenpt.key` so you can't
accidentally commit it.

The key from the vibe session (Vibe001) is already at
`./greenpt.key` in this folder if vibe wrote it there during the
probe session — check `cat greenpt.key` first to confirm.

## Run

```bash
cd GreenPT
python3 main.py
```

You should see something like:

```
using key ending in ...ee71QI
endpoint: https://api.greenpt.ai

=== GET /v1/models ===
  HTTP 200
  26 models available
  GreenPT-native: green-embedding, green-embeddings, green-l, green-l-raw, ...

=== POST /v1/embeddings ===
  HTTP 200
  tokens: prompt=2 total=2
  embedding: dim=2560 first 3=[9.7e-05, -0.005, 0.036]
  carbon telemetry (impact version 20250922)
    inference time: 22 ms
    energy:         5680 Wms
    emissions:      88 ugCO2e
    energy converted: 1.578 mWh (0.001578 Wh)

=== POST /v1/chat/completions ===
  query: 'Reply with one sentence: what is the SI unit of electric charge?'
  HTTP 200
  x-credits-remaining: 4823
  response: 'The SI unit of electric charge is the coulomb (C).'
  tokens: prompt=22 completion=12 total=34
  carbon telemetry (impact version 20250922)
    ...
```

If the chat call shows `HTTP 402` and `x-credits-remaining: 0`, the key
needs a top-up at https://greenpt.com — embeddings will still work to
prove auth and telemetry.

## What this proves

- **Network reachability**: GreenPT's API is reachable from your Mac
  (and was already reachable from inside the vibe container without
  firewall changes).
- **Auth**: the Vibe001 key is valid and accepted on the `Authorization:
  Bearer` header.
- **Carbon telemetry shape**: the `impact` field in every response carries
  versioned `inferenceTime` (ms), `energy` (Wms), `emissions` (ugCO2e).
  Conversion to mWh: divide energy by 3600.
- **Pricing model**: `x-credits-remaining` header decrements with each
  metered call. Embeddings appear free at probe time; chat is metered
  in EUR.

## Folder contents

- `main.py` — the smoke-test script
- `README.md` — this file
- `.gitignore` — excludes `greenpt.key` (and `__pycache__/`)
- `greenpt.key` — local-only, gitignored, contains the Vibe001 key

## Related

The full vibe-side probe findings + integration recommendation live at
`/workspace/.vs/audits/green-ai-probe.md`. This standalone app is just
the Mac-side smoke test.
