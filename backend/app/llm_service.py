import json
import os
from json import JSONDecodeError
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


def build_deepseek_messages(agent_name: str, user_prompt: str) -> list[dict[str, str]]:
    """Build model messages with a minimal system instruction and user prompt."""
    cleaned_prompt = user_prompt.strip()
    if not cleaned_prompt:
        raise ValueError("User prompt must not be empty.")

    system_prompt = (
        "You are an assistant inside an agent platform. "
        f"Current agent name: {agent_name}. "
        "Answer clearly and helpfully in markdown."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": cleaned_prompt},
    ]


def parse_deepseek_response(payload: dict[str, Any]) -> str:
    """Parse DeepSeek chat completion response and return assistant content."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) == 0:
        raise ValueError("DeepSeek response does not contain choices.")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("DeepSeek choice entry format is invalid.")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("DeepSeek response does not contain message payload.")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("DeepSeek response message content is empty.")

    return content.strip()


def invoke_deepseek_chat(agent_name: str, user_prompt: str) -> str:
    """Call DeepSeek chat completion API and return assistant text."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY is not set.")

    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
    timeout_seconds = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60"))

    payload = {
        "model": model,
        "messages": build_deepseek_messages(agent_name=agent_name, user_prompt=user_prompt),
        "temperature": 0.7,
    }
    request_body = json.dumps(payload).encode("utf-8")
    request = Request(
        url=f"{base_url}/chat/completions",
        data=request_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek HTTP error {exc.code}: {error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"DeepSeek network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("DeepSeek request timed out.") from exc

    try:
        response_payload = json.loads(raw_body)
    except JSONDecodeError as exc:
        raise RuntimeError("DeepSeek response is not valid JSON.") from exc

    return parse_deepseek_response(response_payload)


def stream_deepseek_chat(agent_name: str, user_prompt: str) -> Iterator[str]:
    """Call DeepSeek streaming API and yield incremental content chunks."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY is not set.")

    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
    timeout_seconds = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60"))

    payload = {
        "model": model,
        "messages": build_deepseek_messages(agent_name=agent_name, user_prompt=user_prompt),
        "temperature": 0.7,
        "stream": True,
    }
    request_body = json.dumps(payload).encode("utf-8")
    request = Request(
        url=f"{base_url}/chat/completions",
        data=request_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue

                data_block = line[len("data:") :].strip()
                if data_block == "[DONE]":
                    break

                try:
                    payload_block = json.loads(data_block)
                except JSONDecodeError:
                    continue

                choices = payload_block.get("choices")
                if not isinstance(choices, list) or len(choices) == 0:
                    continue

                first_choice = choices[0]
                if not isinstance(first_choice, dict):
                    continue

                delta = first_choice.get("delta")
                if not isinstance(delta, dict):
                    continue

                content = delta.get("content")
                if isinstance(content, str) and content:
                    yield content
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek HTTP error {exc.code}: {error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"DeepSeek network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("DeepSeek request timed out.") from exc
