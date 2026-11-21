# Veterinary follow-up and outcome measurement

## What the workflow now records

Every health event can have an append-only follow-up history. An assigned farm veterinarian records the date and whether the contact was completed, missed, or the farmer could not be reached. Completed contacts require a veterinarian-assessed health outcome, case disposition, and farmer-reported treatment adherence status. The veterinarian can record care or treatment actually provided or reviewed. This is a clinical record field, not prescribing or dose calculation. A case remains open with a new due date when more review is needed. Closed and resolved cases leave the active queue but remain in the farm's case history.

Optional cost-to-date and milk farm-gate price are explicitly stored as farmer-reported values. These are not independently audited costs or prices. Follow-up records retain the authenticated veterinarian and are visible only to members of that farm through the API and PostgreSQL row-level policies.

## Recorded productivity context

For completed follow-ups, the API looks for animal-linked milk entries recorded in liters. It compares the seven calendar days before the health event with the seven calendar days after the follow-up. A comparison is shown only when each window has at least three distinct days with recorded milk and the post-follow-up window is complete. It reports the number of observed days, average liters per recorded day, the unadjusted difference, and—if the farmer supplied a milk price—a daily gross-value-rate difference.

This is a descriptive association, not proof that veterinary care or Terravanta caused a change. It does not adjust for lactation stage, feed, season, milking practice, other illnesses, sale rejection, or missing records. A missing result means there is not enough recorded data; it does not mean production was zero.

## What is required before claiming commercial return

The current fields are not a complete cost-effectiveness or return-on-investment measure. Before reporting ROI, a study needs a prespecified outcome period and comparison group or credible within-animal design, sufficiently complete daily production, and complete episode costs. Those costs should state whether they include veterinary fees, medicine, transport, labor, milk withdrawal, and repeat visits, with source and dates. A farmer-reported milk price and a partial case-cost-to-date figure cannot establish net return or causal impact.

## Suggested pilot measures

1. Follow-up completion: completed contacts divided by scheduled follow-ups, with the due-date window fixed before data collection.
2. Follow-up timeliness: days from scheduled date to completed contact; report missed and unreachable separately.
3. Clinical outcome distribution at follow-up: resolved, improving, unchanged, worsened, referred, or unable to assess; report deaths separately.
4. Recording quality: share of events with a scheduled date, actual attempt date, assigned veterinarian, disposition, and usable linked production observations.
5. Exploratory productivity: the displayed pre-event and post-follow-up animal milk windows, with coverage counts and no causal claim.
6. Economic feasibility: collect full episode cost and price data first; estimate return only under a reviewed analysis plan with a comparator and sensitivity analysis.

Use real records only with farm and veterinarian consent and the appropriate university or institutional ethics review. Exclude synthetic demo records from any study dataset. Do not use AI output as a clinical outcome or as a substitute for veterinarian assessment.

## API and deployment

- `GET /api/v1/farms/{farm_id}/health-events` returns farm-member-visible case and follow-up summaries.
- `GET /api/v1/health-events/{event_id}/follow-ups` returns the full follow-up history and milk-record context.
- `POST /api/v1/health-events/{event_id}/follow-ups` writes a new follow-up. It is veterinarian-only and append-only.
- Apply migration `0009_health_followups` through the existing release migration command (`alembic upgrade head`) before running the API build that uses these endpoints.
