# Task&I agent-exchange wire fixtures (contract v2.2)

- Source: `/brain2/andeye/Task&I-agent-exchange-fixtures/` (the ten `*.json` files), themselves byte-for-byte copies of `web/tests/fixtures/agent-exchange/*.json` in taskandeye.
- taskandeye branch `claude/exchange-20261030`, commit 62e50fa5.
- Copied: 2026-10-31, byte for byte (task_064). Do not edit these files; if Task&I changes them, recopy from the source and update this note.
- All values are invented. The wire rules these fixtures do not show are in that folder's `README.md`, section "Wire details (answers for the vibe client, 2026-10-31)".

## SHA-256 of the ten fixture files

The committed copies are pinned by these hashes (`sha256sum *.json` format: hash, two spaces, file name). checks_52 AC15 verifies every listed file exists and matches; if a file is recopied, update its line here in the same commit.

```
243c651122f1495e30e7b7d03c8c4ea2a74537855774bc699d02d6e8ed025eca  ask.json
bf536e1145a9c8a2a41507c1ad202eeff5b830e52001dc225141457c30f3b0f2  ask_status.json
1ec6f6984a84b9e8ee9856cbd4a13d1fffd81fc9615194b754a48493f15971fe  capabilities.json
5c0ad9f68b069ca00dbe8cdf7d90b833c89bfcb3c84e2dfd27054f7be7dd1da3  comment.json
4d052db986b72144882ec2bc405b0cfea046583421d85d78c82f67925d47126b  complete.json
a900b472ce581ca46b39879d00dc4dcee3da8ac9a6a03430e2440a2698394227  list_asks.json
69a220bc84c71b64ec2fb83cda0f455a1ca26226709ed5b6980f79a35c968c28  next_task.json
7099ee12a6453866b37c3d3fe85f50afacce030b3e641b3314a15c7850ccc928  record_time.json
4d32b31a30072eae4a04c72cf71638c058983a98688132fd5c84d6a10afbe11b  record_usage.json
7795914a2401e648e9eb8813834458a143128d64992cd371bc62a7c19a1a339d  release.json
```
