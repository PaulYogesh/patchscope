import difflib
import hashlib
import json
from pathlib import Path

from openai import OpenAI

from patchscope.llm import get_config
from patchscope.tools import list_source_files, read_source_file


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "fixtures" / "mini_repo"
MAX_STEPS = 6

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List Python source files.",
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
            "description": "Read an allowed source file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]


def parse_json(content):
    """Accept plain JSON or one Markdown-fenced JSON block."""
    raw = (content or "").strip()
    lines = raw.splitlines()

    if (
        len(lines) >= 3
        and lines[0].strip() in {"```json", "```"}
        and lines[-1].strip() == "```"
    ):
        raw = "\n".join(lines[1:-1])

    return json.loads(raw)


def execute_tool(name, arguments):
    """Execute only approved read-only repository tools."""
    if name == "list_files" and arguments == {}:
        return {"files": list_source_files(REPO)}

    if name == "read_file":
        if (
            isinstance(arguments, dict)
            and set(arguments) == {"path"}
            and isinstance(arguments["path"], str)
        ):
            return read_source_file(
                REPO, arguments["path"], max_chars=2000
            )

    raise ValueError("Unapproved tool request")


def main():
    config = get_config()
    client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=180,
        max_retries=0,
    )

    issue = (REPO / "issue.md").read_text(encoding="utf-8")

    messages = [
        {
            "role": "system",
            "content": (
                "You are investigating a Python repository bug. "
                "Use tools to inspect source code. "
                "Do not guess code from filenames. "
                "You may output a JSON tool request with "
                "exactly 'name' and 'arguments' if native "
                "tool calling is unavailable. "
                "Stop investigating when you have enough evidence."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Bug report:\n{issue}\n\n"
                "Locate the faulty implementation by inspecting "
                "repository source files."
            ),
        },
    ]

    inspected = {}
    events = []
    prompt_tokens = 0
    completion_tokens = 0

    def record_usage(response):
        nonlocal prompt_tokens, completion_tokens
        if response.usage:
            prompt_tokens += response.usage.prompt_tokens
            completion_tokens += response.usage.completion_tokens

    print("--- Autonomous investigation ---")

    for step in range(1, MAX_STEPS + 1):
        response = client.chat.completions.create(
            model=config["model"],
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
            max_tokens=350,
        )
        record_usage(response)

        assistant = response.choices[0].message

        if assistant.tool_calls:
            messages.append(
                assistant.model_dump(exclude_none=True)
            )

            actions = [
                (
                    call.function.name,
                    json.loads(call.function.arguments or "{}"),
                    call.id,
                    "native",
                )
                for call in assistant.tool_calls
            ]
        else:
            try:
                request = parse_json(assistant.content)
            except (ValueError, TypeError):
                print("Agent ended investigation.")
                break

            if (
                not isinstance(request, dict)
                or set(request) != {"name", "arguments"}
            ):
                print("Agent returned a non-tool response.")
                break

            actions = [
                (
                    request["name"],
                    request["arguments"],
                    None,
                    "text_fallback",
                )
            ]
            messages.append({
                "role": "assistant",
                "content": assistant.content,
            })

        for name, arguments, call_id, mode in actions:
            repeated_read = (
                name == "read_file"
                and isinstance(arguments, dict)
                and isinstance(arguments.get("path"), str)
                and arguments["path"] in inspected
            )

            if repeated_read:
                result = {
                    "path": arguments["path"],
                    "already_read": True,
                    "message": (
                        "This file was already inspected. "
                        "Use the earlier observation, inspect "
                        "another file, or finish."
                    ),
                }
            else:
                result = execute_tool(name, arguments)

            events.append({
                "step": step,
                "tool": name,
                "arguments": arguments,
                "mode": mode,
                "repeated_read": repeated_read,
            })

            print(f"Step {step}: {name}({arguments}) [{mode}]")

            if name == "read_file" and not repeated_read:
                inspected[result["path"]] = result["content"]

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
                        "Continue if further evidence is needed."
                    ),
                })

    if not inspected:
        print("No files inspected. No patch can be proposed.")
        return

    print("\nFiles inspected:", list(inspected))

    # Only give the repair proposer code that the agent
    # actually chose to inspect.
    observations = "\n\n".join(
        f"FILE: {path}\n{content}"
        for path, content in inspected.items()
    )

    proposal_messages = [
        {
            "role": "system",
            "content": (
                "You are a Python repair assistant. "
                "Using ONLY the inspected code, propose "
                "one minimal repair. Return only JSON with "
                "exactly three string fields: path, old, new. "
                "The old text must match the source exactly. "
                "Do not modify tests or invent code."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Bug report:\n{issue}\n\n"
                f"Code inspected by the agent:\n{observations}\n\n"
                "Propose the smallest justified repair."
            ),
        },
    ]

    print("\n--- Model-generated repair proposal ---")

    response = client.chat.completions.create(
        model=config["model"],
        messages=proposal_messages,
        temperature=0,
        max_tokens=450,
    )
    record_usage(response)

    proposal = parse_json(
        response.choices[0].message.content
    )

    if (
        not isinstance(proposal, dict)
        or set(proposal) != {"path", "old", "new"}
        or not all(
            isinstance(proposal[k], str)
            for k in ("path", "old", "new")
        )
    ):
        raise ValueError("Invalid patch proposal format")

    path = proposal["path"]

    if path not in inspected:
        raise ValueError(
            "Agent proposed editing a file it never inspected"
        )

    if path not in list_source_files(REPO):
        raise ValueError("Unapproved edit target")

    old, new = proposal["old"], proposal["new"]
    source_path = REPO / path
    original = source_path.read_text(encoding="utf-8")

    if (
        not old or old == new
        or len(old) > 4000 or len(new) > 4000
        or original.count(old) != 1
    ):
        raise ValueError("Ambiguous or invalid edit")

    modified = original.replace(old, new, 1)

    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    ))

    record = {
        "task_id": "mini-average-001",
        "model": config["model"],
        "events": events,
        "inspected_files": list(inspected),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "source_sha256": hashlib.sha256(
            source_path.read_bytes()
        ).hexdigest(),
        "proposal": proposal,
    }

    output = ROOT / "runs" / "autonomous_proposal.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(proposal, indent=2))
    print("\n--- Proposed diff ---")
    print(diff)
    print("Total prompt tokens:", prompt_tokens)
    print("Total completion tokens:", completion_tokens)
    print("Proposal saved:", output)
    print("\nNo edits applied. No tests executed.")


if __name__ == "__main__":
    main()
