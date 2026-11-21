"""Validate Terravanta's commercial state/action harness configuration."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "config" / "terravanta-commercial-harness.json"
ALLOWED_STATES = {
    "unvalidated",
    "buyer_problem_verified",
    "data_authorized",
    "baseline_measured",
    "retrospective_case_reconstructed",
    "counterparty_response_recorded",
    "priced_repeat_approved",
    "second_repeat_positive_margin",
    "repeatable_product",
}


def main() -> None:
    harness = json.loads(HARNESS_PATH.read_text(encoding="utf-8"))
    assert harness["schema_version"] == 1
    assert harness["state_scope"] == "repository_audit_not_live_telemetry"

    current = harness["current_state"]
    for count_key in (
        "real_cooperative_claims_reconstructed",
        "real_processor_responses_recorded",
        "documented_paid_repeats",
    ):
        assert isinstance(current[count_key], int) and current[count_key] >= 0, count_key
    assert current["commercial_stage"] == "unvalidated_manual_receivables_slice"
    assert not current["live_source_connectors"]

    states = harness["state_machine"]
    assert states[0] == "unvalidated" and states[-1] == "repeatable_product"
    assert len(states) == len(set(states)) and set(states) == ALLOWED_STATES

    objectives = harness["objectives"]
    objective_ids = [objective["id"] for objective in objectives]
    assert len(objective_ids) == len(set(objective_ids))
    for objective in objectives:
        for field in ("direction", "measure", "evidence_owner", "pass_rule"):
            assert objective.get(field), f"Objective {objective['id']} is missing {field}"

    assert harness["hard_constraints"]
    assert harness["action_rules"]
    for rule in harness["action_rules"]:
        assert rule.get("when") and rule.get("action")

    print(
        f"Commercial harness valid: {len(objectives)} objectives, "
        f"{len(states)} gated states, {len(harness['hard_constraints'])} hard constraints."
    )


if __name__ == "__main__":
    main()
