"""Run a local, scripted demonstration of both PatchScope proposal contracts."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from patchscope.agent import run_episode
from patchscope.proposal_contract import LEGACY_CONTRACT, LINE_CONTRACT
from patchscope.swebench_dev import (
    external_manifest, prepare_dev_instance, save_episode_prediction,
)
from scripts.report_swebench_dev_pair import main as report_main


MODEL = "scripted-demo"
ISSUE = "demo__calculator-1"
SOURCE = "def subtract(x, y):\n    return x - y\n\ndef average(x, y):\n    return x - y\n"
REPLACEMENT = "    return (x + y) / 2\n"


class ScriptedClient:
    """Provide recorded-shaped responses at the same interface as the model SDK."""

    def __init__(self, proposal):
        self.proposal = proposal
        self.exploration_calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **request):
        calls = []
        if "tools" not in request:
            content = json.dumps(self.proposal)
        else:
            self.exploration_calls += 1
            content = "I inspected the implementations of subtract and average."
            if self.exploration_calls == 1:
                content = None
                calls = [SimpleNamespace(
                    id="demo-read", type="function", function=SimpleNamespace(
                        name="read_file_range",
                        arguments=json.dumps({"path": "calculator.py", "start_line": 1,
                                              "end_line": 5}),
                    ),
                )]
        message = SimpleNamespace(content=content, tool_calls=calls)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
        )


def demo(root):
    root.mkdir(parents=True)
    source = root / "source"
    source.mkdir()

    def git(*args):
        return subprocess.check_output(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args],
            cwd=source, text=True,
        ).strip()

    git("init", "--quiet")
    (source / "calculator.py").write_text(SOURCE, encoding="utf-8")
    git("add", "--", "calculator.py")
    git("-c", "user.name=PatchScope Demo", "-c", "user.email=demo@example.invalid",
        "commit", "--quiet", "-m", "Add calculator demo fixture")
    public = {
        "instance_id": ISSUE, "repo": "demo/calculator", "base_commit": git("rev-parse", "HEAD"),
        "problem_statement": "average(2, 4) should return 3. Preserve subtract.",
    }

    proposals = (
        ("baseline", LEGACY_CONTRACT,
         {"path": "calculator.py", "old": "    return x - y\n", "new": REPLACEMENT}),
        ("candidate", LINE_CONTRACT,
         {"path": "calculator.py", "start_line": 5, "end_line": 5, "replacement": REPLACEMENT}),
    )
    for arm, contract, proposal in proposals:
        arm_root = root / arm
        workspace = prepare_dev_instance(public, arm_root, clone_source=source)
        manifest, item = external_manifest(public, model=MODEL)
        manifest.update(experiment_id=f"offline_demo_{arm}", proposal_contract=contract)
        record = run_episode(
            item=item, manifest=manifest, root=workspace, client=ScriptedClient(proposal),
            model=MODEL, provenance={
                "benchmark": "offline-demo", "split": "demo", "base_commit": public["base_commit"],
                "public_issue_sha256":
                    hashlib.sha256(public["problem_statement"].encode()).hexdigest(),
            },
        )
        prediction = save_episode_prediction(workspace, record, model=MODEL)
        print(f"{arm} ({contract}) — {record['error'] or record['outcome']['status']}")
        if arm == "baseline" and (prediction or record["error"] !=
                                  "ProposalContractError: patch_old_not_unique_in_observed"):
            raise RuntimeError("The baseline did not reproduce the repeated-fragment rejection")
        if arm == "candidate" and prediction is None:
            raise RuntimeError(f"The candidate did not export a patch. Inspect {workspace}")
        if prediction is not None:
            print(f"  preflight passed. Exported {prediction}")

    instances = root / "instances.txt"
    instances.write_text(ISSUE + "\n", encoding="utf-8")
    print("\nScripted demonstration. Token usage is synthetic and there is no official grading.\n")
    return report_main(["--instances", str(instances),
                        "--baseline", str(root / "baseline"),
                        "--candidate", str(root / "candidate")])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="A new output directory")
    args = parser.parse_args(argv)
    try:
        return demo(args.output.resolve())
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
