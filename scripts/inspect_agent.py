import json
from pathlib import Path

from openai import OpenAI

from patchscope.llm import get_config
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
            "description": "List permitted source files in the repository.",
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
            "description": (
                "Read the contents of a source file. "
                "The path must be relative to the repository."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative source file path",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]


def execute_tool(name, arguments):
    """Validate and execute one approved read-only tool."""

    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")

    if name == "list_files":
        if arguments != {}:
            raise ValueError("Invalid list_files arguments")

        return {"files": list_source_files(REPO)}

    if name == "read_file":
        if (
            set(arguments) != {"path"}
            or not isinstance(arguments["path"], str)
        ):
            raise ValueError("Invalid read_file arguments")

        return read_source_file(
            REPO,
            arguments["path"],
            max_chars=2000,
        )

    raise ValueError(f"Unknown tool: {name}")


def parse_text_tool_call(content):
    """Handle a narrowly validated JSON fallback."""

    try:
        request = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None

    if not isinstance(request, dict):
        return None

    if set(request) != {"name", "arguments"}:
        return None

    if request["name"] not in {"list_files", "read_file"}:
        return None

    # Actual argument validation happens in execute_tool.
    return request


def main():
    config = get_config()

    client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=180,
        max_retries=0,
    )

    issue = (REPO / "issue.md").read_text(
        encoding="utf-8"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a coding agent investigating a bug. "
                "Use repository tools to gather evidence. "
                "Inspect actual code before concluding. "
                "Do not assume a file's contents from its name. "
                "You may read multiple source files. "
                "Do not claim to have fixed the bug. "
                "If native tool calling fails, you may output "
                "a single JSON tool request with exactly "
                "'name' and 'arguments' fields."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Investigate this bug:\n\n{issue}\n\n"
                "Find the likely faulty implementation. "
                "Explain your conclusion using source-code evidence."
            ),
        },
    ]

    prompt_tokens = 0
    completion_tokens = 0
    tool_count = 0
    inspected_files = []

    for step in range(1, MAX_STEPS + 1):
        print(f"\n--- Agent step {step} ---")

        response = client.chat.completions.create(
            model=config["model"],
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
            max_tokens=400,
        )

        if response.usage:
            prompt_tokens += response.usage.prompt_tokens
            completion_tokens += response.usage.completion_tokens

        assistant = response.choices[0].message

        # Standard structured tool calls.
        if assistant.tool_calls:
            messages.append(
                assistant.model_dump(exclude_none=True)
            )

            for call in assistant.tool_calls:
                if tool_count >= MAX_TOOL_CALLS:
                    print("Tool-call limit reached")
                    return

                name = call.function.name
                arguments = json.loads(
                    call.function.arguments or "{}"
                )

                result = execute_tool(name, arguments)
                tool_count += 1

                print(f"Native tool: {name}({arguments})")
                print("Result:", json.dumps(result))

                if name == "read_file":
                    inspected_files.append(arguments["path"])

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result),
                })

            continue

        # Validated text fallback for local models.
        request = parse_text_tool_call(assistant.content)

        if request is not None:
            if tool_count >= MAX_TOOL_CALLS:
                print("Tool-call limit reached")
                return

            name = request["name"]
            arguments = request["arguments"]

            result = execute_tool(name, arguments)
            tool_count += 1

            print(f"Fallback tool: {name}({arguments})")
            print("Result:", json.dumps(result))

            if name == "read_file":
                inspected_files.append(arguments["path"])

            messages.append({
                "role": "assistant",
                "content": assistant.content,
            })

            messages.append({
                "role": "user",
                "content": (
                    f"Tool result for {name}:\n"
                    f"{json.dumps(result)}\n\n"
                    "Continue investigating if necessary. "
                    "Base conclusions only on inspected code."
                ),
            })

            continue

        # The model has produced a final answer.
        print("\nAgent conclusion:")
        print(assistant.content or "(empty response)")
        break

    else:
        print("\nInvestigation budget exhausted.")

        messages.append({
            "role": "user",
            "content": (
                "Your investigation budget is exhausted. "
      		"Do not request tools. Give a concise diagnosis "
        	"in at most 100 words. Identify the faulty file, "
        	"exact expression, explanation, and proposed correction. "
        	"Use only evidence from inspected code. "
        	"Do not claim you applied a patch."
            ),
        })

        final = client.chat.completions.create(
            model=config["model"],
            messages=messages,
            temperature=0,
            max_tokens=500,
        )

        if final.usage:
            prompt_tokens += final.usage.prompt_tokens
            completion_tokens += final.usage.completion_tokens

        print("\nAgent conclusion (budget exhausted):")
        print(
            final.choices[0].message.content
            or "(empty response)"
        )

    print("\n--- Run summary ---")
    print("Model:", config["model"])
    print("Tool executions:", tool_count)
    print("Files inspected:", inspected_files)
    print("Prompt tokens:", prompt_tokens)
    print("Completion tokens:", completion_tokens)


if __name__ == "__main__":
    main()
