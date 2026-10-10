# PROFF58 Final Processing Matrix v1

**Date:** 2026-10-10  
**Status:** INTERNAL REVIEW CANDIDATE  
**Scope:** factual current processing for proff58.ru

This matrix is a technical/legal reconciliation artifact. It must not be read as assigning a contractual legal role where the accepted contract has not been evidenced.

| Process | Source / subject | Personal data / identifiers | Local storage | Current external recipient | Purpose | Retention / stop rule | Deletion / minimization |
|---|---|---|---|---|---|---|---|
| Account registration and login | Registered customer | name, phone, e-mail, password hash, account/security metadata | User/Profile, auth/session storage | MAX only when user chooses MAX auth/link | account creation, authentication, security | while account is active; inactivity lifecycle after 3 years + 30d warning | shared irreversible anonymization; password disabled; direct identifiers scrubbed |
| Guest checkout | Buyer/recipient without account | name, phone, e-mail where provided, delivery/order details, guest bearer token | Order + temporary access token | ATOL Pay for payment/fiscal flow; delivery provider only if/when active for selected delivery flow | place/fulfil order, payment, delivery | order ledger per legal/business retention; guest bearer token max 90d | expired guest access token physically cleared; excess contact data removed when no longer needed |
| B2C order | Customer/recipient | order number, items, value, status, payment/delivery data, fulfilment contact snapshot | Order and related payment/fulfilment records | ATOL Pay; 1C internal accounting; MAX for service notifications where linked | order fulfilment, accounting, service communication | ledger retained where legally required; excess PII not tied to ledger retention automatically | terminal-order excess PII scrubbed on account deletion; account link detached |
| B2B account/order | Representative / IP / legal entity | representative contact data; company name; tax/registration details where used; order data | Profile/Order | 1C internal accounting; ATOL Pay if paid online | contract/order/accounting/tax workflow | only while necessary for contract/accounting/legal purposes | excess B2B profile/order PII scrubbed when purpose/legal basis ends |
| ATOL Pay payment / fiscalization | Payer / buyer | transaction/order identifiers; amount; receipt positions; buyer e-mail where used for receipt; provider callback metadata | Payment + bounded callback snapshot | АО «АТОЛ Пэй» payment/fiscal contour | online payment, fiscal receipt, payment status | callback diagnostic snapshot max 30d; financial/fiscal records according to applicable accounting/tax duties | raw/excess callback data minimized; full card data not formed/stored by proff58 backend |
| MAX login/link/tracking/service notifications | User who voluntarily uses MAX | MAX user/chat identifiers, phone/link metadata, service event identifiers, order number/status note | MaxAccount, auth attempts, tracking grants, notification records | ООО «МАХ» platform | authentication/link, order tracking, service notifications | auth metadata 24h terminal retention; account linkage while active/needed | account deletion anonymizes/deactivates MAX account and deletes attempts/grants; old identity cannot revive tombstone |
| 1C order exchange | Buyer / B2B customer represented in order | minimized customer name/phone/type as required; order/items/status/totals | local 1C workstation in Penza + website sync records | none: 1C is Operator's internal local system | accounting/order synchronization | operational/accounting/legal retention; 1C backups 30d owner rule | website export excludes customer e-mail, delivery address and free delivery comment; separate backup/DR process |
| Support / returns / warranty | Person contacting store | contact details, request/claim content, related order/product data | support/operational records | none unless a specific fulfilment/legal service requires it | support, returns, warranty, claims | support max 1y after closure; claims/warranty 3y after closure; longer only for active dispute/legal duty | delete/anonymize after retention/lawful-purpose end |
| Restock notification | Person requesting availability notice | contact/account link + product/subscription state | ProductAvailabilitySubscription | MAX only if notification uses active MAX channel | requested stock-availability notice | notified/cancelled max 30d; never-notified max 6mo | scheduled cleanup; deleted on account deletion where linked |
| Security / access logging | Site visitor/user | IP/request metadata, user-agent, timestamps, security/technical context | nginx/application/security logs | RUVDS infrastructure hosts the logs on the Russian VPS | security, incident response, availability | access-log IP max 30d; broader security/application logs max 90d, incident exception only while required | rotation/deletion; query secrets masked for sensitive callback paths |
| Cookies / browser storage | Website visitor | session identifiers; CSRF token; auth-state flag; cookie-consent choice; local browser preferences; temporary order access reference | browser + server session where applicable | none for required storage; Yandex only if corresponding map/analytics action is activated under required conditions | site operation, cart/session, consent choice | per cookie/storage table; analytics max 13mo if enabled | user may clear browser data; consent withdrawal changes optional analytics behavior |
| Backups proff58 | Data subjects present in DB/media at backup time | backup image of applicable DB/media data | protected local backup directory on production VPS in Russia | RUVDS infrastructure | disaster recovery only | hard max 14×24h, cleanup every 15 min | automatic exact-age deletion; post-restore privacy reconciliation prevents resurrection of later-deleted PII |
| Backups 1C | Persons represented in local 1C | copy of applicable local 1C data | local PC; approved target is separate encrypted removable media | none | disaster recovery | 30 calendar days | rotation/delete older copies; physical DR evidence still open |

## External-service status

### Active current external services

**RUVDS / ООО «МТ ФИНАНС»**

- Function: hosting/infrastructure in Rucloud, Korolyov, Russia.
- Production DB/media/log/backup contour is hosted on the Russian VPS.
- proff58 / ИП Шатров remains the personal-data operator for store-customer processing.
- Do not call RUVDS a processor-by-instruction for store-customer data unless the accepted contract/DPA explicitly establishes that role.

**MAX / ООО «МАХ»**

- Function: platform for voluntary login/link, tracking and service notifications.
- Official developer rules require the Developer to maintain its own lawful basis/privacy documents and describe the Developer as independently processing application-user data.
- FINAL wording should describe the factual independent platform/developer contours, not imply that MAX becomes the store's generic data processor.

**ATOL Pay / АО «АТОЛ Пэй»**

- Function: payment/fiscal service.
- Full card details are not formed or stored by proff58 backend.
- Exact contractual role and provider-side retention terms remain subject to the actual merchant/acquiring agreement.

### Internal system, not external recipient

**1C 7.7**

- Local Operator-controlled accounting system.
- Physical location: Penza, Russia.
- Access: ИП Шатров.
- No confirmed remote/cloud access contour.

### Runtime-off / inactive current integrations

The current runtime inventory does not treat these as active current recipients:

- Sentry;
- Yandex Metrika;
- VK ID;
- Yandex ID;
- CDEK backend integration;
- outbound SMTP staff channel.

Future activation requires the corresponding privacy/legal/consent review before they are described as current recipients.

## Security wording approved by evidence

The FINAL policy may factually state that the Operator applies organizational and technical measures appropriate to the current processing, including:

- restricted administrative access to production systems and local 1C;
- hosting of the production database/media on Russian infrastructure;
- separate application/database service boundaries in containers;
- authentication and authorization controls;
- CSRF and application security controls;
- masking of sensitive OAuth/payment callback query parameters in logs;
- limited log retention and rotation;
- purpose-limited retention janitors for short-lived authentication/payment/access artifacts;
- restrictive backup permissions and automatic backup rotation;
- account anonymization and integration-link cleanup;
- post-restore privacy reconciliation before restored data is returned to external operation;
- minimization of data exported to 1C;
- optional analytics disabled unless configured and consent-gated.

## Claims that are NOT currently supported

Do not state without new evidence:

- formal certification of the information system;
- encryption of all data at rest;
- universal end-to-end encryption controlled by the Operator;
- a processor-by-instruction legal role for RUVDS;
- a specific processor/independent-operator role for ATOL Pay without merchant-contract evidence;
- active use of CDEK, Metrika, VK ID, Yandex ID, Sentry or SMTP where runtime says OFF;
- any OpenAI / USA / voice-processing flow for proff58.ru;
- completed Roskomnadzor registration before receipt/registry evidence exists.

## Remaining legal/owner evidence

1. Physical 1C DR media implementation or explicit owner acceptance of single-device continuity risk.
2. Accepted RUVDS agreement/DPA if a specific processing role is to be stated.
3. Actual ATOL Pay merchant/acquiring agreement/accepted offer for exact role and provider-side retention terms.
4. Initial Roskomnadzor filing and preserved receipt/registry evidence.
5. Owner/legal approval of the FINAL policy text.
