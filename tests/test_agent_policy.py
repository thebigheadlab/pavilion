"""Check agent admission with synthetic requests. Use no real private data."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent_policy.py"
SPEC = importlib.util.spec_from_file_location("agent_policy", SCRIPT)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)
SHA_A = "a" * 40
SHA_B = "b" * 40


def worker(**changes):
    request = {
        "agent_id": "actor-002", "provider": "codex", "model": "gpt-6.1-sol",
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
        decision = policy.admit(request, active or [])
        self.assertFalse(decision["admitted"])
        self.assertTrue(any(text in r for r in decision["reasons"]), decision["reasons"])

    def test_valid_worker_passes(self):
        self.assertTrue(policy.admit(worker(), [])["admitted"])

    def test_every_role_accepts_its_purposes(self):
        for role in policy.load_policy()["roles"]:
            for purpose in role["purposes"]:
                request = worker(provider=role["provider"], model=role["model"], purpose=purpose, optional_approved=True)
                if purpose == "review":
                    request.update(review(provider=role["provider"], model=role["model"], optional_approved=True))
                self.assertTrue(policy.admit(request, [])["admitted"], (role["model"], purpose))

    def test_wrong_provider_or_purpose(self):
        self.reject(worker(provider="claude"), "not allowed for this provider")
        self.reject(worker(purpose="docs"), "purpose is not in the role")

    def test_sonnet_is_not_a_reviewer(self):
        self.reject(review(model="claude-sonnet-5-5", provider="claude", author={"agent_id": "actor-001", "model": "gpt-6.1-sol"}), "purpose is not in the role")

    def test_optional_roles_need_approval(self):
        self.reject(worker(provider="codex", model="gpt-6-astra", purpose="unresolved_question"), "optional_approved")
        self.reject(worker(provider="claude", model="claude-fable-5-1", purpose="ui_ux"), "optional_approved")

    def test_cursor_allowlist(self):
        for model in ["composer-2", "claude-sonnet-5-5", "gemini-3", "auto", "grok-4.5"]:
            self.reject(worker(provider="cursor", model=model, purpose="code"), "allowlist")

    def test_cursor_untested_capability_and_warning(self):
        self.reject(worker(provider="cursor", model="grok-4.7", purpose="code", capabilities=["git"]), "not validated")
        ok = policy.admit(worker(provider="cursor", model="grok-4.7", purpose="code", capabilities=["write", "test"]), [])
        self.assertTrue(ok["admitted"])
        untested = policy.admit(worker(provider="cursor", model="grok-4.6", purpose="code"), [])
        self.assertIn("model is untested", untested["warnings"])

    def test_effort_rules(self):
        self.reject(worker(effort="high"), "raised effort needs evidence, scope, stop_condition")
        self.reject(worker(effort="high", evidence="e-001", scope="s-001"), "stop_condition")
        self.reject(worker(effort="turbo"), "effort is not valid")
        full = worker(effort="high", evidence="e-001", scope="s-001", stop_condition="c-001")
        self.assertTrue(policy.admit(full, [])["admitted"])

    def test_coordinator_effort_is_low(self):
        self.reject({"kind": "coordinator", "agent_id": "actor-009", "effort": "medium", "lane": "lane-001"}, "must be low")
        ok = policy.admit({"kind": "coordinator", "agent_id": "actor-009", "effort": "low", "lane": "lane-001"}, [])
        self.assertTrue(ok["admitted"])

    def test_lane_cap(self):
        self.assertTrue(policy.admit(worker(), ledger(2))["admitted"])
        self.reject(worker(), "lane cap", ledger(3))
        self.assertTrue(policy.admit(worker(), ledger(3, "lane-002"))["admitted"])

    def test_global_cap_counts_reserved_and_nested(self):
        full = []
        for lane in range(4):
            full += ledger(3 if lane < 3 else 1, f"lane-{lane + 10}")
        full[0]["state"] = "reserved"
        full[1]["parent"] = "actor-100"
        self.assertEqual(10, len(full))
        self.reject(worker(), "global cap", full)

    def test_route_order_and_paid_upgrade(self):
        self.reject(worker(route="codex-cloud"), "T3Code offline")
        self.assertTrue(policy.admit(worker(route="codex-cloud", t3code_online=False), [])["admitted"])
        self.reject(worker(route="other"), "route is not allowed")
        self.reject(worker(paid_upgrade=True), "paid upgrades")

    def test_reviewer_must_differ_from_author(self):
        self.assertTrue(policy.admit(review(), [])["admitted"])
        self.reject(review(author={"agent_id": "actor-002", "model": "claude-sonnet-5-5"}), "reviewer is the author")
        self.reject(review(author={"agent_id": "actor-001", "model": "gpt-6.1-sol"}), "model of the author")
        self.reject(review(author={}), "needs author")

    def test_review_evidence_binds_to_head(self):
        self.reject(review(head_sha=SHA_B), "stale")
        self.reject(review(evidence={"candidate_sha": "abc123"}, head_sha="abc123"), "40-hex")
        self.reject(review(evidence={}), "40-hex")
        self.reject(review(head_sha=SHA_A.upper()), "40-hex")


class CliTests(unittest.TestCase):
    def run_cli(self, request, active):
        with tempfile.TemporaryDirectory() as tmp:
            files = []
            for name, data in [("request.json", request), ("ledger.json", active)]:
                path = Path(tmp) / name
                path.write_text(json.dumps(data), encoding="utf-8")
                files.append(str(path))
            return policy.main(files)

    def test_exit_codes(self):
        self.assertEqual(0, self.run_cli(worker(), []))
        self.assertEqual(1, self.run_cli(worker(effort="max"), []))
        self.assertEqual(2, policy.main(["missing-request.json", "missing-ledger.json"]))


if __name__ == "__main__":
    unittest.main()
