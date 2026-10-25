#!/usr/bin/env python3
"""Admit or reject an agent request under policy/agent-policy.json."""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys


POLICY = Path(__file__).resolve().parents[1] / "policy" / "agent-policy.json"
EXAMPLE_ROUTING = Path(__file__).resolve().parents[1] / "policy" / "routing.example.json"
ROUTING_ENV = "PAVILION_ROUTING_FILE"
MAX_ROUTING_BYTES = 64 * 1024
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


def validate_routing(routing, policy):
    # Errors never include file content.
    if not isinstance(routing, dict) or set(routing) != {"version", "executors"} or type(routing["version"]) is not int or routing["version"] != 1:
        raise InputError("routing file has the wrong shape")
    executors = routing["executors"]
    names = set(policy["executors"].values())
    if not isinstance(executors, dict) or set(executors) != names:
        raise InputError("routing file has the wrong shape")
    for entry in executors.values():
        if not isinstance(entry, dict) or set(entry) != {"models"}:
            raise InputError("routing file has the wrong shape")
        models = entry["models"]
        if not isinstance(models, list) or not models or not all(nonempty_str(m) for m in models):
            raise InputError("routing file has the wrong shape")
    return {name: {norm(m, "routing") for m in entry["models"]} for name, entry in executors.items()}


def read_routing(path):
    # Reject links, special files, and large files before the read. Errors omit the path.
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ROUTING_BYTES:
            raise InputError("routing file is not accepted")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
    except OSError:
        raise InputError("routing file is not readable") from None
    with os.fdopen(fd, "rb") as handle:
        after = os.fstat(handle.fileno())
        if not stat.S_ISREG(after.st_mode) or after.st_size > MAX_ROUTING_BYTES:
            raise InputError("routing file is not accepted")
        data = handle.read(MAX_ROUTING_BYTES + 1)
    if len(data) > MAX_ROUTING_BYTES:
        raise InputError("routing file is not accepted")
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError:
        raise InputError("routing file is not valid") from None


def load_routing(policy, path=None):
    # Order: explicit path, then the environment variable, then the public example.
    path = path or os.environ.get(ROUTING_ENV) or EXAMPLE_ROUTING
    routing = read_routing(path)
    validate_routing(routing, policy)
    return routing


def find_role(policy, model):
    for role in policy["roles"]:
        if norm(role["model"], "role") == model:
            return role
    return None


def check_executor(policy, request, reasons):
    executor = request.get("executor", policy["executors"]["primary"])
    if executor not in policy["executors"].values():
        reasons.append("executor is not allowed")
    elif executor == policy["executors"]["fallback"] and request.get("primary_available") is not False:
        reasons.append("fallback executor needs primary_available set to false")
    if request.get("paid_upgrade"):
        reasons.append("paid upgrades are not allowed")


def check_model(policy, routing, request, reasons, warnings):
    model = opt_norm(request.get("model"), "model")
    executor = request.get("executor", policy["executors"]["primary"])
    if isinstance(executor, str) and executor in routing and model not in routing[executor]:
        reasons.append("model is not on the executor allowlist")
        return
    role = find_role(policy, model)
    if role is None:
        reasons.append("model has no role")
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


def nonempty_str(value):
    return isinstance(value, str) and bool(value.strip())


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
        escalation = opt_dict(request.get("escalation"), "escalation")
        missing = [f for f in rules["raised_requires"] if not nonempty_str(escalation.get(f))]
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
    for value, name in ((sha, "candidate_sha"), (head, "head_sha")):
        if not isinstance(value, str):
            raise InputError(name + " must be a string")
    if not SHA.fullmatch(sha) or not SHA.fullmatch(head):
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


def admit(request, ledger, policy=None, routing=None):
    policy = policy or load_policy()
    # Supplied routing gets the same schema check as a routing file.
    routing = validate_routing(load_routing(policy) if routing is None else routing, policy)
    if not isinstance(request, dict):
        raise InputError("request must be an object")
    if not isinstance(ledger, list) or not all(isinstance(a, dict) for a in ledger):
        raise InputError("ledger must be a list of objects")
    for entry in ledger:
        for field in ("agent_id", "lane"):
            if not nonempty_str(entry.get(field)):
                raise InputError("ledger entry needs a non-empty string " + field)
        if "state" in entry and not nonempty_str(entry["state"]):
            raise InputError("ledger state must be a non-empty string")
    reasons, warnings = [], []
    check_identity(request, reasons)
    if reasons:
        return {"admitted": False, "reasons": reasons, "warnings": warnings}
    check_executor(policy, request, reasons)
    check_effort(policy, request, reasons)
    check_caps(policy, request, ledger, reasons)
    check_model(policy, routing, request, reasons, warnings)
    if request.get("purpose") == "review":
        check_review(request, reasons)
    return {"admitted": not reasons, "reasons": reasons, "warnings": warnings}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help="JSON file with one request")
    parser.add_argument("ledger", help="JSON file with a list of active or reserved agents")
    parser.add_argument("--policy", default=str(POLICY))
    parser.add_argument("--routing", help="private routing file; default is the environment variable, then the example")
    args = parser.parse_args(argv)
    try:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        ledger = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
        policy = load_policy(args.policy)
        decision = admit(request, ledger, policy, load_routing(policy, args.routing))
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print("agent_policy: input error", file=sys.stderr)
        return 2
    print(json.dumps(decision, indent=2))
    return 0 if decision["admitted"] else 1


if __name__ == "__main__":
    sys.exit(main())
