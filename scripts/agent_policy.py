#!/usr/bin/env python3
"""Admit or reject an agent request under policy/agent-policy.json."""

import argparse
import json
from pathlib import Path
import re
import sys


POLICY = Path(__file__).resolve().parents[1] / "policy" / "agent-policy.json"
SHA = re.compile(r"[0-9a-f]{40}")


def load_policy(path=POLICY):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_role(policy, provider, model):
    for role in policy["roles"]:
        if role["provider"] == provider and role["model"] == model:
            return role
    return None


def check_route(policy, request, reasons):
    route = request.get("route", "t3code")
    if route not in policy["routes"]["order"]:
        reasons.append("route is not allowed")
    elif route == "codex-cloud" and request.get("t3code_online", True):
        reasons.append("codex-cloud needs T3Code offline")
    if request.get("paid_upgrade"):
        reasons.append("paid upgrades are not allowed")


def check_model(policy, request, reasons, warnings):
    provider, model = request.get("provider"), request.get("model")
    if provider == "cursor" and model not in policy["cursor"]["allow"]:
        reasons.append("cursor model is not on the allowlist")
        return
    role = find_role(policy, provider, model)
    if role is None:
        reasons.append("model is not allowed for this provider")
        return
    purpose = request.get("purpose")
    if purpose not in role["purposes"]:
        reasons.append("purpose is not in the role of this model")
    if role["optional"] and not request.get("optional_approved"):
        reasons.append("optional role needs optional_approved")
    if "validated" in role:
        extra = [c for c in request.get("capabilities", []) if c not in role["validated"]]
        if extra:
            reasons.append("capability is not validated for this model")
        if role.get("status") == "untested" or not role["validated"]:
            warnings.append("model is untested")


def check_effort(policy, request, reasons):
    rules = policy["effort"]
    effort = request.get("effort")
    if effort not in rules["levels"]:
        reasons.append("effort is not valid")
    elif request.get("kind", "worker") == "coordinator":
        if effort != rules["coordinator"]:
            reasons.append("coordinator effort must be low")
    elif effort != rules["worker_default"]:
        missing = [f for f in rules["raised_requires"] if not request.get(f)]
        if missing:
            reasons.append("raised effort needs " + ", ".join(missing))


def check_caps(policy, request, ledger, reasons):
    # Nested children and reserved waits are ledger entries, so they count.
    caps = policy["caps"]
    if len(ledger) >= caps["global"]:
        reasons.append("global cap reached")
    if sum(1 for a in ledger if a.get("lane") == request.get("lane")) >= caps["lane"]:
        reasons.append("lane cap reached")


def check_review(request, reasons):
    author = request.get("author") or {}
    if not author.get("agent_id") or not author.get("model"):
        reasons.append("review needs author agent_id and model")
    else:
        if author["agent_id"] == request.get("agent_id"):
            reasons.append("reviewer is the author")
        if author["model"] == request.get("model"):
            reasons.append("reviewer uses the model of the author")
    sha = (request.get("evidence") or {}).get("candidate_sha", "")
    head = request.get("head_sha", "")
    if not SHA.fullmatch(str(sha)) or not SHA.fullmatch(str(head)):
        reasons.append("evidence and head need a 40-hex commit SHA")
    elif sha != head:
        reasons.append("evidence is stale: SHA differs from head")


def admit(request, ledger, policy=None):
    policy = policy or load_policy()
    reasons, warnings = [], []
    check_route(policy, request, reasons)
    check_effort(policy, request, reasons)
    check_caps(policy, request, ledger, reasons)
    if request.get("kind", "worker") != "coordinator":
        check_model(policy, request, reasons, warnings)
        if request.get("purpose") == "review":
            check_review(request, reasons)
    return {"admitted": not reasons, "reasons": reasons, "warnings": warnings}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help="JSON file with one request")
    parser.add_argument("ledger", help="JSON file with a list of active or reserved agents")
    parser.add_argument("--policy", default=str(POLICY))
    args = parser.parse_args(argv)
    try:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        ledger = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
        decision = admit(request, ledger, load_policy(args.policy))
    except (OSError, ValueError, KeyError, TypeError):
        print("agent_policy: input error", file=sys.stderr)
        return 2
    print(json.dumps(decision, indent=2))
    return 0 if decision["admitted"] else 1


if __name__ == "__main__":
    sys.exit(main())
