# Farm decision support and messaging channels

## Implemented in this slice

### Farm record decision support

`GET /api/v1/farms/{farm_id}/insights` returns deterministic, permission-checked summaries from recorded livestock, case follow-up, crops, feed inventory, production and source-linked deliveries. Production comparisons use equal 14-day windows and report the number of recorded days; missing days are not treated as zero. The response includes data gaps and rule-based next steps so the farmer can see what the system knows and what it does not.

`POST /api/v1/farms/{farm_id}/ai-assistant` prepares a review draft from the same farm snapshot. It requires request-level consent before sending data to NVIDIA, excludes account names, emails, farm coordinates, animal names and tags, and sends only an allowlisted farm summary plus approved knowledge sources. Farmer-entered crop/feed labels and aggregate quantities may be sent. The user's question is sent as written, so the UI asks users to omit personal/contact details. The service logs outcome and latency and keeps the answer separate from verified records. If the provider is unconfigured or unavailable, deterministic indicators remain available. It must not be used to diagnose, prescribe, calculate rations or doses, certify safety, claim causality, or promise ROI.

The Overview page shows these record indicators and next steps. The user can ask a question about the current snapshot; an unchecked NVIDIA permission results in no external request.

### Request a veterinarian

Farmers can submit an in-app contact request linked to their farm and optionally an animal. Assigned farm veterinarians receive an inbox notification. One veterinarian can accept the request, record that contact was made, decline, or complete it after acceptance. The request and every transition are audited and recorded as farm-domain events. A farmer can cancel a request while it is still pending.

`preferred_contact_method` is captured as a preference (`phone_call`, `whatsapp`, or `in_app`). A request remains available in the in-app inbox. If outbound WhatsApp is later enabled, a generic alert is queued only for assigned veterinarians with a verified number and active WhatsApp consent. Requests require at least one veterinarian to be assigned to the farm; there is no automatic public vet directory or dispatch service. The interface tells users to contact local veterinary help directly for an emergency.

Each contact request also has an authenticated, farm-scoped conversation thread. Messages are immutable, attributed to their sender, deduplicated by client message ID, represented as farm-domain events, and notify the other participant in the in-app inbox. Only the requesting farmer and the assigned veterinarian can continue a non-pending thread; a farm veterinarian can inspect a pending request before accepting it. These messages coordinate contact and are not verified clinical records. The API and database enforce the same access boundary.

## WhatsApp safety and delivery layer

The provider-ready integration is implemented behind an off-by-default configuration gate. `0013_whatsapp_delivery_safety` adds one-use pairing challenges, a per-user phone and consent record, a durable communication outbox, and deduplicated Meta webhook receipts. The settings screen lets any signed-in farmer, veterinarian, cooperative user, or processor user opt in, link a number, inspect recent delivery states and revoke consent. Thread text is relayed only when both sender and recipient have independently linked a number and granted channel consent; a request alert also requires consent from its farmer requester and the receiving veterinarian.

Pairing begins from the signed-in app and asks the user to send `TVLINK <one-time-code>` to the configured Terravanta number. Only the signed Meta webhook can verify and bind that sender number. A request message uses `TV <request-code> <message>` and is accepted only from the linked, consented number when its account is the farmer who opened that veterinarian request or the veterinarian assigned to it. A phone number alone never authenticates a user or grants farm access. WhatsApp messages are copied into the same request thread and generate an in-app notification; they do not create or verify clinical records.

The GET webhook route performs Meta's verification-token handshake. POST payloads are size limited, the HMAC SHA-256 signature is checked over the raw body, and events for a different business phone ID are ignored. Message IDs and delivery status transitions are deduplicated. Outbound jobs are idempotently enqueued, claimed with `FOR UPDATE SKIP LOCKED`, checked again for live consent, retried with bounded exponential backoff, and updated from signed sent/delivered/read/failed callbacks. Logs and the user status view omit phone numbers and message bodies.

The database role `terravanta_worker` inherits normal application privileges and alone can execute the global delivery claim/finish functions. Do not grant it to the API runtime login. Before enabling sends in production, create a separate `terravanta_worker_runtime` login, grant it membership in `terravanta_worker`, and use that login only for `WHATSAPP_WORKER_DATABASE_URL`. The ordinary API runtime cannot read or claim other users' outbox records.

Signed webhook processing uses a separate `terravanta_webhook` NOLOGIN role, with RLS policies and table/column grants limited to verified phone pairing, veterinary request participants, channel messages and delivery receipts. Configure its separate login as `WHATSAPP_WEBHOOK_DATABASE_URL` on the API. The webhook handler does not use the migration owner URL or the regular API runtime login.

Outbound messages are not enabled in this repository configuration. No Meta credentials, production number, approved template, or live webhook has been provisioned or verified. To enable the channel later:

1. Apply migration `0013_whatsapp_delivery_safety` with the migration owner before deploying the web UI.
2. Create the `terravanta_webhook_runtime` login after the migration and set `WHATSAPP_WEBHOOK_DATABASE_URL` on the API service. Also set `WHATSAPP_PAIRING_SECRET`, `META_WA_BUSINESS_NUMBER`, `META_WA_PHONE_NUMBER_ID`, `META_WA_APP_SECRET`, and `META_WA_VERIFY_TOKEN` to allow pairing and signed webhooks. Keep `META_WA_SEND_ENABLED=false` until the worker is ready.
3. Prepare the worker-only database login after the migration, set `WHATSAPP_WORKER_DATABASE_URL` to its internal Render URL, and leave API `DATABASE_URL` on `terravanta_runtime`.
4. To enable outbound sends, set `META_WA_SEND_ENABLED=true` on API and worker, then set the following only on the worker service. Do not enable the flag in only one service.
5. Register `https://terravanta.onrender.com/api/v1/integrations/meta/whatsapp/webhook` in Meta with GET and POST subscriptions for WhatsApp messages, and use the same verify token as the API environment value.

Backend environment variables:

| Variable | Purpose |
| --- | --- |
| `WHATSAPP_PAIRING_SECRET` | HMAC key for storing one-time pairing codes as hashes; API only |
| `WHATSAPP_WEBHOOK_DATABASE_URL` | Dedicated restricted webhook database login; API only |
| `META_WA_BUSINESS_NUMBER` | Business number used to open the user-initiated `wa.me` pairing link; API only |
| `META_WA_APP_SECRET` | Verify inbound webhook signatures; API only |
| `META_WA_VERIFY_TOKEN` | Verify Meta's webhook handshake; API only |
| `META_WA_SEND_ENABLED` | Outbound queue/provider kill switch; false by default, set consistently on API and worker |
| `WHATSAPP_WORKER_DATABASE_URL` | Separate worker login; only the worker can execute global queue functions |
| `META_WA_ACCESS_TOKEN` | Server-side credential to call Cloud API; worker only |
| `META_WA_PHONE_NUMBER_ID` | Business phone-number ID used to validate signed webhook events on the API and send through Cloud API on the worker |
| `META_WA_GRAPH_API_VERSION` | Explicit Meta Graph API version; worker only, update deliberately |
| `META_WA_NOTIFICATION_TEMPLATE` | Approved utility template name with one body variable for the request code; worker only |
| `META_WA_TEMPLATE_LANGUAGE` | Approved template language code; worker only |

Never add these values to frontend environment variables or source control. The app uses free-form text only inside the recipient's 24-hour user-initiated messaging window; outside it, the approved template carries only the request code and the full message stays in the Terravanta inbox. Meta's Graph API send endpoint and webhook signature requirements are documented in the [WhatsApp Business Platform overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/overview) and [webhook validation guidance](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/).

Delivery is at least once: outbox enqueues are idempotent, but a provider timeout after Meta accepts a message can make a retry duplicate that notification. Users see provider receipt states; a queued or sent state does not mean a veterinarian has read or acted on a request. No automated AI reply, diagnosis, prescription, clinical verification, consent grant, financial approval or payment action is connected to this channel. AI provider consent remains separate from WhatsApp consent.

## Next engineering sequence

1. Apply the new migration and prepare the distinct worker database login before enabling delivery.
2. Provision the Meta Business portfolio, WhatsApp Business account, production number, system user token and approved utility template; configure Meta webhook subscriptions.
3. Run one controlled end-to-end pairing, request alert, inbound thread reply and delivery-receipt check before inviting pilot users.
4. Measure contact request acknowledgement time, completion rate, opt-out rate and failed delivery rate with assigned veterinarians before automating further.
