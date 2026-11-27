import os

from openai import OpenAI


def get_config():
    """Read model configuration from environment variables."""
    return {
        "model": os.getenv(
            "PATCHSCOPE_MODEL", "qwen2.5-coder:7b"
        ),
        "base_url": os.getenv(
            "PATCHSCOPE_BASE_URL",
            "http://localhost:11434/v1",
        ),
        "api_key": os.getenv(
            "PATCHSCOPE_API_KEY", "ollama"
        ),
    }


def chat(messages):
    """Send messages to a configurable LLM provider."""
    config = get_config()

    client = OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=120.0,
        max_retries=0,
    )

    response = client.chat.completions.create(
        model=config["model"],
        messages=messages,
        temperature=0,
        max_tokens=200,
    )

    usage = response.usage

    return {
        "model": config["model"],
        "content": response.choices[0].message.content,
        "prompt_tokens": (
            usage.prompt_tokens if usage else None
        ),
        "completion_tokens": (
            usage.completion_tokens if usage else None
        ),
    }
