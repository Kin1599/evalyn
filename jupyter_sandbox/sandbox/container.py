"""
Container — управление отдельным gVisor контейнером.

Абстрагирует работу с контейнером и его оркестратором через JSON-RPC.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional

from .errors import ProtocolError, ContainerError

logger = logging.getLogger(__name__)


class Container:
    """Обертка над процессом gVisor (или моком) с JSON-RPC интерфейсом к оркестратору."""

    def __init__(
        self,
        container_id: str,
        venv_hash: str,
        process: asyncio.subprocess.Process,
        workspace_path: str,
    ):
        """
        Инициализация контейнера.

        Args:
            container_id: Уникальный ID контейнера.
            venv_hash: Хеш окружения (для переиспользования).
            process: Процесс `runsc do` (или python для мока).
            workspace_path: Путь к рабочей директории.
        """
        self.container_id = container_id
        self.venv_hash = venv_hash
        self.process = process
        self.workspace_path = workspace_path
        
        self.active_kernels = 0
        self.last_activity = asyncio.get_event_loop().time()
        
        self._lock = asyncio.Lock()  # Блокировка для send_command

    def touch(self):
        """Обновляет время последней активности."""
        self.last_activity = asyncio.get_event_loop().time()

    async def send_command(self, cmd: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """
        Отправляет JSON-RPC команду оркестратору и ждет ответ.

        Args:
            cmd: Словарь с командой.
            timeout: Таймаут ожидания ответа.

        Returns:
            Ответ от оркестратора.

        Raises:
            ProtocolError: Ошибка взаимодействия или таймаут.
            ContainerError: Контейнер завершился.
        """
        self.touch()
        
        # Убедимся, что процесс жив
        if self.process.returncode is not None:
            raise ContainerError(f"Контейнер {self.container_id} неожиданно завершился.")

        async with self._lock:  # Только один запрос за раз для избежания путаницы с ответами
            try:
                # Отправка команды
                cmd_str = json.dumps(cmd) + "\n"
                logger.debug(f"[{self.container_id}] SEND: {cmd_str.strip()}")
                self.process.stdin.write(cmd_str.encode('utf-8'))
                await self.process.stdin.drain()

                # Чтение ответа
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=timeout)
                
                if not line:
                    raise ContainerError(f"Контейнер {self.container_id} закрыл stdout (вероятно, завершился).")
                    
                line_str = line.decode('utf-8').strip()
                logger.debug(f"[{self.container_id}] RECV: {line_str}")
                
                response = json.loads(line_str)
                
                if "error" in response and cmd.get("cmd") != "shutdown":
                    logger.error(f"[{self.container_id}] Error in response: {response['error']}")
                    
                return response
                
            except asyncio.TimeoutError:
                with open(f'container_{self.container_id}_err.log', 'wb') as f:
                    f.write(self.process.stderr._buffer)
                #print(self.process.stderr._buffer)
                raise ProtocolError(f"Таймаут (>{timeout}с) ожидания ответа от контейнера {self.container_id}")
            except json.JSONDecodeError as e:
                with open(f'container_{self.container_id}_err.log', 'wb') as f:
                    f.write(self.process.stderr._buffer)
                #print(self.process.stderr._buffer)
                raise ProtocolError(f"Невалидный JSON от контейнера: {e}. Получено: {line_str}")
            except Exception as e:
                with open(f'container_{self.container_id}_err.log', 'wb') as f:
                    f.write(self.process.stderr._buffer)
                #print(self.process.stderr._buffer)
                raise ProtocolError(f"Ошибка протокола связи с контейнером log записан {self.container_id}: {e}")

    async def create_kernel(self) -> str:
        """
        Создает новое ядро в оркестраторе.

        Returns:
            ID ядра (kernel_id).
        """
        resp = await self.send_command({"cmd": "create_kernel"}, timeout=125.0)
        if "error" in resp:
            raise ContainerError(f"Не удалось создать ядро: {resp['error']}")
            
        kernel_id = resp["kernel_id"]
        self.active_kernels += 1
        return kernel_id

    async def destroy_kernel(self, kernel_id: str) -> None:
        """
        Уничтожает ядро в оркестраторе.

        Args:
            kernel_id: ID ядра для удаления.
        """
        if self.process.returncode is not None:
             # Если контейнер уже мёртв, очищаем счётчик и выходим
             self.active_kernels = max(0, self.active_kernels - 1)
             return

        try:
            await self.send_command({"cmd": "destroy_kernel", "kernel_id": kernel_id}, timeout=10.0)
        except Exception as e:
            logger.warning(f"Ошибка при удалении ядра {kernel_id} (контейнер мог умереть): {e}")
        finally:
            self.active_kernels = max(0, self.active_kernels - 1)

    async def shutdown(self) -> None:
        """Посылает команду завершения работы оркестратору."""
        if self.process.returncode is None:
            try:
                # Отправляем shutdown, но не ждём ответа долго, так как он может закрыться сразу
                await self.send_command({"cmd": "shutdown"}, timeout=5.0)
            except Exception as e:
                logger.debug(f"Игнорируем ошибку при shutdown контейнера {self.container_id}: {e}")

