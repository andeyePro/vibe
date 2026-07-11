# /vsss async human input — design synthesis (2026-07-11)

Question (Martin): are the Time&I brain2 channels the optimum way for `/vsss` to take asynchronous human input — Martin answers whenever free, agentic work never stops?

Method: one Fable analyst read the live Time&I channel files + the /vsss protocol; three blind designers (1 Fable, 2 Opus, byte-identical briefs, no shared context) designed from scratch. Full reports: scratchpad `async-input-analyst.md`, `-brainstorm-A/B/C.md` (session-local); this memo is the durable synthesis. Convergence was strong — all four independently landed on the same skeleton, which per the /vs panel doctrine is earned confidence, and their rationale textures differed (file-truth vs projection-purity vs channel-splitting), so it is not correlated consensus.

## Verdict on Time&I

Adapt its **conventions**, don't generalise its **files**. The numbering / gap-means-archived / one-item-per-number rules are excellent and stay. But the three shared files were built for one app's ongoing dialogue: they have no decision-point binding (an answer can't say WHICH fork it authorises), no lifecycle for "the loop took a default two hours ago", and multiple concurrent /vsss loops sharing them would collide. And /vsss ships to all vibe users while brain2 is Martin-only — so brain2 cannot be the canonical store.

## The design (convergent core, adjudicated details)

1. **Canonical store = per-project ask ledger**: `.vss/qa/<Q-project-seq>.md`, one file per question, a small state machine `OPEN → DEFAULTED|PARKED → ANSWERED → APPLIED|SUPERSEDED → ARCHIVED`, recording the decision point (task + HEAD SHA at ask time), the declared default, the revisit window, and the eventual answer. Committed (audit-trail value, matches `.vss/sessions/`); public-facing repos may gitignore via an opt-out. Single-writer, atomic tmp+mv, IDs never reused.
2. **Three-class decision taxonomy** (replaces today's binary abort-or-decide):
   - **PROCEED-on-default**: both branches workable, reversible — declare the default in the ledger, do it, keep a revisit window; a late answer that contradicts spawns a revision task rather than rewriting history.
   - **PARK**: the answer genuinely gates the task — shelve THAT task, post the question, continue the loop on other queue items. This is the big win: today's hard-escalate kills hours of remaining budget.
   - **HARD-ABORT (unchanged, never soft-forked)**: the existing hard-escalate list byte-for-byte — credit spend beyond grants, push, destructive git, guard/firewall edits, SSH, hardware. "Answer me later" is structurally barred from authorising irreversible or costly effects. (One designer proposed opt-in park classes for credit/push behind a flag; rejected for now — consent invariants outrank convenience, revisit only if Martin asks.)
3. **Transports are disposable projections of the ledger** — each does only its strong thing:
   - **brain2 pair per project** (`<App>-fromClaude` / `-fromMartin` in `/brain2/andeye/`, Time&I conventions verbatim) = the phone/Obsidian write surface, REGENERATED from the ledger each iteration so sync races and hand-edits can't corrupt state. NO aggregation/inbox surface — Martin's correction (2026-07-11): each vibe is a complete per-project workspace (fromClaude read-pane + fromMartin write-pane + a Ghostty action space + optional test space), and merged numbered lists across apps confuse rather than help. Numbering displays plain 1..N per project (Time&I convention); the globally-unique IDs live only in the ledger.
   - **The terminal itself is the monitor layer** — Martin runs up to four vibes as quarter-tiles on a dedicated screen and glances at it. So the statusLine gains a question segment (e.g. ` · Q:2` when the ledger has OPEN/PARKED questions, with the bell on transition) and wait-mode prints a loud one-liner naming the open question IDs — the quarter-tile IS the notification surface when he's at the Mac.
   - **PushNotification** = doorbell only for when he's away from the monitor screen: fires on PARK events, a digest when the loop enters wait-mode, and at exit. Never carries state.
   - **/remote-control** = express lane: replies land mid-turn, but are reconciled INTO the ledger before being applied — never applied directly, so the fast path and slow path can't diverge.
4. **Answer binding is by ID, never position**: an answer names its question ID; the loop applies it only if that question's window is still open, else surfaces it as a revision candidate. Misnumbered/late/contradictory answers therefore degrade to visible follow-ups, never silent misapplication. The resumption protocol's git-log cross-check extends to APPLIED answers.
5. **Cadence & the watchdog interaction**: channels are read at every iteration boundary (free). When ONLY parked work remains: drain, then a wakeup ladder capped at **1500s** — deliberately under the stall watchdog's 1800s default so a legitimately-waiting loop can never be killed as a wedge (each wakeup's tool calls also refresh the heartbeat; the cap is belt-and-braces). After a configurable idle budget (default ~30 min) the loop exits cleanly with the parked questions in `## Final state § Deferred` — a `--sessions` relaunch or `/vsss --resume` picks them up, and an answered question is the first thing resumption applies.
6. **Multi-project**: IDs carry the project slug; channels are per-project; each vibe's own workspace (quarter-tile + fullscreen space) is its complete surface. Two loops can never read each other's questions.

## Additional design objective (Martin, 2026-07-11)

**Minimise the human-only surface.** Every question the loop asks must first pass "could the loop do this itself with more effort/tooling?" — the action space (Martin's Ghostty pane) exists for the residue, and each thing that lands there repeatedly is a feature request against vibe (e.g. things that today need Mac-side hands: `vibe repos add` registration, pushes, MANUAL-TESTS runs, Obsidian-side authorisation stamps). The ask-ledger doubles as the measurement instrument: recurring question shapes = the automation backlog, reviewable from `.vss/qa/` archives.

## Migration path (smallest shippable slice first)

1. Executor gains the third outcome ("park-and-ask") + the ledger dir + ID scheme; hard-escalate list untouched.
2. brain2 projection + fromMartin ingestion (Time&I numbering rules), gated on the brain2 mount existing (non-Martin users: ledger + push only).
3. PushNotification doorbell + wait-mode ladder + Deferred-exit wiring into `--sessions`.
4. Optional later: /remote-control reconciliation note in the vsss spec (mechanism already works today — it's how this design conversation happened).

Time&I/Money&I/Mail&I keep their existing channels for their own app dialogues; when those projects run /vsss with this protocol, their per-project pairs are the same files they already use — no migration for Martin's habits, just added lifecycle discipline underneath.
