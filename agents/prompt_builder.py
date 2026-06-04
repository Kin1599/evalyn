from typing import Any


def build_code_review_prompt(
    assignment_title: str,
    assignment_description: str,
    assignment_criteria: str | None,
    submission_text: str,
    sandbox_summary: str | None = None,
) -> list[dict[str, Any]]:
    system_prompt = (
        "Ты — автоматический помощник-преподаватель, который проверяет код студента и помогает сформировать структуру фидбека. "
        "Ты не должен отвечать свободным текстом. Ответ должен быть строго в формате JSON. "
        "Если у тебя нет уверенности по какому-то пункту, оцени его как suggestion."
    )

    user_prompt = (
        f"Assignment title: {assignment_title}\n"
        f"Description: {assignment_description}\n"
        f"Criteria: {assignment_criteria or 'not provided'}\n\n"
        f"Student submission:\n{submission_text}\n\n"
        "Please review the submission and return only valid JSON with the following fields:\n"
        "- overall_score: a number from 0 to 10\n"
        "- summary: a short evaluation summary\n"
        "- strengths: a list of strengths\n"
        "- items: an array of issue objects with category, severity, title, description, location, suggestion\n\n"
        "Categories: code_style, logic, tests, docs, performance, security. "
        "Severity values: error, warning, suggestion. "
        "If code execution results are available, incorporate them into your assessment. "
    )

    if sandbox_summary:
        user_prompt += f"\nExecution results:\n{sandbox_summary}\n\n"

    user_prompt += (
        "Return only the JSON object, without any additional explanation. "
        "If you cannot parse the structure, return an empty items array and explain the problem in summary."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
