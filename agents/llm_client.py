import json
import asyncio
from typing import Any

import httpx

from core.config import settings


async def chat(model: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 1200) -> str:
    """Send a chat completion request to OpenRouter using httpx to avoid
    AsyncOpenAI/httpx incompatibilities at import time.
    """
    if not settings.openrouter_api_key:
        raise RuntimeError("OpenRouter API key is not set (openrouter_api_key).")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        last_response: httpx.Response | None = None
        for attempt in range(3):
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except Exception as exc:  # network/connection errors
                if attempt == 2:
                    raise RuntimeError(f"OpenRouter request failed: {exc}") from exc
                await asyncio.sleep(2 ** attempt)
                continue

            last_response = resp
            if resp.status_code == 429 and attempt < 2:
                retry_after = resp.headers.get("Retry-After")
                wait_seconds = 15.0
                if retry_after:
                    try:
                        wait_seconds = float(retry_after)
                    except ValueError:
                        wait_seconds = 15.0
                await asyncio.sleep(wait_seconds)
                continue

            if resp.status_code != 200:
                body_text = resp.text
                raise RuntimeError(f"OpenRouter returned {resp.status_code}: {body_text}")
            break
        else:
            if last_response is not None:
                raise RuntimeError(f"OpenRouter returned {last_response.status_code}: {last_response.text}")
            raise RuntimeError("OpenRouter request failed without a response.")

    data = resp.json()
    # Expecting OpenAI-compatible response
    try:
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"Unexpected OpenRouter response format: {json.dumps(data)}") from exc
