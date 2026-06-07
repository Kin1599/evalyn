"""
Тесты для KernelOrchestrator.
"""

import pytest
import asyncio
import json
import base64
from unittest.mock import AsyncMock, patch, MagicMock

from sandbox.kernel_orchestrator import KernelOrchestrator, KernelEntry


@pytest.fixture
def orchestrator():
    """Создаёт экземпляр KernelOrchestrator."""
    return KernelOrchestrator()


@pytest.mark.asyncio
async def test_handle_create_kernel(orchestrator):
    """Тест команды create_kernel."""
    with patch("sandbox.kernel_orchestrator.AsyncKernelManager") as mock_akm:
        mock_manager = AsyncMock()
        mock_client = AsyncMock()
        mock_manager.client.return_value = mock_client
        mock_akm.return_value = mock_manager

        req = {"cmd": "create_kernel"}
        resp = await orchestrator.handle_request(req)

        assert "kernel_id" in resp
        kernel_id = resp["kernel_id"]
        assert kernel_id == "kernel_1"
        assert kernel_id in orchestrator.kernels

        mock_manager.start_kernel.assert_called_once()
        mock_client.start_channels.assert_called_once()
        mock_client.wait_for_ready.assert_called_once_with(timeout=10)


@pytest.mark.asyncio
async def test_handle_destroy_kernel(orchestrator):
    """Тест команды destroy_kernel."""
    mock_manager = AsyncMock()
    mock_client = AsyncMock()
    
    orchestrator.kernels["kernel_1"] = KernelEntry(mock_manager, mock_client)
    
    req = {"cmd": "destroy_kernel", "kernel_id": "kernel_1"}
    resp = await orchestrator.handle_request(req)
    
    assert resp["status"] == "ok"
    assert "kernel_1" not in orchestrator.kernels
    mock_client.stop_channels.assert_called_once()
    mock_manager.shutdown_kernel.assert_called_once_with(now=True)


@pytest.mark.asyncio
async def test_handle_file_operations(orchestrator, tmp_path):
    """Тест работы с файлами (read_file, write_file, list_files)."""
    orchestrator.workspace = tmp_path
    
    # 1. Write file
    content = b"print('hello')"
    content_b64 = base64.b64encode(content).decode()
    
    req_write = {
        "cmd": "write_file",
        "path": "test.py",
        "content": content_b64
    }
    resp_write = await orchestrator.handle_request(req_write)
    assert resp_write["status"] == "ok"
    assert (tmp_path / "test.py").exists()
    
    # 2. Read file
    req_read = {
        "cmd": "read_file",
        "path": "test.py"
    }
    resp_read = await orchestrator.handle_request(req_read)
    assert resp_read["content"] == content_b64
    
    # 3. List files
    req_list = {
        "cmd": "list_files"
    }
    resp_list = await orchestrator.handle_request(req_list)
    assert len(resp_list["files"]) == 1
    assert resp_list["files"][0]["name"] == "test.py"
    assert resp_list["files"][0]["type"] == "file"
