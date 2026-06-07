from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import nbformat

REPO_ROOT = Path(__file__).resolve().parent.parent
HW_CHECKER_PATH = REPO_ROOT / "hw_checker" / "rule_engine"
if str(HW_CHECKER_PATH) not in sys.path:
    sys.path.insert(0, str(HW_CHECKER_PATH))

from check_core import (  # type: ignore
    Annotation,
    CheckBlock,
    CheckCondition,
    CheckResult,
    CheckRule,
    Config,
    ExpressionCheck,
    GradingConfig,
    InputSpec,
    LLMCheck,
    RuleEngine,
    ScriptCheck,
    Submission,
)


@dataclass(slots=True)
class RuleEngineRunResult:
    check_result: CheckResult
    raw_rule: dict


def _annotation_to_review_item(annotation: Annotation) -> dict[str, str | None]:
    category = "rule_engine"
    if annotation.location:
        category = "code"
    severity = annotation.severity if annotation.severity in {"error", "warning", "suggestion"} else "suggestion"
    return {
        "category": category,
        "severity": severity,
        "title": annotation.message[:200],
        "description": annotation.message,
        "location": annotation.location,
        "suggestion": None,
    }


def _load_rule_from_dict(payload: dict) -> CheckRule:
    blocks: list[CheckBlock] = []
    for block_data in payload.get("blocks", []):
        inputs = [
            InputSpec(
                alias=spec["alias"],
                type=spec["type"],
                search_strategy=spec.get("search_strategy", "auto"),
                strict_name=spec.get("strict_name", False),
                expected_name=spec.get("expected_name"),
                constraints=spec.get("constraints"),
                search_scope=spec.get("search_scope", "all"),
            )
            for spec in block_data.get("inputs", [])
        ]
        conditions: list[CheckCondition] = []
        for condition_data in block_data.get("conditions", []):
            condition_type = condition_data.get("type")
            if condition_type == "expression":
                conditions.append(
                    ExpressionCheck(
                        expression=condition_data["expression"],
                        expected=condition_data.get("expected"),
                        tolerance=condition_data.get("tolerance", 0.0),
                        message=condition_data.get("message", ""),
                    )
                )
            elif condition_type == "llm":
                conditions.append(
                    LLMCheck(
                        prompt_template=condition_data["prompt_template"],
                        context_sources=condition_data.get("context_sources", []),
                        output_type=condition_data.get("output_type", "annotations"),
                    )
                )
            elif condition_type == "script":
                conditions.append(
                    ScriptCheck(
                        script=condition_data["script"],
                        generated=condition_data.get("generated", False),
                    )
                )
        blocks.append(
            CheckBlock(
                id=block_data["id"],
                description=block_data.get("description", ""),
                inputs=inputs,
                conditions=conditions,
                depends_on=block_data.get("depends_on", []),
            )
        )
    grading = payload.get("grading")
    grading_config = GradingConfig(**grading) if isinstance(grading, dict) else None
    return CheckRule(
        rule_id=payload.get("rule_id", "assignment-rule"),
        blocks=blocks,
        stop_on_error=payload.get("stop_on_error", False),
        grading=grading_config,
    )


async def run_assignment_rule_engine(
    *,
    rule_json: str,
    notebook_text: str,
    timeout_seconds: int = 60,
) -> RuleEngineRunResult:
    payload = json.loads(rule_json)
    rule = _load_rule_from_dict(payload)

    with tempfile.TemporaryDirectory(prefix="evalyn_rule_engine_") as tmpdir:
        notebook_path = Path(tmpdir) / "submission.ipynb"
        try:
            notebook = nbformat.reads(notebook_text, as_version=4)
        except Exception:
            notebook = nbformat.v4.new_notebook()
            notebook.cells = [nbformat.v4.new_code_cell(notebook_text)]
        nbformat.write(notebook, notebook_path)

        submission = Submission(notebook_path=notebook_path)
        config = Config(
            venv_name=payload.get("venv_name", "datascience-py311"),
            venv_storage_path=payload.get("venv_storage_path", str(Path.home() / ".sandbox_data" / "venvs")),
            containers_path=payload.get("containers_path", str(Path.home() / ".sandbox_data" / "containers")),
            requirements=payload.get("requirements", []),
            sandbox_ttl=payload.get("sandbox_ttl", timeout_seconds),
            cell_timeout=payload.get("cell_timeout", 30),
            llm_provider=payload.get("llm_provider", "openrouter"),
            llm_endpoint=payload.get("llm_endpoint"),
            llm_api_key=payload.get("llm_api_key"),
            llm_model=payload.get("llm_model", "openai/gpt-4o"),
            stop_on_error=payload.get("stop_on_error", False),
            max_retries=payload.get("max_retries", 2),
        )

        engine = RuleEngine()
        result = engine.run(rule, submission, config)
        return RuleEngineRunResult(check_result=result, raw_rule=payload)


def serialize_check_result(result: CheckResult) -> dict:
    return {
        "rule_id": result.rule_id,
        "annotations": [asdict(annotation) for annotation in result.annotations],
        "scores": result.scores,
    }
