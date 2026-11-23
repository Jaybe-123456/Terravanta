# Terravanta core infrastructure status

**Status date:** 23 November 2026
**Evidence basis:** local repository source review. This is not a live audit of Render, Supabase, Vercel, Meta or NVIDIA settings.

## Current system boundary

- Supabase Auth handles user identity and sessions.
- FastAPI is the public business API. Render PostgreSQL/PostGIS is the operational source of truth; Alembic owns schema changes and tenant RLS is the second authorization boundary.
- A restricted API runtime, a restricted workflow worker and separate WhatsApp webhook/sending roles are documented in the release guide. Their live grants and service URLs still need verification against the production database and Render services.
- The durable workflow worker handles scheduled veterinary follow-up reminders and in-app notifications. It is deterministic and does not call an AI model.
- Terras navigation is deterministic routing to existing product workflows; it is not an autonomous agent and cannot write data through an LLM.
- WhatsApp delivery and signed webhook code exist, but the channel depends on Meta business eligibility, a stable domain, user pairing/consent, credentials and an end-to-end message receipt. Keep the existing WhatsApp values unchanged and sending disabled during domain/bootstrap work.
- Browser offline support is a local queued-write path, not a complete offline-first service: queued data is not an encrypted, conflict-resolving multi-device store.

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
2. **Verify production database identity and RLS.** Confirm the current API, worker and webhook logins, group memberships, `NOBYPASSRLS`, grants and migration head. Exercise unrelated-user and cross-farm access on a staging copy for farmer, veterinarian, cooperative and processor roles before live records.
3. **Complete evidence operations before scale.** Current documented storage is a private Render persistent disk for a single API instance. Add malware scanning, documented retention/deletion, backup and restore drills, then move evidence to private S3-compatible storage before horizontal scaling.
4. **Complete offline guarantees.** Decide which forms may queue, encrypt sensitive queued records at rest, show sync failures and conflicts, and define how edits from multiple devices are reconciled. Do not present the current queue as a full offline database.
5. **Verify external integrations from real receipts.** Keep WhatsApp configuration unchanged until the stable domain and Meta account review are ready. Before enabling it, test signature verification, phone pairing/consent, outbound template delivery, retries/deduplication and the signed delivery receipt. No processor/MIS connector is configured; continue using explicit imports.
6. **Run operational security review.** Rotate any credentials previously pasted into chat or browser-visible fields; move them to the appropriate provider secret stores; review session rotation, token revocation, rate limits, logging redaction, domain security and incident/deletion procedures.
7. **Measure product proof.** Before a paid rollout, run one authorized, anonymized retrospective cooperative close or processor claim, baseline preparation time and exception rework, record the counterparty response, and capture the budget owner's decision on a paid repeat.

## Not required for the current build

Kubernetes and Supabase Edge Functions are not needed to deliver the current domain API, RLS, follow-up worker, or optional AI calls. Keep one canonical PostgreSQL data plane and the current narrow workers until production load, partner callback contracts or operating evidence justifies a new service boundary.
