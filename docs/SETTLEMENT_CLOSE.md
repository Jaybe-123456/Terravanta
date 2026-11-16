# Cooperative settlement close

## Product boundary

The settlement close is the first implemented step toward Terravanta's proposed cooperative-paid settlement-assurance service. It reconciles three existing UTF-8 CSV exports for a cooperative's period close: farmer/collection intake, processor settlement, and farmer payouts. It does not replace the cooperative's MIS, initiate or certify a payment, edit source records, send a farmer statement automatically, or establish that the service has product-market fit. The buyer, willingness to pay, source-system gaps, and the economic value of the close still need to be validated with real cooperatives.

## Input contracts

All three files must include a unique header row, one record per source event, and dates inside the supplied period. Extra columns are accepted and ignored. Each file is limited to 5 MB and 20,000 non-empty rows.

Collection export:

```csv
member_code,delivery_date,quantity_liters,receipt_reference
```

Processor settlement export:

```csv
member_code,settlement_date,accepted_liters,gross_amount_kes,deductions_kes,net_amount_kes,settlement_reference
```

Payout export:

```csv
member_code,payout_date,amount_kes,payout_reference
```

`member_code` is trimmed and uppercased before matching. Dates use `YYYY-MM-DD`. Quantities and KES amounts must be finite, non-negative decimal numbers, with quantities/settlement amounts required to be greater than zero. Values are aggregated by member code for the period. Source row numbers and references are retained in the close item for audit navigation. Money is evaluated to KES 0.01 and milk volume to 0.1 litres.

## Automated checks and review

The API performs these deterministic comparisons:

- Collection litres versus processor accepted litres.
- Processor gross minus deductions versus processor net amount.
- Processor net amount versus the payout export amount.
- Presence of each member's records in all three exports.

Any missing source, volume difference, processor arithmetic difference, or payout difference is routed to `needs_review`; an exact row is `reconciled`. A cooperative reviewer may add a follow-up note or accept an exception with a note. Follow-up leaves the close pending. Acceptance records the user, timestamp and note, but it does not overwrite the imported amount or resolve the underlying system discrepancy. A close cannot be approved until every exception has been accepted with a note. A named cooperative user then approves the close with an overall note. Approval is a review attestation only, not payment authorization.

After approval, the cooperative can download a member-code statement CSV with period quantities, processor gross/deductions/net, payout, variance and exception review notes. The export neutralizes spreadsheet formula-like text. The API logs source-file SHA-256 fingerprints, the acting user, review decisions, approval and statement-pack download. Uploaded file binaries are not retained. The normalized aggregate and row/reference provenance are retained in the database.

## APIs

All routes are `/api/v1` versioned and restricted server-side to a user assigned as the cooperative administrator for exactly one organization.

```text
POST /api/v1/cooperative/settlement-closes
GET  /api/v1/cooperative/settlement-closes
GET  /api/v1/cooperative/settlement-closes/{close_id}
POST /api/v1/cooperative/settlement-closes/{close_id}/items/{item_id}/review
POST /api/v1/cooperative/settlement-closes/{close_id}/approve
GET  /api/v1/cooperative/settlement-closes/{close_id}/statement-pack
```

Creation accepts multipart fields `period_start`, `period_end`, `collection_file`, `processor_file` and `payout_file`. Re-importing identical content for the same organization and dates is rejected. Creating a corrected close with new input changes the source fingerprint and preserves the previous close as its own audit record.

## Product and architecture extensions

Keep deterministic source validation, reconciliation, review policy and approval in the domain service. Add cooperative/processor MIS connectors as replaceable source adapters only after sample exports and data-access terms are obtained. A versioned mapping profile can then map each real system's columns into the normalized collection, settlement and payout contracts. Do not ask farmers to duplicate entries in a second operational ledger.

AI may later suggest a mapping for an unfamiliar export or summarize a variance from its source evidence. Such output must be a draft with provenance and human confirmation. Model availability, a NVIDIA key, and model quality are not prerequisites to this close workflow. No AI decides money, silently promotes a match, changes imported values, or approves the close.

## Known limits before a paid live pilot

- No connector exists for a named cooperative MIS, processor, bank or mobile-money provider; only the documented CSV contracts are implemented.
- Source binaries are not retained. A cooperative must keep its source exports under its own retention controls.
- Member codes need an agreed, stable cross-system mapping. This version treats case/whitespace-normalized codes as exact identities; it does not infer or fuzzy-match members.
- The close sums records by member and period. It does not calculate milk prices, validate quality deductions, assess taxes, fees, credit balances, payout destination ownership or explain a source discrepancy.
- Reviewer acceptance and close approval do not authorize payment or certify that a farmer received funds.
- Farmer statements are exported for the cooperative to deliver through its existing channel. No SMS, email, M-Pesa or bank delivery integration exists.
- The settlement service buyer hypothesis and unit economics are unvalidated. Observe an actual close, baseline work and rework, get buyer approval and test a paid pilot before promising savings or scaling onboarding.
