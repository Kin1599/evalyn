"""
Конфигурация библиотеки Check Core.

Вынесена отдельно, чтобы не зависеть от RuleEngine при импорте.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    # Песочница
    venv_name: str = "datascience-py311"
    venv_storage_path: str = "~/.sandbox_data/venvs"
    requirements: list[str] = field(default_factory=list)
    containers_path: str = "~/.sandbox_data/containers"
    sandbox_ttl: int = 600
    cell_timeout: int = 30

    # LLM
    llm_provider: str = "openrouter"     # "openai", "openrouter", "ollama"
    llm_endpoint: Optional[str] = None   # для Ollama: http://localhost:11434
    llm_api_key: Optional[str] = None
    llm_model: str = "openai/gpt-4o"

    # Прочее
    stop_on_error: bool = False
    max_retries: int = 2