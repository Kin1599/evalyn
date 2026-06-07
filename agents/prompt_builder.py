from typing import Any


def build_code_review_prompt(
    assignment_title: str,
    assignment_description: str,
    assignment_criteria: str | None,
    submission_text: str,
    sandbox_summary: str | None = None,
    system_prompt_override: str | None = None,
) -> list[dict[str, Any]]:
    system_prompt = system_prompt_override or (
        "Ты — автоматический помощник-преподаватель, который проверяет код студента и помогает сформировать структуру фидбека. "
        "Ты не должен отвечать свободным текстом. Ответ должен быть строго в формате JSON. "
        "Если у тебя нет уверенности по какому-то пункту, оцени его как suggestion."
    )

    user_prompt = (
        f"Название задания: {assignment_title}\n"
        f"Описание: {assignment_description}\n"
        f"Критерии: {assignment_criteria or 'не заданы'}\n\n"
        f"Работа студента:\n{submission_text}\n\n"
        "Проверь работу и верни только корректный JSON со следующими полями:\n"
        "- overall_score: число от 0 до 10\n"
        "- summary: краткий итог проверки\n"
        "- strengths: список сильных сторон\n"
        "- weaknesses: список слабых сторон или основных зон роста\n"
        "- items: массив замечаний с полями category, severity, title, description, location, suggestion\n\n"
        "Категории: code_style, logic, tests, docs, performance, security. "
        "Значения severity: error, warning, suggestion. "
        "Если есть результаты выполнения кода, учитывай их в оценке. "
    )

    if sandbox_summary:
        user_prompt += f"\nРезультаты выполнения:\n{sandbox_summary}\n\n"

    user_prompt += (
        "Верни только JSON-объект без дополнительных пояснений. "
        "Если структура не парсится, верни пустой массив items и объясни проблему в summary."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
