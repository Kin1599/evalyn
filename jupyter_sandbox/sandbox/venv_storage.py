"""
VenvStorage — управление виртуальными окружениями.

Кэширует виртуальные окружения по хешу требований.
Использует `uv` для создания и установки зависимостей.
"""
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict
import tempfile


from .errors import VenvBuildError
from .utils import hash_requirements, ensure_dir

logger = logging.getLogger(__name__)


class VenvStorage:
    """Менеджер кэшированных виртуальных окружений."""

    def __init__(self, storage_path: str):
        """
        Инициализирует VenvStorage.

        Args:
            storage_path: путь к директории для хранения окружений
        """
        self.storage_path = Path(storage_path)
        self._locks: Dict[str, asyncio.Lock] = {}  # Блокировки для каждого venv_hash

    async def get_or_create(
        self,
        venv_name: Optional[str] = "",
        requirements: Optional[List[str]] = None,
    ) -> str:
        """
        Получить или создать виртуальное окружение.

        Args:
            venv_name: имя предсуществующего окружения (или явное имя)
            requirements: список pip-требований (если venv_name не задан)

        Returns:
            Путь к директории venv

        Raises:
            ValueError: если не переданы ни venv_name ни requirements
            VenvBuildError: если сборка окружения не удалась
        """
        # Определяем ключ (venv_hash) для кэширования
        if requirements:
            venv_hash = venv_name + "_" + hash_requirements(requirements)
        else:
            raise ValueError("Нужно передать requirements")

        venv_path = self.storage_path / venv_hash

        # Получаем или создаём блокировку для этого venv_hash
        if venv_hash not in self._locks:
            self._locks[venv_hash] = asyncio.Lock()
        print('venv hash', venv_hash)
        print('venv path', venv_path)
        async with self._locks[venv_hash]:
            # Проверяем, существует ли уже такое окружение
            if venv_path.exists():
                logger.info(f"VenvStorage: найдено существующее окружение: {venv_hash}")
                return str(venv_path)

            # Создаём новое окружение
            logger.info(f"VenvStorage: создаю новое окружение: {venv_hash}")
            await ensure_dir(venv_path)

            try:
                # Создаём venv через `uv`
                if False:
                    await self._create_venv_uv(venv_path)

                    # Устанавливаем зависимости, если они переданы
                    if requirements:
                        await self._install_requirements(venv_path, requirements)
                await self.create_portable_venv(venv_path, requirements)
                logger.info(f"VenvStorage: успешно создано окружение: {venv_hash}")
                return str(venv_path)

            except Exception as e:
                # Очищаем директорию при ошибке
                logger.error(f"VenvStorage: ошибка при создании окружения: {e}")
                if venv_path.exists():
                    import shutil
                    shutil.rmtree(venv_path, ignore_errors=True)
                raise VenvBuildError(f"Не удалось создать venv {venv_hash}: {e}") from e

    async def _create_venv_uv(self, venv_path: Path) -> None:
        """Создаёт виртуальное окружение через `uv venv`."""
        cmd = ["uv", "venv", "--link-mode=copy", str(venv_path)]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise VenvBuildError(
                    f"`uv venv` failed with code {process.returncode}: "
                    f"{stderr.decode('utf-8', errors='replace')}"
                )

        except FileNotFoundError:
            raise VenvBuildError(
                "`uv` не установлен или не найден в PATH. "
                "Установите его: pip install uv"
            )

    async def _install_requirements(
        self, venv_path: Path, requirements: List[str]
    ) -> None:
        """Устанавливает pip-зависимости в venv через `uv pip install`."""
        if not requirements:
            return

        # Определяем путь к интерпретатору Python внутри venv
        if sys.platform == "win32":
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            python_exe = venv_path / "bin" / "python"

        if not python_exe.exists():
            raise VenvBuildError(
                f"Python executable not found in venv at {python_exe}. "
                "Venv creation may have failed."
            )

        # Используем uv pip install --python <python_exe> пакеты
        cmd = ["uv", "pip", "install", "--python", str(python_exe)] + requirements

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

            if process.returncode != 0:
                raise VenvBuildError(
                    f"uv pip install failed with code {process.returncode}: "
                    f"{stderr.decode('utf-8', errors='replace')}"
                )
        except asyncio.TimeoutError:
            raise VenvBuildError("uv pip install timeout (300 seconds)")

    async def clear_cache(self) -> None:
        """Очистить весь кэш окружений."""
        import shutil

        if self.storage_path.exists():
            shutil.rmtree(self.storage_path, ignore_errors=True)
            logger.info("VenvStorage: кэш очищен")


    async def create_portable_venv(
        self,
        target_path: Path,
        requirements: Optional[List[str]] = None,
        python_version: str = "3.11",
        use_uv: bool = False,      # использовать uv для ускорения установки
    ) -> Path:
        """
        Создаёт переносимый venv в Docker-контейнере и сохраняет его на хост.

        Args:
            target_path: куда сохранить venv на хосте
            requirements: список пакетов pip (или uv)
            python_version: версия Python (например, "3.13", "3.11")
            use_uv: использовать uv вместо pip (быстрее)

        Returns:
            Path к созданному venv (target_path)

        Raises:
            RuntimeError: если Docker не доступен или команда не удалась
        """
        if target_path.exists():
            import shutil
            shutil.rmtree(target_path)

        # Готовим команду для установки зависимостей
        reqs_str = "\n".join(requirements) if requirements else ""
        install_cmd = ""
        if use_uv:
            # Установим uv внутрь контейнера, затем создадим venv через uv
            install_cmd = f"""
            pip install uv -q && \
            uv venv --python {python_version} --copies /venv && \
            source /venv/bin/activate && \
            echo "{reqs_str}" > /tmp/requirements.txt && \
            uv pip install -r /tmp/requirements.txt
            """
        else:
            install_cmd = f"""
            python -m venv --copies /venv && \
            /venv/bin/pip install --upgrade pip -q && \
            echo "{reqs_str}" > /tmp/requirements.txt && \
            /venv/bin/pip install -r /tmp/requirements.txt
            """

        # Команда Docker: запускаем одноразовый контейнер, внутри выполняем скрипт, затем копируем результат
        # Используем `docker run --rm` с именем, чтобы потом скопировать файлы, но контейнер удалится автоматически.
        # Копировать нужно ДО того, как контейнер будет удалён, поэтому придётся без --rm и удалять вручную.
        container_name = f"venv_builder_{hash(str(target_path)) & 0xffffffff}"

        try:
            # 1. Запускаем контейнер в фоне
            run_cmd = [
                "docker", "run", "-d",
                "--name", container_name,
                f"python:{python_version}-slim",
                "sleep", "infinity"
            ]
            proc = await asyncio.create_subprocess_exec(*run_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"Docker run failed: {stderr.decode()}")

            # 2. Выполняем установку внутри контейнера
            exec_cmd = [
                "docker", "exec", container_name,
                "bash", "-c", install_cmd
            ]
            proc = await asyncio.create_subprocess_exec(*exec_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"Installation failed: {stderr.decode()}")
            
            # 3. Копируем venv из контейнера на хост
            target_path.parent.mkdir(parents=True, exist_ok=True)
            cp_cmd = ["docker", "cp", f"{container_name}:/venv/.", str(target_path)]
            proc = await asyncio.create_subprocess_exec(*cp_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"docker cp failed: {stderr.decode()}")

            return target_path

        finally:
            # Очистка: остановить и удалить контейнер
            await asyncio.create_subprocess_exec("docker", "rm", "-f", container_name, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)