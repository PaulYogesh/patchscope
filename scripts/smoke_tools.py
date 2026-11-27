import json
from pathlib import Path

from openai import OpenAI

from patchscope.llm import get_config
from patchscope.retrieval import discover_files


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "fixtures" / "mini_repo"


def list_files():
    """List source files from the fixed test repository."""
    return [
        str(path.relative_to(REPO))
        for path in discover_files(REPO)
    ]


def is_valid_text_tool_request(content):
    """Accept only a precisely defined read-only request."""
    try:
        request = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return False

    return (
        isinstance(request, dict)
        and set(request) == {"name", "arguments"}
        and request["name"] == "list_files"
        and request["arguments"] == {}
    )


def main():
    config = get_config()

    client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=180,
        max_retries=0,
    )

    tools = [{
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
    }]

    issue = (REPO / "issue.md").read_text(
        encoding="utf-8"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a coding agent. "
                "Use list_files before answering. "
                "Never claim to have read code you have not seen."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Bug report:\n{issue}\n\n"
                "Call list_files, then identify which source "
                "file you would inspect first."
            ),
        },
    ]

    response = client.chat.completions.create(
        model=config["model"],
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0,
        max_tokens=350,
    )

    message = response.choices[0].message
    calls = message.tool_calls or []

    if calls:
        # Standard structured API tool-call path.
        mode = "native"

        messages.append(
            message.model_dump(exclude_none=True)
        )

        for call in calls:
            arguments = json.loads(
                call.function.arguments or "{}"
            )

            if (
                call.function.name != "list_files"
                or arguments != {}
            ):
                raise ValueError("Unapproved tool request")

            result = {"files": list_files()}

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result),
            })

    elif is_valid_text_tool_request(message.content):
        # Development-only fallback for a read-only tool.
        mode = "validated_text_fallback"

        messages.append({
            "role": "assistant",
            "content": message.content,
        })

        result = {"files": list_files()}

        # No genuine tool_call_id exists. Supply the result
        # as a user message, not a fabricated tool response.
        messages.append({
            "role": "user",
            "content": (
                "The application executed the validated "
                "read-only list_files request.\n"
                f"Tool result: {json.dumps(result)}\n"
                "Identify the file to inspect first. "
                "Do not claim you have read its contents."
            ),
        })

    else:
        raise RuntimeError(
            "No valid tool request received. "
            f"Model output: {message.content!r}"
        )

    print("Tool-call mode:", mode)
    print("Executed: list_files")
    print("Tool result:", json.dumps(result))

    final = client.chat.completions.create(
        model=config["model"],
        messages=messages,
        temperature=0,
        max_tokens=250,
    )

    print("\nFinal agent response:")
    print(final.choices[0].message.content)

    if response.usage and final.usage:
        print("\nTotal reported tokens:")
        print(
            "Prompt:",
            response.usage.prompt_tokens
            + final.usage.prompt_tokens,
        )
        print(
            "Completion:",
            response.usage.completion_tokens
            + final.usage.completion_tokens,
        )


if __name__ == "__main__":
    main()
