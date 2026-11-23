# Implemented scope and roadmap

## Working MVP in this repository

- Three distinct views: farmer recordkeeping, veterinarian assigned-case review and verification, and a cooperative read-only delivery portal.
- Optional synthetic role switching behind an explicit flag; default Supabase email/password sign-in and farmer registration with server-validated JWTs and farmer-only account provisioning.
- New real farmer accounts start with an empty workspace; farm identity and operating records are entered by the account owner and remain private until an explicit consent grant.
- Supabase refresh tokens are stored in an HttpOnly cookie by a same-origin Next.js route; access tokens remain in memory. Role claims from signup metadata are ignored.
- Farm registration, farm passport, plots, livestock, health events, veterinary queue and signed verification, feed inventory/allocation, manure, compost and plot application.
- Production source records, product lots and deliveries; delivery quantities cannot exceed their source record, and active consent controls cooperative access.
- Consent targets registered cooperative organizations or a cooperative administrator email; cooperative views show only delivery-summary fields plus a documentation prompt based on a missing shared delivery reference. They do not reveal clinical or laboratory records.
- System-agnostic cooperative settlement-close workbench: import collection, processor settlement and payout CSVs; match by normalized member code and period; compare volume and exact KES arithmetic; retain hashes, source row references, exception notes and approver audit; download statement-pack CSV only after server-enforced approval. This workflow does not use NVIDIA, edit source ledgers, initiate payments or automatically deliver statements.
- Receivables assurance vertical slice: cooperative claim intake and item lines, authenticated private PDF/CSV upload, seller assertion and processor submission, processor accept/partial/dispute/reject/information response, transparent aging, source-hashed ZIP export, receipt allocation, and a budget-owner repeat decision record. Composite tenant-scoped keys bind case/evidence/processor response. Processor organization/user provisioning is an operator-only CLI.
- A private operator CLI creates cooperative/processor organizations and provisions Supabase identities with farm or organization membership. Staff roles cannot be assigned through public signup.
- Rule-based alerts, AI provider abstraction, opt-in NVIDIA veterinary draft workflow, local PDF text extraction, configurable Nemotron Parse NIM image parsing and review-only structured document drafts.
- Durable farm events, scheduled follow-up reminders, a recipient-scoped in-app notification inbox and an assigned-veterinarian contact-request workflow. Contact requests are not phone calls or WhatsApp messages.
- Farm record indicators for production comparisons, feed inventory, crop/plot links, follow-up completion and source-linked deliveries, plus an opt-in AI review draft that uses an allowlisted, aggregated record summary.
- Offline POST queue for one browser, scoped to the current user; the API remains the source of truth after synchronization.
- SQLAlchemy UUID schema, Alembic initial migration, PostGIS point geometry, synthetic demo seed, Docker Compose, OpenAPI docs and workflow tests.
- Alembic revision `0008_tenant_rls` adds a restricted PostgreSQL app role, request-scoped tenant context, explicit table grants and RLS policies for farms, clinical records, consented deliveries, cooperative settlement and processor claims. CI includes a PostgreSQL smoke check for cross-farm isolation and the narrow consent projection. The API uses a separate migration/operator owner URL. This security boundary is newly implemented and still requires staging permission-matrix validation before use with live records.

## Not production complete

- The supplied project is a functional MVP, not a launched service or validated clinical product. The included Kiambu farm and all associated organizations, people, events, and deliveries are synthetic.
- Real farmer self-registration and first-login provisioning are implemented but have not been connected to a configured Terravanta Supabase project in this workspace. Live signup, email confirmation and token rotation still need an end-to-end run with project credentials.
- The Render production database must be given the restricted runtime login and role membership before migration `0008_tenant_rls` is deployed. No production database migration or deploy was run by this workspace session.
- Veterinarian and cooperative accounts still require an operator to send a Supabase Auth invitation and run the private provisioning CLI. A self-service invitation portal, role administration UI, recovery operations and abuse controls remain to be built; users cannot self-assign those roles.
- Session refresh tokens use an HttpOnly, SameSite cookie and access tokens remain in memory. Complete a security review for reverse-proxy deployments, CSRF, session revocation and XSS before production launch.
- User-scoped offline queue prevents one account from replaying another account's queued writes. It is not encrypted, does not support conflict resolution or multi-device merge, and only queues POST records. Historical unscoped queue entries should be reviewed/cleared during upgrade.
- The local PostgreSQL volume may still contain the previous fictional seed records. Disabling synthetic mode stops new seeding and demo login but does not delete existing records. New accounts cannot access these rows because they have no membership.
- Compose uses a private local upload volume. Render's Blueprint uses a private persistent disk and one API instance; S3-compatible private storage can be selected for a future scale-out. The service validates allowed file type and size, stores by random key, checks file hash on retrieval and authorizes each download. Malware scanning, automated retention/deletion, backup/restore validation and review of live-data operating controls remain before real financial uploads.
- AI has not been exercised with a live NVIDIA credential in this build. The default chat ID is configurable and documented, but account entitlement, model behavior, rate limits, endpoint availability and data terms require an operator's validation. Do not use API credentials that were pasted into the original build prompt; rotate them.
- Parse uses NVIDIA's documented hosted Nemotron Parse multipart endpoint. The URL is explicit, and the implementation falls back to the server-side NVIDIA chat key if no separate Parse key is supplied. PDF text extraction is local; all extracted data stays a draft.
- There are no bundled approved veterinary references, no veterinarian-reviewed AI evaluation set, and no evidence that the heuristic safety filter catches every unsafe output. Do not use AI output for diagnosis, prescribing or treatment decisions.
- Normalized tables exist for vaccination/treatment/reproduction/quality/laboratory records, but some still lack dedicated end-user workflows. No milk is certified safe and no agronomic/nutrient balance is inferred.
- There is no cooperative ERP, processor, scale/hardware, bank/M-Pesa, buyer identity or lab integration. Contracts cannot yet be managed/confirmed from the UI; there is no source export adapter, OCR matching, lender portal, automatic follow-up, legal arrears determination or payment initiation. The existing settlement close only covers downstream cooperative member payouts and does not prove a processor receivable. No authorized real claim, processor response, budget-owner decision or paid repeat is in evidence; no PMF, savings, arrears recovery or revenue is claimed.
- WhatsApp safety and delivery code is implemented, but no Meta business number, credentials, approved template or live webhook has been configured and verified. Outbound delivery stays off by default. The channel is not production-ready until the worker role is provisioned and a complete pairing, request, reply and receipt flow is observed.
- Add production observability, backups/restore drills, idempotent API persistence, rate-limit storage suitable for multiple workers, privacy/retention review, penetration testing, accessibility checks and on-call support before onboarding real farms.

## Next build sequence

1. Obtain one cooperative that will authorize one retrospective claim; identify its claims owner, processor AP reviewer and actual budget owner.
2. Review private evidence storage, backup, retention and access controls; gather written authority for each file before upload.
3. Measure existing claim assembly time/rework, run the submitted claim and record the processor's real response and source.
4. Ask for the paid-repeat decision, record the actual price unit and attach the approval artifact if approved.
5. Compare the result against incumbent MIS and finance operations; add scanning/retention controls and one reusable adapter before repeating with another period.
6. Configure and continue validating Supabase accounts, offline farm record workflows and consent controls; keep farmer/veterinary features as supporting systems rather than presumed proof of the commercial wedge.
7. Provision Meta, apply migration `0013_whatsapp_delivery_safety`, create the dedicated worker database login, and validate a complete WhatsApp pilot before enabling outbound messages.
8. Validate NVIDIA access, data terms, evidence retrieval, structured extraction, unsafe outputs, latency and availability with the target account; leave AI optional and out of financial adjudication.
9. Replicate to a second cooperative/processor relationship only after paid repeat, counterparty response, safe access behavior and viable service cost in the first relationship.
