# PROFF58 Privacy Policy Review Register

**Candidate:** `PROFF58_PRIVACY_POLICY_FINAL_CANDIDATE_v1_2026-10-10.md`  
**Review model:** Legal → Technical → Owner  
**Status vocabulary:** `AI_REVIEWED` means reviewed against current project evidence and cited/current legal requirements; it is not an external lawyer opinion or owner approval.

| Section | Legal review | Technical review | Owner approval | Notes |
|---|---|---|---|---|
| 1. Общие положения | AI_REVIEWED | TECHNICAL_PASS | OWNER_APPROVED | purpose limitation/minimization aligned |
| 2. Оператор | AI_REVIEWED | TECHNICAL_PASS | OWNER_APPROVED | operator/requisites/privacy email from evidence |
| 3. Состав данных | AI_REVIEWED | TECHNICAL_PASS | OWNER_APPROVED | B2B legal-entity requisites separated from representative/IP personal data |
| 4. Цели | AI_REVIEWED | TECHNICAL_PASS | OWNER_APPROVED | current processes only; analytics/marketing conditional |
| 5. Правовые основания и способы | AI_REVIEWED | TECHNICAL_PASS | OWNER_APPROVED | no blanket consent; separate consent rule; actions/automation added |
| 6. Cookie/browser storage | AI_REVIEWED | TECHNICAL_PASS | OWNER_APPROVED | Metrika currently inactive; Yandex map click-to-load |
| 7. Внешние сервисы/1C | AI_REVIEWED | TECHNICAL_PASS | OWNER_APPROVED | RUVDS/ATOL role-neutral where contract evidence missing; MAX factual; 1C internal |
| 8. Retention/deletion | AI_REVIEWED | TECHNICAL_PASS | OWNER_APPROVED | mapped to implemented retention matrix |
| 9. Backup/restore | AI_REVIEWED | TECHNICAL_PASS | OWNER_APPROVED | public text contains current facts only; planned 1C DR media remains internal gate |
| 10. Меры защиты | AI_REVIEWED | TECHNICAL_PASS | PENDING | factual measures only; unsupported certification/encryption excluded |
| 11. Права субъекта | AI_REVIEWED | TECHNICAL_PASS | PENDING | access/correction/block/delete/withdraw/complaint preserved |
| 12. Localization/cross-border | AI_REVIEWED | TECHNICAL_PASS | PENDING | current contour in Russia; current cross-border transfer = none |
| 13. Изменение Политики | AI_REVIEWED | TECHNICAL_PASS | PENDING | permanent URL + separate consent where required |
| 14. Контакты | AI_REVIEWED | TECHNICAL_PASS | PENDING | privacy channel fixed |

## Legal-pass changes applied

1. Explicitly separated consent from other accepted/signed documents.
2. Clarified that legal-entity requisites are not automatically personal data of a natural person.
3. Added processing actions and automated/non-automated processing wording.
4. Removed inactive-integration inventory from the public-recipient list; future activation is governed by a change rule.
5. Removed planned 1C removable-media topology from public current-state wording.
6. Rephrased backup reconciliation and security measures into public, factual language.
7. Changed cross-border wording from audit uncertainty to current-state statement supported by the inventory.

## External gates preserved

- physical 1C DR evidence / owner risk decision;
- accepted RUVDS/ATOL contract evidence if stronger contractual role wording is desired;
- initial Roskomnadzor filing and receipt/registry evidence;
- Owner/legal approval;
- publication via DRF-2797 and live verification.

## Next pass

Technical review must now check every public statement against actual code/runtime/configuration. All sections have passed the current Technical review against repository/runtime evidence. Owner approval may proceed section-by-section. External evidence gates remain separate and must still be closed before publication.


## Technical-pass evidence summary

- Sections 1–5: account/profile/order/payment/MAX models and lifecycle code match the stated data categories and purposes; no blanket-consent behavior is relied on.
- Section 6: cookie/storage wording is based on the current frontend technical table; Yandex Metrika remains runtime-off and the map is click-to-load.
- Section 7: active services match the verified runtime inventory (RUVDS, MAX, ATOL Pay, internal 1C); inactive integrations are no longer enumerated as current recipients in the public candidate.
- Section 8: retention values match implemented janitors and production smoke #679.
- Section 9: proff58 backup hard cutoff and restore reconciliation are implemented and production-evidenced; public wording now contains only current 1C backup facts.
- Section 10: security wording maps to current settings/code/runtime and avoids unsupported certification/encryption claims.
- Sections 11–14: no technical behavior is claimed beyond the implemented privacy contact, current Russian localization/runtime inventory, permanent policy route and update process.

**Technical verdict:** no known code/runtime contradiction blocks Owner review of the candidate.


## Owner approvals

- 2026-10-10: Owner approved sections 1–5 as reviewed, without additional amendments.


- 2026-10-10: Owner approved sections 6–9 as reviewed, without additional amendments.
