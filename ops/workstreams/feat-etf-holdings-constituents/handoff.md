# feat/etf-holdings-constituents

Created from `staging` at `89bb5c05ad1635156285d392b7c39b3c341ad8f1`.

## Human authorization

- Initial continuation recorded: 2026-08-30T18:48:23.255917+00:00
- Approved plan persistence recorded: 2026-09-02
- Request: continue the existing ETF holdings provider coverage goal from the
  current green staging lineage, and persist the fully approved exhaustive plan
  so another Codex model can implement it in full.
- Closure authorization: pending; do not integrate or deploy until the human
  explicitly authorizes closure.

## Current branch state

- Latest staging merge: `9bc42091ac3d95bcc11ad8783692fb3cd8f9d2e4`
- Incorporated staging SHA: `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`
- Current code-derived state: 496 registered, 371 native/live-backed, 125
  fallback-only.
- Current fallback status split: 8 access-blocked, 108 discovery, 3
  non-executable public source, 6 non-portfolio-publisher (the ledger's dated
  terminal dispositions preserve each record's original runtime audit status).
- `docs/etf-provider-universe.md` has been reconciled from code to the current
  496/371/125 snapshot; future updates must remain code-derived.
- Validation tier: `full_integration`.
- Local validation profile: `docker_integration`.
- Planning session: `197b239d-3322-4fc6-bf4b-0d0aecebf5e0`.
- Latest implementation checkpoint: `2963751a` (EA Series Trust dated
  non-portfolio-publisher disposition; prior DVx Ventures dated
  non-portfolio-publisher disposition; prior Discipline Funds dated
  non-executable-route disposition); prior `9cc5be81` (CresAlta native CVGD/CVSM
  holdings tables); prior `fd07b17f` (Conductor native CGV declared
  holdings CSV); prior `1aa7cc48` (Castellan native CTEF/CTIF
  holdings tables); prior `992a554d` (CapForce native FFTY/BOUT
  holdings tables); prior `b9a984c4` (Bushido native SMRI/RNIN
  holdings tables); prior `b967113b` (BufferLABS native BFLB
  holdings table and live coverage); prior Brookstone checkpoint `6aa2adb3` (Brookstone native BAMD/BAMG/BAMV/
  BAMB/BAMU/BAMA/BAMO/BAMY holdings routes and live coverage); prior Bridgeway
  checkpoint `c1caf555` (Bridgeway native BBLU/BAGX/BRSV/BSVO/BUSM holdings routes
  and live coverage); prior Blueprint checkpoint
  `ba4b80ea` (Blueprint native TFPN holdings route); prior BeeHive checkpoint `bc77c274` (BeeHive native holdings route plus
  promoted-adapter contract alignment);
  prior Ballast/Avory/ARS checkpoints are `b4c96335`/`695dea16`/`f33224ab` and
  the Guggenheim audit receipt remains `c4bef2ec`.
- Product implementation is underway; current changes add Guggenheim, ARS,
  Avory, Ballast, Bancreek, BeeHive, Blueprint, Bridgeway, Brookstone, BufferLABS,
  Bushido, CapForce, Castellan, Conductor, and CresAlta
  native coverage and issuer-specific audit dispositions for the ranked fallback
  records reviewed so far.
- The Discipline Funds audit is explicitly not a promotion: the official DDV,
  DDX, and DDXX pages expose a nonce-backed wpDataTables loader, bounded live
  attempts did not prove a complete executable artifact (DDV had no parseable
  rows; DDX/DDXX exposed only ten rows), and the public AJAX probe returned no
  usable dataset. Commit `c1287c90` removes the experimental adapter and records
  the dated `non_executable_public_source` disposition.

## Durable implementation direction

The human-approved exhaustive plan is
`ops/workstreams/feat-etf-holdings-constituents/implementation-plan.md`.
The schema-4 contract is `plan.yaml`. A later Codex implementation model must
read both completely, follow the automatic agent-session workflow, and work
only in this branch's registered local worktree.

## Historical continuity

The former master-based branch was fully represented in staging before its
remote ref was removed. Its prior checkpoint `a8d6189` recorded 496 registered,
339 native/live-backed, and 157 fallback-only providers. Current code has
advanced to 371/125, including the Guggenheim, ARS, Avory, Ballast, Bancreek,
BeeHive, Blueprint, Bridgeway, Brookstone, BufferLABS, Bushido, CapForce, Castellan, Conductor, and CresAlta promotions. Continue current gaps; do not recreate completed work or
restore a dead route merely to reproduce historical counts.

## Next action

The baseline provider-audit ledger now accounts for all 140 fallback keys and an
exhaustive invariant test proves its key/count/rank alignment with runtime code.
`guggenheim`, `ars`, `avory`, `ballast`, `bancreek`, `beehive`, `blueprint`, `bridgeway`, `brookstone`, `bufferlabs`, `bushido`, `capforce`, `castellan`, `conductor_fund`, and `cresalta` are native-promoted; `advisors_asset_management` and `amplius` are
issuer-access-blocked; `alphamark_advisors` is classified as an
inactive/successor disposition; `amg_national` is a non-portfolio publisher;
and `anydrus`, `baillie_gifford`, and `discipline_funds` are non-executable public sources;
`alphaclone` is an inactive/successor disposition; `argent` and `arin` are
issuer-access-blocked; `azimut`, `desjardins`, `dvx_ventures`, and `ea_series_trust` are dated
non-portfolio-publisher dispositions. The DVx record resolves the source identity
to the separately tracked VistaShares ETF publisher: DVx's own site is a
venture/company-creation platform, not an ETF portfolio publisher. The EA Series
Trust record resolves the trust/platform identity to each fund's actual sponsor
or sub-adviser rather than a duplicate trust-wide route. The audit ledger
currently has 93 queued fallback records still requiring issuer-specific
evidence and final dispositions; existing terminal/blocked records must remain
evidence-backed. Continue replacing baseline placeholders with first-party route
evidence, starting with the ranked queue after the EA Series Trust
non-portfolio-publisher disposition at `elements`, and checkpoint
each coherent provider changeset before moving to the next.

Update this handoff at every coherent implementation and operations boundary.
