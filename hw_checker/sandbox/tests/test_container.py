"""
Тесты для Container класса.
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock

from sandbox.container import Container
from sandbox.errors import ProtocolError, ContainerError


@pytest.fixture
def mock_process():
    process = AsyncMock()
    process.returncode = None
    process.stdin = AsyncMock()
    process.stdout = AsyncMock()
    return process


@pytest.fixture
def container(mock_process):
    return Container(
        container_id="cnt_123",
        venv_hash="hash456",
        process=mock_process,
        workspace_path="/tmp/workspace"
    )


def test_container_init(container):
    assert container.container_id == "cnt_123"
    assert container.active_kernels == 0


@pytest.mark.asyncio
async def test_send_command_success(container, mock_process):
    # Setup mock stdout to return a JSON response
    mock_process.stdout.readline.return_value = b'{"status": "ok", "result": 42}\n'
    
    cmd = {"cmd": "test_cmd", "arg": "value"}
    resp = await container.send_command(cmd)
    
    assert resp["status"] == "ok"
    assert resp["result"] == 42
    
    # Check that it serialized correctly
    mock_process.stdin.write.assert_called_once_with(b'{"cmd": "test_cmd", "arg": "value"}\n')


@pytest.mark.asyncio
async def test_send_command_timeout(container, mock_process):
    # Setup mock to timeout
    mock_process.stdout.readline.side_effect = asyncio.TimeoutError()
    
    with pytest.raises(ProtocolError, match="Таймаут"):
        await container.send_command({"cmd": "test"}, timeout=0.1)


@pytest.mark.asyncio
async def test_send_command_bad_json(container, mock_process):
    mock_process.stdout.readline.return_value = b'{"status": broken \n'
    
    with pytest.raises(ProtocolError, match="Невалидный JSON"):
        await container.send_command({"cmd": "test"})


@pytest.mark.asyncio
async def test_send_command_process_dead(container, mock_process):
    mock_process.returncode = 1  # Process died
    
    with pytest.raises(ContainerError, match="неожиданно завершился"):
        await container.send_command({"cmd": "test"})


@pytest.mark.asyncio
async def test_create_kernel(container, mock_process):
    mock_process.stdout.readline.return_value = b'{"kernel_id": "kernel_1"}\n'
    
    kernel_id = await container.create_kernel()
    
    assert kernel_id == "kernel_1"
    assert container.active_kernels == 1


@pytest.mark.asyncio
async def test_destroy_kernel(container, mock_process):
    container.active_kernels = 2
    mock_process.stdout.readline.return_value = b'{"status": "ok"}\n'
    
    await container.destroy_kernel("kernel_1")
    
    assert container.active_kernels == 1
    mock_process.stdin.write.assert_called_once_with(b'{"cmd": "destroy_kernel", "kernel_id": "kernel_1"}\n')


@pytest.mark.asyncio
async def test_shutdown(container, mock_process):
    mock_process.stdout.readline.return_value = b'{"status": "ok"}\n'
    
    await container.shutdown()
    
    mock_process.stdin.write.assert_called_once_with(b'{"cmd": "shutdown"}\n')
