# Recording the vibe demo cast

This is the exact procedure for turning a real vibe session into the cast
that plays in the terminal pane on vibe.andeye.com. Follow it in order —
the redaction and marker-insertion in `scrub.mjs` depend on the typed text
below matching what you actually type, verbatim.

## 1. Record

```
brew install asciinema
```

From a throwaway project directory (NOT one with real secrets, real IPs, or
a real GitHub org you care about staying off the page — `scrub.mjs` redacts
known patterns, but recording clean input beats relying on redaction):

```
asciinema rec --output-format asciicast-v2 --idle-time-limit 2 --cols 96 --rows 28 site/demo/raw.cast
```

`--cols 96 --rows 28` must match the player's mount (`CastPlayer.astro` and
the deck's `term_title` copy both say `96×28` — if you ever change one,
change all three). `--idle-time-limit 2` caps dead air between lines so the
cast doesn't sit on a silent terminal.

Type each of the 13 sections below **in order**, exactly as shown, letting
each command's real output land before moving to the next. Press `Ctrl-D`
or run `exit` when done to stop the recording.

## 2. Scrub

```
node site/demo/scrub.mjs site/demo/raw.cast
```

This redacts secrets/emails/home paths/private IPs/real repo slugs, inserts
`"m"` markers by finding each section's typed text below in the recorded
output, and writes `site/public/demo/vibe.cast` + `site/public/demo/markers.json`
(defaults; override with `--out` / `--markers` / `--record`).

## 3. Commit

Commit `site/public/demo/vibe.cast` and `site/public/demo/markers.json`
(not `raw.cast` — that's your unredacted scratch file, keep it local or
delete it). `site/public/vendor/` (the player bundle) is gitignored and
rebuilt by `scripts/vendor-player.mjs` on every `npm run build` — don't
commit that.

## CSP note (out of scope, for later)

The vendored player bundle inlines its VT engine's WASM as a base64
`data:` URL rather than fetching a separate `.wasm` file. If a `_headers`
CSP is ever added for Cloudflare Pages, its `script-src` will need
`wasm-unsafe-eval` (or the WASM instantiation will be blocked) — plain
`unsafe-inline`/`unsafe-eval` is not enough and not what you want anyway.

---

## Sections — type these in order

Each section names the chip it drives (`id` — must match `data-step` in
`index.astro` / the deck order in `home.md`), the literal text to type,
and what to watch for before moving on. "Wait for" quotes the tail of the
chip's own scripted transcript in `home.md` — the point is realism, not a
word-for-word match (the real launcher's own output will differ in detail;
`site-check.mjs`'s `inBoth()` guards only pin specific launcher/firewall
strings, not full lines).

### 1. `launch` — Launch

Type:
```
cd yourproject && vibe
```
Wait for: the container to finish starting, the firewall verification
line, and Claude Code's ready prompt (mirrors "ready – what shall we
build?").

### 2. `first-launch` — First launch

Type (a repo `vibe` has never seen before, so the PAT prompt actually
fires):
```
cd yourproject && vibe
```
Wait for: the "No GitHub token found" prompt, the token-saved
confirmation, and the container image build completing.

### 3. `pat` — Rotate the PAT

Type:
```
vibe pat
```
Wait for: "stored token found — it will be replaced" through to the
final "Token saved" confirmation.

### 4. `vs` — Build, adversarially

Type:
```
/vs "add CSV export to the monthly report"
```
Wait for: the spec draft, the critic's revise pass, the builder's diff,
the tester's first (failing) run, the fix, the second (passing) run, and
the reviewer's pass verdict.

### 5. `vss` — One task, solo

Type:
```
/vss
```
Wait for: the TODO.md pick, the redirect-window notice, the change
landing, the passing test run, and the "committed — not pushed" line.

### 6. `vsss` — Overnight loop

Type:
```
/vsss --sessions 2
```
Wait for: at least two committed iterations, a parked question, the
auto-resume relaunch line, and the perfection-gate stop.

### 7. `curl` — Try to phone out

Type:
```
curl https://sketchy.example
```
Wait for: the connection failure, then narrate (or let vibe's own output
show) the allowlist and fail-closed behaviour.

### 8. `leak` — Try to leak a secret

Type (with a **fake** key already staged in a throwaway `config.js` —
never a real one):
```
git commit -m "wip"   # config.js still holds a pasted API key
```
Wait for: the BLOCK finding on the staged secret, and the note that WARN
fires the same way on private IPs/home paths/emails.

### 9. `push` — Ship it

Type:
```
git push
```
Wait for: the outgoing-range re-scan line and the push completing.

### 10. `budget` — /budget

Type:
```
/budget
```
Wait for: the month-to-date token line and the Fable-credit estimate
caveat.

### 11. `learn` — /learn

Type:
```
/learn "lead with the literal command"
```
Wait for: the write-confirm prompt and the saved confirmation.

### 12. `copy` — /c

Type:
```
/c
```
Wait for: the scratch-file write and the clipboard-watcher confirmation.

### 13. `diet` — /diet · /feast

Type:
```
/diet
```
Wait for: lean-mode-on confirmation and the `/feast` mention.
