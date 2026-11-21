# Terravanta commercial viability and pre-build harness

**Review date:** 21 November 2026

**Scope:** product repository, deployment configuration, published competitor descriptions, and Kenya's current legal/regulatory materials. This is a product and operating-risk review, not a legal opinion, market-size estimate, or proof of demand.

## Decision

Terravanta is **not yet a proven smallholder business**. The farmer/veterinary workspace is a useful product surface, but an individual smallholder's willingness and ability to pay for another digital record system has not been established. The product should not depend on farmer subscriptions for its first revenue.

The most plausible commercial wedge is a **cooperative-side processor receivables operations service**: turn existing settlement and evidence files into a reviewable, source-linked position; track what the cooperative asserts, what the processor confirms or disputes, what has actually been received, and which reviewed contract term supports the due date. Sell an operational deliverable per processor-period, with source setup priced separately. This is a hypothesis, not a demonstrated moat or promise of quicker cash.

The opportunity is conditional on four facts being proven together: the cooperative has recurring claims that its current systems do not resolve; it can lawfully authorize the source records; a named payer values the result enough to pay again; and delivery effort falls enough for positive contribution margin. At present the repository documents **zero validated real claims, zero real processor responses and zero paid repeats**. Synthetic demo data, recorded founder notes and a working UI do not count as commercial proof.

## Competitive reality

Competitor pages are evidence of what vendors claim, not independent evidence of active usage, market share, or performance.

| Competitor or program | Publicly described overlap | Strategic implication |
| --- | --- | --- |
| DairyCore | Offline milk collection, SMS receipts, member records, deductions, M-Pesa batch payouts, loans, invoices, eTIMS and overdue-account chasing. [DairyCore](https://dairycore.co.ke/core/for-cooperatives/) | Do not rebuild cooperative collection, payout or member records. Import its exports if authorized; look for the unresolved seller-to-processor exception it does not close. |
| Maziwa Plus | Member and route records, collection/handover, quality, payments, statements, stock, sales and processing. [Maziwa Plus](https://www.alpobiz.com/maziwa-plus.html) | “One connected dairy record” and basic reconciliation are not enough to differentiate. |
| DCERP / Pinch Africa | Pinch publicly markets broad cooperative ERP coverage including collection, quality, farmer payments, credit, traceability, finance, approvals, and integrations. [Pinch Africa](https://www.pinch.africa/industry-agriculture) | Treat these platforms as systems of record and potential export sources, not gaps to fill with another broad MIS. Validate actual exports and deployment practices in discovery. |
| eDairy | Describes digital scales and cards, milk-quality analyzers, cooperative/regulator portals, and DTB-linked mobile loans/settlements; it says the system was developed in collaboration with KDB. [eDairy](https://edairy.africa/edairy-system/) | Digital weighing, quality capture, farmer identity and finance are already claimed by an integrated incumbent. Do not claim those capabilities as a moat. |
| Farmer Visibility Project | Mastercard, Heifer, KCB Foundation and KCB Bank announced a program targeting 30,000 farmers over a nine-month pilot, using transaction visibility and payment/financial-service enablement. This is an announced target, not a verified outcome. [Mastercard announcement](https://www.mastercard.com/news/eemea/en/newsroom/press-releases/en/2026/july/heifer-mastercard-and-kcb-launch-digital-payments-initiative-for-dairy-farmers/) | Farmer visibility and payment history will become more available. Terravanta must solve exception resolution across records and parties, not sell visibility alone. |

The defensible positioning is **“the cooperative's evidence and exception desk across the systems it already uses.”** The buyer's job is to answer, for each processor-period: which lines are supported, which are disputed, what is confirmed, what cash arrived, what remains unresolved, and what follow-up is authorized. Do not claim a legal debt, successful recovery, finance approval, farmer income increase, or faster payment unless those outcomes are measured and attributable.

## Who may pay, and why the financial bottleneck matters

| Candidate payer | Incentive | Main obstacle | What the pilot must establish |
| --- | --- | --- | --- |
| Cooperative / union | Owns the seller's claim and bears the staff work and member pressure. | Arrears may mean it has the least spare cash; board, manager, finance lead and procurement authority may differ. | Named budget owner, approval path, source authority, recurring claim frequency, and a written paid repeat. |
| Processor | May reduce AP exceptions, duplicate disputes and source-chasing. | A seller-facing tool can strengthen supplier claims; the processor may see little reason to onboard. | Processor-side time saved, a named AP sponsor, and an accepted response workflow that benefits its own close. |
| Bank / invoice financier | May value complete source evidence and verified acceptance before diligence. | Seller assertion alone is weak collateral; the lender controls underwriting and may already have its own partner data and origination channels. | A financier reviews a redacted, authorized pack, names missing evidence, and documents a paid or budgeted use. Financing remains the lender's decision. |
| Farmer | Benefits if cooperative cash flow improves and delivery/payment records are more transparent. | Benefits are indirect and depend on the cooperative and processor; onboarding, devices and support create cost. | Farmer understanding and consent; do not assume a direct subscription or charge farmers for access to their own records. |

Start with discovery across all three institutional seats, but do not sell a three-sided marketplace. The cooperative can be the first claim owner; the financier may ultimately have the stronger software budget; the processor may only participate when the workflow reduces its own work. A fixed fee per reviewed counterparty-period is a safer initial price experiment than a fee on recovered funds or a share of financing proceeds. Do not publish a price until the service hours and buyer threshold are measured.

Model the service before automating it:

```text
contribution per repeat = contracted fee
                         - analyst claim-review hours
                         - onboarding and mapping hours
                         - processor follow-up and support hours
                         - direct storage, transfer, security and delivery cost
```

Count founder time at a realistic replacement rate. If the service only works when founder labor is free, it is not a scalable software business. If time stays high but the buyer pays, Terravanta may first be a specialist managed service; productize only the repeated steps that reduce delivery cost without reducing evidence quality.

## The moat: a hypothesis with a proof ladder

“Farm data,” AI, a dashboard, an evidence graph, or a connector list is not a moat by itself. A vendor with an installed cooperative ERP can copy a screen and often has better access to collection data. Exportability is necessary for trust, but means customers can leave.

The candidate moat is a **permissioned, cross-party exception history** built from repeatable imports: each material claim line is linked to source evidence and a reviewed term; the counterparty can respond as an authenticated organization; cash receipts and corrections are linked later; and the workflow learns reusable mappings without pooling customer data unlawfully. It becomes harder to replace only if it repeatedly lowers the work to explain and resolve a claim across different systems and counterparties.

Build the proof in order:

1. One real cooperative reconstructs one authorized historical claim faster or more completely than its existing method.
2. The processor records a response, or its non-response and reason are captured accurately.
3. A named budget owner approves and pays for a repeat at a measured price.
4. A second repeat uses the same mapping/review playbook with positive contribution margin.
5. A second cooperative/processor pair reuses enough of that playbook to lower onboarding cost, and a lender or processor confirms the pack fits an actual workflow.

Until stages 3–5 exist, call this a **wedge under validation**, not a proven moat. Stop or reposition if the incumbent already resolves the same exceptions at acceptable cost.

## Product and engineering audit

| Area | Repository state | Commercial consequence / next gap |
| --- | --- | --- |
| Cooperative receivables workflow | Manual claim intake, item lines, evidence upload, reviewed due-date aging, seller/processor amount separation, processor response, receipt allocation, export and a pilot-decision record are implemented. | Strong enough for an operator-led retrospective pilot; not evidence of customer demand or a legal receivable. |
| Authorization | Supabase JWT identity, server roles, organization checks, Postgres RLS migration and an RLS smoke check in CI exist. | RLS is newly introduced; CI is not a production security audit. Verify the production migration, role grants, real tenant combinations and backup/restore before live data. |
| Source integration | Evidence is manually uploaded. No live MIS, scale, bank, M-Pesa, KDB, or lender connector is implemented. Source-mapping tables exist, but the current receivables route inventory has no mapping-profile or contract-management workflow. | The first delivery still has service labor. Do not pitch “automated reconciliation” until a buyer's repeated file formats and exception rules are mapped and tested. |
| Cash and finance | Receipts can be recorded/allocated; the system does not move funds, originate finance or decide credit. | Keep those boundaries. Use a licensed bank/financier for any bridge product, after regulatory and contract review. |
| Evidence operations | Private local disk or private S3-compatible storage, SHA-256 checking and a one-instance Render disk are configured. Malware scanning, automatic retention/deletion, validated restore and formal security review are absent. | Not ready for broad real-record ingestion. S3 alone does not solve scanning, retention, access review or recovery. |
| Deployment and data location | Render Blueprint places the API in Singapore and uses one instance with a persistent evidence disk; Vercel serves the web UI. No Kubernetes manifests or cluster exist. | Cross-border data transfer and vendor/subprocessor locations need an approved legal basis and safeguards before real Kenyan personal data. Do not assume changing regions alone completes compliance. |
| Demand evidence | Product documents say no real cooperative claim, processor response or paid repeat has been validated. | The next spend should be buyer discovery and a paid-pilot attempt, not more broad modules or infrastructure. |

The older `GO_TO_MARKET.md` has been aligned with this implementation in this change. See `docs/RECEIVABLES_ASSURANCE.md` for endpoint/storage boundaries and `docs/DEPLOYMENT.md` for the CI/CD structure.

## Financial and legal gates

This section flags product-design gates for Kenyan counsel and a data-protection professional; it does not decide how a particular entity is classified.

1. **Data-controller / processor registration and purpose.** ODPC guidance says entities must assess and register their controller/processor roles; the ODPC FAQ lists debt administration and factoring, as well as financial services, among processing purposes that are not exempt from mandatory registration regardless of the small-entity threshold. Because Terravanta is positioning around receivables claims and future finance diligence, have counsel/ODPC guidance classify the actual service and determine whether Terravanta, the cooperative, or both need registrations. Execute written data-processing and sharing terms, define who answers data-subject requests, retention, correction, deletion and breach notices. [ODPC FAQ](https://www.odpc.go.ke/faqs/), [registration guidance](https://www.odpc.go.ke/wp-content/uploads/2024/02/ODPC-Guidance-Note-on-Registration-of-Data-Controllers-and-Data-Processors.pdf)
2. **Cross-border hosting.** The checked-in Render Blueprint sets `region: singapore`. Kenya's Data Protection Act sections 48–49 and ODPC's September 2026 cross-border guidance require an applicable transfer route and appropriate safeguards; sensitive personal data has added requirements. Inventory Render, Supabase, Vercel, object storage, email and model-provider locations, subprocessors, backups and support access. Obtain a counsel-reviewed transfer instrument and complete any required ODPC notification before importing real personal data. A data-region change may reduce exposure but is not, by itself, legal compliance. [Data Protection Act](https://new.kenyalaw.org/akn/ke/act/2019/24/eng%402022-12-31/source.pdf), [ODPC cross-border guidance](https://odpc.go.ke/wp-content/uploads/2026/09/ODPC-%E2%80%93-Guidance-Notes-for-Cross-border-Data-Transfers.pdf)
3. **Credit, factoring and funds.** The CBK Act now describes licensing for non-deposit-taking credit business; CBK's 2025 NDTCP rules were published as draft regulations. Keep Terravanta as workflow/evidence software and do not lend, buy/advance against receivables, hold customer money, initiate payouts, make a credit decision, service repayments or promise recovery until a Kenyan financial-regulatory lawyer has analyzed the exact model and a licensed partner is contracted. A security interest/assignment over receivables also needs contract and perfection analysis under the Movable Property Security Rights Act. [CBK Act](https://www.centralbank.go.ke/wp-content/uploads/2026/03/Central-Bank-of-Kenya-Act.pdf), [CBK draft-rule notice](https://www.centralbank.go.ke/2025/08/07/draft-non-deposit-taking-credit-providers-ndtcps-regulations-2025/), [Movable Property Security Rights Act](https://new.kenyalaw.org/akn/ke/act/2017/13/eng%402022-12-31/source.pdf)
4. **Cooperative authority.** Verify each society's registered by-laws, board/general-meeting resolutions and delegated authority before borrowing, pledging receivables, sharing member-level records or appointing an agent. The Co-operative Societies Act restricts loans/credit and conditions borrowing from non-members by by-laws/rules; a screen or user role is not the society's mandate. [Co-operative Societies Act](https://kenyalaw.org/kl/fileadmin/pdfdownloads/Acts/Co-operativeSocietiesActCap490.pdf)
5. **Dairy claims.** The Milk Sales Contract Regulations provide for written terms, payment arrangements and a route to request KDB intervention where a buyer does not honor payment obligations. Encode only the contract and date a person has reviewed; do not automatically decide default, calculate a legal interest claim or certify that a balance is recoverable. Confirm current regulatory language and the actual contract with Kenyan counsel/KDB before a demand or escalation. [Kenya Law regulations](https://new.kenyalaw.org/akn/ke/act/ln/2021/20/eng%402022-12-31/source.pdf)

## Multi-objective state/action harness

The machine-readable configuration is `config/terravanta-commercial-harness.json`. It is explicitly a repository audit snapshot, **not a live production probe**. The validator in `scripts/validate_commercial_harness.py` runs in GitHub Actions to catch missing objectives, broken stage gates or accidental claims that an unvalidated wedge is already repeatable. The product's current Render and Vercel states still need an operator to verify them in their dashboards.

Use a constrained, multi-objective policy rather than one vanity KPI:

- **Buyer value:** staff time to prepare and review a claim pack.
- **Evidence integrity:** source coverage, false matches and preservation of separate seller, counterparty and cash positions.
- **Resolution:** counterparty response, elapsed time and reasoned disputes.
- **Economics:** approved repeat revenue less all direct service and delivery costs.
- **Trust/compliance:** authority, data rights, transfer safeguards, accurate correction, access and retention.

Treat trust, lawful authority and financial boundaries as **hard constraints**, not weighted goals that a high revenue number can trade away. For the other objectives, record the baseline and buyer-set thresholds before the pilot. Do not invent weights or universal pass rates. When objectives conflict, prefer the smallest reversible action that resolves the earliest failed gate; do not automate unresolved judgment or evidence.

### Harness loop

1. **Observe:** record named actor, customer, source system, claim period, evidence, user time, current workaround, deployment/data path and known legal authority. Mark each item as `verified`, `reported`, `inferred` or `unknown`.
2. **Set desired state:** state one buyer outcome, measured baseline, target chosen with the buyer, allowed data, stop conditions and accountable reviewer. Keep claims about legal debt/finance outside the software's outcome target.
3. **Choose action:** use the JSON `action_rules`. Missing buyer evidence means discovery, not a feature sprint; missing authority means pause data; missing counterparty response means do not call the pack finance-ready; negative service margin means rescope/reprice/stop.
4. **Build the smallest slice:** only after the preceding state gate passes, make one workflow change with deterministic math, source lineage and a human review point. AI cannot set amounts, due dates, legal labels or financing eligibility.
5. **Verify:** run the existing API/web CI, PostGIS migration and RLS smoke checks; inspect the preview; run the one-claim scenario with synthetic data first; then get the cooperative and processor to validate authorized real evidence.
6. **Measure and decide:** record observed outcome, cost-to-serve, buyer decision and evidence artifact. Promote the state only when its gate has evidence; otherwise revise the hypothesis or stop. Repeat the same workflow twice before generalizing it.

The objectives form a Pareto review: no single objective can mask a loss in trust or economics. Each pilot review should record the objective vector, failed gate, next action, owner and expiry date in the pilot record. Do not use reinforcement learning or autonomous multi-agent actions here; the state space is small, evidence is sparse, consequences are financial/legal, and human accountability is essential.

## Kubernetes decision

**Do not add Kubernetes or a Kubernetes manifest compiler now.** This deployment is one FastAPI service, one managed Postgres database and a Vercel frontend. Render's Blueprint and Vercel's project configuration already serve as the infrastructure declaration, while GitHub Actions checks migrations, RLS smoke behavior and frontend/API builds. Kubernetes would not produce customer evidence, lender acceptance, shared evidence retention or lawful data transfers. It would add cluster operations, secrets, ingress, backups and monitoring work before demand is proven.

Revisit orchestration only after measured paid demand requires multiple stateless API workers, background document jobs, shared object storage, queue guarantees, service SLOs and an operator budget. First migrate evidence to a private shared object store, add scanning/retention/restore, and prove scaling limits under the current managed host. Keep current and desired product states in the committed harness; keep live infrastructure state in the hosting control planes and verify it during releases.

## Next decision gates

1. Complete data-protection and cross-border review before real records enter the current production stack.
2. Find one cooperative claim owner and budget owner; learn the current workflow with anonymized files and no member-level data initially.
3. Agree on one retrospective claim, source authority, baseline, success thresholds and secure transfer route.
4. Get a processor response and ask one lender/financier to review the resulting redacted pack only if the cooperative authorizes it.
5. Ask the budget owner for a priced repeat and capture a quote/PO/decision artifact. Do not build connectors or a lending product until this result supports them.
