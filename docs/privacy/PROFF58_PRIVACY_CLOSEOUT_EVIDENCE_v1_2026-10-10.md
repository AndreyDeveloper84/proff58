# PROFF58 Privacy Closeout Evidence v1

**Date:** 2026-10-10  
**Scope:** proff58.ru current live production-serving stack  
**Owner:** ИП Шатров Алексей Григорьевич  
**Status:** INTERNAL EVIDENCE — source for FINAL policy review, not public policy text

## 1. Production mapping

Live/VPS evidence in DRF-2862 confirms:

- public `proff58.ru` and `www.proff58.ru` proxy to `127.0.0.1:8082`;
- that endpoint is served by compose project `proff58_staging` checked out on branch `dev`;
- therefore the environment name `staging` is historical naming only; this stack serves current public production traffic;
- production hosting: RUVDS / Rucloud, Korolyov, Russia;
- PostgreSQL and media are local Docker volumes on the same Russian VPS.

## 2. Runtime privacy gate

Deploy #679, SHA `3e3e785a0a540ce7da17395c3fd2282316de9276`, completed successfully on the production-serving stack.

Aggregate PII-free runtime smoke:

- guest access token TTL: 90 days;
- payment webhook snapshot retention: 30 days;
- MAX auth metadata retention: 24 hours;
- expired guest tokens: 0;
- expired payment webhook payloads: 0;
- stale MAX pending attempts: 0;
- old MAX terminal attempts: 0;
- active deleted-account tombstones: 0;
- privacy restore manifest export command: available;
- privacy restore reconciliation command: available;
- sampled 1C order export: minimized;
- result: `privacy_runtime_smoke=PASS`.

The smoke prints counts and boolean contract results only; it does not print customer PII, order contents, tokens or webhook payload contents.

## 3. proff58 backups

Current production-serving backup controls:

- backup retention target: maximum 14 days;
- backup directories hardened to owner-only access;
- backup creation uses restrictive permissions;
- cleanup-only cron runs every 15 minutes with `umask 077`;
- exact-age cleanup uses a 14×24-hour cutoff;
- Deploy #679 post-cleanup scan: `expired_backups=0`.

## 4. Account lifecycle and deletion

Implemented and tested:

- active account data retained while required for service;
- after 3 years of inactivity, warning is issued;
- after 30 additional days without activity, account is anonymized;
- user-requested deletion and inactivity deletion use the same shared anonymization service;
- password login becomes impossible;
- original email/phone/name are removed from the account tombstone;
- wishlist is deleted;
- MAX/OAuth bindings are removed or anonymized;
- repeat deletion is idempotent;
- re-registration using the same contact data creates a new technical identity instead of reviving the deleted row;
- terminal-order excess contact/free-text PII is scrubbed while the required order ledger is retained.

Deletion audit is intentionally non-identifying and does not contain user PII.

## 5. Restore privacy reconciliation

DRF-2964 is PASS:

- pre-restore manifest is exported outside the restored DB and must be mode 0600;
- destructive restore is not considered complete until privacy reconciliation succeeds;
- reconciliation re-applies anonymization to identities that had been anonymized after the restored backup was created;
- retention janitors are re-run before external services resume;
- test covers: account contains PII in old backup -> account later anonymized -> old state simulated -> reconciliation -> PII anonymized again;
- `user_deleted` receivers used in reconciliation perform local DB cleanup only; no external HTTP/API notification delivery is invoked.

## 6. 1C

Confirmed current facts:

- 1C 7.7 runs on a local computer in Penza, Russia;
- access is limited to ИП Шатров;
- no RDP / AnyDesk / cloud remote-access contour is confirmed;
- 1C is an internal accounting system of the Operator, not an external processor;
- order export to 1C is active;
- current export shape is minimized and excludes customer e-mail, delivery address and free delivery comment;
- Deploy #679 runtime smoke confirms the minimized shape.

1C backup owner decision:

- local backup retention: 30 calendar days;
- separate encrypted removable DR media is the approved target topology;
- media should remain physically disconnected between backup cycles;
- no cloud/mail/messenger backup is allowed without separate privacy review.

**Open evidence:** physical implementation of the separate encrypted media and one verified 30-day rotation/copy cycle.

## 7. Active external services

### RUVDS / ООО «МТ ФИНАНС»

Confirmed:

- active hosting/infrastructure provider;
- production location: Rucloud, Korolyov, Russia;
- public offer and privacy materials identify ООО «МТ ФИНАНС» / RUVDS;
- proff58 remains the personal-data operator for store-customer data.

Do not state a processor-by-instruction role for customer data inside a generic VPS unless the actually accepted hosting agreement/DPA establishes it.

### MAX / ООО «МАХ»

Confirmed:

- active for login/link/service notifications/order tracking;
- official developer rules require the Developer to maintain its own privacy/legal basis;
- official rules describe the Developer as acting independently from ООО «MAX» for processing app-user data;
- deleted account bindings are cleaned locally and cannot revive a deleted identity.

Policy wording may describe the independent developer/operator contour factually; retain the accepted license agreement internally when available.

### ATOL Pay / АО «АТОЛ Пэй»

Confirmed:

- active payment/fiscal contour;
- provider operates a separate payment surface;
- proff58 backend does not form or store full bank-card details;
- local callback diagnostic payload is minimized and retention-limited to 30 days.

**Open evidence:** actual merchant/acquiring agreement or accepted offer used by ИП Шатров for exact contractual role/retention terms.

## 8. Runtime-off integrations

Current runtime evidence shows these are not active current recipients:

- Sentry — OFF;
- Yandex Metrika — not configured;
- VK ID — OFF;
- Yandex ID — OFF;
- CDEK backend — stub / inactive;
- SMTP outbound staff channel — not configured.

They must not be described in FINAL policy as active current recipients. Future activation requires the corresponding privacy review/consent conditions.

## 9. Roskomnadzor

Operator has not filed before. Required filing type: **initial notification**, not update.

Prepared factual pack includes:

- operator identity/requisites/contact;
- categories of subjects;
- categories of personal data;
- purposes;
- systems/localization;
- current active external services;
- retention anchors;
- security/organizational measures;
- no confirmed current cross-border PII transfer in the active runtime inventory.

**Open evidence/actions:**

- verify the current official Roskomnadzor submission form/mechanism immediately before filing;
- owner review;
- submit the initial notification;
- retain receipt/registration evidence and reconcile the registry entry with the FINAL policy.

## 10. Public policy publication

Current `/info/privacy` implementation is still a legal placeholder:

- badge `ПРОЕКТ ДОКУМЕНТА`;
- legal-pending note;
- sections containing `Раздел заполняется юристом`;
- placeholder service list broader than current runtime truth.

FINAL publication must:

1. replace the placeholder with the approved canonical policy text;
2. remove all draft/legal-pending markers;
3. list current recipients and runtime-off integrations accurately;
4. preserve only cookie/storage statements that match effective runtime;
5. keep registration/checkout/cookie links pointing to the permanent policy URL;
6. include regression coverage preventing placeholder text from reappearing.

## 11. Remaining FINAL gates

At this revision, remaining closeout gates are:

1. **1C physical DR evidence** — encrypted removable media + verified 30-day rotation/copy cycle, or an explicit owner acceptance of the single-device continuity risk.
2. **Contract evidence** — accepted RUVDS hosting agreement/DPA if a specific processor role is claimed, and actual ATOL Pay merchant/acquiring agreement; MAX role is already materially grounded in official developer rules.
3. **Initial Roskomnadzor filing** — current official form verification, owner review, submission and retained receipt/registry evidence.
4. **Final Legal + Technical reconciliation** — compare FINAL wording against this evidence pack and current runtime.
5. **Canonical publication** — replace `/info/privacy` placeholder, remove PROJECT markers and verify all links on the live site.

No other historical privacy implementation gaps should be silently reintroduced into the FINAL text.
