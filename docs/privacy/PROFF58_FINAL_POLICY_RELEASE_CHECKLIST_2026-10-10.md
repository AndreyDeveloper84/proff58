# PROFF58 FINAL Privacy Policy Release Checklist

**Purpose:** prevent publishing a legally/technically inconsistent FINAL policy.

## Preconditions

- [ ] Privacy closeout evidence pack is merged and current.
- [ ] Final processing matrix is merged and current.
- [ ] Production runtime privacy gate is PASS on the live proff58.ru-serving stack.
- [ ] 1C physical DR decision/evidence is recorded.
- [ ] RUVDS/ATOL contractual wording is evidence-backed or deliberately role-neutral.
- [ ] Initial Roskomnadzor filing is submitted and receipt/registration evidence is preserved.
- [ ] Operator/legal owner has approved the final policy wording.

## FINAL text checks

- [ ] Operator details and privacy contact are correct.
- [ ] Categories of subjects match actual processing.
- [ ] Categories of data match actual processing.
- [ ] Purposes are purpose-specific; no blanket purpose.
- [ ] Legal bases are matched to purposes and do not rely on a universal blanket consent.
- [ ] Retention periods match the implemented matrix.
- [ ] Account deletion/inactivity wording matches shared anonymization behavior.
- [ ] Backup/restore wording matches 14d proff58 retention, 30d 1C owner rule, and post-restore reconciliation.
- [ ] RUVDS / MAX / ATOL Pay wording does not invent an unsupported contractual role.
- [ ] 1C is described as the Operator's internal local system, not an external processor.
- [ ] Runtime-off integrations are not presented as active current recipients.
- [ ] No OpenAI / USA / voice flow is included without new production evidence.
- [ ] Cross-border statement matches the current active runtime inventory.
- [ ] Cookie/storage table matches the effective frontend/runtime.
- [ ] Security measures are factual and do not claim unsupported certification or universal encryption.
- [ ] Roskomnadzor wording/registry details match the filed notification.

## Storefront replacement

- [ ] Remove `ПРОЕКТ ДОКУМЕНТА` badge.
- [ ] Remove legal-pending note.
- [ ] Remove every `Раздел заполняется юристом` placeholder.
- [ ] Replace placeholder service list with evidence-backed current recipients/inactive status.
- [ ] Keep permanent URL `/info/privacy`.
- [ ] Registration link points to `/info/privacy`.
- [ ] Checkout link points to `/info/privacy`.
- [ ] Cookie banner/settings link points to `/info/privacy`.
- [ ] Add regression test forbidding placeholder/legal-pending markers.

## Live verification after deploy

- [ ] GET `/info/privacy` returns 200.
- [ ] FINAL title/badge state is correct.
- [ ] No draft placeholder strings appear.
- [ ] Links from registration/checkout/cookie UI resolve to the policy.
- [ ] Cookie settings/withdrawal still work.
- [ ] Production privacy runtime smoke remains PASS after the policy release.
- [ ] Store deployed SHA and review evidence in DRF-2860.

## Closeout

Only after every item above is satisfied:

- [ ] mark DRF-2797 Done;
- [ ] mark DRF-2961 Done;
- [ ] mark DRF-2965 Done or explicitly document accepted role-neutral wording with retained evidence;
- [ ] mark DRF-2963 Done or record owner-accepted single-device DR risk;
- [ ] mark DRF-2860 Done;
- [ ] archive the approved FINAL policy revision and closeout evidence version together.
