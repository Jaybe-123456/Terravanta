# Farm decision support and messaging channels

## Implemented in this slice

### Farm record decision support

`GET /api/v1/farms/{farm_id}/insights` returns deterministic, permission-checked summaries from recorded livestock, case follow-up, crops, feed inventory, production and source-linked deliveries. Production comparisons use equal 14-day windows and report the number of recorded days; missing days are not treated as zero. The response includes data gaps and rule-based next steps so the farmer can see what the system knows and what it does not.

`POST /api/v1/farms/{farm_id}/ai-assistant` prepares a review draft from the same farm snapshot. It requires request-level consent before sending data to NVIDIA, excludes account names, emails, farm coordinates, animal names and tags, and sends only an allowlisted farm summary plus approved knowledge sources. Farmer-entered crop/feed labels and aggregate quantities may be sent. The user's question is sent as written, so the UI asks users to omit personal/contact details. The service logs outcome and latency and keeps the answer separate from verified records. If the provider is unconfigured or unavailable, deterministic indicators remain available. It must not be used to diagnose, prescribe, calculate rations or doses, certify safety, claim causality, or promise ROI.

The Overview page shows these record indicators and next steps. The user can ask a question about the current snapshot; an unchecked NVIDIA permission results in no external request.

### Request a veterinarian

Farmers can submit an in-app contact request linked to their farm and optionally an animal. Assigned farm veterinarians receive an inbox notification. One veterinarian can accept the request, record that contact was made, decline, or complete it after acceptance. The request and every transition are audited and recorded as farm-domain events. A farmer can cancel a request while it is still pending.

`preferred_contact_method` is captured as a preference (`phone_call`, `whatsapp`, or `in_app`). It does not initiate a call or send a WhatsApp message. Requests require at least one veterinarian to be assigned to the farm; there is no automatic public vet directory or dispatch service. The interface tells users to contact local veterinary help directly for an emergency.

## WhatsApp integration boundary

Terravanta does not yet connect to WhatsApp. No Meta credentials, business phone number, verified user phone numbers, pairing flow, webhook, or outbound message provider are configured. A saved WhatsApp preference is not evidence that a message was delivered.

The proposed first provider is the official WhatsApp Business Platform Cloud API. Meta documents its message endpoint as `/{WHATSAPP_BUSINESS_PHONE_NUMBER_ID}/messages`, and webhook event notifications include a SHA-256 signature in `X-Hub-Signature-256`; webhook signatures should be verified before processing payloads. See the [WhatsApp Business Platform overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/overview) and [Meta webhook validation guidance](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/).

Before enabling production messaging, implement these controls:

1. Link each farmer or veterinarian to a phone only after an authenticated, expiring, one-time pairing challenge. Never match a phone number to an account using display name or an unverified message alone.
2. Record explicit, revocable consent for WhatsApp delivery. Keep this distinct from consent to send farm records to an AI provider.
3. Verify Meta's webhook signature over the raw request body using the app secret. Validate the webhook handshake, enforce payload size limits, and deduplicate provider message IDs before side effects.
4. Reuse the signed-in user's farm role and PostgreSQL RLS for every inbound request. If a user has multiple farms, ask them to select one; do not infer or broaden the farm scope.
5. Keep incoming text as untrusted user input. Terras may summarize records and prepare a proposal. Require an explicit confirmation for every write and keep clinical verification, treatment, sharing consent, financial approval and payment actions outside autonomous execution.
6. Use a delivery outbox with retries, idempotency, status callbacks, redacted logs, retention rules, and delivery failure visibility. Do not claim that a request has been received by a veterinarian until an acknowledged status is recorded.
7. Keep AI provider consent separate. WhatsApp transport does not authorize external AI processing; the user must opt in for the particular AI request.

Expected backend-only settings after a WhatsApp Business account is provisioned:

| Variable | Purpose |
| --- | --- |
| `META_WA_ACCESS_TOKEN` | Server-side credential to call the Cloud API |
| `META_WA_PHONE_NUMBER_ID` | Business phone-number ID used by the messages endpoint |
| `META_WA_APP_SECRET` | Verify inbound webhook signatures |
| `META_WA_VERIFY_TOKEN` | Verify webhook subscription handshake |
| `META_WA_GRAPH_API_VERSION` | Explicit Graph API version, reviewed before upgrading |

Do not add these values to the frontend environment or commit them. No values are required until the integration is implemented and the business number is provisioned.

## Next engineering sequence

1. Add user phone pairing, consent and revocation with audit history.
2. Add the signed webhook endpoint, raw-body signature validation, inbound deduplication and a restricted channel command router.
3. Add an outbound WhatsApp delivery outbox for contact requests and reminders, initially with status-only notices and no private clinical details.
4. Add confirmation cards/replies for Terras proposals and enforce the same API authorization as the web application.
5. Pilot with farmers and assigned veterinarians and measure contact-request acknowledgement time, completion rate and no-response rate before automating further.
