# Terravanta market wedge and validation plan

## Strategic thesis

Terravanta should not sell itself as another cooperative MIS or as a farmer recordkeeping subscription. Those categories already have capable systems. The code in this repository proves a useful workflow, but it does not prove that cooperatives will buy it, that current systems leave a costly gap, or that the workflow is a moat.

Evidence from Kenya already shows cooperatives using digital systems for milk collection, member records, quality checks, payment processing, check-off deductions and farmer statements. Mau Dairy's case describes a system used by over 1,500 registered farmers; commercial platforms such as DairyCore and eDairy advertise overlapping collection-to-payment workflows. This makes a standalone daily collection-sheet matcher a weak entry position and creates a real integration and switching-cost challenge. These examples show that the category has buyers and existing solutions; they do not prove that a specific cooperative has an unmet need Terravanta can sell into. [SNV's Mau Dairy case](https://www.snv.org/update/digitization-a-game-changer-for-dairy-cooperatives-in-kenya), [DairyCore cooperative offering](https://dairycore.co.ke/core/for-cooperatives/), [eDairy Africa](https://edairy.africa/edairy-system/).

The stronger commercial hypothesis to test is a **system-agnostic milk settlement assurance service** for cooperatives whose existing systems do not produce one trusted close across collection, processor settlement, quality adjustments, deductions and farmer payout records. Terravanta would ingest exports from the systems already in use, prepare a reconciled evidence pack for each payout period, route only unresolved discrepancies to authorized staff, and return a clear member statement after approval. Do not ask farmers or collectors to re-enter the same delivery in a second system. Keep the cooperative's current MIS as the operational source until a buyer asks for a replacement.

The repository now contains the first system-agnostic settlement-close workflow: a cooperative administrator can import collection, processor-settlement and payout CSVs, review member-period variances, record a named approval and download a statement pack. A separate intake reconciliation flow still compares cooperative collection rows with consented farmer delivery records. Neither flow has a named MIS/processor adapter, automatic farmer statement delivery, closed-loop correction handling or payout authorization. The service offer and economic value remain hypotheses until observed and paid for by a real cooperative. Any financial discrepancy or source-record correction remains subject to named cooperative review.

The offer to test is: **“For each monthly payout close, we reconcile your collection, processor settlement and payout exports, prepare a traceable farmer statement pack, and send only unresolved discrepancies to your team for approval; priced per cooperative and settlement cycle, with onboarding/support scoped separately.”** This is a pricing shape, not a quoted rate or a savings promise. A smaller pilot can charge for one close cycle. Only quote after observing a real close, collecting current workload and rework baselines, and identifying the budget owner. A percentage of farmer funds, sale of farm data, or a revenue-share claim is not part of the initial model.

This remains an unvalidated hypothesis. Product-market fit requires repeated use on real source files, an identified budget owner, a paid pilot or renewal, and service gross margin after data setup, support and exception handling. Founder conviction, a large national dairy sector, AI capability, and a successful software demo are not substitutes for those observations.

Kenya Dairy Board's 2025 profile gives national context of roughly 1.8 million smallholder households and estimated production of 5.2 billion litres annually. These are category context figures, **not Terravanta's reachable market, customer count, or revenue forecast**. Validate current county, cooperative, farm, and procurement counts before sizing a serviceable market. [KDB profile](https://www.kdb.go.ke/wp-content/uploads/2025/09/KDB-PROFILE.pdf).

## Why this entry point

- **A recurring financial close:** collection is daily, while member settlements and payout records commonly close on a period. A service that materially reduces close effort or unresolved payment discrepancies can be tied to a budget and operating deadline.
- **A clear institutional buyer:** a cooperative or processor can pay for an operational outcome and sponsor farmer onboarding. Farmers should not pay for recordkeeping that mainly serves the institution before farmer value and willingness to pay are demonstrated.
- **An existing trust need:** animal health and production records need source attribution. A veterinarian can verify a clinical event without the AI signing it or changing the source record.
- **An integration wedge, if validated:** existing collection/payments platforms already provide many features in the broad category. Terravanta must reconcile across fragmented systems or deliver a verified job incumbent systems leave undone; it must not assume a cooperative will replace a working MIS.
- **AI is supporting infrastructure:** the service must run from deterministic rules, reliable imports, evidence and approvals. AI may help map unfamiliar source columns or summarize an exception, but cannot create a financial fact, change a farmer record, resolve a disputed balance or authorize payment.

The synthetic Githunguri cooperative in the demo is not a partner, endorsement, customer, or evidence of local demand. Kiambu is a discovery candidate because the prototype data is set there and the area has documented dairy operations; the first real cooperative and corridor must be selected with local operators. Kenya Dairy Board national production estimates are category context, not Terravanta's reachable market, paying customer count, or revenue forecast. Validate the current registered-cooperative list, operating systems and serviceable volume directly before sizing a market.

## First users and jobs

| User | Initial job to be done | Evidence the pilot must collect |
| --- | --- | --- |
| Dairy farmer | Record herd events and production once, keep a usable history, and share delivery details without exposing private health notes | Time to record; completion rate; weekly return; consent comprehension; offline sync success; willingness to continue after facilitated onboarding |
| Veterinarian or animal-health professional | See assigned open cases, review the recorded history, and sign only the clinical event actually reviewed | Queue use; time to review; correction rate; proportion of records with complete event date, animal, observer and follow-up fields |
| Cooperative finance/records team | Close a payout period across collection, processor settlement and payment exports; explain every mismatch and issue an approved member statement | Time to close; records that auto-match with evidence; exception amount/count and age; correction/rework rate; complaints; paid renewal decision |

The buyer of the first contract is a **hypothesis**: test a cooperative-paid settlement-assurance service with free or low-friction farmer participation. Do not assume farmers or cooperatives will pay before interviews and a paid pilot. Price discovery should be in KES and tied to settlement closes, transaction volume, setup and support—not to monetizing or reselling farmer data. Measure the current finance/records workload and the cost of rework before comparing a service price to the job being done.

## Go-to-market sequence

### 1. Discovery before a broad launch

Run structured interviews with 15–20 dairy farmers, 4–6 veterinarians or animal-health workers, and 3–5 cooperative finance/records decision-makers in one candidate corridor. For the cooperative sample, include both operators using a mature MIS and operators using fragmented spreadsheets/manual steps. Observe an actual payout close with permission and request anonymized sample exports from collection, processor settlement, deductions and payment confirmation. Map current systems, duplicate entry, unresolved discrepancy ownership, statement correction and payout delay. These are proposed research counts, not completed interviews.

Proceed only if a named buyer can show source files that fail to reconcile cleanly in its existing MIS, an accountable staff member owns the unresolved work, farmer data can be used lawfully and with understood consent, and the buyer agrees to a paid or explicitly budgeted pilot. If a mature incumbent already closes the job accurately and on time, do not ask that cooperative to buy a duplicate system.

### 2. Eight-week, one-cooperative pilot

Recruit a manageable cohort (initial planning range: 30–50 farms) and a named cooperative champion plus veterinary reviewer. Enrol farmers with informed consent; record a baseline for reconciliation effort and missing references; train field staff; support low-connectivity capture; review use weekly. Do not use a cooperative's identity or logo in product screens without written authorization. Start with records that farmers and staff already need; do not force AI use.

The app supports real farmer accounts, farm and animal records, plots, feed and compost relationships, milk/harvest production, lot/delivery links, case review, consent revocation, a cooperative delivery view, and an offline POST queue. The new service harness imports collection CSVs, matches deterministically, retains exceptions, lets cooperative staff confirm or log follow-up, and builds a consent-filtered trace graph. Pilot staff accounts can be provisioned through a private operator command after a Supabase invitation. Before this pilot, exercise the production release and restore paths with a dedicated project and add real support and incident procedures, storage controls, and a field-tested onboarding flow.

### 3. Convert value into a paid renewal

At pilot end, present each partner with its own measured baseline and result. Offer a paid renewal only if the cooperative can identify the budget owner, the service materially improves the close, farmer data use is authorized, and support economics are viable. Test a per-cooperative/per-close service price and a fixed onboarding/support fee. A per-active-farm fee is a secondary packaging test, not the value metric. Track service and onboarding cost alongside revenue so growth does not depend on unprofitable founder-led data cleanup.

### 4. Expand only after repeatability

First replicate with another cooperative in the same region using the same onboarding and data definitions. Then test adjacent counties and different cooperative operating models. Add lab and food-safety workflows only with verified lab records and an explicit data-sharing scope. Expand feed/crop modules when farms use the recorded resource chain. Treat lenders, insurance, marketplaces, and cross-county language support as later products requiring separate consent, evidence and commercial validation.

## Product-market-fit scorecard

Use a weekly cohort review. Establish the baseline in discovery; the following are **provisional pilot gates**, not industry benchmarks:

- **Activation:** a farmer creates a farm, registers at least one animal, and records production or a health event within seven days of onboarding.
- **Habit and retention:** measure weekly active farms and week-4/week-8 retention by cohort and by self-serve versus field-assisted onboarding; investigate why users stop.
- **Record usefulness:** share of pilot deliveries linked to a source production entry and a receipt reference; count quantity/identity mismatches and correction time.
- **Farmer trust:** percentage who can explain what the cooperative sees, find/revoke a grant, and continue using the product without AI. Any material consent misunderstanding blocks expansion.
- **Veterinary utility:** review completion and record correction rates. AI answer use is secondary and never a clinical-quality proxy.
- **Cooperative value:** time to close the payout period, time spent resolving each exception, value/count of discrepancies, statement rework and disputes, number of active reviewers, and a documented renewal or paid-pilot decision.
- **Operational quality:** offline record loss/duplication, sync latency, support minutes per active farm, API availability, and cost per active farm.

As initial gates, target at least 60% of onboarded farms activated by day 7, at least 50% of activated farms returning in week 4, at least 80% of pilot deliveries linked to a source record, and zero unresolved consent-scope incidents. Revisit these thresholds after the baseline; they are hypotheses for deciding whether to iterate, not evidence of PMF. Seek a second paid renewal and a second cooperative using the same playbook before calling the motion repeatable.

## Growth model and scaling constraints

**Proposed primary loop:** cooperative finance uploads existing collection, processor-settlement and payout exports for a close → Terravanta reconciles exact member-period volume and monetary arithmetic → unresolved discrepancies are assigned to a named cooperative reviewer → approved close yields a member-code statement pack for delivery through the cooperative's existing channel → repeated use reveals stable source mappings and the next manual exceptions worth automating. The current product implements this CSV loop and reviewer/approver audit; it does not send statements to farmers, connect to payout rails or write back to a cooperative MIS. Farmers should not be asked to record a second copy of collection data to make this loop work.

The current intake matching flow is documented in [the reconciliation service contract](COOPERATIVE_RECONCILIATION.md), and the new financial close is documented in [the settlement-close contract](SETTLEMENT_CLOSE.md). Both preserve source provenance and send exceptions through a reviewer loop. The first release can reconcile only the documented CSV contracts. The next autopilot steps are to map one real source system at a time, persist and version approved mappings, re-run deterministic checks on new exports, and prepare statements for the cooperative's existing delivery channel. Disputed balances, source-record changes and payout release remain under named human accountability.

The platform's defensible advantage is not the user interface, a chatbot, or generic access to farm data. It could emerge from (1) reusable connectors to heterogeneous cooperative and processor systems, (2) a permissioned, provenance-preserving graph linking collection, settlement and farmer records, (3) measured exception decisions that reduce repeated manual handling, and (4) dependable close-time service with low onboarding/support cost. None of those advantages is established yet. Enforce least privilege, exportability, consent revocation, retention rules and audit logs as usage grows. Do not train external models on farm records without appropriate consent and contractual permission.

Before increasing cohort size, observe support hours, sync failures, mistaken animal/farm links, consent revocation behavior, data correction burden, and cooperative onboarding time. Add organization tooling and idempotent sync before running multiple independent cohorts. Preserve a low-bandwidth mobile workflow and test language support with speakers; the selected NVIDIA model card does not list Swahili among its supported languages, so the product must not imply Swahili AI support without a verified model and field evaluation.

## NVIDIA use in the wedge

- The veterinary assistant is a backend-only, opt-in draft feature. It uses the configurable NVIDIA Build chat endpoint and defaults to the exact model ID `nvidia/nemotron-3.5-lightning-30b-a3b`. Availability, terms, rate limits, data handling and language coverage must be rechecked in the account before launch. [NVIDIA Build model card](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard)
- Selectable PDF text is extracted locally. The image path is an adapter for the native Nemotron Parse NIM `/v1/parse` multipart contract, configured by `NVIDIA_PARSE_URL`; it is **not a fabricated NVIDIA Build hosted endpoint**. The parsed text can be mapped to a structured draft by the chat model. Every extracted value stays pending human review. [Nemotron Parse API reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-parse-infer)
- Forecasts and anomaly alerts use explainable record rules and statistical baselines first. Kumo, voice, image-based clinical interpretation and the named blueprints are not required for this launch wedge. Add them only with sufficient data, verified language support, and a clear user benefit.

## Decision rule

If farmers do not return without intensive prompting, or a cooperative cannot show measurable reconciliation value, **narrow the workflow or change the buyer before adding more modules or models**. If the records are repeatedly used, consent is understood, a partner renews at a price covering support, and another cooperative can onboard without founder-led customization, then expand one adjacent geography at a time.
