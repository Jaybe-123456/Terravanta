# Terravanta market wedge and validation plan

## Strategic thesis

Terravanta should not sell itself as another cooperative MIS, farmer-record subscription, payout rail or invoice-finance product. Those categories already have capable systems and active payment/finance initiatives. The current code proves useful record and payout-close workflows; it does not prove that buyers will pay, that receivables remain unserved, or that Terravanta has a moat.

The incumbent bar is higher than digital record capture. DairyCore advertises collection through M-Pesa payout, member/herd records, invoices and overdue-account chasing. eDairy advertises collection, quality and DTB-linked finance. Mastercard/Heifer/KCB's Farmer Visibility Project is creating digital dairy transaction histories and enabling financial-service/payment access. ZuriCap and SWAFI publicly describe invoice finance for agricultural suppliers, including processor/buyer approval. These claims do not prove comparative performance, but they rule out generic “digital visibility,” “faster farmer payment,” “invoice finance,” and “another cooperative portal” as Terravanta's differentiated promise. [DairyCore](https://dairycore.co.ke/core/for-cooperatives/), [eDairy](https://edairy.africa/edairy-system/), [Farmer Visibility Project](https://www.mastercard.com/news/eemea/en/newsroom/press-releases/en/2026/july/heifer-mastercard-and-kcb-launch-digital-payments-initiative-for-dairy-farmers/), [ZuriCap](https://zuricapltd.com/about/), [SWAFI](https://www.swafi.co/post/boosting-dairy-production-with-swafi-s-financial-support).

The stronger hypothesis is **cross-system receivables assurance**: help a cooperative assemble and age its seller-side claim on a processor, connect the claim to contractual terms, supply/acceptance records, quality adjustments, invoices/statements and actual cash receipts, then get a recorded counterparty response. The system should show what the cooperative asserts, what the processor confirms or disputes, what has been received, who owes whom under which reviewed term, and days past the reviewed contractual due date. This is different from the existing payout close, which concerns the cooperative's downstream payable to its members.

The repository currently contains a member payout-close workflow, not an accounts-receivable workbench. It imports collection, processor-settlement and payout CSVs, reviews member-period variances and exports a statement pack; it does not establish the cooperative's receivable from a processor, store contract-backed due dates, capture buyer confirmations, allocate incoming cash to claims or produce a lender diligence pack. The receivables data foundation is being added separately; no end-to-end receivables workflow or processor connector is yet implemented. See [the receivables-assurance architecture and validation contract](RECEIVABLES_ASSURANCE.md).

The offer to test is: **“For each processor settlement period, we assemble a source-linked receivables register showing each cooperative claim, counterparty response, open balance, contractual due date and days overdue, then prepare a reviewed evidence pack for collection or finance diligence; priced per counterparty-period with source onboarding scoped separately.”** This is a service hypothesis, not a promise of faster payment, recovery, credit, or a published price. Interview cooperative claim owners, processor AP teams and invoice-finance/bank diligence teams separately before choosing who pays. Do not quote until one buyer agrees to a paid repeat workflow.

This remains an unvalidated hypothesis. Arrears evidence does not prove Terravanta can accelerate processor cash or that a lender will rely on its claim file. PMF requires real source files, response from a counterparty, an identified budget owner, a paid repeat, and service margin after mapping/support work. Founder conviction, national dairy output, AI capability, and a software demo do not substitute for those observations.

For the first operator-led discovery conversation, candidate shortlist, safe data-preparation checklist and paid-pilot gate, use the [cooperative settlement pilot kit](COOPERATIVE_PILOT_KIT.md).

Kenya Dairy Board's 2025 profile gives national context of roughly 1.8 million smallholder households and estimated production of 5.2 billion litres annually. These are category context figures, **not Terravanta's reachable market, customer count, or revenue forecast**. Validate current county, cooperative, farm, and procurement counts before sizing a serviceable market. [KDB profile](https://www.kdb.go.ke/wp-content/uploads/2025/09/KDB-PROFILE.pdf).

## Why this entry point

- **A real cash-flow problem with an existing remedy:** Kenya's Milk Sales Contract Regulations define contract terms, payment timing, default interest and a route for requesting KDB intervention. Actual claim age and enforceability still depend on the specific contract and evidence. Terravanta should preserve that evidence chain, not offer a legal opinion. [Kenya Law regulations](https://new.kenyalaw.org/akn/ke/act/ln/2021/20/eng%402022-12-31/source.pdf)
- **A gap between records and usable proof:** digital delivery/payment data can exist while seller and buyer records disagree about acceptance, deductions, invoices or partial receipts. Confirm this gap in a target cooperative; don't infer it from sector stories.
- **A buyer question, not an assumption:** the cooperative owns the claim but may be cash-constrained; a lender may have stronger budget but already lends on receivables; a processor may want cleaner AP but may resist a seller-sponsored claim system. Test budget, authority, data rights and purchase separately for each.
- **An existing trust need:** animal health and production records need source attribution. A veterinarian can verify a clinical event without the AI signing it or changing the source record.
- **An interoperability wedge, if validated:** import and link existing MIS and payment records; do not replace stable collection or payout operations. The possible edge is cross-party confirmation and reusable evidence mappings, not the connector alone.
- **AI is supporting infrastructure:** the service must run from deterministic rules, reliable imports, evidence and approvals. AI may help map unfamiliar source columns or summarize an exception, but cannot create a financial fact, change a farmer record, resolve a disputed balance or authorize payment.

The synthetic Githunguri cooperative in the demo is not a partner, endorsement, customer, or evidence of local demand. Kiambu is a discovery candidate because the prototype data is set there and the area has documented dairy operations; the first real cooperative and corridor must be selected with local operators. Kenya Dairy Board national production estimates are category context, not Terravanta's reachable market, paying customer count, or revenue forecast. Validate the current registered-cooperative list, operating systems and serviceable volume directly before sizing a market.

## First users and jobs

| User | Initial job to be done | Evidence the pilot must collect |
| --- | --- | --- |
| Dairy farmer | Record herd events and production once, keep a usable history, and share delivery details without exposing private health notes | Time to record; completion rate; weekly return; consent comprehension; offline sync success; willingness to continue after facilitated onboarding |
| Veterinarian or animal-health professional | See assigned open cases, review the recorded history, and sign only the clinical event actually reviewed | Queue use; time to review; correction rate; proportion of records with complete event date, animal, observer and follow-up fields |
| Cooperative finance/claims team | Assemble a processor receivable claim, substantiate its basis, track confirmation/dispute and receipts, and prepare a claim or lender pack | Staff time to assemble; asserted vs confirmed vs disputed vs received KES; age on reviewed due date; counterparty response time; later payment outcome; paid-repeat decision |
| Processor accounts-payable team | Match supplier claims to contract, accepted supply, quality adjustments and cash application; respond to exceptions | AP handling time; unresolved claims and age; duplicate/invalid claims caught; buyer-side budget and willingness to invite suppliers |
| Invoice-finance / bank operations | Assess a supplier receivable with less manual document chase while retaining credit decisions | Diligence time; share accepted by processors; unsupported claims rejected; loss/repayment data if lawfully available; paid data/service contract |

The buyer is an open question. Start with the cooperative as claim owner and data holder; simultaneously ask one lender/financier whether it would pay for evidence preparation or sponsor a pilot, and one processor whether it will confirm/contest claims in a shared workflow. Do not presume the party with the most pain controls budget. Price discovery should be in KES and tied to counterparty-period, source complexity and support—not a cut of farmer funds or sale of farm data. A free test is not PMF.

## Go-to-market sequence

### 1. Discovery before a broad launch

Start with 3–5 cooperative claims/finance owners, 3–5 processor accounts-payable/finance owners, and 2–3 invoice-finance/bank operations owners in one corridor. These are proposed discovery counts, not completed interviews. Ask each to walk through one real, recent processor receivable from contract to receipt, show where the current system records each step, explain who owns exceptions and budget, and identify whether any source-linked buyer confirmation is still manual. No member-level data is needed in discovery.

Proceed only if one named buyer demonstrates recurring staff effort and cost around an unresolved processor claim, can lawfully authorize the relevant sources, and has a route to invite the counterparty to respond. Ask for buyer response before lender diligence: a seller-only assertion may have little finance value. If incumbent systems already prove the receivable and handle claim response well, stop this product wedge for that customer.

### 2. Retrospective one-claim pilot

Select one completed or overdue processor-period claim, one cooperative, one processor relationship and a named cooperative claim owner. Use only the minimum authorized records to connect contract terms, supply, acceptance, adjustments, invoice/statement, correspondence and actual cash receipts. Record the existing staff time and age basis before reconstruction. Obtain a recorded processor response if possible; invite a lender to review a redacted pack only with explicit authority. Do not use partner identity or logos without written permission, and do not touch live payments or ledgers.

Farmer, veterinarian and mixed-farm capabilities remain supporting product lines, not the first PMF proof. The app has a manual seller claim register and processor response path, private PDF/CSV evidence storage, reviewed-date aging, receipt allocation and evidence export. This is a pilot tool, not a validated business outcome. It still needs written authority, reviewed production storage/retention controls, a real processor relationship and a budget owner before real-data claims are entered.

### 3. Convert value into a paid renewal

At pilot end, present the evidence-assembly baseline, source coverage, seller/buyer amount positions, response time, actual later receipts and service effort separately. Offer a paid repeat only if a named budget owner chooses it, the buyer threshold is met, authority is clear and cost-to-serve leaves a viable margin. Test a per-counterparty-period or per-claim-pack price with onboarding scoped separately. A processor response alone is not commercial validation; a lender introduction alone is not a paid buyer.

### 4. Expand only after repeatability

First repeat with the same cooperative/processor relationship to prove recurring claims and cost. Then onboard a second cooperative or processor using the same evidence schema and mapping playbook. Add lender packs only after a financier is a paid or explicitly budgeted design partner. Expand into other agricultural receivables only after dairy mapping is repeatable; keep farm/veterinary, insurance and marketplace scope tied to separately validated use.

## Product-market-fit scorecard

Use a weekly deal/pilot review. Establish the baseline in discovery; these are **provisional gates**, not industry benchmarks:

- **Buyer problem:** claim frequency, age, unresolved amount and person-hours by role, compared with the current MIS/workaround.
- **Evidence quality:** asserted value mapped to primary sources; contract/date basis completeness; false-match rate on reviewed samples; amount/period traceability.
- **Two-sided confirmation:** share of claim value acknowledged, partly accepted, disputed and unanswered by a verified counterparty user; response time and reason codes.
- **Cash outcome:** actual receipt and allocation timing, partial-payment accuracy and remaining balance. Do not attribute faster payment to Terravanta absent a comparison and causal evidence.
- **Financier value:** diligence time, percentage of packs accepted as decision-ready, required gaps and any documented paid contract; credit approval remains the lender's decision.
- **Commercial proof:** named buyer, procurement path, written success threshold, paid repeat and cost-to-serve by case/counterparty period.
- **Trust and security:** consent/mandate comprehension, access revocation, privacy incidents, audit completeness, retention/deletion and zero unauthorized sharing.

The pilot passes only if the cooperative validates the source trail, an authorized processor response is obtained (or the paid buyer explicitly values seller-side claims without it), a budget owner agrees to a priced repeat, delivery cost is known, and no material data-rights issue remains. Define numerical success thresholds with the buyer before the retrospective run; do not invent universal arrears-recovery, match-rate or response-time benchmarks. Require a second paid relationship using the same playbook before calling the motion repeatable.

## Growth model and scaling constraints

**Proposed primary loop:** cooperative submits a documented processor claim and supporting sources → Terravanta links supply/acceptance, invoice/adjustment and payment evidence → cooperative reviews its asserted balance → processor user confirms, partly confirms or disputes with a reason → actual cash receipts are allocated and remaining balance aged → authorized reviewer receives an evidence pack → outcomes improve future mappings and reduce repeated evidence assembly. A manual first version of the claim, response, receipt, aging and export workflow is now implemented. The loop still requires a real counterparty to participate; source adapters, a lender portal and payment remain outside the current release.

The current intake matching flow is documented in [the reconciliation service contract](COOPERATIVE_RECONCILIATION.md), and the existing member payout close in [the settlement-close contract](SETTLEMENT_CLOSE.md). Neither is the receivables workbench. The manual claim, processor response, evidence export and access-control paths now exist; source adapters, contract management, malware scanning and formal retention/deletion remain incomplete. Automation may prepare evidence and route reminders, but disputed claims, source corrections and finance decisions remain under named accountability. No cooperative claim, processor response or paid repeat has been validated yet.

The platform's possible advantage is a permissioned graph linking the source evidence to a seller claim, an authenticated buyer response, an actual cash receipt and a later outcome—backed by reusable adapters and fast, reliable claim operations. The UI, a chatbot, raw farm data and a generic AI model are not moats. None of the proposed advantage is established yet. If processors do not confirm and lenders do not rely on the pack, it remains a cooperative-side filing tool. Preserve exportability and customer ownership; never pool confidential claims or train external models without appropriate legal and contractual permission.

Before onboarding multiple organizations, measure connector setup, evidence-review and counterparty follow-up hours, duplication/false-match rates, access revocation, deletion, source corrections and per-case cost. Add organization-level sharing tools and idempotent source ingestion before scaling. Farm/mobile workflows and language support still need field evaluation; they do not substitute for receivables workflow validation.

## NVIDIA use in the wedge

- The veterinary assistant is a backend-only, opt-in draft feature. It uses the configurable NVIDIA Build chat endpoint and defaults to the exact model ID `nvidia/nemotron-3.5-lightning-30b-a3b`. Availability, terms, rate limits, data handling and language coverage must be rechecked in the account before launch. [NVIDIA Build model card](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard)
- Selectable PDF text is extracted locally. The image path is an adapter for the native Nemotron Parse NIM `/v1/parse` multipart contract, configured by `NVIDIA_PARSE_URL`; it is **not a fabricated NVIDIA Build hosted endpoint**. The parsed text can be mapped to a structured draft by the chat model. Every extracted value stays pending human review. [Nemotron Parse API reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-parse-infer)
- Forecasts and anomaly alerts use explainable record rules and statistical baselines first. Kumo, voice, image-based clinical interpretation and the named blueprints are not required for this launch wedge. Add them only with sufficient data, verified language support, and a clear user benefit.

## Decision rule

If processor responses cannot be obtained, the incumbent already resolves the job, or no buyer will pay for a repeat claim pack, **stop this wedge before broad feature work**. If repeated claims use the same evidence protocol, a buyer pays, service margin improves, and another counterparty relationship onboards without founder-led custom work, then expand one corridor at a time.
