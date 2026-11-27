import difflib
import hashlib
import json
from pathlib import Path

from openai import OpenAI

from patchscope.llm import get_config


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "fixtures" / "mini_repo"
SOURCE = REPO / "calculator.py"
ISSUE = REPO / "issue.md"


def main():
    config = get_config()

    client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=180,
        max_retries=0,
    )

    original = SOURCE.read_text(encoding="utf-8")
    issue = ISSUE.read_text(encoding="utf-8")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a Python bug-fixing assistant. "
                "Propose the smallest possible source-code edit. "
                "Return ONLY a JSON object with exactly three "
                "string fields: path, old, new. "
                "The old field must match an exact substring of "
                "the supplied source code. "
                "The new field must be its replacement. "
                "Do not use Markdown or code fences."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Bug report:\n{issue}\n\n"
                f"File: calculator.py\n"
                f"Source code:\n{original}\n\n"
                "Propose a minimal repair."
            ),
        },
    ]

    print("Requesting patch from:", config["model"])

    response = client.chat.completions.create(
        model=config["model"],
        messages=messages,
        temperature=0,
        max_tokens=450,
    )

    raw = (response.choices[0].message.content or "").strip()
    format_mode = "plain_json"

    # Accept one complete Markdown-fenced JSON block.
    lines = raw.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip() in {"```json", "```"}
        and lines[-1].strip() == "```"
    ):
        raw = "\n".join(lines[1:-1])
        format_mode = "fenced_json"

    try:
        proposal = json.loads(raw)
    except json.JSONDecodeError:
        print("Model did not return valid JSON:")
        print(raw)
        raise SystemExit(1)

    # Validate the proposed edit before using it.
    if not isinstance(proposal, dict):
        raise ValueError("Proposal must be a JSON object")

    if set(proposal) != {"path", "old", "new"}:
        raise ValueError("Unexpected proposal fields")

    if not all(
        isinstance(proposal[key], str)
        for key in ("path", "old", "new")
    ):
        raise ValueError("All proposal fields must be strings")

    if proposal["path"] != "calculator.py":
        raise ValueError("Unexpected target file")

    old = proposal["old"]
    new = proposal["new"]

    if not old or old == new:
        raise ValueError("Invalid or unchanged edit")

    if len(old) > 4000 or len(new) > 4000:
        raise ValueError("Edit exceeds size limit")

    if original.count(old) != 1:
        raise ValueError(
            "Proposed old fragment must match exactly once"
        )

    modified = original.replace(old, new, 1)

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile="a/calculator.py",
            tofile="b/calculator.py",
        )
    )

    usage = response.usage

    record = {
        "model": config["model"],
        "output_format": format_mode,
        "source_sha256": hashlib.sha256(
            original.encode("utf-8")
        ).hexdigest(),
        "prompt_tokens": (
            usage.prompt_tokens if usage else None
        ),
        "completion_tokens": (
            usage.completion_tokens if usage else None
        ),
        "proposal": proposal,
    }

    output = ROOT / "runs" / "day4_proposal.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(
        json.dumps(record, indent=2),
        encoding="utf-8",
    )

    print("\n--- Model-generated proposal ---")
    print(json.dumps(proposal, indent=2))

    print("\n--- Proposed code changes ---")
    print(diff)

    print("\nProposal saved to:", output)
    print("Prompt tokens:", record["prompt_tokens"])
    print("Completion tokens:", record["completion_tokens"])
    print("\nNo source files were modified.")
    print("No tests were executed.")


if __name__ == "__main__":
    main()
