import json
import asyncio
import logging
from typing import Any

import httpx

from core.config import settings
from core.models_registry import FREE_MODEL_IDS

_OPENROUTER_SEMAPHORE = asyncio.Semaphore(1)
logger = logging.getLogger(__name__)


def _candidate_models(model: str) -> list[str]:
    candidates = [model]
    if model in FREE_MODEL_IDS or model == "openrouter/free":
        candidates.extend(model_id for model_id in FREE_MODEL_IDS if model_id != model)
    return list(dict.fromkeys(candidates))


async def chat(model: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 1200) -> str:
    """Send a chat completion request to OpenRouter using httpx to avoid
    AsyncOpenAI/httpx incompatibilities at import time.
    """
    if not settings.openrouter_api_key:
        raise RuntimeError("OpenRouter API key is not set (openrouter_api_key).")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}", "Content-Type": "application/json"}
    base_payload: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with _OPENROUTER_SEMAPHORE, httpx.AsyncClient(timeout=60.0) as client:
        last_response: httpx.Response | None = None
        last_error: Exception | None = None
        for candidate_model in _candidate_models(model):
            payload = {**base_payload, "model": candidate_model}
            for attempt in range(2):
                try:
                    logger.info("OpenRouter request model=%s attempt=%s", candidate_model, attempt + 1)
                    resp = await client.post(url, headers=headers, json=payload)
                except Exception as exc:  # network/connection errors
                    last_error = exc
                    if attempt == 1:
                        break
                    await asyncio.sleep(2 ** attempt)
                    continue

                last_response = resp
                if resp.status_code == 429:
                    logger.warning("OpenRouter 429 model=%s; trying fallback if available", candidate_model)
                    retry_after = resp.headers.get("Retry-After")
                    wait_seconds = 5.0
                    if retry_after:
                        try:
                            wait_seconds = min(float(retry_after), 15.0)
                        except ValueError:
                            wait_seconds = 5.0
                    await asyncio.sleep(wait_seconds)
                    break

                if resp.status_code != 200:
                    body_text = resp.text
                    raise RuntimeError(f"OpenRouter returned {resp.status_code}: {body_text}")
                break
            else:
                continue

            if last_response is not None and last_response.status_code == 200:
                break
        else:
            if last_response is not None:
                raise RuntimeError(f"OpenRouter returned {last_response.status_code}: {last_response.text}")
            if last_error is not None:
                raise RuntimeError(f"OpenRouter request failed: {last_error}") from last_error
            raise RuntimeError("OpenRouter request failed without a response.")

    data = resp.json()
    # Expecting OpenAI-compatible response
    try:
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"Unexpected OpenRouter response format: {json.dumps(data)}") from exc
