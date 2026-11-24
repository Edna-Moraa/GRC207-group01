"""Request four fictional GRC drafts from a free hosted or local API."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from assess import load_json

ACCOUNTS = ("AC-02", "AC-03", "AC-04", "AC-11")
MODELS = {"gemini": "gemini-2.5-flash-lite", "ollama": "gemma3:1b"}
DRAFT_KEYS = ("account_id", "status", "summary", "proposed_next_action")
# gemma3:1b treats format "json" as any object. Require the drafts schema.
OLLAMA_FORMAT = {
    "type": "object",
    "properties": {
        "drafts": {
            "type": "array",
            "minItems": len(ACCOUNTS),
            "maxItems": len(ACCOUNTS),
            "items": {
                "type": "object",
                "properties": {
                    "account_id": {"type": "string"},
                    "status": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "summary": {"type": "string"},
                    "proposed_next_action": {"type": "string"},
                },
                "required": ["account_id", "status", "evidence_ids", "summary", "proposed_next_action"],
            },
        }
    },
    "required": ["drafts"],
}
GEMINI_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"


def make_prompt():
    snapshot = load_json("data/baseline.json")
    assessment = load_json("output/baseline_results.json")
    policy = load_json("data/policy.json")
    if (assessment["snapshot_id"], assessment["assessment_date"]) != (
        snapshot["snapshot_id"], snapshot["assessment_date"]
    ):
        raise ValueError("Generate the baseline results from data/baseline.json first.")

    evidence = {record["account_id"]: record for record in snapshot["records"]}
    results = {record["account_id"]: record for record in assessment["results"]}
    cases = []
    for account in ACCOUNTS:
        source = evidence[account]
        result = results[account]
        if result["evidence_id"] != source["evidence_id"]:
            raise ValueError(f"Evidence ID mismatch in baseline results for {account}.")
        cases.append({
            "account_id": account,
            "control_result": {key: result[key] for key in ("status", "reason")},
            "source_record": {
                key: source[key] for key in (
                    "evidence_id", "active", "privileged", "last_review_date", "review_status"
                )
            },
        })

    context = {
        "assessment_date": snapshot["assessment_date"],
        "policy": {key: policy[key] for key in (
            "control_id", "control_statement", "maximum_review_age_days",
            "required_review_status"
        )},
        "cases": cases,
    }
    template = Path("templates/ai-prompt.txt").read_text(encoding="utf-8").rstrip()
    return template + "\n\n" + json.dumps(context, indent=2)


def make_request(provider, model, prompt):
    headers = {"Content-Type": "application/json"}
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise ValueError("Set GEMINI_API_KEY privately as described in FREE-API-SETUP.txt.")
        headers["x-goog-api-key"] = key
        url = f"{GEMINI_ROOT}/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            },
        }
    else:
        url = OLLAMA_ENDPOINT
        payload = {
            "model": model,
            "prompt": prompt,
            "format": OLLAMA_FORMAT,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 1200},
        }
    return Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")


def read_drafts(provider, response):
    if provider == "gemini":
        candidate = response.get("candidates", [{}])[0]
        parts = candidate.get("content", {}).get("parts", [])
        generated = "".join(part.get("text", "") for part in parts if not part.get("thought"))
    else:
        generated = response.get("response", "")
    try:
        parsed = json.loads(generated)
    except (TypeError, ValueError) as error:
        raise ValueError("The model did not return usable JSON. Retry once or use the other API.") from error

    drafts = parsed.get("drafts") if isinstance(parsed, dict) else None
    if not isinstance(drafts, list) or len(drafts) != len(ACCOUNTS):
        raise ValueError("Expected a JSON object with a drafts array containing four entries.")
    text_keys = DRAFT_KEYS
    for draft in drafts:
        if (not isinstance(draft, dict)
                or any(not isinstance(draft.get(key), str) for key in text_keys)
                or not isinstance(draft.get("evidence_ids"), list)
                or any(not isinstance(item, str) for item in draft["evidence_ids"])):
            raise ValueError("Drafts must contain the expected text fields and an evidence_ids array.")
    return drafts


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=MODELS)
    parser.add_argument("--model", help="Use the supplied default or a confirmed free-tier/local model.")
    args = parser.parse_args()
    model = args.model or MODELS[args.provider]
    pattern = r"[A-Za-z0-9_.-]+" if args.provider == "gemini" else r"[A-Za-z0-9_.:-]+"
    if not re.fullmatch(pattern, model):
        parser.error("Enter a model ID using only the characters in the documented model name.")

    try:
        prompt = make_prompt()
        request = make_request(args.provider, model, prompt)
        with urlopen(request, timeout=180) as reply:
            response = json.load(reply)
            http_status = reply.status
        drafts = read_drafts(args.provider, response)
    except HTTPError as error:
        advice = {
            401: "Check the API key.",
            403: "Check the key and account access, or use the local API.",
            404: "Check the model ID or pull the Ollama model first.",
            429: "Wait for the free quota to reset or use the local API.",
        }.get(error.code, "Check FREE-API-SETUP.txt or retry once.")
        sys.exit(f"API returned HTTP {error.code}. {advice}")
    except (URLError, TimeoutError) as error:
        sys.exit(f"API connection failed. Check the network or local Ollama service ({type(error).__name__}).")
    except (OSError, KeyError, IndexError, ValueError) as error:
        sys.exit(f"Could not generate drafts: {error}")

    output = Path("output")
    output.mkdir(exist_ok=True)
    write_json(output / "ai_api_drafts.json", drafts)
    write_json(output / "ai_api_run.json", {
        "provider": args.provider,
        "requested_model": model,
        "response_model": response.get("modelVersion") or response.get("model") or model,
        "http_status": http_status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_accounts": list(ACCOUNTS),
        "draft_count": len(drafts),
    })
    print(f"Saved {len(drafts)} drafts from {args.provider} ({model}), HTTP {http_status}.")


if __name__ == "__main__":
    main()
