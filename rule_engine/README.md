 чтобы добавить sandbox как зависимость
uv add path to sandbox

### OpenRouter
config = Config(
    llm_provider="openrouter",
    llm_api_key="sk-or-v1-...",
    llm_model="openai/gpt-4o",
)

### Ollama (локально)
config = Config(
    llm_provider="ollama",
    llm_endpoint="http://localhost:11434",
    llm_model="llama3.1",
)

### OpenAI
config = Config(
    llm_provider="openai",
    llm_api_key="sk-...",
    llm_model="gpt-4o",
)
