"""Starter runner for screening AI drafts against baseline results."""

import argparse
import json
from pathlib import Path

from assess import load_json


def check_draft(draft, results_by_account):
    """Return a list of flags. Return an empty list when checks pass."""
    # TODO: Return an unknown_account flag if no assessment result exists.
    # Otherwise flag status_mismatch and evidence_mismatch as applicable.
    # Require a non-empty list of evidence IDs for the same account.
   
    result = results_by_account.get(draft.get("account_id"))
    if result is None:
        return ["unknown_account"]

    flags = []
    if draft.get("status") != result["status"]:
        flags.append("status_mismatch")

    evidence_ids = draft.get("evidence_ids")
    expected = result["evidence_id"]
    if (
        not isinstance(evidence_ids, list)
        or len(evidence_ids) != 1
        or evidence_ids[0] != expected
    ):
        flags.append("evidence_mismatch")
    return flags
    # raise NotImplementedError("Implement check_draft in check_ai.py first.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", help="Baseline assessment output JSON")
    parser.add_argument("drafts", help="AI drafts JSON")
    parser.add_argument("--out", required=True, help="Path to the screening output")
    args = parser.parse_args()

    results = load_json(args.results)["results"]
    by_account = {item["account_id"]: item for item in results}
    drafts = load_json(args.drafts)
    try:
        checks = [
            {"account_id": draft.get("account_id"), "flags": check_draft(draft, by_account)}
            for draft in drafts
        ]
    except NotImplementedError as error:
        parser.exit(2, f"{error}\n")

    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    print(f"Screened {len(checks)} drafts. Review their claims against the sources.")


if __name__ == "__main__":
    main()
