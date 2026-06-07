"""
SandboxSession — асинхронный интерфейс для взаимодействия с ядром.

Предоставляет API для выполнения кода, работы с файлами и переменными.
"""

import asyncio
import json
import base64
import logging
import pickle
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from collections import OrderedDict
import nbformat

from .errors import SandboxError, TimeoutError, KernelError, ProtocolError
from .models import CellInfo, CellResult, VariableMeta
from .utils import generate_id

if TYPE_CHECKING:
    from .container import Container
    from .manager import SandboxManager

logger = logging.getLogger(__name__)


class SandboxSession:
    """Сессия для работы с одним ядром IPython в контейнере."""

    def __init__(
        self,
        session_id: str,
        container: 'Container',
        kernel_id: str,
        manager: 'SandboxManager',
        ttl: Optional[int] = None,
    ):
        self.session_id = session_id
        self.container = container
        self.kernel_id = kernel_id
        self.manager = manager
        self.ttl = ttl
        self.last_activity = asyncio.get_event_loop().time()
        
        self.cells: OrderedDict[str, CellInfo] = OrderedDict()
        self._lock = asyncio.Lock()

    def touch(self):
        """Обновляет время активности сессии."""
        self.last_activity = asyncio.get_event_loop().time()
        self.container.touch()

    async def _send(self, cmd: dict, timeout: float = 30.0) -> dict:
        """Внутренний метод для отправки команд с `kernel_id`."""
        cmd["kernel_id"] = self.kernel_id
        self.touch()
        return await self.container.send_command(cmd, timeout=timeout)

    # ------------------------------------------------------------------------
    # Файловые операции
    # ------------------------------------------------------------------------

    async def upload_file(self, name: str, content: bytes) -> None:
        content_b64 = base64.b64encode(content).decode('ascii')
        resp = await self._send({
            "cmd": "write_file",
            "path": name,
            "content": content_b64
        }, timeout=10.0)
        
        if "error" in resp:
            raise SandboxError(f"Failed to upload file {name}: {resp['error']}")

    async def get_file(self, name: str) -> bytes:
        resp = await self._send({
            "cmd": "read_file",
            "path": name
        }, timeout=10.0)
        
        if "error" in resp:
            raise SandboxError(f"Failed to get file {name}: {resp['error']}")
            
        return base64.b64decode(resp["content"])

    async def list_files(self, path: str = "") -> List[Dict[str, Any]]:
        resp = await self._send({
            "cmd": "list_files",
            "path": path
        }, timeout=10.0)
        
        if "error" in resp:
            raise SandboxError(f"Failed to list files: {resp['error']}")
            
        return resp.get("files", [])

    # ------------------------------------------------------------------------
    # Управление ноутбуком и ячейками
    # ------------------------------------------------------------------------

    async def open_notebook(self, filename: str) -> List[CellInfo]:
        """Считывает `.ipynb` файл из контейнера, парсит и загружает ячейки."""
        try:
            content_bytes = await self.get_file(filename)
            nb_text = content_bytes.decode('utf-8')
            nb = nbformat.reads(nb_text, as_version=4)
        except Exception as e:
            raise SandboxError(f"Failed to parse notebook: {e}")

        async with self._lock:
            self.cells.clear()
            for cell in nb.cells:
                cell_id = cell.metadata.get('id', generate_id("c"))
                
                info = CellInfo(
                    cell_id=cell_id,
                    cell_type=cell.cell_type,
                    source=cell.source,
                    origin="original",
                    metadata=cell.metadata
                )
                self.cells[cell_id] = info
                
            return list(self.cells.values())

    async def add_cell(self, code: str, origin: str = "added") -> str:
        cell_id = generate_id("c")
        info = CellInfo(
            cell_id=cell_id,
            cell_type="code",
            source=code,
            origin=origin
        )
        async with self._lock:
            self.cells[cell_id] = info
        return cell_id

    async def list_cells(self) -> List[CellInfo]:
        async with self._lock:
            return list(self.cells.values())

    async def get_cell(self, cell_id: str) -> CellInfo:
        async with self._lock:
            if cell_id not in self.cells:
                raise SandboxError(f"Cell {cell_id} not found")
            return self.cells[cell_id]

    # ------------------------------------------------------------------------
    # Выполнение кода
    # ------------------------------------------------------------------------

    async def execute_cell(self, cell_id: str, timeout: Optional[int] = 30) -> CellResult:
        cell = await self.get_cell(cell_id)
        if cell.cell_type != "code":
            raise SandboxError(f"Cannot execute non-code cell {cell_id}")
            
        return await self._execute(cell_id, cell.source, timeout)

    async def execute_code(self, code: str, timeout: Optional[int] = 30) -> CellResult:
        return await self._execute("adhoc", code, timeout)

    async def _execute(self, cell_id: str, code: str, timeout: Optional[int]) -> CellResult:
        timeout = timeout or 30
        
        try:
            resp = await self._send({
                "cmd": "execute",
                "cell_id": cell_id,
                "code": code,
                "timeout": timeout
            }, timeout=timeout + 5.0)  # Таймаут на уровне JSON-RPC должен быть больше
        except ProtocolError as e:
            if "Таймаут" in str(e):
                return CellResult(cell_id=cell_id, status="timeout", error={"message": "JSON-RPC Timeout"})
            raise
            
        if "error" in resp and resp["error"] and isinstance(resp["error"], str):
            # Внутренняя ошибка оркестратора
            raise KernelError(resp["error"])
            
        return CellResult(
            cell_id=cell_id,
            stdout=resp.get("stdout", ""),
            stderr=resp.get("stderr", ""),
            images=resp.get("images", []),
            error=resp.get("error"),  # JSON dict с ename, evalue, traceback
            status=resp.get("status", "ok")
        )

    # ------------------------------------------------------------------------
    # Переменные
    # ------------------------------------------------------------------------

    async def list_variables(self) -> List[VariableMeta]:
        resp = await self._send({"cmd": "get_variables"}, timeout=10.0)
        if "error" in resp:
            raise SandboxError(f"Failed to list variables: {resp}")
            
        return [
            VariableMeta(name=v["name"], type_name=v["type"], size_bytes=v["size"])
            for v in resp.get("variables", [])
        ]

    async def get_variable(self, name: str) -> bytes:
        resp = await self._send({"cmd": "get_variable", "name": name}, timeout=15.0)
        if "error" in resp:
            if "not found" in resp["error"]:
                raise KeyError(name)
            raise SandboxError(resp["error"])
            
        return base64.b64decode(resp["pickle"])

    async def export_state(self) -> bytes:
        """Экспорт всех переменных (не реализовано на уровне оркестратора, собираем через get_variable)."""
        vars_meta = await self.list_variables()
        state = {}
        for v in vars_meta:
            try:
                pickled = await self.get_variable(v.name)
                state[v.name] = pickle.loads(pickled)
            except Exception as e:
                logger.warning(f"Failed to export variable {v.name}: {e}")
                
        return pickle.dumps(state)

    # ------------------------------------------------------------------------
    # Изображения
    # ------------------------------------------------------------------------

    async def get_images(self, cell_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not cell_id:
            raise ValueError("cell_id is required")
            
        resp = await self._send({
            "cmd": "get_images",
            "cell_id": cell_id
        }, timeout=10.0)
        
        if "error" in resp:
            raise SandboxError(resp["error"])
            
        images = resp.get("images", [])
        # Декодировать base64 если нужно, но оставим как есть для Web API
        return images

    # ------------------------------------------------------------------------
    # Жизненный цикл
    # ------------------------------------------------------------------------

    async def cancel_cell(self) -> None:
        # Для отправки interrupt без блокировки основного канала,
        # в оркестраторе должна быть поддержка неблокирующих команд или
        # мы можем просто отправить новый процесс sigint
        pass

    async def shutdown_kernel(self) -> None:
        await self.container.destroy_kernel(self.kernel_id)

    async def terminate(self) -> None:
        """Полное удаление сессии."""
        try:
            await self.shutdown_kernel()
        except Exception as e:
            logger.warning(f"Error shutting down kernel {self.kernel_id}: {e}")
            
        await self.manager.remove_session(self.session_id)
