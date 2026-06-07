from __future__ import annotations

import asyncio
import io
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import nbformat


@dataclass(slots=True)
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    timed_out: bool
    error: str | None = None


def is_python_code(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith("{") and "cells" in stripped:
        return True
    keywords = ["def ", "class ", "import ", "print(", "if ", "for ", "while ", "return "]
    return any(keyword in text for keyword in keywords)


def _extract_notebook_cells(code: str) -> list[str]:
    notebook = nbformat.reads(code, as_version=4)
    cells = [
        cell["source"]
        for cell in notebook.cells
        if cell.cell_type == "code"
    ]
    if not cells:
        raise ValueError("Notebook has no code cells")
    return cells


async def _run_hw_checker_notebook(code: str, timeout_seconds: int) -> SandboxResult:
    try:
        from sandbox import SandboxManager
    except Exception as exc:
        return SandboxResult(
            success=False,
            stdout="",
            stderr="",
            timed_out=False,
            error=f"hw_checker sandbox unavailable: {exc}",
        )

    try:
        notebook = nbformat.reads(code, as_version=4)
    except Exception as exc:
        return SandboxResult(
            success=False,
            stdout="",
            stderr="",
            timed_out=False,
            error=f"Invalid notebook: {exc}",
        )

    with tempfile.TemporaryDirectory(prefix="evalyn_hw_checker_") as tmpdir:
        root = Path(tmpdir)
        venv_path = root / "venvs"
        containers_path = root / "containers"
        venv_path.mkdir(parents=True, exist_ok=True)
        containers_path.mkdir(parents=True, exist_ok=True)

        manager = SandboxManager(
            venv_storage_path=str(venv_path),
            containers_path=str(containers_path),
        )
        session = await manager.create_session(
            venv_name="datascience-py311",
            ttl=timeout_seconds,
            requirements=[
                "ipykernel>=6.29",
                "jupyter-client>=8.6",
                "nbformat>=5.9",
                "aiofiles>=23.0",
            ],
        )

        try:
            await session.upload_file("notebook.ipynb", code.encode("utf-8"))
            cells = await session.open_notebook("notebook.ipynb")
            stdout_chunks: list[str] = []
            stderr_chunks: list[str] = []

            for cell in cells:
                if cell.cell_type != "code":
                    continue
                result = await session.execute_cell(cell.cell_id, timeout=timeout_seconds)
                if result.stdout:
                    stdout_chunks.append(result.stdout)
                if result.status == "error" and result.error:
                    stderr_chunks.append(json.dumps(result.error, ensure_ascii=False))
                elif result.stderr:
                    stderr_chunks.append(result.stderr)

            return SandboxResult(
                success=not stderr_chunks,
                stdout="\n".join(stdout_chunks),
                stderr="\n".join(stderr_chunks),
                timed_out=False,
                error=None if not stderr_chunks else "Notebook execution finished with errors",
            )
        finally:
            await session.terminate()
            await manager.shutdown()


async def _run_inline_python(code: str, timeout_seconds: int) -> SandboxResult:
    async def execute() -> SandboxResult:
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(code, {"__builtins__": __builtins__, "__name__": "__main__"})
            return SandboxResult(
                success=True,
                stdout=stdout_capture.getvalue(),
                stderr=stderr_capture.getvalue(),
                timed_out=False,
            )
        except Exception as exc:
            return SandboxResult(
                success=False,
                stdout=stdout_capture.getvalue(),
                stderr=str(exc),
                timed_out=False,
                error=str(exc),
            )

    try:
        return await asyncio.wait_for(execute(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return SandboxResult(
            success=False,
            stdout="",
            stderr="",
            timed_out=True,
            error="Execution timeout",
        )


async def run_python_code(code: str, timeout_seconds: int = 8) -> SandboxResult:
    try:
        if code.strip().startswith("{"):
            try:
                _extract_notebook_cells(code)
                return await _run_hw_checker_notebook(code, timeout_seconds)
            except Exception:
                pass
        return await _run_inline_python(code, timeout_seconds)
    except Exception as exc:
        return SandboxResult(
            success=False,
            stdout="",
            stderr="",
            timed_out=False,
            error=f"Sandbox error: {exc}",
        )
