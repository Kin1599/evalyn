from dataclasses import dataclass
from typing import Any

import httpx

from core.config import settings


@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    timed_out: bool
    error: str | None = None


def is_python_code(text: str) -> bool:
    keywords = ["def ", "class ", "import ", "print(", "if ", "for ", "while "]
    return any(keyword in text for keyword in keywords)


async def run_python_code(code: str, timeout_seconds: int = 8) -> SandboxResult:
    if not settings.sandbox_url:
        return SandboxResult(
            success=False,
            stdout="",
            stderr="",
            timed_out=False,
            error="Sandbox URL is not configured.",
        )

    async with httpx.AsyncClient(timeout=timeout_seconds + 5) as client:
        try:
            response = await client.post(
                f"{settings.sandbox_url.rstrip('/')}/run",
                json={"code": code, "timeout_seconds": timeout_seconds},
                headers={"Content-Type": "application/json"},
            )
        except httpx.RequestError as exc:
            return SandboxResult(
                success=False,
                stdout="",
                stderr="",
                timed_out=False,
                error=f"Sandbox service request failed: {exc}",
            )

    if response.status_code != 200:
        return SandboxResult(
            success=False,
            stdout="",
            stderr="",
            timed_out=False,
            error=f"Sandbox service returned HTTP {response.status_code}: {response.text}",
        )

    data = response.json()
    return SandboxResult(
        success=data.get("success", False),
        stdout=data.get("stdout", ""),
        stderr=data.get("stderr", ""),
        timed_out=data.get("timed_out", False),
        error=data.get("error"),
    )
