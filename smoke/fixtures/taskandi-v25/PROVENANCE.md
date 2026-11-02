# Task&I agent-exchange wire fixtures for create_task / update_task / repeat (contract v2.5)

- Source: `/brain2/andeye/Task&I-agent-exchange-fixtures/` (the seven `*.json` files below). They are byte-for-byte copies of taskandeye's `web/tests/fixtures/agent-exchange/*.json`.
- History: `create_task`, `create_task_agent`, `create_task_refusals` and `update_task` came with v2.4 (branch `claude/exchange-4-20261031` at c813788e, not pushed). `create_task_repeat` and `update_task_clear_repeat` came with v2.5 (`claude/repeats-20261031` at 6c085722, not pushed), which also replaced `create_task_refusals`' `repeat` case with `invalid_repeat`. Every copy says `vibe-agent-exchange-v2.5`. `capabilities.json` is the same file as in `../taskandi-v23/` (same hash), copied here so these fixtures stand alone: it lists `create_task`, `update_task` and the `title`, `next_action` and `notes` limits.
- Wire rules: that folder's `README.md`, sections "v2.4 changes" and "v2.5 changes"; the repeat object is spelled out in `/brain2/andeye/vibe-taskandeye-client-brief.md` ("Contract v2.5").
- Copied: 2026-10-31, byte for byte (task_067). Do not edit these files. If Task&I changes them, recopy from the source and update this note.
- All values are invented.

## SHA-256 of the seven fixture files

The committed copies are pinned by these hashes (`sha256sum *.json` format: hash, two spaces, file name). If a file is recopied, update its line here in the same commit.

```
cd10d0365bc2055079a1db78c65eadd25c029a2f54e8292e60da25ca21b11dc7  capabilities.json
8e16a74b4339de3670413963edf47584f5516ecdb38d7c5de20904ea7d482e61  create_task.json
9ed91dbd422dba94214d7bde3604186fbfb6d7ff32b9e76d6174f0ab3efae170  create_task_agent.json
bec2ab0ad37c6dc03a99cc551c63168c408188c53664ff0a29840ce7e03cae7c  create_task_refusals.json
c6d992653fc3d95c976898c41c07b631c57f8262dc3ad7d2eca8d1ba03608821  create_task_repeat.json
addb325cfed9985a4ca32a6980fb16dc3916c9e35bac7271f65f2e4c73256bb3  update_task.json
b8b45bbde2856e59e978dc561e1b089af8f465b493d7cbf48fbfcced618b06fa  update_task_clear_repeat.json
```
