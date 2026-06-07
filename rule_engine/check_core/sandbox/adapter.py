"""
Sandbox Adapter — синхронная обёртка над асинхронной песочницей.
"""

import asyncio
import logging
import pickle
from pathlib import Path
from typing import Any

from ..exceptions import SandboxError
from ..models import ExecutionContext, ExecutedCell

logger = logging.getLogger(__name__)


class SandboxAdapter:
    """
    Выполняет ноутбук в изолированной среде и собирает результаты.
    """

    def execute(self, submission, stop_on_error: bool, config) -> ExecutionContext:
        """
        Запускает ноутбук из submission в песочнице, возвращает контекст выполнения.

        Args:
            submission: объект Submission с notebook_path и additional_files.
            stop_on_error: остановить выполнение при первой ошибке в ячейке.
            config: объект Config с настройками подключения.

        Returns:
            ExecutionContext с глобальными переменными, результатами ячеек и маппингом.
        """
        return asyncio.run(self._execute_async(submission, stop_on_error, config))

    async def _execute_async(self, submission, stop_on_error: bool, config) -> ExecutionContext:
        from sandbox import SandboxManager  # предполагаем, что пакет песочницы доступен

        # Инициализация менеджера
        venv_path = Path(config.venv_storage_path).expanduser().resolve()
        containers_path = Path(config.containers_path).expanduser().resolve()
        venv_path.mkdir(parents=True, exist_ok=True)
        containers_path.mkdir(parents=True, exist_ok=True)

        manager = SandboxManager(
            venv_storage_path=str(venv_path),
            containers_path=str(containers_path)
        )

        # Сбор требований
        requirements = [
            'ipykernel>=6.29',
            'jupyter-client>=8.6',
            'nbformat>=5.9',
            'pydantic>=2.0',
            'aiofiles>=23.0',
        ]
        requirements.extend(config.requirements)
        # requirements = ['ipykernel>=6.29', 'jupyter-client>=8.6',
        #                'nbformat>=5.9', 'pydantic>=2.0', 'aiofiles>=23.0']
        # Если студент предоставил requirements.txt, добавляем (упрощённо)
        # В реальности надо прочитать файл, но здесь передадим как есть
        # Пусть будет параметр config.extra_requirements

        session = await manager.create_session(
            venv_name=config.venv_name,
            ttl=config.sandbox_ttl,
            requirements=requirements
        )

        try:
            # Загружаем ноутбук и доп. файлы
            notebook_bytes = submission.notebook_path.read_bytes()
            await session.upload_file("notebook.ipynb", notebook_bytes)
            for filename, content in submission.additional_files:
                await session.upload_file(filename, content)

            # Открываем ноутбук
            cells = await session.open_notebook("notebook.ipynb")
            logger.info("Найдено %d ячеек", len(cells))

            executed_cells = []
            variable_cells = {}
            known_names = set()

            # Получаем начальный список переменных (может быть пустым)
            try:
                initial_vars = await session.list_variables()
                known_names = {v.name for v in initial_vars}
            except Exception:
                known_names = set()

            # Выполняем ячейки
            for idx, cell in enumerate(cells):
                if cell.cell_type != "code":
                    continue

                # Запоминаем переменные до выполнения
                prev_names = set(known_names)

                try:
                    result = await session.execute_cell(cell.cell_id, timeout=config.cell_timeout)
                except Exception as e:
                    raise SandboxError(f"Ошибка выполнения ячейки {cell.cell_id}: {e}")

                # Собираем результат ячейки
                stdout = result.stdout if result.status == "ok" else ""
                error = None
                if result.status == "error":
                    error = result.error

                images = []
                if result.images:
                    try:
                        images = await session.get_images(cell.cell_id)
                    except Exception:
                        logger.warning("Не удалось получить изображения для ячейки %s", cell.cell_id)

                executed_cells.append(ExecutedCell(
                    cell_id=cell.cell_id,
                    source=cell.source,
                    stdout=stdout,
                    error=error,
                    images=images
                ))

                # Обновляем список переменных и фиксируем новые
                try:
                    current_vars = await session.list_variables()
                    current_names = {v.name for v in current_vars}
                except Exception:
                    current_names = set()

                new_names = current_names - prev_names
                for name in new_names:
                    variable_cells[name] = idx  # индекс ячейки
                known_names = current_names

                if stop_on_error and error:
                    logger.info("Остановка из-за ошибки в ячейке %s", cell.cell_id)
                    break

            # Извлекаем глобальные переменные
            globals_dict = {}
            try:
                final_vars = await session.list_variables()
            except Exception:
                final_vars = []

            for var in final_vars:
                try:
                    raw = await session.get_variable(var.name)
                    obj = pickle.loads(raw)
                    globals_dict[var.name] = obj
                except Exception as e:
                    logger.warning("Не удалось десериализовать переменную %s: %s", var.name, e)

            return ExecutionContext(
                globals=globals_dict,
                cells=executed_cells,
                variable_cells=variable_cells
            )

        finally:
            await session.terminate()
            await manager.shutdown()