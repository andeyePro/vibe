# Task&I agent-exchange wire fixtures (contract v2.3 family, copied as v2.5)

- Source: `/brain2/andeye/Task&I-agent-exchange-fixtures/` (the thirteen `*.json` files below, for the calls task_066 covers). They are byte-for-byte copies of taskandeye's `web/tests/fixtures/agent-exchange/*.json`.
- History: v2.3 came from branch `claude/exchange-2-20261031`: service commit b8121150, fixtures 8dd5c84e, and the `record_usage` follow-up 72578feb. brain2 then recopied every file as v2.4 (`claude/exchange-4-20261031` at c813788e) and as v2.5 (`claude/repeats-20261031` at 6c085722). These copies say `vibe-agent-exchange-v2.5`. For the calls covered here, v2.4 and v2.5 add nothing to v2.3, so the client treats all three alike (task_066 spec, "Rev 3 addendum").
- Wire rules: that folder's `README.md`, sections "v2.3 changes", "Decided", "v2.4 changes" and "v2.5 changes".
- Copied: 2026-10-31, byte for byte (task_066). The `create_task*` and `update_task*` files are task_067's. Do not edit these files. If Task&I changes them, recopy from the source and update this note.
- All values are invented.

## SHA-256 of the thirteen fixture files

The committed copies are pinned by these hashes (`sha256sum *.json` format: hash, two spaces, file name). If a file is recopied, update its line here in the same commit.

```
d324e582b0ce487004f4a26b96a0cccaca251a702697ff229be5816d08281ffe  ask.json
aa7691ffaec50f835f239254b93d39c607e0dfc481ea445be26ef823c14aad6d  ask_status.json
cd10d0365bc2055079a1db78c65eadd25c029a2f54e8292e60da25ca21b11dc7  capabilities.json
a661f8976349202db6c19d1c06c76517e03870d9bb1aa9aecf96b40979f60bac  comment.json
955d1de749d132bdc163285aadce09f03030efddfa179f6d4e90c7ef477a091f  complete.json
8b1dc633b3bfeb5e0d803901af5db815cadaf624033bff01386ab476864492bd  list_asks.json
fba0c5de141f3f94529364dc0fefec07534ddc2664f769a2edec3465f6a29ddc  next_task.json
1b0c14b2b6f4b79d4ba44dfedf680a7a4a73224eaef1d2abdc98ee5ea2c26e4a  next_task_claim.json
8127d993d3be5398e45211f32e5cdd5dd8a386b032e0a5c5c9b2da11ee15e9a9  over_budget.json
ac9570e36d440504716a55758004a184d05d7073897c1ee7cac5b27396cbbc5e  record_time.json
682ec10ecd820194b8c7e9bf7c27793a44adc2ff63bb6191dd5c5c721e991c91  record_usage.json
0d4b2ae56a41a6cb82efc5366c789233eee5a264632f1e94a94d150f30e88fc5  release.json
92524235e87d0fb304902b3cb00369df2611048ed6364e8a3353a75a26ab0027  retry.json
```
