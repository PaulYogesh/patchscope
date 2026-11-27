"""Real Ollama tool-protocol smoke test; read-only, no generated code execution."""
from __future__ import annotations

import argparse
import json
import os

from patchscope.protocol import (
    TOOL_MODE_FALLBACK_ALLOWED, TOOL_MODE_NATIVE_REQUIRED, TOOLS,
    assistant_message, decode_message,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect", choices=["native", "native-or-fallback"], default="native")
    parser.add_argument("--model", default=os.environ.get("PATCHSCOPE_MODEL", "qwen3.5:9b"))
    args = parser.parse_args(argv)
    from openai import OpenAI
    from patchscope.llm import get_config
    settings = get_config()
    client = OpenAI(base_url=settings["base_url"], api_key=settings["api_key"],
                    timeout=120, max_retries=0)
    mode = TOOL_MODE_NATIVE_REQUIRED if args.expect == "native" else TOOL_MODE_FALLBACK_ALLOWED
    messages = [
        {"role": "system", "content": "You must use repository tools to answer. Never make up file content."},
        {"role": "user", "content": "List the available source files using list_files, then tell me whether calculator.py is available."},
    ]
    response = client.chat.completions.create(model=args.model, messages=messages, tools=TOOLS,
                                              tool_choice="auto", temperature=0, seed=1234, max_tokens=350)
    assistant = response.choices[0].message
    actions, final = decode_message(assistant, mode=mode)
    if len(actions) != 1 or actions[0].name != "list_files":
        raise RuntimeError(f"Expected exactly one list_files call, got {actions!r}; final={final!r}")
    messages.append(assistant_message(assistant))
    action = actions[0]
    content = json.dumps({"files": ["calculator.py", "billing.py"]})
    messages.append({"role": "tool", "tool_call_id": action.call_id, "content": content} if action.call_id
                    else {"role": "user", "content": "Tool result: " + content})
    followup = client.chat.completions.create(model=args.model, messages=messages,
                                               temperature=0, seed=1234, max_tokens=160)
    actual = action.mode
    print("Model:", args.model)
    print("Observed protocol:", actual)
    print("Follow-up:", followup.choices[0].message.content)
    print("Primary eligible:", actual == "native")
    for purpose, completion in (("call", response), ("follow_up", followup)):
        if completion.usage is None:
            raise RuntimeError(f"No token usage returned for {purpose}")
        print(purpose, "prompt", completion.usage.prompt_tokens,
              "completion", completion.usage.completion_tokens)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
