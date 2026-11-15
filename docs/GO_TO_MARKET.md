# Terravanta market wedge and validation plan

## Strategic thesis

Terravanta should enter by **selling the completed milk-record reconciliation job to one dairy cooperative in a Kiambu corridor**, while building farmer-controlled farm records as the data foundation. Today a cooperative collection clerk or records officer checks intake sheets against farm identities, delivery records and receipt references; the MVP handles exact matching and exception routing while the cooperative reviewer retains the final decision. The wedge is the recurring operational output—reconciled rows and an auditable source-to-intake trace—not an AI chat feature or a generic farm dashboard.

The first service offer to test is: **“We reconcile every daily milk collection sheet against currently shared farm deliveries, route only mismatches to your reviewer, and return a trace for each intake row, priced as a monthly cooperative service with a per-sheet or collection-point component.”** This is a pricing shape to validate, not a published rate or a savings claim. Start with spreadsheet uploads; integrate scales, payout ledgers or ERP systems only after the reconciliation job is repeatedly used and a buyer asks for that outcome.

This is a wedge hypothesis, not proven product-market fit. The app demonstrates deterministic CSV matching, a cooperative exception queue, reviewer decisions, an audit trail and consent-filtered provenance. It does not yet integrate with a cooperative's weighing hardware, payout ledger, or existing ERP, and follow-up notes are not sent to farmers. Those integrations should follow evidence that staff repeatedly use the reconciliation service and will pay for a measured reduction in manual checking.

Kenya Dairy Board's 2025 profile gives national context of roughly 1.8 million smallholder households and estimated production of 5.2 billion litres annually. These are category context figures, **not Terravanta's reachable market, customer count, or revenue forecast**. Validate current county, cooperative, farm, and procurement counts before sizing a serviceable market. [KDB profile](https://www.kdb.go.ke/wp-content/uploads/2025/09/KDB-PROFILE.pdf)

## Why this entry point

- **Frequent job:** milk and collection events recur daily or near-daily, giving the product a natural habit loop and quick feedback on data quality.
- **A clear counterpart:** a cooperative can distribute onboarding and has a concrete delivery-summary workflow, while the farmer retains control of sharing.
- **An existing trust need:** animal health and production records need source attribution. A veterinarian can verify a clinical event without the AI signing it or changing the source record.
- **A credible expansion path:** after delivery records are complete and used, add validated lab attachments, feed traceability, and crop–livestock resource links. They extend the same farm record instead of requiring a new acquisition story.
- **AI is supporting infrastructure:** the initial value proposition is dependable records, consent and reconciliation. The assistant is optional, requires a per-request sharing choice, and must not diagnose or prescribe.

The synthetic Githunguri cooperative in the demo is not a partner, endorsement, customer, or evidence of local demand. Kiambu is the proposed discovery area because the prototype data is set there; the first real corridor must be selected with local operators.

## First users and jobs

| User | Initial job to be done | Evidence the pilot must collect |
| --- | --- | --- |
| Dairy farmer | Record herd events and production once, keep a usable history, and share delivery details without exposing private health notes | Time to record; completion rate; weekly return; consent comprehension; offline sync success; willingness to continue after facilitated onboarding |
| Veterinarian or animal-health professional | See assigned open cases, review the recorded history, and sign only the clinical event actually reviewed | Queue use; time to review; correction rate; proportion of records with complete event date, animal, observer and follow-up fields |
| Cooperative collection or records team | Reconcile each daily collection sheet to consented farm deliveries, route exceptions, and produce a traceable intake record | Reconciliation time per sheet; match and exception rates; review minutes per exception; duplicate import rate; consent-related skips; renewal decision |

The buyer of the first contract is a **hypothesis**: test a cooperative-paid reconciliation service with a free or low-friction farmer record account. Do not assume farmers or cooperatives will pay before interviews and a paid pilot. Price discovery should be in KES and tied to sheets or collection points, setup and support—not to monetizing or reselling farmer data. Measure the current outsourced and in-house clerk workload before comparing the service price to the job being done.

## Go-to-market sequence

### 1. Discovery before a broad launch

Run structured interviews with 15–20 dairy farmers, 4–6 veterinarians or animal-health workers, and 3–5 cooperative collection/records decision-makers in one candidate corridor. Observe one actual milk-recording and delivery-reconciliation shift with permission. Map the current paper, WhatsApp, spreadsheet and cooperative-system workflows; record where identifiers, timestamps, quantities and receipts are lost. These are proposed research counts, not completed interviews.

Proceed only if one recurring problem is common to both farm and cooperative staff, the farmer's data-entry burden can fit the real routine, and an identified cooperative champion can recruit and support a pilot cohort.

### 2. Eight-week, one-cooperative pilot

Recruit a manageable cohort (initial planning range: 30–50 farms) and a named cooperative champion plus veterinary reviewer. Enrol farmers with informed consent; record a baseline for reconciliation effort and missing references; train field staff; support low-connectivity capture; review use weekly. Do not use a cooperative's identity or logo in product screens without written authorization. Start with records that farmers and staff already need; do not force AI use.

The app supports real farmer accounts, farm and animal records, plots, feed and compost relationships, milk/harvest production, lot/delivery links, case review, consent revocation, a cooperative delivery view, and an offline POST queue. The new service harness imports collection CSVs, matches deterministically, retains exceptions, lets cooperative staff confirm or log follow-up, and builds a consent-filtered trace graph. Pilot staff accounts can be provisioned through a private operator command after a Supabase invitation. Before this pilot, exercise the production release and restore paths with a dedicated project and add real support and incident procedures, storage controls, and a field-tested onboarding flow.

### 3. Convert value into a paid renewal

At pilot end, present each partner with its own measured baseline and result. Offer a limited paid renewal only if the cooperative can identify the budget owner and farmer usage remains voluntary. Test simple pricing units—cooperative subscription, per active farm, or a small implementation/support fee—without locking into one until purchase conversations reveal budget fit. Track service and onboarding cost alongside revenue so growth does not depend on unprofitable field support.

### 4. Expand only after repeatability

First replicate with another cooperative in the same region using the same onboarding and data definitions. Then test adjacent counties and different cooperative operating models. Add lab and food-safety workflows only with verified lab records and an explicit data-sharing scope. Expand feed/crop modules when farms use the recorded resource chain. Treat lenders, insurance, marketplaces, and cross-county language support as later products requiring separate consent, evidence and commercial validation.

## Product-market-fit scorecard

Use a weekly cohort review. Establish the baseline in discovery; the following are **provisional pilot gates**, not industry benchmarks:

- **Activation:** a farmer creates a farm, registers at least one animal, and records production or a health event within seven days of onboarding.
- **Habit and retention:** measure weekly active farms and week-4/week-8 retention by cohort and by self-serve versus field-assisted onboarding; investigate why users stop.
- **Record usefulness:** share of pilot deliveries linked to a source production entry and a receipt reference; count quantity/identity mismatches and correction time.
- **Farmer trust:** percentage who can explain what the cooperative sees, find/revoke a grant, and continue using the product without AI. Any material consent misunderstanding blocks expansion.
- **Veterinary utility:** review completion and record correction rates. AI answer use is secondary and never a clinical-quality proxy.
- **Cooperative value:** time spent reconciling a delivery, missing-reference rate, number of active staff reviewers, and a documented renewal or paid-pilot decision.
- **Operational quality:** offline record loss/duplication, sync latency, support minutes per active farm, API availability, and cost per active farm.

As initial gates, target at least 60% of onboarded farms activated by day 7, at least 50% of activated farms returning in week 4, at least 80% of pilot deliveries linked to a source record, and zero unresolved consent-scope incidents. Revisit these thresholds after the baseline; they are hypotheses for deciding whether to iterate, not evidence of PMF. Seek a second paid renewal and a second cooperative using the same playbook before calling the motion repeatable.

## Growth model and scaling constraints

**Primary loop:** cooperative manager uploads the existing collection sheet → Terravanta resolves exact matches and presents only exceptions → staff review the uncertain rows and see the source-to-intake trace → recurring missing fields show which farms need supported onboarding → the cooperative invites those farmers → farmers record production and grant delivery-summary sharing → the next collection sheet has more reliable matches. A veterinarian improves record trust by verifying only reviewed clinical events. Referrals or QR enrollment can be tested later; neither should be assumed to drive growth.

The harness format, matching rules, reviewer loop, trace graph and pilot metrics are defined in [the reconciliation service contract](COOPERATIVE_RECONCILIATION.md). The implementation is a human-reviewed service step toward autopilot: do not remove the cooperative's accountability for disputed quantities, farmer identity, payout or safety decisions.

The platform's durable advantage should be **trusted, farmer-controlled and well-attributed records**, not an opaque prediction or access to sensitive data. Enforce least privilege, exportability, revocation, retention rules and audit logs as usage grows. Do not train external models on farm records without appropriate consent and contractual permission.

Before increasing cohort size, observe support hours, sync failures, mistaken animal/farm links, consent revocation behavior, data correction burden, and cooperative onboarding time. Add organization tooling and idempotent sync before running multiple independent cohorts. Preserve a low-bandwidth mobile workflow and test language support with speakers; the selected NVIDIA model card does not list Swahili among its supported languages, so the product must not imply Swahili AI support without a verified model and field evaluation.

## NVIDIA use in the wedge

- The veterinary assistant is a backend-only, opt-in draft feature. It uses the configurable NVIDIA Build chat endpoint and defaults to the exact model ID `nvidia/nemotron-3.5-lightning-30b-a3b`. Availability, terms, rate limits, data handling and language coverage must be rechecked in the account before launch. [NVIDIA Build model card](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard)
- Selectable PDF text is extracted locally. The image path is an adapter for the native Nemotron Parse NIM `/v1/parse` multipart contract, configured by `NVIDIA_PARSE_URL`; it is **not a fabricated NVIDIA Build hosted endpoint**. The parsed text can be mapped to a structured draft by the chat model. Every extracted value stays pending human review. [Nemotron Parse API reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-parse-infer)
- Forecasts and anomaly alerts use explainable record rules and statistical baselines first. Kumo, voice, image-based clinical interpretation and the named blueprints are not required for this launch wedge. Add them only with sufficient data, verified language support, and a clear user benefit.

## Decision rule

If farmers do not return without intensive prompting, or a cooperative cannot show measurable reconciliation value, **narrow the workflow or change the buyer before adding more modules or models**. If the records are repeatedly used, consent is understood, a partner renews at a price covering support, and another cooperative can onboard without founder-led customization, then expand one adjacent geography at a time.
