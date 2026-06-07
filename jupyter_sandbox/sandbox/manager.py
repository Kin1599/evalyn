"""
SandboxManager — главная точка входа библиотеки.

Управляет жизненным циклом сессий и контейнеров.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
import shutil
import uuid

from .errors import SandboxError, ContainerError, VenvBuildError
from .utils import generate_id, hash_requirements
from .venv_storage import VenvStorage
from .gvisor_provider import GVisorProvider, MockGVisorProvider
from .container import Container
from .session import SandboxSession

logger = logging.getLogger(__name__)


class SandboxManager:
    """Менеджер для выполнения кода в изолированных окружениях."""

    def __init__(
        self,
        #isolation: str = "gvisor",  # "gvisor" или "mock"
        venv_storage_path: str,
        containers_path: str,
        container_idle_ttl: int = 300,
        container_max_kernels: int = 10,
        container_cleanup_interval: int = 60,
    ):
        """
        Инициализирует менеджер.

        Args:
            isolation: Тип изоляции ("gvisor" или "mock" для тестов).
            venv_storage_path: Путь к хранилищу окружений.
            containers_path: Путь к рабочей директории контейнеров.
            container_idle_ttl: Время жизни контейнера без ядер (сек).
            container_max_kernels: Максимальное кол-во ядер в одном контейнере.
            container_cleanup_interval: Интервал проверки неактивных контейнеров.
        """
        self.venv_storage = VenvStorage(venv_storage_path)
        isolation = "gvisor"
        if isolation == "gvisor":
            self.provider = GVisorProvider()
        elif isolation == "mock":
            self.provider = MockGVisorProvider()
        else:
            raise ValueError(f"Unknown isolation type: {isolation}")
            
        self.containers_path = Path(containers_path)
        self.container_idle_ttl = container_idle_ttl
        self.container_max_kernels = container_max_kernels
        self._cleanup_interval = container_cleanup_interval

        self.containers: Dict[str, Container] = {}  # container_id -> Container
        self.sessions: Dict[str, SandboxSession] = {}  # session_id -> SandboxSession
        
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._is_running = True
        
        # Создаём базовые директории
        self.containers_path.mkdir(parents=True, exist_ok=True)
        
        # Запускаем фоновую очистку
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def create_session(
        self,
        venv_name: Optional[str] = None,
        requirements: Optional[List[str]] = None,
        ttl: Optional[int] = None,
        files: Optional[Dict[str, bytes]] = None,
    ) -> SandboxSession:
        """
        Создаёт новую сессию (ядро в контейнере).

        Args:
            venv_name: имя предсуществующего окружения
            requirements: список требований pip
            ttl: таймаут неактивности сессии (сек)
            files: словарь начальных файлов {'filename': b'content'}

        Returns:
            SandboxSession
        """
        if not self._is_running:
            raise SandboxError("Менеджер остановлен.")

        # Получаем/Создаём Venv
        venv_path = await self.venv_storage.get_or_create(venv_name, requirements)
        
        if venv_name:
            venv_hash = venv_name
        else:
            venv_hash = hash_requirements(requirements or [])

        # Ищем существующий или создаем новый контейнер
        container = await self._get_or_create_container(venv_hash, venv_path)

        # Создаем ядро
        try:
            kernel_id = await container.create_kernel()
        except Exception as e:
            # Если не удалось создать ядро, возможно контейнер "устал". 
            # Можно попробовать ещё раз в новом контейнере.
            logger.warning(f"Ошибка создания ядра в {container.container_id} {e}")
            await self.shutdown_container(container.container_id)
            #container = await self._get_or_create_container(venv_hash, venv_path)
            #kernel_id = await container.create_kernel()

        # Создаем сессию
        session_id = str(uuid.uuid4())
        session = SandboxSession(
            session_id=session_id,
            container=container,
            kernel_id=kernel_id,
            manager=self,
            ttl=ttl
        )
        
        async with self._lock:
            self.sessions[session_id] = session

        # Загружаем файлы, если переданы
        if files:
            for name, content in files.items():
                await session.upload_file(name, content)

        return session

    async def _get_or_create_container(self, venv_hash: str, venv_path: str) -> Container:
        """Находит подходящий контейнер или создает новый."""
        async with self._lock:
            # 1. Поиск существующего подходящего контейнера
            suitable_containers = [
                c for c in self.containers.values()
                if c.venv_hash == venv_hash and c.active_kernels < self.container_max_kernels
                and c.process.returncode is None
            ]
            
            if suitable_containers:
                # Берем тот, где меньше всего ядер, для балансировки (или наоборот)
                container = suitable_containers[0]
                container.touch()
                return container

        # 2. Создание нового
        container_id = generate_id("cnt")
        workspace = self.containers_path / container_id
        
        # Подготовка директорий для overlay
        upper_dir = workspace / "upper"
        work_dir = workspace / "work"
        upper_dir.mkdir(parents=True)
        work_dir.mkdir(parents=True)
        
        # Передаём SANDBOX_WORKSPACE для оркестратора в верхнем слое
        # Для gvisor мы монтируем rootfs. Оркестратор будет использовать текущую директорию.
        
        logger.info(f"Запуск нового контейнера {container_id} (venv: {venv_hash})")
        process = await self.provider.start(
            overlay_lowerdir=venv_path,
            workspace_path=str(workspace)
        )
        
        container = Container(
            container_id=container_id,
            venv_hash=venv_hash,
            process=process,
            workspace_path=str(workspace)
        )
        
        async with self._lock:
            self.containers[container_id] = container
            
        return container

    async def get_session(self, session_id: str) -> Optional[SandboxSession]:
        """Получить сессию по ID."""
        async with self._lock:
            return self.sessions.get(session_id)

    async def remove_session(self, session_id: str) -> None:
        """Удалить сессию из активных."""
        async with self._lock:
            self.sessions.pop(session_id, None)

    async def shutdown_container(self, container_id: str) -> None:
        """Принудительно останавливает контейнер."""
        container = None
        async with self._lock:
            container = self.containers.pop(container_id, None)
            
        if container:
            # Закрываем все сессии, связанные с этим контейнером
            sessions_to_close = []
            async with self._lock:
                for s_id, s in list(self.sessions.items()):
                    if s.container.container_id == container_id:
                        sessions_to_close.append(s)
                        
            for s in sessions_to_close:
                await self.remove_session(s.session_id)

            await container.shutdown()
            await self.provider.stop(container.process)
            
            # Очистка файловой системы
            try:
                shutil.rmtree(container.workspace_path, ignore_errors=True)
            except Exception as e:
                logger.error(f"Не удалось удалить workspace {container.workspace_path}: {e}")

    async def _cleanup_loop(self) -> None:
        """Фоновая задача очистки неактивных ресурсов."""
        while self._is_running:
            await asyncio.sleep(self._cleanup_interval)
            logger.debug("Запуск очистки (cleanup)...")
            
            now = asyncio.get_event_loop().time()
            
            # 1. Проверка истекших сессий (TTL)
            expired_sessions = []
            async with self._lock:
                for s_id, s in self.sessions.items():
                    if s.ttl is not None and (now - s.last_activity) > s.ttl:
                        expired_sessions.append(s)
            
            for s in expired_sessions:
                logger.info(f"Сессия {s.session_id} истекла по TTL, завершение...")
                try:
                    await s.terminate()
                except Exception as e:
                    logger.error(f"Ошибка при terminate сессии по TTL: {e}")
            
            # 2. Проверка истекших контейнеров
            expired_containers = []
            async with self._lock:
                for c_id, c in self.containers.items():
                    if c.active_kernels == 0 and (now - c.last_activity) > self.container_idle_ttl:
                        expired_containers.append(c_id)
            
            for c_id in expired_containers:
                logger.info(f"Контейнер {c_id} истек по TTL (нет ядер), остановка...")
                await self.shutdown_container(c_id)

    async def shutdown(self) -> None:
        """Завершить все сессии и контейнеры."""
        self._is_running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Менеджер останавливается. Завершение всех контейнеров...")
        
        # Получаем копию всех IDs
        container_ids = []
        async with self._lock:
            container_ids = list(self.containers.keys())
            
        # Останавливаем все (это также удалит сессии)
        for c_id in container_ids:
            await self.shutdown_container(c_id)
            
        logger.info("Все контейнеры остановлены.")

