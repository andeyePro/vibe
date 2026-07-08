## What this changes

One or two lines on what and why.

## Checklist

- [ ] `python3 code-check.py` green (shellcheck over `vibe` + every `.sh`).
- [ ] `python3 smoke-test.py` green (host-side black-box tests).
- [ ] New behaviour ships with a smoke test (or a MANUAL-TESTS.md entry if it needs docker) and its doc update, in this PR.
- [ ] `CHANGELOG.md` entry added in the same commit as the code (repo convention — done work goes in CHANGELOG.md, not TODO.md).
- [ ] If this touches the Dockerfile, `devcontainer.json`, `postStartCommand`, or the `vibe` launcher's container lifecycle: walked the relevant `MANUAL-TESTS.md` section.
- [ ] Read `CONTRIBUTING.md`.
