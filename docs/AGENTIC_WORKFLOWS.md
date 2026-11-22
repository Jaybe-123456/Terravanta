# Farm events, workflow worker, and notification inbox

## What is implemented

Terravanta now has an append-only `farm_domain_events` log, durable `workflow_runs`, and an in-app `notifications` inbox. The first workflow is veterinary follow-up reminder handling:

1. Creating a health event or recording a veterinarian follow-up appends the domain event and scheduled reminder steps in the same database transaction as the clinical record.
2. A worker polls the workflow queue. PostgreSQL claims due steps with `FOR UPDATE SKIP LOCKED`, so multiple worker instances do not process the same step concurrently.
3. The database function rechecks that the case is still open and its current due date still matches the scheduled date. Rescheduled or closed cases cancel old pending steps.
4. Upcoming, due-today, and overdue steps create recipient-specific in-app notifications for farm members with owner, farmer, or veterinarian membership. A stable idempotency key prevents duplicate inbox items after retries.
5. Each recipient can list their own notifications and mark only their own items as read. PostgreSQL RLS and column-level grants protect the inbox.

Migration `0010` schedules the current open health cases that already have a follow-up date, so existing due dates enter the same reminder workflow after deployment. The migration attributes these backfill events to the system (`actor_user_id` is empty) and marks their payload as migration-generated.

This is deterministic workflow automation. It does not call an AI model, send email or SMS, update a clinical outcome, recommend treatment, or close a case. A veterinarian continues to create and verify clinical follow-up records.

## Farmer-to-veterinarian contact requests

Migration `0011_veterinary_contact_requests` adds a request and response lifecycle. A farmer can submit a farm-scoped request with an optional animal, urgency, short observation, and preferred contact method. The API notifies veterinarians assigned to that farm. A veterinarian claims the request by accepting it, and only that veterinarian can then mark it contacted. Pending requests can be cancelled by their requester. Status transitions are audited, represented in the farm event log, validated at the API, constrained by RLS, and protected by a PostgreSQL transition trigger.

The selected contact method is only a preference and does not place a telephone call. The request always creates an in-app notification; when the WhatsApp safety layer is configured and outbound delivery is explicitly enabled, an additional generic alert is queued only for assigned veterinarians with verified numbers and active consent. If no veterinarian is assigned to the farm, the API rejects the request with a clear action. This is not an emergency dispatch mechanism.

## Farm-level decision support

The Overview page calls `GET /api/v1/farms/{farm_id}/insights` for record-derived measures across feed, crops, livestock cases, follow-ups, production and source-linked deliveries. The calculations are transparent baselines; missing observation days are not treated as zero production. They do not estimate ration sufficiency, clinical treatment effect, food safety, yield causality or ROI.

`POST /api/v1/farms/{farm_id}/ai-assistant` is a separate opt-in request. It uses a context-limited snapshot without personal identifiers, retrieves only approved knowledge sources, logs outcome and latency, and returns an unverified review draft. The request does not write farm records. With no NVIDIA key, no model answer is fabricated and the deterministic indicators remain available.

See [farm decision support and messaging channels](CHANNELS_AND_FARM_INTELLIGENCE.md) for data boundaries and WhatsApp Cloud API prerequisites.

## Local development

The worker runs alongside the API when using Docker Compose:

```powershell
docker compose up --build -d
docker compose logs -f workflow-worker
```

It uses the local database URL. `WORKFLOW_POLL_SECONDS` defaults to 30 seconds and is clamped between 5 and 300 seconds.

## Render deployment

Alembic migration `0010_farm_event_workflows` is applied by the API service startup using `MIGRATIONS_DATABASE_URL`. The new `terravanta-workflow-worker` Render background service uses only the restricted `DATABASE_URL` for `terravanta_runtime`; do not put the owner URL or `MIGRATIONS_DATABASE_URL` on the worker.

The worker service needs:

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `SERVICE_MODE` | `worker` |
| `DATABASE_URL` | Same internal PostgreSQL URL used by the API runtime role |
| `WORKFLOW_POLL_SECONDS` | `30` |
| `ENABLE_SYNTHETIC_DATA` | `false` |

The background worker is a separate Render service and may add hosting cost. Deploy the API migration before the worker starts processing. The worker retries a failed poll without deleting pending queue rows.

For WhatsApp delivery, the migration creates a distinct `terravanta_worker` database group role. Create a `terravanta_worker_runtime` login, grant it only to that group, and set `WHATSAPP_WORKER_DATABASE_URL` on the worker. Do not grant the worker group to `terravanta_runtime`; it can claim other users' WhatsApp queue entries. Keep `META_WA_SEND_ENABLED=false` until Meta credentials, the approved template, the signed webhook and this separate database URL are configured.

The API service remains `SERVICE_MODE=api` (the default), and continues to receive `MIGRATIONS_DATABASE_URL`, Supabase configuration, and its normal environment variables.

## Authorization and audit boundary

- Domain event writes happen through existing authenticated API routes. The actor is derived from the verified session.
- The event log is append-only for the application role.
- The database worker function has one narrow operation: process scheduled follow-up reminder rows and insert in-app notifications for current farm members. It cannot modify health events or follow-up outcomes.
- Notification reads are restricted to `recipient_user_id = current_user_id()`; the application role can update only `read_at`.
- Event and workflow rows retain `farm_id` and RLS checks. The worker connects with the restricted runtime credential and invokes a `SECURITY DEFINER` function with a fixed search path; it does not receive the database-owner URL.
- Notifications contain an animal tag and scheduled date, not clinical notes or treatment details.

## MCP and model-driven actions

The durable workflow and notification base is ready for a narrowly scoped tool adapter. A network-facing MCP server, model-driven action proposals, approval queue, email/SMS providers, and cooperative payout workflows are not included in this migration. Add those only with explicit tool schemas, per-request Supabase identity and tenant authorization, action idempotency, audit records, and an approval gate for consequential writes. Do not expose raw SQL, shell access, arbitrary record updates, or external payment actions to a model.
