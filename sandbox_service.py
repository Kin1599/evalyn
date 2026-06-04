import ast
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

RESTRICTED_MODULES = {
    "os",
    "sys",
    "subprocess",
    "pathlib",
    "shutil",
    "socket",
    "requests",
    "urllib",
    "http",
    "ftplib",
    "paramiko",
    "multiprocessing",
    "asyncio",
    "threading",
}


class SandboxRequest(BaseModel):
    code: str
    timeout_seconds: int = 8


class SandboxResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    timed_out: bool
    error: str | None = None


def _check_imports(code: str) -> tuple[bool, str | None]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc.msg}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                if root_name in RESTRICTED_MODULES:
                    return False, f"Import of module '{root_name}' is not allowed."
    return True, None


async def _execute_code(code: str, timeout_seconds: int) -> SandboxResponse:
    with tempfile.TemporaryDirectory() as temp_dir:
        script_path = Path(temp_dir) / "sandbox.py"
        script_path.write_text(code, encoding="utf-8")

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(script_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=temp_dir,
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            return SandboxResponse(
                success=process.returncode == 0,
                stdout=stdout.decode("utf-8", errors="replace").strip(),
                stderr=stderr.decode("utf-8", errors="replace").strip(),
                timed_out=False,
                error=None,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return SandboxResponse(
                success=False,
                stdout="",
                stderr="",
                timed_out=True,
                error="Execution timed out.",
            )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run", response_model=SandboxResponse)
async def run_sandbox(request: SandboxRequest) -> SandboxResponse:
    safe, error = _check_imports(request.code)
    if not safe:
        return SandboxResponse(success=False, stdout="", stderr="", timed_out=False, error=error)

    return await _execute_code(request.code, timeout_seconds=request.timeout_seconds)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("sandbox_service:app", host="0.0.0.0", port=8001, log_level="info")
