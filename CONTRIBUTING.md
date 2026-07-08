# Contributing to vibe

The pitch is dogfooding: contribute to vibe using vibe. Clone it, point your `vibe` at the clone, and hack on the launcher from inside a vibe session.

## Set up a dev clone

```bash
git clone https://github.com/andeyePro/vibe.git
cd vibe
./install.sh
```

`install.sh` detects the in-place clone and points `~/bin/vibe` straight at your working tree, so edits take effect with no separate pull step. If you'd rather not touch `~/bin`, symlink it yourself: `ln -sf "$PWD/vibe" ~/bin/vibe`.

Then `cd vibe && vibe` opens a container on the repo itself. Work on the launcher, commit, and open a PR against `main`.

## Before you open a PR

Run both gates — they're fast, no docker, no network:

```bash
python3 code-check.py    # shellcheck over vibe + every .sh
python3 smoke-test.py    # host-side black-box tests
```

Both must pass. If your change touches the Dockerfile, `devcontainer.json`, `postStartCommand`, or the launcher's container lifecycle, also walk the relevant section of `MANUAL-TESTS.md` — those paths need a real Docker daemon and can't be covered by the smoke suite.

Tests and docs are part of "done", not a follow-up. New behaviour ships with a smoke test (or a MANUAL-TESTS entry if it needs docker) and its doc update in the same PR.

## Backlog and history

- `TODO.md` — open backlog plus parked/abandoned items (`[ ]` open, `[!]` abandoned with a one-line failure note). Add new work here.
- `CHANGELOG.md` — done-work audit log (`[x]` entries, newest first). Append the entry in the same commit as the code that closed the task.

Don't put done items in `TODO.md`, and don't put open items in `CHANGELOG.md` — the two files have one job each.

## Licence

vibe is MIT, and there is nothing extra to sign. We looked at an AGPL-3.0 + CLA move and set it aside — MIT's freedom to adopt, embed and contribute is worth more to a dev tool than copyleft protection. If that position ever changes it will be announced here first, and existing contributors will be asked before their work is carried over.
