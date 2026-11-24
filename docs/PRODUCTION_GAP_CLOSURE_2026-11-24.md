# Production gap closure — 24 November 2026

This records the implementation scope and the remaining provider-side work. CI uses a disposable PostGIS database only; it does not connect to `terravanta-db-dev` or another Render database. WhatsApp variables and behavior are unchanged.

## Tenant isolation and recovery checks

The PostGIS CI job is configured to apply the migration chain through the current head, then verify cooperative/processor/unrelated-organization reads and writes for claims, line reviews, and evidence. It creates a second temporary database, restores a custom-format `pg_dump`, and compares migration head, PostGIS availability, and selected table row counts. A separate isolated storage check restores an evidence object and verifies its SHA-256. This local session confirmed the migration head but could not run PostGIS because Docker access is blocked; the GitHub Actions run is still required. These checks are not a production restore drill.

## Evidence controls

Every receivable evidence upload is scanned before it is written. The API uses ClamAV `clamd` INSTREAM over a private trusted network. A missing, unavailable, or invalid scanner verdict blocks upload; no public malware-scanning service receives evidence. Configure `EVIDENCE_SCANNER_HOST` to a private endpoint reachable only by the API and keep port 3310 off the public internet. The `clamd` TCP protocol does not provide transport authentication or encryption, so it must remain on a trusted private network ([ClamAV protocol](https://docs.clamav.net/manual/Usage/ClamdProtocol.html)).

Render-specific setup and the free-plan limitation are documented in [`EVIDENCE_SCANNER_RENDER_SETUP.md`](EVIDENCE_SCANNER_RENDER_SETUP.md).

Evidence records now carry `legal_hold`, `retention_basis`, `retention_reviewed_at`, and the existing nullable `retention_until`. New rows default to a legal hold and an unreviewed retention basis. Timed purge is disabled and the API refuses `EVIDENCE_RETENTION_PURGE_ENABLED=true`; the read-only `apps/api/scripts/evidence_retention_inventory.py` reports review counts. Set no universal retention period in code. Kenyan data protection law limits storage to what is reasonably necessary and includes evidence-related exceptions; tax records may have a separate statutory period. Agree the applicable schedule, legal holds, and deletion process with counsel and each data controller before enabling any purge ([Data Protection Act, sections 39–40](https://new.kenyalaw.org/akn/ke/act/2019/24/eng%402022-12-31/source.pdf); [Tax Procedures Act, section 23](https://new.kenyalaw.org/akn/ke/act/2015/29/eng%402021-07-01/source)).

## Offline behavior

The web app caches the non-sensitive app shell and static Next.js assets after a successful online visit. Supported create forms use an account-scoped AES-GCM encrypted IndexedDB queue; the app requests persistent browser storage, adds a stable idempotency key, and reports blocked syncs. The API stores the successful response and idempotency receipt in the same transaction for farm, animal, plot, veterinary event, feed, compost, production, and delivery creates. The queue does not cache private dashboard data or provide a first-time offline sign-in; browser storage can still be cleared or evicted. Users must keep source records until the app confirms sync. The offline queue protects raw IndexedDB payloads from casual inspection but does not protect a compromised browser session or XSS.

## Provider setup required in Render

`render.yaml` now declares the optional API-only NVIDIA settings: `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `NVIDIA_CHAT_MODEL`, `NVIDIA_PARSE_MODEL`, `NVIDIA_PARSE_URL`, and optional `NVIDIA_PARSE_API_KEY`. The API already exposes authenticated `GET /api/v1/ai/provider-status`, which reports configuration presence without returning secrets. Rotate any NVIDIA key previously pasted in chat, enter the replacement in the Render API service only, redeploy, and verify the status endpoint. AI stays consent-gated; configuration presence is not a connectivity or quality check. Do not change WhatsApp settings as part of this work.

## Before enabling these paths in production

- Configure a private reachable ClamAV scanner; evidence uploads correctly remain unavailable until it returns a clean verdict.
- Move evidence from the single Render disk to private object storage with versioning/backup and run a restore drill paired with a database backup. The CI restore check is a test, not production recovery evidence.
- Apply and verify the new Alembic migrations on an isolated staging copy before any production migration. Do not run them against the Render database marked Production without an approved backup and deployment window.
- Rotate the exposed NVIDIA key and confirm the new backend-only value through provider status.
- Re-run the CI workflow and inspect its PostGIS RLS and restore jobs before merging/deploying.
