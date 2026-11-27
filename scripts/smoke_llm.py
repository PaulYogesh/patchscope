import json
from pathlib import Path

from patchscope.llm import chat


issue_path = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "mini_repo"
    / "issue.md"
)

issue = issue_path.read_text(encoding="utf-8")

messages = [
    {
        "role": "system",
        "content": (
            "You are a software debugging assistant. "
            "Do not invent repository contents. "
            "If you have not inspected the code, say so."
        ),
    },
    {
        "role": "user",
        "content": (
            f"Here is a bug report:\n{issue}\n\n"
            "What information would you inspect first "
            "to investigate this bug? Reply briefly."
        ),
    },
]

result = chat(messages)

print(json.dumps(result, indent=2))
