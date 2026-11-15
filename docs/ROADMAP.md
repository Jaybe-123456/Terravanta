# Implemented scope and roadmap

## Working MVP in this repository

- Three distinct views: farmer recordkeeping, veterinarian assigned-case review and verification, and a cooperative read-only delivery portal.
- Optional synthetic role switching behind an explicit flag; default Supabase email/password sign-in and farmer registration with server-validated JWTs and farmer-only account provisioning.
- New real farmer accounts start with an empty workspace; farm identity and operating records are entered by the account owner and remain private until an explicit consent grant.
- Supabase refresh tokens are stored in an HttpOnly cookie by a same-origin Next.js route; access tokens remain in memory. Role claims from signup metadata are ignored.
- Farm registration, farm passport, plots, livestock, health events, veterinary queue and signed verification, feed inventory/allocation, manure, compost and plot application.
- Production source records, product lots and deliveries; delivery quantities cannot exceed their source record, and active consent controls cooperative access.
- Consent targets registered cooperative organizations or a cooperative administrator email; cooperative views show only delivery-summary fields plus a documentation prompt based on a missing shared delivery reference. They do not reveal clinical or laboratory records.
- A private operator CLI can create cooperative organizations and provision invited veterinarian/cooperative identities with farm or organization membership. Staff roles cannot be assigned through public signup.
- Rule-based alerts, AI provider abstraction, opt-in NVIDIA veterinary draft workflow, local PDF text extraction, configurable Nemotron Parse NIM image parsing and review-only structured document drafts.
- Offline POST queue for one browser, scoped to the current user; the API remains the source of truth after synchronization.
- SQLAlchemy UUID schema, Alembic initial migration, PostGIS point geometry, synthetic demo seed, Docker Compose, OpenAPI docs and workflow tests.

## Not production complete

- The supplied project is a functional MVP, not a launched service or validated clinical product. The included Kiambu farm and all associated organizations, people, events, and deliveries are synthetic.
- Real farmer self-registration and first-login provisioning are implemented but have not been connected to a configured Terravanta Supabase project in this workspace. Live signup, email confirmation and token rotation still need an end-to-end run with project credentials.
- Veterinarian and cooperative accounts still require an operator to send a Supabase Auth invitation and run the private provisioning CLI. A self-service invitation portal, role administration UI, recovery operations and abuse controls remain to be built; users cannot self-assign those roles.
- Session refresh tokens use an HttpOnly, SameSite cookie and access tokens remain in memory. Complete a security review for reverse-proxy deployments, CSRF, session revocation and XSS before production launch.
- User-scoped offline queue prevents one account from replaying another account's queued writes. It is not encrypted, does not support conflict resolution or multi-device merge, and only queues POST records. Historical unscoped queue entries should be reviewed/cleared during upgrade.
- The local PostgreSQL volume may still contain the previous fictional seed records. Disabling synthetic mode stops new seeding and demo login but does not delete existing records. New accounts cannot access these rows because they have no membership.
- Compose uploads use a local volume. S3-compatible private storage, antivirus/content scanning, signed download links, retention jobs and asynchronous workers are still required for real documents.
- AI has not been exercised with a live NVIDIA credential in this build. The default chat ID is configurable and documented, but account entitlement, model behavior, rate limits, endpoint availability and data terms require an operator's validation. Do not use API credentials that were pasted into the original build prompt; rotate them.
- Parse is an adapter to the native NIM multipart `/v1/parse` contract. A reachable `NVIDIA_PARSE_URL` and any required Parse credentials are required. A Build hosted Parse contract has not been verified here. PDF text extraction is local; all extracted data stays a draft.
- There are no bundled approved veterinary references, no veterinarian-reviewed AI evaluation set, and no evidence that the heuristic safety filter catches every unsafe output. Do not use AI output for diagnosis, prescribing or treatment decisions.
- Normalized tables exist for vaccination/treatment/reproduction/quality/laboratory records, but some still lack dedicated end-user workflows. No milk is certified safe and no agronomic/nutrient balance is inferred.
- There is no cooperative ERP, scale/hardware, payout, buyer identity or lab integration. Market assumptions are recorded as hypotheses in [Go-to-market plan](GO_TO_MARKET.md); no PMF or revenue is claimed.
- Add production observability, backups/restore drills, idempotent API persistence, rate-limit storage suitable for multiple workers, privacy/retention review, penetration testing, accessibility checks and on-call support before onboarding real farms.

## Next build sequence

1. Run field discovery and baseline reconciliation observation in one candidate Kiambu dairy corridor; refine the record flow with farmers, vets and cooperative staff.
2. Configure the dedicated Supabase project and test farmer email confirmation, session refresh, account recovery, farm creation, operator staff provisioning and email-scoped consent. Add a self-service invitation and organization administration workflow only after pilot operations are defined.
3. Pilot the delivery/animal record loop with one cooperative and a small voluntary cohort; instrument activation, retention, missing references, correction effort, consent understanding, support burden and renewal willingness.
4. Implement encrypted/idempotent offline synchronization and private object storage with a durable document-processing queue.
5. Add lab results, food-safety reporting and medication/vaccination workflows only with authorized source verification and clinical review.
6. Validate NVIDIA access, data terms, evidence retrieval, structured extraction, unsafe outputs, latency and availability with the target account; leave AI optional and non-blocking.
7. Replicate to a second cooperative only after the first pilot shows retention, measurable reconciliation value, safe consent behavior and sustainable service costs.
