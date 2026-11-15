# Cooperative milk reconciliation service

## Outcome being sold

Terravanta's first service wedge is: **we reconcile each cooperative's daily milk-collection sheet against farmer-consented delivery records, route only exceptions for human review, and return an auditable source-to-intake trace.** The workflow starts with CSV because it fits the records most cooperatives already export. The current build is an exception-reduction system: the cooperative still owns review and final decisions. It does not claim automated payouts, milk safety certification, or ERP write-back.

The initial buyer hypothesis is a dairy cooperative's collection or records manager. A cooperative can sponsor farm record onboarding because traceable production records improve matching coverage; veterinary records remain private unless a different, explicit consent scope is designed and granted. Farmers keep ownership and revocation controls over the delivery summary used for matching.

## Harness: intake contract

Upload a UTF-8 CSV with these exact headers, in any order: `farm_code,collection_date,milk_litres,receipt_reference`. Dates use `YYYY-MM-DD`; litres must be positive and at most 1,000,000. The API accepts files up to 2 MB and 2,000 data rows. Empty lines are ignored. A row with a malformed date, quantity, or column count is retained as an exception where possible so the operator can see the source row that needs correction. Unsupported headers and empty files are rejected before a run is created.

The source file is hashed and duplicate imports in the same cooperative are rejected. Row number and submitted values remain attached to the run. A collection sheet is not sent to NVIDIA or another external model. It is stored as operational source data in the Terravanta database; the MVP does not retain the uploaded binary itself.

## Deterministic matching

Matching considers only milk lots with delivery unit `L`, delivery status `pending` or `accepted`, the same farm code, and the same local delivery date. Quantity comparison rounds both values to one decimal litre. A supplied receipt reference is compared case-insensitively. Results are explicitly classified as `matched`, `missing_reference`, `quantity_mismatch`, `reference_mismatch`, `ambiguous`, `missing_delivery`, `invalid_row`, or `not_shared`.

No probabilistic match is silently promoted. When several same-day deliveries could fit, the row remains ambiguous. A reference or quantity discrepancy can carry a candidate delivery link for a cooperative reviewer, but the automatic result remains an exception. A farmer without a current, non-expired `delivery_summary` grant is not matched; the response does not reveal farm name, delivery, lot, or their trace nodes.

## Human review loop

`CSV import → deterministic matching → exception queue → cooperative reviewer decision → audit trail and graph`.

The reviewer can confirm an exception only if a candidate delivery is linked and its farm's consent is still active. Confirmation records the reviewer, timestamp, decision and note; it does not change the farm's verified production or delivery record. A reviewer can instead record a follow-up note of at least three characters. That is an internal status only: the MVP does not yet message the farmer, create a field-officer task, correct a source record, or reconcile a cash payout. Those are deliberate next integrations after the review loop is validated.

Each review action is written to the audit log. A reviewer can download a result CSV containing the intake values, current consented match, review status and trace path; formula-like cells are neutralized to prevent spreadsheet execution. Revocation or expiry is checked again when a run is read and when a reviewer attempts confirmation. The run is organization-scoped on every request; only a cooperative administrator assigned to exactly one cooperative can operate the workflow.

## Trace graph

For a consented exact or candidate match the UI displays `Farm → production record → product lot → delivery → cooperative intake row`. A non-match displays `cooperative intake row → exception`. Graph details are assembled from current authorized records at read time rather than copied into a permanent snapshot. This preserves provenance and means consent revocation removes future farm and delivery detail from the cooperative response.

## Success measures before autopilot

Collect a baseline and pilot measurements for: minutes per collection sheet, exception percentage, percentage of rows with stable farm codes and receipt references, human review minutes per exception, correction rate, unresolved age, consent-related skips, duplicate imports and trace completeness. Compare against each cooperative's current process. Price a paid pilot by sheets or collection volume plus a setup/support component, then test renewal against measured workload reduction. Do not promise a savings percentage until a customer baseline supports it.

Move from a human-reviewed service to more autonomous processing only after real sheets show stable identifiers and acceptance rules, reviewers agree with the matching classifications, and a cooperative explicitly authorizes the destination workflow. Payout decisions, food-quality decisions and changes to farmer records continue to require accountable human approval.
