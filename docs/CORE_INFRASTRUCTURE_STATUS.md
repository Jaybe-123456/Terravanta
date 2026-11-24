# Terravanta core infrastructure status

**Status date:** 24 November 2026
**Evidence basis:** local repository source review. This is not a live audit of Render, Supabase, Vercel, Meta or NVIDIA settings.

## Current system boundary

- Supabase Auth handles user identity and sessions.
- FastAPI is the public business API. Render PostgreSQL/PostGIS is the operational source of truth; Alembic owns schema changes and tenant RLS is the second authorization boundary.
- A restricted API runtime, a restricted workflow worker and separate WhatsApp webhook/sending roles are documented in the release guide. Their live grants and service URLs still need verification against the production database and Render services.
- The durable workflow worker handles scheduled veterinary follow-up reminders and in-app notifications. It is deterministic and does not call an AI model.
- Terras navigation is deterministic routing to existing product workflows; it is not an autonomous agent and cannot write data through an LLM.
- Cooperative receivables now include local, version-pinned contract registration and processor review. Migration `0014_bilateral_supply_contracts` adds an append-only counterparty decision bound to the exact source-PDF/terms fingerprint; contract-based due dates are checked against the captured payment term. This code is not live until the migration is deployed.
- The claim desk now has source-agnostic CSV mapping using existing tenant-scoped profile, evidence, case-line and event tables: schema preview, explicit mapping approval, row-level source locators and all-or-nothing import into an empty draft claim. Migration `0015_immutable_source_mapping_profiles` restricts approved-profile updates; it depends on migration `0014`. No vendor connector, automatic cross-system match or real export validation is in place.
- The processor now has bilateral line review: append-only matched/value-difference/missing findings snapshot seller and processor amounts plus direction; matching requires both amount and direction to agree. Processor-owned source files remain private until explicitly attached to one submitted claim, after which both parties can read them under case-scoped authorization. Migration `0016_counterparty_line_reconciliation` adds tenant-RLS tables, narrow grants, shared-artifact read rules and database checks. This is manual comparison, not a vendor connector or automated match. GitHub Actions is configured to migrate through `0018_offline_write_idempotency` and run RLS/restore checks on disposable PostGIS; that workflow has not yet run for these changes. No Render database has been migrated or used as staging.
- WhatsApp delivery and signed webhook code exist, but the channel depends on Meta business eligibility, a stable domain, user pairing/consent, credentials and an end-to-end message receipt. Keep the existing WhatsApp values unchanged and sending disabled during domain/bootstrap work.
- Browser offline support is a limited, encrypted local queued-write path with server-side idempotency, not a complete offline-first service: private dashboard data is not cached, first-time sign-in requires connectivity, and there is no multi-device conflict resolution.

## AI operations

| Workflow | Provider need | Current safe behavior |
| --- | --- | --- |
| Terras navigation and farm-record indicators | None | Deterministic, server-derived rules and calculations |
| Farm record question | NVIDIA chat API key and configured model | No model call until the user opts in; missing provider returns an unconfigured state; result is a review draft |
| Veterinary case question | NVIDIA chat API key and configured model | Explicit case-data consent; safe response filtering; no diagnosis, prescription or dose instructions |
| Selectable-text PDF | None | Text extraction runs locally; values remain an unreviewed draft |
| Photo/image parsing | A deployed Nemotron Parse endpoint; separate endpoint token only if required | No image call without per-upload consent and endpoint configuration |
| Parsed document field mapping | Parse endpoint plus NVIDIA chat key | Unverified extracted fields remain a draft for human review |
| Follow-up reminders, WhatsApp notifications, payout close and receivables matching | None | Deterministic workflow; no model makes clinical, settlement or payment decisions |

The API now exposes authenticated `GET /api/v1/ai/provider-status`. It reports only whether required settings are present and the configured model identifiers; it does not return secrets or endpoint URLs and does not perform a connectivity test. Use the AI provider-status panel to distinguish configured from not configured. The deployment checklist is in [`RENDER_DEPLOYMENT.md`](RENDER_DEPLOYMENT.md#optional-nvidia-ai-providers).

A one-time minimal request confirmed that the supplied NVIDIA key can authenticate and that `nvidia/nemotron-3.5-bolt-e4b` returns a response; the `stg/` alias returned 404 for that account. The key was used only for this check and was not saved in source control or Render. Rotate it because it was exposed in chat, then add the replacement only to the Render API service, never Vercel. Production AI remains unconfigured until that rotated key is set; verify connectivity with synthetic data before enabling real farm information.

## Remaining production work, in order

1. **Resolve and verify onboarding/auth in production.** Earlier browser reports showed `/api/v1/auth/onboard` returning 401 and a Vercel preview-origin CORS failure. Reproduce against the stable production origin, inspect the API response body and Render logs, and confirm Supabase subject, email-confirmation status, allowed redirect and exact CORS origin. Do not broaden CORS to every preview.
2. **Verify production database identity and RLS.** Confirm the current API, worker and webhook logins, group memberships, `NOBYPASSRLS`, grants and migration head through `0018_offline_write_idempotency`. CI exercises migration and tenant boundaries on disposable PostGIS; production remains untouched. Run the same checks against an isolated staging copy before live records or production migration.
3. **Evidence controls implemented; production setup remains.** Uploads fail closed unless the private scanner is reachable; retention metadata defaults to legal hold and timed purge is rejected. The CI workflow includes disposable database and local-object restore checks, but still needs a successful run. Configure the scanner and a separately backed-up private evidence store, then run a production restore drill before horizontal scaling.
4. **Offline capture implemented with explicit limits.** The public shell caches after an online visit; supported creates use encrypted account-scoped storage and atomic server idempotency receipts. Private records are not cached, first-time sign-in is online, and browser storage may be evicted; keep source records until confirmed sync.
5. **Verify external integrations from real receipts.** Keep WhatsApp configuration unchanged until the stable domain and Meta account review are ready. Before enabling it, test signature verification, phone pairing/consent, outbound template delivery, retries/deduplication and the signed delivery receipt. No processor/MIS connector is configured; continue using explicit imports.
6. **Run operational security review.** Rotate any credentials previously pasted into chat or browser-visible fields; move them to the appropriate provider secret stores; review session rotation, token revocation, rate limits, logging redaction, domain security and incident/deletion procedures.
7. **Measure product proof.** Before a paid rollout, run one authorized, anonymized retrospective cooperative close or processor claim, baseline preparation time and exception rework, record per-line counterparty findings and a processor response, and capture the budget owner's decision on a paid repeat. Code is not evidence that a processor or cooperative has used it.

## Not required for the current build

Kubernetes and Supabase Edge Functions are not needed to deliver the current domain API, RLS, follow-up worker, or optional AI calls. Keep one canonical PostgreSQL data plane and the current narrow workers until production load, partner callback contracts or operating evidence justifies a new service boundary.
