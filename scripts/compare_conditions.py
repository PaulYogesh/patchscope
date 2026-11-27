import argparse
import difflib
import json
from pathlib import Path
from time import perf_counter

from openai import OpenAI

from patchscope.context import build_context_seed
from patchscope.llm import get_config
from patchscope.repair import apply_exact_edit, run_pytest, temporary_repo
from patchscope.tools import list_source_files, read_source_file


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "fixtures" / "mini_repo"

MAX_STEPS = 6
MAX_TOOL_CALLS = 8

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List source files in the repository.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a Python source file by relative path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]


def parse_object(text):
    """Parse raw JSON or a single fenced JSON block."""
    text = (text or "").strip()
    lines = text.splitlines()

    if (
        len(lines) >= 3
        and lines[0].strip() in {"```json", "```"}
        and lines[-1].strip() == "```"
    ):
        text = "\n".join(lines[1:-1])

    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None

    return value if isinstance(value, dict) else None


def validate_proposal(proposal, observed):
    """Ensure the edit concerns code actually supplied to the model."""
    if (
        not isinstance(proposal, dict)
        or set(proposal) != {"path", "old", "new"}
    ):
        raise ValueError("Invalid proposal structure")

    if not all(
        isinstance(proposal[key], str)
        for key in ("path", "old", "new")
    ):
        raise ValueError("Proposal fields must be strings")

    path = proposal["path"]
    old = proposal["old"]
    new = proposal["new"]

    if path not in observed:
        raise ValueError("Target file was not observed")

    if path not in list_source_files(REPO):
        raise ValueError("Target file is not approved")

    if (
        not old
        or old == new
        or len(old) > 4000
        or len(new) > 4000
    ):
        raise ValueError("Invalid edit fragment")

    if observed[path].count(old) != 1:
        raise ValueError("Edit does not match observed code uniquely")

    return proposal


def run(condition):
    config = get_config()

    client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=180,
        max_retries=0,
    )

    issue = (REPO / "issue.md").read_text(encoding="utf-8")
    started = perf_counter()

    seed = {
        "seed_text": "",
        "sources": [],
        "retrieval_ms": 0.0,
    }

    observed = {}
    seeded_paths = set()

    # Only the BM25 condition receives initial code context.
    if condition == "bm25":
        seed = build_context_seed(
            REPO,
            issue,
            top_k=1,
            max_chars_per_file=1600,
        )

        for source in seed["sources"]:
            path = source["path"]
            observed[path] = read_source_file(
                REPO, path, max_chars=1600
            )["content"]
            seeded_paths.add(path)

    system_prompt = (
        "You are investigating a Python repository bug. "
        "Use repository tools to inspect code. "
        "Do not infer source code from filenames. "
        "Stop investigating when you have enough evidence. "
        "If native tool calling is unavailable, output one "
        "JSON tool request with exactly 'name' and "
        "'arguments'. Do not modify source files."
    )

    user_prompt = (
        f"Bug report:\n{issue}\n\n"
        "Locate the faulty implementation by inspecting "
        "source files."
    )

    if seed["seed_text"]:
        user_prompt += (
            "\n\nRetrieved code context "
            "(may or may not be relevant):\n"
            + seed["seed_text"]
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    events = []
    prompt_tokens = 0
    completion_tokens = 0
    model_calls = 0
    tool_count = 0
    agent_final = None
    error = None

    def ask(conversation, *, tools=None, max_tokens=350):
        nonlocal prompt_tokens, completion_tokens, model_calls

        options = {
            "model": config["model"],
            "messages": conversation,
            "temperature": 0,
            "max_tokens": max_tokens,
        }

        if tools is not None:
            options["tools"] = tools
            options["tool_choice"] = "auto"

        response = client.chat.completions.create(**options)
        model_calls += 1

        if response.usage:
            prompt_tokens += response.usage.prompt_tokens
            completion_tokens += response.usage.completion_tokens

        return response.choices[0].message

    proposal = None
    repair_verified = None
    before_passed = None
    after_passed = None

    try:
        for step in range(1, MAX_STEPS + 1):
            assistant = ask(messages, tools=TOOLS)

            if assistant.tool_calls:
                messages.append(
                    assistant.model_dump(exclude_none=True)
                )

                actions = [
                    (
                        call.function.name,
                        parse_object(call.function.arguments),
                        call.id,
                        "native",
                    )
                    for call in assistant.tool_calls
                ]

            else:
                request = parse_object(assistant.content)

                if (
                    request is None
                    or set(request) != {"name", "arguments"}
                ):
                    agent_final = assistant.content
                    break

                messages.append({
                    "role": "assistant",
                    "content": assistant.content,
                })

                actions = [
                    (
                        request["name"],
                        request["arguments"],
                        None,
                        "text_fallback",
                    )
                ]

            for name, arguments, call_id, mode in actions:
                if tool_count >= MAX_TOOL_CALLS:
                    error = "tool_call_budget_exhausted"
                    break

                tool_count += 1
                repeated = False

                try:
                    if name == "list_files" and arguments == {}:
                        result = {
                            "files": list_source_files(REPO)
                        }

                    elif (
                        name == "read_file"
                        and isinstance(arguments, dict)
                        and set(arguments) == {"path"}
                        and isinstance(arguments["path"], str)
                    ):
                        path = arguments["path"]
                        repeated = path in observed

                        if repeated:
                            result = {
                                "path": path,
                                "already_provided": True,
                            }
                        else:
                            result = read_source_file(
                                REPO,
                                path,
                                max_chars=2000,
                            )
                            observed[path] = result["content"]
                    else:
                        raise ValueError("Unapproved tool request")

                except (ValueError, OSError) as exc:
                    result = {"error": str(exc)}

                events.append({
                    "step": step,
                    "name": name,
                    "arguments": arguments,
                    "mode": mode,
                    "repeated_read": repeated,
                    "result_error": "error" in result,
                })

                print(
                    f"Step {step}: {name}({arguments}) [{mode}]"
                    + (" repeated" if repeated else "")
                )

                if call_id is not None:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(result),
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Tool result:\n{json.dumps(result)}\n"
                            "Continue if needed."
                        ),
                    })

            if error:
                break

        # The same repair proposer is used in both conditions.
        if observed:
            observations = "\n\n".join(
                f"FILE: {path}\n{code}"
                for path, code in observed.items()
            )

            proposal_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a Python repair assistant. "
                        "Using ONLY the provided code, propose "
                        "one minimal repair. Return only JSON "
                        "with exactly three string fields: "
                        "path, old, new. The old fragment must "
                        "match supplied code exactly. "
                        "Do not edit tests."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Bug report:\n{issue}\n\n"
                        f"Observed code:\n{observations}\n\n"
                        "Propose the smallest justified repair."
                    ),
                },
            ]

            proposal = parse_object(
                ask(proposal_messages, max_tokens=450).content
            )

            validate_proposal(proposal, observed)

            original = (
                REPO / proposal["path"]
            ).read_text(encoding="utf-8")

            if original.count(proposal["old"]) != 1:
                raise ValueError("Source no longer matches edit")

            modified = original.replace(
                proposal["old"],
                proposal["new"],
                1,
            )

            diff = "".join(difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile="a/" + proposal["path"],
                tofile="b/" + proposal["path"],
            ))

            print("\n--- Review proposed change ---")
            print(diff)

            print(
                "Tests can execute model-generated code. "
                "Only approve this trusted toy fixture."
            )

            approved = input(
                "Type YES to test this edit in a temporary copy: "
            ).strip().upper() == "YES"

            if approved:
                with temporary_repo(REPO) as working:
                    before_passed = run_pytest(working)["passed"]

                    apply_exact_edit(
                        working,
                        proposal["path"],
                        proposal["old"],
                        proposal["new"],
                    )

                    after_passed = run_pytest(working)["passed"]

                repair_verified = (
                    before_passed is False
                    and after_passed is True
                )
            else:
                error = "testing_skipped_no_manual_approval"

        else:
            error = error or "no_source_code_observed"

    except (ValueError, OSError) as exc:
        error = f"{type(exc).__name__}: {exc}"

    record = {
        "task_id": "mini-average-001",
        "condition": condition,
        "model": config["model"],
        "seed_sources": seed["sources"],
        "seed_chars": len(seed["seed_text"]),
        "retrieval_ms": seed["retrieval_ms"],
        "seeded_paths": sorted(seeded_paths),
        "observed_paths": sorted(observed),
        "events": events,
        "tool_calls": tool_count,
        "repeated_reads": sum(
            event["repeated_read"] for event in events
        ),
        "model_calls": model_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "wall_seconds": round(
            perf_counter() - started, 3
        ),
        "agent_final": agent_final,
        "proposal": proposal,
        "before_passed": before_passed,
        "after_passed": after_passed,
        "repair_verified": repair_verified,
        "error": error,
    }

    output = (
        ROOT / "runs" / f"experiment_{condition}.json"
    )
    output.parent.mkdir(exist_ok=True)

    output.write_text(
        json.dumps(record, indent=2),
        encoding="utf-8",
    )

    summary_keys = (
        "condition",
        "model",
        "seed_sources",
        "tool_calls",
        "repeated_reads",
        "prompt_tokens",
        "completion_tokens",
        "wall_seconds",
        "repair_verified",
        "error",
    )

    print("\n--- Experiment summary ---")
    print(json.dumps({
        key: record[key] for key in summary_keys
    }, indent=2))
    print("Log:", output)

    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--condition",
        choices=["native", "bm25"],
        required=True,
    )

    args = parser.parse_args()
    run(args.condition)
