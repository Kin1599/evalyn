"""
run_check.py — пример запуска проверки студенческой работы.
"""

import json
import sys
from pathlib import Path

# Добавляем пути к библиотекам
sys.path.insert(0, str(Path.home() / "projects" / "check-core"))
sys.path.insert(0, str(Path.home() / "projects" / "sandbox" / "src"))

from check_core import (
    Config,
    CheckRule,
    CheckBlock,
    InputSpec,
    ExpressionCheck,
    LLMCheck,
    ScriptCheck,
    Submission,
    RuleEngine,
)

def load_rule(json_path: str) -> CheckRule:
    """Загружает правило из JSON-файла."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    blocks = []
    for block_data in data["blocks"]:
        inputs = [
            InputSpec(
                alias=inp["alias"],
                type=inp["type"],
                search_strategy=inp.get("search_strategy", "auto"),
                constraints=inp.get("constraints"),
                search_scope=inp.get("search_scope", "all"),
            )
            for inp in block_data["inputs"]
        ]

        conditions = []
        for cond in block_data["conditions"]:
            if cond["type"] == "expression":
                conditions.append(ExpressionCheck(
                    expression=cond["expression"],
                    expected=cond.get("expected"),
                    tolerance=cond.get("tolerance", 0.0),
                    message=cond.get("message", ""),
                ))
            elif cond["type"] == "llm":
                conditions.append(LLMCheck(
                    prompt_template=cond["prompt_template"],
                    context_sources=cond.get("context_sources", []),
                    output_type=cond.get("output_type", "annotations"),
                ))
            elif cond["type"] == "script":
                conditions.append(ScriptCheck(
                    script=cond["script"],
                    generated=cond.get("generated", False),
                ))

        blocks.append(CheckBlock(
            id=block_data["id"],
            description=block_data["description"],
            inputs=inputs,
            conditions=conditions,
        ))

    return CheckRule(
        rule_id=data["rule_id"],
        blocks=blocks,
        stop_on_error=data.get("stop_on_error", False),
    )


def main():
    # 1. Загружаем правило
    rule = load_rule("test_check_1/test_rule.json")
    print(f"✓ Загружено правило: {rule.rule_id}")
    print(f"  Блоков: {len(rule.blocks)}")

    # 2. Готовим работу
    notebook_path = Path("test_check_1/student_work.ipynb")
    if not notebook_path.exists():
        # Создаём тестовый ноутбук, если его нет
        import nbformat as nbf
        nb = nbf.v4.new_notebook()
        cells = [
            nbf.v4.new_code_cell("import networkx as nx\nimport random"),
            nbf.v4.new_code_cell(
                "n = 500\np = 0.016\nG_er = nx.erdos_renyi_graph(n, p, seed=42)\n"
                "print(f'Создан граф с {G_er.number_of_nodes()} вершинами')"
            ),
            nbf.v4.new_code_cell(
                "avg_degree = sum(dict(G_er.degree()).values()) / n\n"
                "clustering = nx.average_clustering(G_er)\n"
                "metrics_er = {'avg_degree': avg_degree, 'clustering': clustering}\n"
                "print(f'Метрики: {metrics_er}')"
            ),
            nbf.v4.new_code_cell("a = 1/0  # ошибка для теста"),
        ]
        nb.cells = cells
        nbf.write(nb, notebook_path)
        print(f"✓ Создан тестовый ноутбук: {notebook_path}")

    submission = Submission(
        notebook_path=notebook_path,
        additional_files=[],  # дополнительных файлов нет
    )

    # 3. Конфигурация
    config = Config(
        venv_name="datascience-py311",
        venv_storage_path="~/.sandbox_data/venvs",
        containers_path="~/.sandbox_data/containers",
        requirements=['networkx>=3.0'],
        sandbox_ttl=600,
        cell_timeout=60,
        # LLM: используем Ollama локально (если нет — закомментируйте)
        llm_provider="ollama",
        llm_endpoint="http://localhost:11434",
        llm_model="gpt-oss:120b-cloud",
        # LLM: OpenRouter (если есть API-ключ)
        # llm_provider="openrouter",
        # llm_api_key="sk-or-v1-...",
        # llm_model="openai/gpt-4o-mini",
        stop_on_error=False,
    )

    # 4. Запуск проверки
    print("\n▶ Запуск проверки...")
    engine = RuleEngine()
    result = engine.run(rule, submission, config)

    # 5. Вывод результатов
    print(f"\n{'='*60}")
    print(f"РЕЗУЛЬТАТЫ ПРОВЕРКИ: {result.rule_id}")
    print(f"{'='*60}")

    if result.annotations:
        for ann in result.annotations:
            icon = {"error": "✗", "warning": "⚠", "positive": "✓", "info": "ℹ"}.get(ann.severity, "?")
            loc = f" [{ann.location}]" if ann.location else ""
            print(f"  {icon} {ann.severity.upper()}{loc}: {ann.message}")
    else:
        print("  ✓ Все проверки пройдены!")

    # 6. Вывод контекста (опционально)
    if result.context:
        print(f"\n{'─'*60}")
        print("КОНТЕКСТ ВЫПОЛНЕНИЯ:")
        print(f"  Ячеек выполнено: {len(result.context.cells)}")
        print(f"  Переменных: {len(result.context.globals)}")
        print(f"  Переменные: {list(result.context.globals.keys())[:10]}...")
        print(f"  Маппинг (переменная → ячейка):")
        for var, cell_idx in list(result.context.variable_cells.items())[:10]:
            print(f"    {var} → ячейка #{cell_idx}")

    # 7. Проверяем ошибки в ячейках
    if result.context:
        errors = [c for c in result.context.cells if c.error]
        if errors:
            print(f"\n{'─'*60}")
            print(f"ОШИБКИ В ЯЧЕЙКАХ СТУДЕНТА ({len(errors)}):")
            for c in errors:
                print(f"  Ячейка {c.cell_id}: {c.error.get('ename', '?')}: {c.error.get('evalue', '?')}")


if __name__ == "__main__":
    main()