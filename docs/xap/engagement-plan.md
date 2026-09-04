# XAP engagement plan

XAP ("eXplicit Attribution Protocol") is a separate standard Martin is drafting — distinct from vibe. This file is staged to move to XAP's own repository once Martin creates it; until then it lives here as a lifted, otherwise-unedited copy of the TODO.md entry. Written 2026-09-04.

---

**Future move (2026-05-18 Martin)**: this entry should likely move to a separate XAP repo eventually — XAP is a distinct standard from vibe, and tracking its engagement plan here couples two unrelated lifecycles. Pending the move, kept here for visibility. Goal: get XAP from "doc Martin wrote" to "standard one or two real projects ship and a maintainer recognises." Sequence (each step gates the next; no parallelism until step c):

- (i) Apply XAP 0.0.1 to `vibe` itself. The meta-test: does the discipline fit a real codebase Martin controls? Author SPEC.md, claim-to-test mapping, XAP.md (Conformant tier initially; add Attested via GitHub Actions in-toto attestation later).
- (ii) Apply XAP 0.0.1 to `electroPioreactor` (AMYBO). High-stakes choice: this is the project where the testing-failure incident in the XAP preface happened. Closing that loop publicly under XAP discipline is a strong demonstration. Hardware claims go in MANUAL-TESTS.md per the standard's hardware-testing rule.
- (iii) Stabilise XAP 0.1 from 0.0.1 based on what the two applications surface. Publish at a stable URL (likely github.com/martincurrie/XAP or own domain). RATE.md frozen at 0.1's referenced revision.
- (iv) File a thoughtful proposal at OpenSSF AI-SLOP working group ([ossf/wg-vulnerability-disclosures Issue #178](https://github.com/ossf/wg-vulnerability-disclosures/issues/178)). Right institutional home; chartered on this exact problem. Likelihood of pickup: low-to-moderate; value if engaged: high (institutional legitimacy).
- (v) Open an issue on `obra/superpowers` proposing XAP as a downstream conformance target Superpowers projects can opt into. Jesse Vincent is the natural ally; XAP positions as complementary, not competing. Likelihood: moderate; value: very high (Superpowers users become XAP early adopters overnight).
- (vi) Post to Hacker News and lobste.rs with the two example projects as evidence. Ambient channel for Stenberg / Hashimoto / Ruiz / Pydantic team to notice. Direct cold-email to those maintainers is unlikely to land; ambient discovery is the realistic path.
- (vii) Submit talks to FOSDEM, XP conf, DevConf for 2027. 6-12 month timeline. Useful for credibility, not urgency.
- (viii) Reach out directly to Jeff Geerling once at least one XAP-conformant Geerling-relevant project exists (one of his Ansible roles or homelab projects could itself adopt XAP first). His video grounded the preface; he'd be the highest-value vocal endorser. Cold approach without prior evidence: unlikely.

Honest realistic ceiling: niche-but-used standard among solo developers and small teams; maintainers eventually recognise it as a useful triage signal even without endorsing it. Industry standard not realistic at year one. Realistic risk: maintainers most hurt by slop have decided contributor-side discipline is unfixable; XAP may land flat with them and find its real audience among contributors trying to be the exception. That is still a success, just a different one than the framing implies.
