---
description: Narrow mode — restores strictly serial dispatch, undoing /wide. One subagent in flight at a time. Reverse with /wide.
---

# /narrow — the width axis, off

`/narrow` restores strictly serial dispatch: exactly one subagent in flight at a time, one stage after another — the same behaviour `/vs`/`/vss`/`/vsss` already have when [`/wide`](wide.md) was never invoked. It is the inverse of `/wide`; see `wide.md` for the caps and stacking table it overrides. `/narrow` × any stacking (with or without `/diet`, `/feast`, `--fable-subagents`) collapses to the same outcome: strictly serial.

Until `/wide` is invoked again, no two `Agent(...)` dispatches share a message: the chair issues one, waits for its completion notification, then issues the next.
