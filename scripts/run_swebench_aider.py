"""Export an Aider patch for the fixed source paths observed in a native run."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

from patchscope.swebench_aider import AIDER_VERSION, run_aider_pilot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-workspace", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--aider-bin", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    try:
        version = subprocess.check_output(
            [str(args.aider_bin.expanduser().resolve()), "--version"],
            text=True, timeout=30, stdin=subprocess.DEVNULL,
        ).strip()
        if version != f"aider {AIDER_VERSION}":
            raise ValueError(f"Expected aider {AIDER_VERSION}, got {version!r}")
        record, prediction = run_aider_pilot(
            args.baseline_workspace, args.workspace_root,
            aider=args.aider_bin, ollama_url=args.ollama_url,
        )
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    print(f"Aider status: {record['outcome']['status']}")
    print(f"Prediction: {prediction or 'NOT EXPORTED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
