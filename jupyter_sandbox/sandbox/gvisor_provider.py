"""
GVisorProvider — интерфейс к gVisor runsc.

Запускает контейнеры, управляет ресурсами, обрабатывает stdin/stdout.
"""

import asyncio
import logging

from .errors import ContainerError

logger = logging.getLogger(__name__)


import subprocess
import os
import tempfile
import time

class GVisorProvider:
    """Провайдер для запуска контейнеров через gVisor runsc."""

    def __init__(self, runsc_path: str = "runsc"):
        """
        Инициализирует GVisorProvider.

        Args:
            runsc_path: путь к executable runsc (по умолчанию ищется в PATH)
        """
        self.runsc_path = runsc_path

    async def start_old(
        self,
        overlay_lowerdir: str,
        workspace_path: str,
        cpu_limit: float = 1.0,
        memory_limit_mb: int = 512,
    ) -> asyncio.subprocess.Process:
        """
        Запустить контейнер с gVisor.

        Args:
            overlay_lowerdir: путь к read-only слою (venv)
            workspace_path: путь к рабочей директории контейнера
            cpu_limit: лимит CPU
            memory_limit_mb: лимит памяти в MB

        Returns:
            asyncio.subprocess.Process контейнера

        Raises:
            ContainerError: если не удалось запустить контейнер
        """
        cmd = [
            self.runsc_path,
            "do",
            "--rootless",
            "--network=none",
            f"--cpu={cpu_limit}",
            f"--memory={memory_limit_mb}m",
            f"--overlay-lowerdir={overlay_lowerdir}",
            f"--overlay-upperdir={workspace_path}/upper",
            f"--overlay-workdir={workspace_path}/work",
            "--",
            "python",
            "-m",
            "sandbox.kernel_orchestrator",
        ]

        logger.info(f"GVisorProvider: запускаю контейнер")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            logger.info(f"GVisorProvider: контейнер запущен (PID: {process.pid})")
            return process

        except FileNotFoundError:
            raise ContainerError(
                f"runsc не найден по пути: {self.runsc_path}. "
                "Установите gVisor или укажите правильный путь."
            )
        except Exception as e:
            raise ContainerError(f"Ошибка при запуске контейнера: {e}") from e
    
    async def start(
        self,
        overlay_lowerdir: str,
        workspace_path: str,
        cpu_limit: float = 1.0,
        memory_limit_mb: int = 512,
    ) -> asyncio.subprocess.Process:
        """
        Запустить контейнер через Docker с runtime=runsc.

        Args:
            overlay_lowerdir: путь к read-only слою (venv)
            workspace_path: путь к рабочей директории контейнера
            cpu_limit: лимит CPU (ядер)
            memory_limit_mb: лимит памяти в MB

        Returns:
            asyncio.subprocess.Process контейнера

        Raises:
            ContainerError: если не удалось запустить контейнер
        """
        # Уникальное имя контейнера (например, на основе PID или таймстампа)
        container_name = f"sandbox_{os.getpid()}_{int(time.time())}"

        #orchestrator_path = os.path.realpath('sandbox/kernel_orchestrator.py')
        orchestrator_path = os.path.dirname(os.path.abspath(__file__)).removesuffix('/gvisor_provider.py') + '/kernel_orchestrator.py'
        # Команда Docker
        cmd = [
            "docker", "run",
            "--rm",                          # удалить контейнер после остановки
            "--runtime=runsc",               # использовать gVisor
            "-i",
            "--name", container_name,
            "--network=none",                # без сети
            f"--cpus={cpu_limit}",           # лимит CPU
            f"--memory={memory_limit_mb}m",  # лимит памяти
            # Монтируем read-only слой (venv) в контейнер только для чтения
            "--mount", f"type=bind,src={overlay_lowerdir},dst=/venv,ro",
            # Монтируем рабочую директорию с возможностью записи (overlay будет на хосте)
            "--mount", f"type=bind,src={workspace_path},dst=/workspace",
             "--mount", f"type=bind,src={orchestrator_path},dst=/workspace/kernel_orchestrator.py,ro",
            # Можно также добавить tmpfs для временных файлов
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            # Команда внутри контейнера
            "--workdir=/workspace",
            "python:3.11-slim",              # образ Python (можно другой)
            "/venv/bin/python", "kernel_orchestrator.py"
        ]

        logger.info(f"DockerProvider: запускаю контейнер {container_name}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info(f"DockerProvider: контейнер запущен (PID: {process.pid}, name: {container_name})")
            return process

        except FileNotFoundError:
            raise ContainerError(
                "Команда 'docker' не найдена. Установите Docker и убедитесь, что он в PATH."
            )
        except Exception as e:
            raise ContainerError(f"Ошибка при запуске Docker-контейнера: {e}") from e
    async def stop(
        self, process: asyncio.subprocess.Process, timeout: int = 10
    ) -> int:
        """
        Остановить контейнер.

        Args:
            process: процесс контейнера
            timeout: таймаут ожидания (сек) перед kill

        Returns:
            exit code процесса
        """
        if process.returncode is not None:
            return process.returncode

        logger.info(f"GVisorProvider: останавливаю контейнер")

        try:
            if process.stdin and not process.stdin.is_closing():
                process.stdin.close()

            process.terminate()
            exit_code = await asyncio.wait_for(process.wait(), timeout=timeout)
            logger.info(f"GVisorProvider: контейнер остановлен")
            return exit_code

        except asyncio.TimeoutError:
            logger.warning(f"GVisorProvider: timeout, убиваю процесс")
            process.kill()
            exit_code = await process.wait()
            return exit_code

        except Exception as e:
            raise ContainerError(f"Ошибка при остановке контейнера: {e}") from e

    async def interrupt(self, process: asyncio.subprocess.Process) -> None:
        """Отправить SIGINT контейнеру (Ctrl+C)."""
        if process.returncode is None:
            process.send_signal(2)  # SIGINT
            logger.info(f"GVisorProvider: отправлен SIGINT")


class MockGVisorProvider(GVisorProvider):
    """Mock провайдер для тестирования (вместо reального runsc)."""

    async def start(
        self,
        overlay_lowerdir: str,
        workspace_path: str,
        cpu_limit: float = 1.0,
        memory_limit_mb: int = 512,
    ) -> asyncio.subprocess.Process:
        """Запустить mock контейнер (обычный Python процесс)."""
        logger.info("MockGVisorProvider: запускаю mock контейнер")

        # Запускаем Python процесс в бесконечном цикле
        process = await asyncio.create_subprocess_exec(
            "python",
            "-c",
            "import asyncio; asyncio.run(asyncio.sleep(float('inf')))",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        return process
