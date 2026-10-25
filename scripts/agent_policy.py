#!/usr/bin/env python3
"""Admit or reject an agent request under policy/agent-policy.json."""

import argparse
import json
from pathlib import Path
import re
import sys


POLICY = Path(__file__).resolve().parents[1] / "policy" / "agent-policy.json"
SHA = re.compile(r"[0-9a-f]{40}")


class InputError(ValueError):
    """The request, ledger, or evidence has the wrong shape."""


def norm(value, name):
    if not isinstance(value, str):
        raise InputError(name + " must be a string")
    return value.strip().lower()


def opt_norm(value, name):
    return None if value is None else norm(value, name)


def opt_dict(value, name):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InputError(name + " must be an object")
    return value


def load_policy(path=POLICY):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_role(policy, provider, model):
    for role in policy["roles"]:
        if norm(role["provider"], "role") == provider and norm(role["model"], "role") == model:
            return role
    return None


def check_route(policy, request, reasons):
    route = request.get("route", "t3code")
    if route not in policy["routes"]["order"]:
        reasons.append("route is not allowed")
    elif route == "codex-cloud" and request.get("t3code_online") is not False:
        reasons.append("codex-cloud needs T3Code offline")
    if request.get("paid_upgrade"):
        reasons.append("paid upgrades are not allowed")


def check_model(policy, request, reasons, warnings):
    provider = opt_norm(request.get("provider"), "provider")
    model = opt_norm(request.get("model"), "model")
    if provider == "cursor" and model not in [norm(m, "policy") for m in policy["cursor"]["allow"]]:
        reasons.append("cursor model is not on the allowlist")
        return
    role = find_role(policy, provider, model)
    if role is None:
        reasons.append("model is not allowed for this provider")
        return
    purpose = request.get("purpose")
    if purpose not in role["purposes"]:
        reasons.append("purpose is not in the role of this model")
    if role["optional"] and request.get("optional_approved") is not True:
        reasons.append("optional role needs optional_approved")
    if "validated" in role:
        caps = request.get("capabilities", [])
        if not isinstance(caps, list) or not all(isinstance(c, str) for c in caps):
            raise InputError("capabilities must be a list of strings")
        extra = [c for c in caps if c not in role["validated"]]
        if extra:
            reasons.append("capability is not validated for this model")
        if role.get("status") == "untested" or not role["validated"]:
            warnings.append("model is untested")


def check_effort(policy, request, reasons):
    rules = policy["effort"]
    coordinator = request.get("kind", "worker") == "coordinator"
    effort = request.get("effort", rules["coordinator"] if coordinator else rules["worker_default"])
    if not isinstance(effort, str) or effort not in rules["levels"]:
        reasons.append("effort is not valid")
    elif coordinator:
        if effort != rules["coordinator"]:
            reasons.append("coordinator effort must be low")
    elif rules["levels"].index(effort) > rules["levels"].index(rules["worker_default"]):
        missing = [f for f in rules["raised_requires"] if not request.get(f)]
        if missing:
            reasons.append("raised effort needs " + ", ".join(missing))


def check_caps(policy, request, ledger, reasons):
    # Nested children and reserved waits are ledger entries, so they count.
    caps = policy["caps"]
    if len(ledger) >= caps["global"]:
        reasons.append("global cap reached")
    if sum(1 for a in ledger if a.get("lane") == request["lane"]) >= caps["lane"]:
        reasons.append("lane cap reached")


def check_review(request, reasons):
    author = opt_dict(request.get("author"), "author")
    author_id = opt_norm(author.get("agent_id"), "author agent_id")
    author_model = opt_norm(author.get("model"), "author model")
    if not author_id or not author_model:
        reasons.append("review needs author agent_id and model")
    else:
        if author_id == norm(request["agent_id"], "agent_id"):
            reasons.append("reviewer is the author")
        if author_model == opt_norm(request.get("model"), "model"):
            reasons.append("reviewer uses the model of the author")
    sha = opt_dict(request.get("evidence"), "evidence").get("candidate_sha", "")
    head = request.get("head_sha", "")
    if not SHA.fullmatch(str(sha)) or not SHA.fullmatch(str(head)):
        reasons.append("evidence and head need a 40-hex commit SHA")
    elif sha != head:
        reasons.append("evidence is stale: SHA differs from head")


def check_identity(request, reasons):
    for field in ("agent_id", "lane"):
        value = request.get(field)
        if value is None or value == "":
            reasons.append("request needs " + field)
        elif not isinstance(value, str) or not value.strip():
            reasons.append(field + " must be a non-empty string")


def admit(request, ledger, policy=None):
    policy = policy or load_policy()
    if not isinstance(request, dict):
        raise InputError("request must be an object")
    if not isinstance(ledger, list) or not all(isinstance(a, dict) for a in ledger):
        raise InputError("ledger must be a list of objects")
    reasons, warnings = [], []
    check_identity(request, reasons)
    if reasons:
        return {"admitted": False, "reasons": reasons, "warnings": warnings}
    check_route(policy, request, reasons)
    check_effort(policy, request, reasons)
    check_caps(policy, request, ledger, reasons)
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
