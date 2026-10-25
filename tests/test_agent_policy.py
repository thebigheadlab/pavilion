"""Check agent admission with synthetic requests. Use no real private data."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent_policy.py"
SPEC = importlib.util.spec_from_file_location("agent_policy", SCRIPT)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)
SHA_A = "a" * 40
SHA_B = "b" * 40
ESC = {"evidence": "e-001", "scope": "s-001", "stop_condition": "c-001"}
PRIMARY, FALLBACK = "executor-primary", "executor-fallback"
# Synthetic routing: the fallback executor alone serves the two grok models.
ROUTING_DATA = {
    "version": 1,
    "executors": {
        PRIMARY: {"models": ["claude-sonnet-5-5", "gpt-6.1-sol", "gpt-6-luna", "claude-opus-5-5", "gpt-6-astra", "claude-fable-5-1"]},
        FALLBACK: {"models": ["grok-4.7", "Grok-4.6 "]},
    },
}


def admit(request, active=None):
    return policy.admit(request, [] if active is None else active, routing=ROUTING_DATA)


def executor_for(model):
    return FALLBACK if model.startswith("grok") else PRIMARY


def fallback(**changes):
    return worker(executor=FALLBACK, primary_available=False, **changes)


def worker(**changes):
    request = {
        "agent_id": "actor-002", "model": "gpt-6.1-sol",
        "purpose": "build", "effort": "medium", "lane": "lane-001",
    }
    request.update(changes)
    return request


def review(**changes):
    request = worker(
        purpose="review", author={"agent_id": "actor-001", "model": "claude-sonnet-5-5"},
        evidence={"candidate_sha": SHA_A}, head_sha=SHA_A,
    )
    request.update(changes)
    return request


def ledger(count, lane="lane-001"):
    return [{"agent_id": f"actor-{i + 100:03d}", "lane": lane, "state": "active"} for i in range(count)]


class AdmitTests(unittest.TestCase):
    def reject(self, request, text, active=None):
        decision = admit(request, active)
        self.assertFalse(decision["admitted"])
        self.assertTrue(any(text in r for r in decision["reasons"]), decision["reasons"])

    def test_valid_worker_passes(self):
        self.assertTrue(admit(worker())["admitted"])

    def test_every_role_accepts_its_purposes(self):
        for role in policy.load_policy()["roles"]:
            for purpose in role["purposes"]:
                request = worker(executor=executor_for(role["model"]), primary_available=False, model=role["model"], purpose=purpose, optional_approved=True)
                if purpose == "review":
                    request.update(review(executor=executor_for(role["model"]), primary_available=False, model=role["model"], optional_approved=True))
                self.assertTrue(admit(request)["admitted"], (role["model"], purpose))

    def test_unknown_model_or_wrong_purpose(self):
        self.reject(worker(model="model-x"), "not on the executor allowlist")
        self.reject(worker(purpose="docs"), "purpose is not in the role")

    def test_sonnet_is_not_a_reviewer(self):
        self.reject(review(model="claude-sonnet-5-5", author={"agent_id": "actor-001", "model": "gpt-6.1-sol"}), "purpose is not in the role")

    def test_optional_roles_need_approval(self):
        self.reject(worker(model="gpt-6-astra", purpose="unresolved_question"), "optional_approved")
        self.reject(worker(model="claude-fable-5-1", purpose="ui_ux"), "optional_approved")

    def test_executor_allowlist(self):
        for model in ["model-x", "gemini-3", "auto", "grok-4.5", "claude-sonnet-5-5"]:
            self.reject(fallback(model=model, purpose="code"), "allowlist")
        # A model on one executor allowlist is not admitted on the other.
        self.reject(worker(model="grok-4.7", purpose="code"), "allowlist")
        self.reject(fallback(model="gpt-6.1-sol", purpose="build"), "allowlist")
        self.reject(worker(model=None), "allowlist")

    def test_untested_capability_and_warning(self):
        self.reject(fallback(model="grok-4.7", purpose="code", capabilities=["git"]), "not validated")
        ok = admit(fallback(model="grok-4.7", purpose="code", capabilities=["write", "test"]))
        self.assertTrue(ok["admitted"])
        untested = admit(fallback(model="grok-4.6", purpose="code"))
        self.assertIn("model is untested", untested["warnings"])

    def test_effort_rules(self):
        self.reject(worker(effort="high"), "raised effort needs evidence, scope, stop_condition")
        self.reject(worker(effort="high", escalation={"evidence": "e-001", "scope": "s-001"}), "stop_condition")
        self.reject(worker(effort="turbo"), "effort is not valid")
        full = worker(effort="high", escalation=ESC)
        self.assertTrue(admit(full)["admitted"])

    def test_coordinator_effort_is_low(self):
        self.reject(worker(kind="coordinator", effort="medium"), "must be low")
        self.assertTrue(admit(worker(kind="coordinator", effort="low", purpose="implement", model="claude-sonnet-5-5"))["admitted"])

    def test_coordinator_passes_model_checks(self):
        low = {"kind": "coordinator", "effort": "low"}
        self.reject(worker(**low, model="auto", purpose="review"), "allowlist")
        self.reject(worker(**low, model="claude-sonnet-5-5", purpose="review"), "purpose is not in the role")

    def test_coordinator_reviewer_needs_review_checks(self):
        low = {"kind": "coordinator", "effort": "low"}
        self.reject(review(**low, head_sha=SHA_B), "stale")
        self.reject(review(**low, author={"agent_id": "actor-002", "model": "x"}), "reviewer is the author")
        self.reject(review(**low, author={"agent_id": "actor-001", "model": "gpt-6.1-sol"}), "model of the author")
        self.assertTrue(admit(review(**low))["admitted"])

    def test_ids_are_normalized(self):
        self.reject(review(author={"agent_id": "actor-001", "model": " GPT-6.1-SOL "}), "model of the author")
        self.reject(review(author={"agent_id": " ACTOR-002 ", "model": "x"}), "reviewer is the author")
        self.assertTrue(admit(worker(model=" GPT-6.1-Sol "))["admitted"])
        self.reject(fallback(model=" AUTO ", purpose="code"), "allowlist")
        self.assertTrue(admit(fallback(model=" Grok-4.7 ", purpose="code"))["admitted"])
        # The routing file entries are normalized in the same way.
        self.assertTrue(admit(fallback(model="grok-4.6", purpose="code"))["admitted"])

    def test_missing_agent_id_or_lane(self):
        for field in ("agent_id", "lane"):
            for value in (None, "", "  "):
                request = worker()
                request[field] = value
                self.reject(request, field)
            request = worker()
            del request[field]
            self.reject(request, field)
            self.reject(worker(**{field: 7}), field)

    def test_fallback_needs_exact_false_flag(self):
        for value in (None, "false", 0, "", [], "no", True):
            self.reject(worker(executor=FALLBACK, primary_available=value, model="grok-4.7", purpose="code"), "primary_available")
        self.reject(worker(executor=FALLBACK, model="grok-4.7", purpose="code"), "primary_available")
        self.assertTrue(admit(fallback(model="grok-4.7", purpose="code"))["admitted"])

    def test_optional_approved_must_be_true(self):
        for value in ("false", "true", 1, "yes", None):
            self.reject(worker(model="gpt-6-astra", purpose="unresolved_question", optional_approved=value), "optional_approved")

    def test_missing_worker_effort_is_medium(self):
        request = worker()
        del request["effort"]
        self.assertTrue(admit(request)["admitted"])

    def test_low_worker_effort_needs_no_evidence(self):
        self.assertTrue(admit(worker(effort="low"))["admitted"])
        self.reject(worker(effort="xhigh"), "raised effort needs")

    def test_bad_shapes_raise_input_error(self):
        bad = [
            ([], []), ("x", []), (worker(), {}), (worker(), "x"), (worker(), [1]),
            (worker(model=3), []), (worker(model=["a"]), []),
            (fallback(model="grok-4.7", purpose="code", capabilities="git"), []),
            (review(author="x"), []), (review(author=[]), []), (review(evidence="x"), []),
            (review(author={"agent_id": 1, "model": "m"}), []),
        ]
        for request, active in bad:
            with self.assertRaises(policy.InputError, msg=(request, active)):
                admit(request, active)

    def test_ledger_entries_need_identity(self):
        for entry in ({}, {"lane": "lane-001"}, {"agent_id": "actor-100"},
                      {"agent_id": "", "lane": "lane-001"}, {"agent_id": "actor-100", "lane": " "},
                      {"agent_id": 5, "lane": "lane-001"}, {"agent_id": "actor-100", "lane": 1},
                      {"agent_id": "actor-100", "lane": "lane-001", "state": ""},
                      {"agent_id": "actor-100", "lane": "lane-001", "state": 3}):
            with self.assertRaises(policy.InputError, msg=entry):
                admit(worker(), [entry])

    def test_escalation_fields_must_be_strings(self):
        for bad in (True, 1, ["x"], {"a": 1}, "  "):
            for field in ESC:
                self.reject(worker(effort="high", escalation=dict(ESC, **{field: bad})), "raised effort needs " + field)

    def test_escalation_must_be_object(self):
        for bad in ("x", ["x"], 1, True):
            with self.assertRaises(policy.InputError, msg=bad):
                admit(worker(effort="high", escalation=bad))

    def test_high_effort_review_is_admitted(self):
        for effort in ("high", "xhigh", "max"):
            decision = admit(review(effort=effort, escalation=ESC))
            self.assertTrue(decision["admitted"], decision["reasons"])
        self.reject(review(effort="high"), "raised effort needs")

    def test_sha_must_be_string(self):
        for bad in (12345, True, ["a"]):
            with self.assertRaises(policy.InputError, msg=bad):
                admit(review(head_sha=bad))
            with self.assertRaises(policy.InputError, msg=bad):
                admit(review(evidence={"candidate_sha": bad}))
        self.reject(review(head_sha=" " + SHA_A + " "), "40-hex")
        self.reject(review(evidence={"candidate_sha": SHA_A + "\n"}), "40-hex")

    def test_lane_cap(self):
        self.assertTrue(admit(worker(), ledger(2))["admitted"])
        self.reject(worker(), "lane cap", ledger(3))
        self.assertTrue(admit(worker(), ledger(3, "lane-002"))["admitted"])

    def test_global_cap_counts_reserved_and_nested(self):
        full = []
        for lane in range(4):
            full += ledger(3 if lane < 3 else 1, f"lane-{lane + 10}")
        full[0]["state"] = "reserved"
        full[1]["parent"] = "actor-100"
        self.assertEqual(10, len(full))
        self.reject(worker(), "global cap", full)

    def test_executor_order_and_paid_upgrade(self):
        self.reject(worker(executor=FALLBACK, model="grok-4.7", purpose="code"), "primary_available")
        self.assertTrue(admit(fallback(model="grok-4.7", purpose="code"))["admitted"])
        self.reject(worker(executor="executor-other"), "executor is not allowed")
        for bad in (["x"], 7, {"a": 1}, ""):
            self.reject(worker(executor=bad), "executor is not allowed")
        self.reject(worker(paid_upgrade=True), "paid upgrades")

    def test_reviewer_must_differ_from_author(self):
        self.assertTrue(admit(review())["admitted"])
        self.reject(review(author={"agent_id": "actor-002", "model": "claude-sonnet-5-5"}), "reviewer is the author")
        self.reject(review(author={"agent_id": "actor-001", "model": "gpt-6.1-sol"}), "model of the author")
        self.reject(review(author={}), "needs author")

    def test_review_evidence_binds_to_head(self):
        self.reject(review(head_sha=SHA_B), "stale")
        self.reject(review(evidence={"candidate_sha": "abc123"}, head_sha="abc123"), "40-hex")
        self.reject(review(evidence={}), "40-hex")
        self.reject(review(head_sha=SHA_A.upper()), "40-hex")


class RoutingValidationTests(unittest.TestCase):
    def test_supplied_routing_is_validated(self):
        for bad in ({}, {"version": 1, "executors": {}}, {"version": True, "executors": ROUTING_DATA["executors"]},
                    {"version": 1, "executors": {PRIMARY: {"models": ["x"]}}},
                    {"version": 1, "executors": {PRIMARY: {"models": []}, FALLBACK: {"models": ["x"]}}},
                    [], "x"):
            with self.assertRaises(policy.InputError, msg=bad):
                policy.admit(worker(), [], routing=bad)

    def test_version_must_be_int(self):
        for bad in (True, 1.0, "1"):
            data = dict(ROUTING_DATA, version=bad)
            with self.assertRaises(policy.InputError, msg=bad):
                policy.validate_routing(data, policy.load_policy())


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(policy.ROUTING_ENV, None)

    def write(self, name, data, raw=False):
        path = self.dir / name
        path.write_text(data if raw else json.dumps(data), encoding="utf-8")
        return str(path)

    def run_cli(self, request, active, *extra):
        files = [self.write("request.json", request), self.write("ledger.json", active)]
        return policy.main([*files, *extra])

    def test_exit_codes(self):
        routing = self.write("routing.json", ROUTING_DATA)
        self.assertEqual(0, self.run_cli(worker(), [], "--routing", routing))
        self.assertEqual(1, self.run_cli(worker(effort="max"), [], "--routing", routing))
        self.assertEqual(2, policy.main(["missing-request.json", "missing-ledger.json"]))
        self.assertEqual(2, self.run_cli([worker()], [], "--routing", routing))
        self.assertEqual(2, self.run_cli(worker(), {"a": 1}, "--routing", routing))
        self.assertEqual(2, self.run_cli(review(evidence="x"), [], "--routing", routing))

    def test_routing_from_environment(self):
        os.environ[policy.ROUTING_ENV] = self.write("routing.json", ROUTING_DATA)
        self.assertEqual(0, self.run_cli(worker(), []))
        self.assertEqual(1, self.run_cli(worker(model="model-x"), []))

    def test_cli_argument_beats_environment(self):
        os.environ[policy.ROUTING_ENV] = self.write("env.json", ROUTING_DATA)
        other = json.loads(json.dumps(ROUTING_DATA))
        other["executors"][PRIMARY]["models"] = ["model-x"]
        self.assertEqual(1, self.run_cli(worker(), [], "--routing", self.write("arg.json", other)))
        self.assertEqual(0, self.run_cli(worker(), []))

    def test_example_routing_is_the_default(self):
        example = policy.load_routing(policy.load_policy())
        self.assertEqual({PRIMARY, FALLBACK}, set(example["executors"]))
        # The example holds placeholders only, so real models fail closed.
        self.assertEqual(1, self.run_cli(worker(), []))
        decision = policy.admit(worker(), [])
        self.assertTrue(any("allowlist" in r for r in decision["reasons"]))
        self.assertEqual(1, self.run_cli(worker(model="model-placeholder-a"), []))

    def test_routing_file_must_be_small_regular_and_not_a_link(self):
        real = self.write("real.json", ROUTING_DATA)
        link = self.dir / "link.json"
        link.symlink_to(real)
        fifo = self.dir / "fifo.json"
        os.mkfifo(fifo)
        big = self.write("big.json", json.dumps(ROUTING_DATA) + " " * policy.MAX_ROUTING_BYTES, raw=True)
        for bad in (link, fifo, Path(big)):
            with self.assertRaises(policy.InputError) as ctx:
                policy.load_routing(policy.load_policy(), str(bad))
            self.assertNotIn(str(self.dir), str(ctx.exception))
            self.assertEqual(2, self.run_cli(worker(), [], "--routing", str(bad)))
        self.assertEqual(0, self.run_cli(worker(), [], "--routing", real))

    def test_missing_routing_file_is_an_input_error(self):
        self.assertEqual(2, self.run_cli(worker(), [], "--routing", str(self.dir / "absent.json")))
        os.environ[policy.ROUTING_ENV] = str(self.dir / "absent.json")
        self.assertEqual(2, self.run_cli(worker(), []))

    def bad_routings(self):
        good = ROUTING_DATA["executors"]
        yield "not json {"
        yield "[]"
        yield "[" * 3000 + "]" * 3000
        yield {"version": 2, "executors": good}
        yield {"version": 1}
        yield {"version": 1, "executors": good, "extra": 1}
        yield {"version": 1, "executors": {PRIMARY: good[PRIMARY]}}
        yield {"version": 1, "executors": {**good, "executor-third": good[PRIMARY]}}
        yield {"version": 1, "executors": {**good, PRIMARY: {"models": []}}}
        yield {"version": 1, "executors": {**good, PRIMARY: {"models": ["ok", 3]}}}
        yield {"version": 1, "executors": {**good, PRIMARY: {"models": ["ok", "  "]}}}
        yield {"version": 1, "executors": {**good, PRIMARY: {"models": "ok"}}}
        yield {"version": 1, "executors": {**good, PRIMARY: {"models": ["ok"], "deny": []}}}
        yield {"version": 1, "executors": {**good, PRIMARY: ["ok"]}}

    def test_bad_routing_schema_is_an_input_error(self):
        for data in self.bad_routings():
            path = self.write("bad.json", data, raw=isinstance(data, str))
            self.assertEqual(2, self.run_cli(worker(), [], "--routing", path), str(data)[:40])

    def test_routing_errors_do_not_echo_content_or_path(self):
        secret = "routing-sentinel-001"
        path = self.write(secret + ".json", {"version": 1, "executors": {PRIMARY: {"models": [secret, 3]}}})
        with mock.patch("sys.stderr") as err, mock.patch("sys.stdout") as out:
            code = self.run_cli(worker(), [], "--routing", path)
        self.assertEqual(2, code)
        shown = "".join(str(c) for c in err.write.call_args_list + out.write.call_args_list)
        self.assertNotIn(secret, shown)

    def test_validate_routing_raises_input_error(self):
        for data in self.bad_routings():
            if isinstance(data, str):
                continue
            with self.assertRaises(policy.InputError):
                policy.validate_routing(data, policy.load_policy())


if __name__ == "__main__":
    unittest.main()
