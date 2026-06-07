from typing import TypedDict


class ModelRegistryItem(TypedDict):
    id: str
    name: str
    type: str


MODELS_REGISTRY: list[ModelRegistryItem] = [
    {"id": "openrouter/free", "name": "OpenRouter Free Auto", "type": "free"},
    {"id": "openai/gpt-oss-20b:free", "name": "GPT OSS 20B Free", "type": "free"},
    {"id": "qwen/qwen3-coder:free", "name": "Qwen3 Coder Free", "type": "free"},
    {"id": "qwen/qwen3-8b:free", "name": "Qwen3 8B Free", "type": "free"},
    {"id": "nvidia/nemotron-nano-9b-v2:free", "name": "Nemotron Nano 9B Free", "type": "free"},
    {"id": "openai/gpt-4o", "name": "GPT-4o", "type": "powerful"},
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "type": "fast"},
    {"id": "anthropic/claude-haiku-4-5", "name": "Claude Haiku", "type": "fast"},
    {"id": "anthropic/claude-sonnet-4-5", "name": "Claude Sonnet", "type": "powerful"},
]


FREE_MODEL_IDS = [model["id"] for model in MODELS_REGISTRY if model["type"] == "free"]
