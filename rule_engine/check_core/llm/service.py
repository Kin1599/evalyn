"""
LLM Adapters — реализации LLMService для разных провайдеров.

Поддерживаются:
- OpenRouter (openrouter.ai)
- Ollama (локальный сервер)
- OpenAI (прямое подключение)
"""

import logging
import json
from abc import ABC, abstractmethod
from typing import Optional, Any

from ..exceptions import LLMServiceError

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Базовый класс
# ──────────────────────────────────────────────

class BaseLLMService(ABC):
    """Абстрактный сервис LLM."""
    
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
    
    @abstractmethod
    def ask(self, prompt: str, system: Optional[str] = None) -> str:
        """Отправить запрос и вернуть текстовый ответ."""
        pass


# ──────────────────────────────────────────────
#  OpenAI
# ──────────────────────────────────────────────

class OpenAIService(BaseLLMService):
    """Прямое подключение к OpenAI API."""
    
    def __init__(self, api_key: str, model: str = "gpt-4o", endpoint: Optional[str] = None):
        super().__init__(model)
        self.api_key = api_key
        self.endpoint = endpoint  # для Azure или прокси
    
    def ask(self, prompt: str, system: Optional[str] = None) -> str:
        try:
            import openai
        except ImportError:
            raise LLMServiceError("Пакет openai не установлен. Установите: pip install openai")
        
        client_kwargs = {"api_key": self.api_key}
        if self.endpoint:
            client_kwargs["base_url"] = self.endpoint
        
        client = openai.OpenAI(**client_kwargs)
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=2000,
            )
            content = response.choices[0].message.content
            if content is None:
                raise LLMServiceError("Пустой ответ от LLM")
            return content
        except Exception as e:
            raise LLMServiceError(f"Ошибка OpenAI: {e}")


# ──────────────────────────────────────────────
#  OpenRouter
# ──────────────────────────────────────────────

class OpenRouterService(BaseLLMService):
    """
    Подключение через OpenRouter API.
    
    OpenRouter предоставляет доступ к множеству моделей через единый API.
    Модель указывается в формате "провайдер/модель", например:
    - "openai/gpt-4o"
    - "anthropic/claude-3.5-sonnet"
    - "google/gemini-2.0-flash"
    
    Сайт: https://openrouter.ai
    """
    
    BASE_URL = "https://openrouter.ai/api/v1"
    
    def __init__(
        self, 
        api_key: str, 
        model: str = "openai/gpt-4o",
        app_name: str = "check-core",
        site_url: Optional[str] = None,
    ):
        """
        Args:
            api_key: API-ключ OpenRouter.
            model: идентификатор модели.
            app_name: название приложения (заголовок HTTP).
            site_url: URL сайта приложения (опционально).
        """
        super().__init__(model)
        self.api_key = api_key
        self.app_name = app_name
        self.site_url = site_url
    
    def ask(self, prompt: str, system: Optional[str] = None) -> str:
        try:
            import requests
        except ImportError:
            raise LLMServiceError("Пакет requests не установлен. Установите: pip install requests")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url or "https://github.com/check-core",
            "X-Title": self.app_name,
        }
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2000,
        }
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if content is None:
                raise LLMServiceError("Пустой ответ от OpenRouter")
            return content
        except requests.exceptions.RequestException as e:
            raise LLMServiceError(f"Ошибка OpenRouter: {e}")
        except (KeyError, IndexError) as e:
            raise LLMServiceError(f"Неожиданный формат ответа OpenRouter: {e}")


# ──────────────────────────────────────────────
#  Ollama
# ──────────────────────────────────────────────

class OllamaService(BaseLLMService):
    """
    Подключение к локальному серверу Ollama.
    
    Ollama запускает модели локально.
    Установка: https://ollama.ai
    Запуск: ollama serve
    Загрузка модели: ollama pull llama3.1
    
    По умолчанию подключается к http://localhost:11434
    """
    
    DEFAULT_BASE_URL = "http://localhost:11434"
    
    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = DEFAULT_BASE_URL,
        keep_alive: str = "5m",
    ):
        """
        Args:
            model: имя модели в Ollama (например "llama3.1", "mistral", "codellama").
            base_url: URL Ollama-сервера.
            keep_alive: как долго держать модель в памяти после запроса.
        """
        super().__init__(model)
        self.base_url = base_url.rstrip("/")
        self.keep_alive = keep_alive
    
    def ask(self, prompt: str, system: Optional[str] = None) -> str:
        try:
            import requests
        except ImportError:
            raise LLMServiceError("Пакет requests не установлен. Установите: pip install requests")
        
        # Формируем промпт с системным сообщением
        full_prompt = prompt
        if system:
            full_prompt = f"<|system|>\n{system}\n<|user|>\n{prompt}"
        
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.1,
                "num_predict": 2000,
            },
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120,  # локальные модели могут быть медленными
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("response", "")
            if not content:
                raise LLMServiceError("Пустой ответ от Ollama")
            return content
        except requests.exceptions.RequestException as e:
            raise LLMServiceError(f"Ошибка Ollama: {e}")
        except json.JSONDecodeError as e:
            raise LLMServiceError(f"Неожиданный формат ответа Ollama: {e}")
    
    def list_models(self) -> list[str]:
        """Возвращает список доступных моделей."""
        try:
            import requests
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.error("Ошибка получения списка моделей Ollama: %s", e)
            return []


# ──────────────────────────────────────────────
#  Фабрика
# ──────────────────────────────────────────────

def create_llm_service(config) -> BaseLLMService:
    """
    Создаёт подходящий LLM-сервис на основе конфигурации.
    
    В Config должны быть поля:
    - llm_provider: "openai", "openrouter", "ollama"
    - llm_endpoint: URL (для ollama — http://localhost:11434, для openrouter опционально)
    - llm_api_key: ключ API (для ollama не обязателен)
    - llm_model: название модели
    
    Returns:
        Экземпляр BaseLLMService.
    
    Raises:
        LLMServiceError: если провайдер не поддерживается.
    """
    provider = getattr(config, "llm_provider", "openai")
    model = config.llm_model
    endpoint = config.llm_endpoint
    api_key = config.llm_api_key or ""
    
    if provider == "openai":
        if not api_key:
            raise LLMServiceError("Не указан api_key для OpenAI")
        return OpenAIService(api_key=api_key, model=model, endpoint=endpoint or None)
    
    elif provider == "openrouter":
        if not api_key:
            raise LLMServiceError("Не указан api_key для OpenRouter")
        return OpenRouterService(api_key=api_key, model=model)
    
    elif provider == "ollama":
        base_url = endpoint or OllamaService.DEFAULT_BASE_URL
        return OllamaService(model=model, base_url=base_url)
    
    else:
        raise LLMServiceError(f"Неподдерживаемый LLM-провайдер: {provider}")