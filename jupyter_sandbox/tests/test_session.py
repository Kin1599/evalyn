"""
Тесты для SandboxSession.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from sandbox.session import SandboxSession
from sandbox.models import CellResult


@pytest.fixture
def mock_container():
    container = AsyncMock()
    container.send_command = AsyncMock()
    container.destroy_kernel = AsyncMock()
    return container


@pytest.fixture
def mock_manager():
    manager = AsyncMock()
    manager.remove_session = AsyncMock()
    return manager


@pytest.fixture
def session(mock_container, mock_manager):
    return SandboxSession(
        session_id="sess_123",
        container=mock_container,
        kernel_id="kernel_1",
        manager=mock_manager
    )


@pytest.mark.asyncio
async def test_session_execute_code(session, mock_container):
    # Мок ответа от контейнера
    mock_container.send_command.return_value = {
        "status": "ok",
        "stdout": "42\n",
        "stderr": "",
        "images": [],
        "error": None
    }
    
    result = await session.execute_code("print(42)")
    
    # Проверка вызова
    mock_container.send_command.assert_called_once()
    cmd_sent = mock_container.send_command.call_args[0][0]
    
    assert cmd_sent["cmd"] == "execute"
    assert cmd_sent["code"] == "print(42)"
    assert cmd_sent["kernel_id"] == "kernel_1"
    
    # Проверка результата
    assert isinstance(result, CellResult)
    assert result.status == "ok"
    assert result.stdout == "42\n"


@pytest.mark.asyncio
async def test_session_list_variables(session, mock_container):
    mock_container.send_command.return_value = {
        "variables": [
            {"name": "x", "type": "int", "size": 28}
        ]
    }
    
    vars_meta = await session.list_variables()
    
    assert len(vars_meta) == 1
    assert vars_meta[0].name == "x"
    assert vars_meta[0].type_name == "int"
    assert vars_meta[0].size_bytes == 28


@pytest.mark.asyncio
async def test_session_add_and_execute_cell(session, mock_container):
    mock_container.send_command.return_value = {"status": "ok"}
    
    # Добавление ячейки
    cell_id = await session.add_cell("x = 10")
    
    assert cell_id in session.cells
    cell = session.cells[cell_id]
    assert cell.source == "x = 10"
    assert cell.cell_type == "code"
    
    # Выполнение
    await session.execute_cell(cell_id)
    
    cmd_sent = mock_container.send_command.call_args[0][0]
    assert cmd_sent["cell_id"] == cell_id
    assert cmd_sent["code"] == "x = 10"


@pytest.mark.asyncio
async def test_session_terminate(session, mock_container, mock_manager):
    await session.terminate()
    
    mock_container.destroy_kernel.assert_called_once_with("kernel_1")
    mock_manager.remove_session.assert_called_once_with("sess_123")
