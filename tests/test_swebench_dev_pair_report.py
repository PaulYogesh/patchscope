import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.report_swebench_dev_pair import compare, grade_index, main


class PairedReportTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.baseline = self.root / "v08"
        self.candidate = self.root / "v09"
        self.grader = self.root / "grader"
        self.baseline.mkdir()
        self.candidate.mkdir()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def episode(self, root, issue, export=False, seed=3):
        patch = "example patch"
        self.write(root / issue / "episode.json", {
            "task_id": issue, "condition": "native", "budgets": {"max_steps": 10},
            "provenance": {"benchmark": "lite", "split": "dev", "base_commit": "abc",
                           "public_issue_sha256": "def", "generation": {"seed": seed}},
            "proposal": {"path": "example.py"} if export else None,
            "proposal_diff": patch if export else None,
            "usage": {"total_tokens": 25, "wall_seconds": 0.125},
            "outcome": {"status": "example", "repair_verified": True},
            "error": None if export else "ProposalContractError: patch_old_not_unique_in_observed",
        })
        if export:
            self.write(root / issue / "prediction.jsonl", {
                "instance_id": issue, "model_patch": patch,
            })

    def test_accounting_uses_official_grade_and_counts_failed_runs(self):
        self.episode(self.baseline, "gain")
        self.episode(self.candidate, "gain", export=True)
        self.episode(self.baseline, "ambiguous", export=True)
        self.episode(self.candidate, "ambiguous", export=True)
        self.write(self.grader / "gain" / "report.json", {
            "gain": {"patch_successfully_applied": True, "resolved": True},
        })
        report = compare(["gain", "ambiguous", "missing"],
                         (self.baseline, {"ambiguous": "resolved"}, None, None),
                         (self.candidate, {"gain": "resolved", "ambiguous": "ambiguous"},
                          self.grader, {"gain", "ambiguous"}))
        self.assertEqual(report["paired_resolution"], {"gain": 1, "unavailable": 2})
        self.assertEqual(report["matched_metadata"], 2)
        self.assertEqual(report["candidate"]["applied"], 1)
        self.assertEqual(report["baseline"]["stages"], {"no_proposal": 1, "exported": 1, "missing": 1})
        self.assertEqual(report["baseline"]["usage"]["tokens"]["total"], 50)
        self.assertEqual(report["baseline"]["generation_failures"],
                         {"patch_old_not_unique_in_observed": 1})

    def test_seed_mismatch_prevents_paired_claim(self):
        self.episode(self.baseline, "issue")
        self.episode(self.candidate, "issue", export=True, seed=4)
        report = compare(["issue"], (self.baseline, {}, None, None),
                         (self.candidate, {"issue": "resolved"}, None, None))
        self.assertEqual(report["paired_resolution"], {"unavailable": 1})
        self.assertEqual(report["issues"][0]["metadata_differences"], ["generation"])

    def test_declared_recovery_ablation_still_requires_matching_seed(self):
        for issue, seed in (("matching", 3), ("different-seed", 4), ("both-off", 3)):
            self.episode(self.baseline, issue)
            self.episode(self.candidate, issue, export=True, seed=seed)
            if issue != "both-off":
                path = self.candidate / issue / "episode.json"
                episode = json.loads(path.read_text())
                episode["tool_call_recovery"] = True
                episode["trajectory"] = [{"kind": "ranged_read_feedback"},
                                         {"kind": "ranged_read_recovered"}]
                self.write(path, episode)
        arms = ((self.baseline, {}, None, None), (self.candidate, {}, None, None))
        issues = ["matching", "different-seed", "both-off"]
        ordinary = compare(issues, *arms)
        self.assertFalse(ordinary["issues"][0]["matched_metadata"])
        deliberate = compare(issues, *arms, tool_call_recovery_ablation=True)
        self.assertEqual(deliberate["matched_metadata"], 1)
        self.assertEqual(deliberate["issues"][1]["metadata_differences"], ["generation"])
        self.assertEqual(deliberate["issues"][2]["metadata_differences"], ["tool_call_recovery"])
        self.assertEqual(deliberate["candidate"]["navigation"], {
            "ranged_read_feedback_episodes": 2, "ranged_read_recovered_episodes": 2,
        })

    def test_rejects_mismatched_prediction(self):
        self.episode(self.baseline, "issue", export=True)
        self.write(self.baseline / "issue" / "prediction.jsonl", {"instance_id": "different"})
        with self.assertRaisesRegex(ValueError, "prediction does not match"):
            compare(["issue"], (self.baseline, {}, None, None),
                    (self.candidate, {}, None, None))

    def test_grading_failure_takes_precedence_over_unresolved(self):
        self.assertEqual(grade_index({"unresolved_ids": ["issue"], "error_ids": ["issue"],
                                     "ambiguous_failure_ids": ["issue"]}),
                         {"issue": "ambiguous"})

    def test_rejects_conflicting_resolved_grade(self):
        with self.assertRaisesRegex(ValueError, "Conflicting official result"):
            grade_index({"resolved_ids": ["issue"], "error_ids": ["issue"]})

    def test_plain_report_rejects_stale_grader_patch(self):
        self.episode(self.candidate, "issue", export=True)
        path = self.grader / "issue" / "report.json"
        self.write(path, {"issue": {"patch_successfully_applied": True, "resolved": True}})
        (path.parent / "patch.diff").write_text("diff from a different run\n")
        with self.assertRaisesRegex(ValueError, "grader patch differs"):
            compare(["issue"], (self.baseline, {}, None, None),
                    (self.candidate, {"issue": "resolved"}, self.grader, {"issue"}))

    def test_cli_rejects_duplicate_assigned_issues(self):
        instances = self.root / "instances.txt"
        instances.write_text("duplicate\nduplicate\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as failure:
            main(["--instances", str(instances), "--baseline", str(self.baseline),
                  "--candidate", str(self.candidate)])
        self.assertEqual(failure.exception.code, 2)
