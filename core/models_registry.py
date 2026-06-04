from typing import TypedDict


class ModelRegistryItem(TypedDict):
    id: str
    name: str
    type: str


MODELS_REGISTRY: list[ModelRegistryItem] = [
    {"id": "openai/gpt-4o", "name": "GPT-4o", "type": "powerful"},
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "type": "fast"},
    {"id": "anthropic/claude-haiku-4-5", "name": "Claude Haiku", "type": "fast"},
    {"id": "anthropic/claude-sonnet-4-5", "name": "Claude Sonnet", "type": "powerful"},
]
