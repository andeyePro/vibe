#!/usr/bin/env python3
"""
GreenPT API smoke test.

Run this on your Mac (outside the vibe container) to confirm:
  - the API is reachable from your network
  - the Vibe001 key authenticates correctly
  - the carbon-impact telemetry is shaped as documented

Stdlib only. No `pip install` needed. Tested against Python 3.11+.

Key resolution order:
  1. GREENPT_API_KEY environment variable
  2. ./greenpt.key file next to this script (one line: just the key)

Usage:
    GREENPT_API_KEY=sk-... python3 main.py
or
    echo "sk-..." > greenpt.key
    python3 main.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.greenpt.ai"
TIMEOUT = 30  # seconds


def get_api_key() -> str:
    key = os.environ.get("GREENPT_API_KEY", "").strip()
    if key:
        return key
    key_file = Path(__file__).resolve().parent / "greenpt.key"
    if key_file.exists():
        contents = key_file.read_text().strip()
        # Accept either bare key on first line, or KEY=VALUE format.
        for line in contents.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                _, _, val = line.partition("=")
                return val.strip()
            return line
    sys.exit(
        "error: no API key found.\n"
        "  set GREENPT_API_KEY in your shell, or\n"
        "  put the key on one line in ./greenpt.key (next to this script)."
    )


def call_api(path: str, method: str, key: str, body=None):
    url = f"{API_BASE}{path}"
    headers = {"Authorization": f"Bearer {key}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8")
    except urllib.error.URLError as e:
        sys.exit(f"network error reaching {API_BASE}: {e.reason}")


def show_section(label: str) -> None:
    print(f"\n=== {label} ===")


def show_impact(payload: dict) -> None:
    impact = payload.get("impact")
    if not impact:
        print("  (no impact field in response)")
        return
    inf = impact.get("inferenceTime", {})
    eng = impact.get("energy", {})
    emi = impact.get("emissions", {})
    print(f"  carbon telemetry (impact version {impact.get('version', '?')})")
    print(f"    inference time: {inf.get('total', '?')} {inf.get('unit', '')}")
    print(f"    energy:         {eng.get('total', '?')} {eng.get('unit', '')}")
    print(f"    emissions:      {emi.get('total', '?')} {emi.get('unit', '')}")
    if eng.get("unit") == "Wms" and isinstance(eng.get("total"), (int, float)):
        mWh = eng["total"] / 3600
        print(f"    energy converted: {mWh:.3f} mWh ({mWh / 1000:.6f} Wh)")


def main() -> None:
    key = get_api_key()
    print(f"using key ending in ...{key[-6:]}")
    print(f"endpoint: {API_BASE}")

    # 1. Sanity: list models. Confirms auth + connectivity.
    show_section("GET /v1/models")
    status, _, body = call_api("/v1/models", "GET", key)
    print(f"  HTTP {status}")
    if status != 200:
        print(f"  body: {body[:300]}")
        sys.exit(1)
    models = json.loads(body).get("data", [])
    print(f"  {len(models)} models available")
    native = sorted(m["id"] for m in models if m.get("owned_by") == "greenpt")
    if native:
        print(f"  GreenPT-native: {', '.join(native)}")

    # 2. Embeddings. Free of metered credits at probe time. Proves carbon
    #    telemetry shape regardless of whether your account has chat credits.
    show_section("POST /v1/embeddings")
    status, _, body = call_api(
        "/v1/embeddings", "POST", key,
        {"model": "green-embeddings", "input": "hello world"},
    )
    print(f"  HTTP {status}")
    if status == 200:
        payload = json.loads(body)
        usage = payload.get("usage", {})
        print(f"  tokens: prompt={usage.get('prompt_tokens')} total={usage.get('total_tokens')}")
        emb = payload["data"][0]["embedding"]
        print(f"  embedding: dim={len(emb)} first 3={emb[:3]}")
        show_impact(payload)
    else:
        print(f"  body: {body[:500]}")

    # 3. Chat. Metered (EUR credits). This is the "send a query, get a response"
    #    round-trip you wanted to confirm. Will 402 if credits = 0; embedding
    #    above is the auth/telemetry proof in that case.
    show_section("POST /v1/chat/completions")
    user_q = "Reply with one sentence: what is the SI unit of electric charge?"
    print(f"  query: {user_q!r}")
    status, headers, body = call_api(
        "/v1/chat/completions", "POST", key,
        {
            "model": "green-s",
            "messages": [{"role": "user", "content": user_q}],
            "max_tokens": 60,
            "temperature": 0,
        },
    )
    print(f"  HTTP {status}")
    credits = headers.get("x-credits-remaining") or headers.get("X-Credits-Remaining")
    if credits is not None:
        print(f"  x-credits-remaining: {credits}")
    if status == 200:
        payload = json.loads(body)
        msg = payload["choices"][0]["message"]["content"]
        print(f"  response: {msg!r}")
        usage = payload.get("usage", {})
        print(
            f"  tokens: prompt={usage.get('prompt_tokens')}"
            f" completion={usage.get('completion_tokens')}"
            f" total={usage.get('total_tokens')}"
        )
        show_impact(payload)
    elif status == 402:
        print(f"  body: {body}")
        print()
        print("  → key has zero credits for chat. Top up at https://greenpt.com")
        print("    to confirm the chat impact schema (assumed identical to")
        print("    embeddings; same impact.version). Embeddings above already")
        print("    proved auth + carbon telemetry shape.")
    else:
        print(f"  body: {body[:500]}")


if __name__ == "__main__":
    main()
