"""Starter runner for the GRC207 privileged access review lab."""

import argparse
from datetime import date
import json
from pathlib import Path

PASS = "Pass"
FAIL = "Fail"
INSUFFICIENT = "Insufficient Evidence"
NOT_APPLICABLE = "Not Applicable"
STATUSES = (PASS, FAIL, INSUFFICIENT, NOT_APPLICABLE)


def parse_date(value):
    """Return a calendar date for a valid ISO date string."""
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def evaluate_record(record, assessment_date, policy):
    """Return (status, reason) for a single account and control."""
    # TODO: Implement the ordered rules in the lab brief.
    active = record.get("active")
    privileged = record.get("privileged")

    if active is False or privileged is False:
        return NOT_APPLICABLE, "Account is explicitly inactive or not privileged."

    if active is not True or privileged is not True:
        return INSUFFICIENT, "Scope is unresolved because active or privileged is missing."

    review_date = parse_date(record.get("last_review_date"))
    review_status = record.get("review_status")
    if (
        review_date is None
        or review_date > assessment_date
        or review_status not in ("approved", "pending")
    ):
        return INSUFFICIENT, "Review date or review status is missing, invalid, or in the future."

    age_days = (assessment_date - review_date).days
    threshold = policy["maximum_review_age_days"]
    if review_status != policy["required_review_status"] or age_days > threshold:
        return FAIL, "Review is pending or older than the allowed review age."

    return PASS, "Approved review is within the allowed review age."


def load_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def assess_snapshot(snapshot, policy):
    assessment_date = parse_date(snapshot["assessment_date"])
    if assessment_date is None:
        raise ValueError("The snapshot assessment_date must be YYYY-MM-DD.")

    for field in ("account_id", "evidence_id"):
        identifiers = [record[field] for record in snapshot["records"]]
        if any(not isinstance(value, str) or not value.strip() for value in identifiers):
            raise ValueError(f"Snapshot has a blank or invalid {field}.")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"Snapshot has duplicate {field} values.")

    results = []
    for record in snapshot["records"]:
        status, reason = evaluate_record(record, assessment_date, policy)
        if status not in STATUSES or not isinstance(reason, str) or not reason.strip():
            raise ValueError("Each evaluation must return a valid status and a reason.")
        results.append({
            "control_id": policy["control_id"],
            "account_id": record["account_id"],
            "evidence_id": record["evidence_id"],
            "status": status,
            "reason": reason,
        })

    return {
        "snapshot_id": snapshot["snapshot_id"],
        "assessment_date": assessment_date.isoformat(),
        "counts": {status: sum(item["status"] == status for item in results)
                   for status in STATUSES},
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", help="Path to the input snapshot JSON")
    parser.add_argument("--policy", default="data/policy.json")
    parser.add_argument("--out", required=True, help="Path to the output results JSON")
    args = parser.parse_args()

    try:
        output = assess_snapshot(load_json(args.snapshot), load_json(args.policy))
    except (KeyError, NotImplementedError, ValueError) as error:
        parser.exit(2, f"{error}\n")

    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["counts"], indent=2))


if __name__ == "__main__":
    main()
