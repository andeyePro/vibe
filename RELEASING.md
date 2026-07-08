# Releasing vibe

Maintainer process for cutting a vibe release. Releases are source-only for now — users install via `install.sh` (curl bootstrap) or a git clone. Binary/installer packaging is parked pending the non-coder-install decision (`.vs/audits/foss-release-and-noncoder-install-2026-07-08.md`).

Version lives in one place: the `VERSION` file at the repo root (bare semver, e.g. `0.1.0`). `vibe --version` reads it. Nothing else hardcodes the number.

## Cut a release

1. Bump `VERSION` to the new semver.
2. Add a `## <version> — <date>` heading to `CHANGELOG.md` (newest at top) summarising what shipped since the last release. Same commit as the VERSION bump.
3. Run the gates:

```bash
python3 code-check.py && python3 smoke-test.py
```

4. Commit both files together:

```bash
git add VERSION CHANGELOG.md
git commit -m "release: vibe v0.1.0"
```

5. Tag and push (maintainer machine — the container never pushes):

```bash
git tag v0.1.0
git push origin main --tags
```

6. Create the GitHub release from the tag:

```bash
gh release create v0.1.0 --title "vibe v0.1.0" --generate-notes
```

Use `--notes-file <path>` instead of `--generate-notes` if you want the CHANGELOG section verbatim rather than auto-generated commit notes.

## Semver rule of thumb

- Patch: fixes, doc updates, no behaviour change to the launch contract.
- Minor: new flags, new opt-in features, backward-compatible container changes.
- Major: anything that breaks `cd project && vibe`, the auth model, or an existing flag.

Pre-1.0 (`0.x`) the minor slot absorbs breaking changes; keep the `## Invariants` in `CLAUDE.md` intact regardless.
