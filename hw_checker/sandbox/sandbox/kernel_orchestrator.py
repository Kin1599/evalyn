"""
kernel_orchestrator.py — скрипт, запускаемый внутри контейнера.

Управляет пулом IPython-ядер и предоставляет JSON-RPC интерфейс через stdin/stdout.
"""

import sys
import json
import base64
import asyncio
import logging
import traceback
import tempfile
import pickle
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

#try:
# from jupyter_client.manager import AsyncKernelManager
# from jupyter_client.client import AsyncKernelClient

from jupyter_client.asynchronous.client import AsyncKernelClient
from jupyter_client import AsyncKernelManager
#except ImportError:
#    # Игнорируем ошибку при проверке синтаксиса до установки зависимостей
#    pass

# Настройка логирования в stderr, чтобы не ломать JSON-RPC в stdout
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("orchestrator")


class KernelEntry:
    """Обертка над одним ядром IPython."""
    def __init__(self, manager: 'AsyncKernelManager', client: 'AsyncKernelClient'):
        self.manager = manager
        self.client = client
        self.images: Dict[str, List[Dict[str, Any]]] = {}  # cell_id -> [{"id", "format", "data"}]


class KernelOrchestrator:
    """Управляет жизненным циклом ядер и обработкой команд."""

    def __init__(self):
        self.kernels: Dict[str, KernelEntry] = {}
        self.running = True
        self._next_kernel_id = 1
        self.workspace = Path(os.environ.get("SANDBOX_WORKSPACE", "."))

    async def handle_request(self, req: dict) -> dict:
        """Диспетчеризация команд."""
        cmd = req.get("cmd")
        try:
            if cmd == "create_kernel":
                return await self.create_kernel(req)
            elif cmd == "destroy_kernel":
                return await self.destroy_kernel(req)
            elif cmd == "execute":
                return await self.execute(req)
            elif cmd == "get_variables":
                return await self.get_variables(req)
            elif cmd == "get_variable":
                return await self.get_variable(req)
            elif cmd == "get_images":
                return await self.get_images(req)
            elif cmd == "read_file":
                return await self.read_file(req)
            elif cmd == "write_file":
                return await self.write_file(req)
            elif cmd == "list_files":
                return await self.list_files(req)
            elif cmd == "shutdown":
                return await self.shutdown(req)
            else:
                return {"error": f"Unknown command: {cmd}"}
        except Exception as e:
            logger.error(f"Error handling {cmd}: {e}\n{traceback.format_exc()}")
            return {"error": str(e), "traceback": traceback.format_exc()}

    async def create_kernel(self, req: dict) -> dict:
        kernel_id = f"kernel_{self._next_kernel_id}"
        self._next_kernel_id += 1
        
        manager = AsyncKernelManager()
        await manager.start_kernel()
        client = manager.client()
        client.start_channels()
        
        try:
            await client.wait_for_ready(timeout=10)
        except RuntimeError:
            # Fallback for wait_for_ready timeout issues in some versions
            pass

        self.kernels[kernel_id] = KernelEntry(manager, client)
        logger.info(f"Created kernel {kernel_id}")
        return {"kernel_id": kernel_id}

    async def destroy_kernel(self, req: dict) -> dict:
        kernel_id = req["kernel_id"]
        if kernel_id in self.kernels:
            entry = self.kernels.pop(kernel_id)
            entry.client.stop_channels()
            await entry.manager.shutdown_kernel(now=True)
            logger.info(f"Destroyed kernel {kernel_id}")
        return {"status": "ok"}

    async def execute(self, req: dict) -> dict:
        kernel_id = req["kernel_id"]
        cell_id = req["cell_id"]
        code = req["code"]
        timeout = req.get("timeout", 30)

        entry = self.kernels.get(kernel_id)
        if not entry:
            return {"error": f"Kernel {kernel_id} not found"}

        client = entry.client
        entry.images[cell_id] = []
        
        msg_id = client.execute(code)
        
        stdout_parts = []
        stderr_parts = []
        exec_error = None
        images_meta = []

        start_time = asyncio.get_event_loop().time()

        try:
            last_text_result = None
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    # Timeout => interrupt and return
                    await entry.manager.interrupt_kernel()
                    return {"status": "timeout"}

                try:
                    # Use a short timeout for polling
                    msg = await client.get_iopub_msg(timeout=0.1)
                except Exception: # queue.Empty is not standard Exception, need to catch all
                    # Also check shell channel for exec_reply
                    try:
                        reply = await client.get_shell_msg(timeout=0.01)
                        if reply['parent_header'].get('msg_id') == msg_id:
                            if reply['content']['status'] == 'error':
                                exec_error = {
                                    'ename': reply['content']['ename'],
                                    'evalue': reply['content']['evalue'],
                                    'traceback': reply['content']['traceback']
                                }
                            break
                    except Exception:
                        pass
                    continue
                
                if msg['parent_header'].get('msg_id') != msg_id:
                    continue
                
                msg_type = msg['header']['msg_type']
                content = msg['content']
                
                if msg_type == 'stream':
                    if content['name'] == 'stdout':
                        stdout_parts.append(content['text'])
                    elif content['name'] == 'stderr':
                        stderr_parts.append(content['text'])
                
                elif msg_type == 'error':
                    exec_error = {
                        'ename': content['ename'],
                        'evalue': content['evalue'],
                        'traceback': content['traceback']
                    }
                
                elif msg_type == 'display_data':# or msg_type == 'execute_result':
                    if 'data' in content:
                        data = content['data']
                        # Поиск изображений
                        img_format = None
                        img_data = None
                        for fmt in ['image/png', 'image/jpeg', 'image/svg+xml']:
                            if fmt in data:
                                img_format = fmt.split('/')[-1]
                                if '+' in img_format:
                                    img_format = img_format.split('+')[0]
                                img_data = data[fmt]
                                break
                        
                        if img_data and img_format:
                            img_id = f"img_{len(entry.images[cell_id])}"
                            entry.images[cell_id].append({
                                "id": img_id,
                                "format": img_format,
                                "data": img_data  # Уже base64 строка в jupyter protocol
                            })
                            images_meta.append({"id": img_id, "format": img_format})
                elif msg_type == 'execute_result':
                    # Сохраняем текстовый вывод последнего выражения
                    if 'data' in content and 'text/plain' in content['data']:
                        last_text_result = content['data']['text/plain']
                elif msg_type == 'status':
                    if content['execution_state'] == 'idle':
                        # Check shell again
                        pass
                        
        except Exception as e:
            logger.error(f"Execution loop error: {e}")

        return {
            "status": "error" if exec_error else "ok",
            "stdout": "".join(stdout_parts),
            "stderr": "".join(stderr_parts),
            "result": last_text_result,   # <-- новый ключ
            "error": exec_error,
            "images": images_meta
        }

    async def get_variables(self, req: dict) -> dict:
        kernel_id = req["kernel_id"]
        entry = self.kernels.get(kernel_id)
        if not entry:
            return {"error": f"Kernel not found"}

        code = (
            "import sys, json\n"
            "_vars = []\n"
            "for _k, _v in list(globals().items()):\n"
            "    if not _k.startswith('_') and _k not in ['In', 'Out', 'exit', 'quit', 'get_ipython']:\n"
            "        _vars.append({'name': _k, 'type': type(_v).__name__, 'size': sys.getsizeof(_v)})\n"
            "print(json.dumps(_vars))"
        )
        
        reply = await self._run_silent_code(entry.client, code)
        try:
            vars_list = json.loads(reply)
            return {"variables": vars_list}
        except Exception as e:
            return {"error": f"Failed to parse variables: {e} {e.with_traceback(None)} JSON:>{reply}<"}

    async def get_variable(self, req: dict) -> dict:
        kernel_id = req["kernel_id"]
        name = req["name"]
        entry = self.kernels.get(kernel_id)
        if not entry:
            return {"error": f"Kernel not found"}

        code = (
            "import pickle, base64\n"
            f"if '{name}' in globals():\n"
            f"    print(base64.b64encode(pickle.dumps(globals()['{name}'])).decode())\n"
            "else:\n"
            "    print('__NOT_FOUND__')"
        )
        
        reply = await self._run_silent_code(entry.client, code)
        reply = reply.strip()
        
        if reply == '__NOT_FOUND__':
            return {"error": f"Variable {name} not found"}
        return {"pickle": reply}

    async def get_images(self, req: dict) -> dict:
        kernel_id = req["kernel_id"]
        cell_id = req["cell_id"]
        entry = self.kernels.get(kernel_id)
        if not entry:
            return {"error": f"Kernel not found"}
            
        images = entry.images.get(cell_id, [])
        return {"images": images}

    # async def _run_silent_code(self, client, code: str) -> str:
    #     msg_id = client.execute(code, silent=True)
    #     stdout = []
    #     try:
    #         while True:
    #             try:
    #                 msg = await client.get_iopub_msg(timeout=0.1)
    #                 if msg['parent_header'].get('msg_id') == msg_id:
    #                     if msg['header']['msg_type'] == 'stream' and msg['content']['name'] == 'stdout':
    #                         stdout.append(msg['content']['text'])
    #             except Exception:
    #                 pass
                
    #             try:
    #                 reply = await client.get_shell_msg(timeout=0.01)
    #                 if reply['parent_header'].get('msg_id') == msg_id:
    #                     break
    #             except Exception:
    #                 pass
    #     except Exception:
    #         pass
            
    #     return "".join(stdout)
    async def _run_silent_code(self, client, code: str) -> str:
        """Выполняет код и возвращает всё, что попало в stdout."""
        msg_id = client.execute(code, silent=False, store_history=False)
        stdout_parts = []

        while True:
            try:
                msg = await asyncio.wait_for(client.get_iopub_msg(), timeout=0.1)
            except asyncio.TimeoutError:
                # если долго нет сообщений, проверяем shell
                try:
                    reply = await asyncio.wait_for(client.get_shell_msg(), timeout=0.01)
                    if reply['parent_header'].get('msg_id') == msg_id:
                        break
                except asyncio.TimeoutError:
                    pass
                continue

            if msg['parent_header'].get('msg_id') != msg_id:
                continue

            msg_type = msg['header']['msg_type']
            content = msg['content']

            if msg_type == 'stream' and content.get('name') == 'stdout':
                text = content.get('text', '')
                if isinstance(text, list):
                    text = ''.join(str(t) for t in text)
                stdout_parts.append(text)
            elif msg_type == 'status' and content.get('execution_state') == 'idle':
                # Основной сигнал завершения
                break
            elif msg_type == 'error':
                stdout_parts.append(''.join(content['traceback']))
                # ошибка выполнения — просто ждём idle / exec_reply
                pass
            # остальные (execute_result, display_data) игнорируем

        return "".join(stdout_parts)
    async def read_file(self, req: dict) -> dict:
        path = self.workspace / req["path"]
        if not path.exists() or not path.is_file():
            return {"error": "File not found"}
        content = path.read_bytes()
        return {"content": base64.b64encode(content).decode('ascii')}

    async def write_file(self, req: dict) -> dict:
        path = self.workspace / req["path"]
        content = base64.b64decode(req["content"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {"status": "ok"}

    async def list_files(self, req: dict) -> dict:
        path = self.workspace / req.get("path", "")
        if not path.exists():
            return {"files": []}
            
        files = []
        for item in path.iterdir():
            files.append({
                "name": item.name,
                "type": "file" if item.is_file() else "dir",
                "size": item.stat().st_size if item.is_file() else 0
            })
        return {"files": files}

    async def shutdown(self, req: dict) -> dict:
        for k_id, entry in list(self.kernels.items()):
            entry.client.stop_channels()
            await entry.manager.shutdown_kernel(now=True)
        self.kernels.clear()
        self.running = False
        return {"status": "ok"}


async def main():
    orchestrator = KernelOrchestrator()
    logger.info("Kernel Orchestrator started")

    loop = asyncio.get_running_loop()

    while orchestrator.running:
        try:
            # Синхронное чтение строки из stdin в отдельном потоке
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            line_str = line.strip()
            if not line_str:
                continue

            req = json.loads(line_str)
            resp = await orchestrator.handle_request(req)

            # Синхронная запись в stdout (быстрая операция, не требует executor)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        except Exception as e:
            logger.error(f"Main loop error: {e}")
            sys.stdout.write(json.dumps({"error": str(e)}) + "\n")
            sys.stdout.flush()

    logger.info("Kernel Orchestrator shutting down")
if __name__ == "__main__":
    # Windows-specific event loop setting for asyncio/subprocess compatibility inside Jupyter
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())

