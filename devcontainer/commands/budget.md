---
description: Budget manager — month-to-date token usage per model across all vibe sessions on this machine, estimated Fable 5 credit spend at list rates, plus quota-pressure context for the Max/Pro plan decision. `/budget` for the rollup; `/budget session` for the current session only.
---

# /budget — spend and quota rollup

You produce a usage report from the session transcripts on disk. Three honest constraints — state them in every report footer, briefly:

1. **Credit figures are estimates, not invoices** — token counts × Anthropic list rates ($10/$50 per MTok for Fable 5; cache reads ~0.1×, cache writes ~1.25× of input). The authoritative credit balance is the account console; there is no API for it on a subscription.
2. **Claude Code only.** Claude chat on phone/desktop shares the same subscription quota but leaves no transcript here — the quota picture is partial.
3. **This Mac only.** Transcripts live in the `vibe-claude-config` volume and don't travel between machines.

## Procedure

Run this script verbatim via Bash (it is self-contained; do not rewrite it ad hoc — edit this file if it needs to change):

```bash
python3 - "$@" <<'PYBUDGET'
import json, os, glob, sys, datetime, collections

FABLE_RATES = {"in": 10.0, "out": 50.0, "cache_read": 1.0, "cache_write": 12.5}  # $/MTok
now = datetime.datetime.now(datetime.timezone.utc)
month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
week_start = now - datetime.timedelta(days=7)

buckets = {"month": collections.defaultdict(lambda: collections.Counter()),
           "week":  collections.defaultdict(lambda: collections.Counter())}
sessions = collections.defaultdict(set)

for path in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
    try:
        with open(path, errors="replace") as f:
            for line in f:
                if '"usage"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message") or {}
                usage = msg.get("usage") or {}
                model = msg.get("model") or "unknown"
                ts = obj.get("timestamp")
                if not ts:
                    continue
                try:
                    t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if t < month_start and t < week_start:
                    continue
                row = {
                    "in": usage.get("input_tokens", 0) or 0,
                    "out": usage.get("output_tokens", 0) or 0,
                    "cache_read": usage.get("cache_read_input_tokens", 0) or 0,
                    "cache_write": usage.get("cache_creation_input_tokens", 0) or 0,
                }
                for period, start in (("month", month_start), ("week", week_start)):
                    if t >= start:
                        for k, v in row.items():
                            buckets[period][model][k] += v
                        sessions[period].add(path)
    except OSError:
        continue

def fable_usd(c):
    return (c["in"] * FABLE_RATES["in"] + c["out"] * FABLE_RATES["out"]
            + c["cache_read"] * FABLE_RATES["cache_read"]
            + c["cache_write"] * FABLE_RATES["cache_write"]) / 1_000_000

for period, label in (("month", f"Month to date ({month_start:%Y-%m})"), ("week", "Past 7 days")):
    print(f"\n== {label} — {len(sessions[period])} session file(s) ==")
    print(f"{'model':<28}{'input':>14}{'output':>14}{'cache_rd':>16}{'cache_wr':>14}")
    total_usd = 0.0
    for model in sorted(buckets[period]):
        if not any(buckets[period][model].values()):
            continue
        c = buckets[period][model]
        line = f"{model:<28}{c['in']:>14,}{c['out']:>14,}{c['cache_read']:>16,}{c['cache_write']:>14,}"
        if "fable" in model or "mythos" in model:
            usd = fable_usd(c)
            total_usd += usd
            line += f"   ≈ ${usd:,.2f} credits"
        else:
            line += "   (subscription quota)"
        print(line)
    print(f"{'':>76}est. credit spend: ${total_usd:,.2f}")
PYBUDGET
```

## Reporting

- Lead with the two numbers Martin actually decides on: **estimated credit spend this month** (money) and **subscription output tokens this month** (quota pressure). Then the per-model table, then the three-constraint footer in one line each.
- If the month's Fable tokens are all dated before 8 Jul 2026, note they fell in the free window and the credit estimate for them is $0 (the script prices all Fable tokens; subtract the pre-cutover portion when it matters).
- When asked "should I downgrade Max→Pro", compare month subscription usage against ~5× headroom: sustained heavy use of the all-model weekly pool argues for keeping Max; a mostly-idle month argues Pro + credits. Give a recommendation, not a survey.

## Per-task budgets

Per-task budget proposal/approval is `/vs`'s job, not this skill's: the Planner's **Model plan** in `.vs/spec.md` carries the estimated tokens per tier and estimated credits if the Fable rung is authorised, and the user amends/approves it with the spec. `/budget` is the observability half: run it before and after a big task to see what the task actually drew.
