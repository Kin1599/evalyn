"""
Тесты для GVisorProvider.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from sandbox.gvisor_provider import GVisorProvider, MockGVisorProvider
from sandbox.errors import ContainerError


@pytest.mark.asyncio
async def test_gvisor_provider_start():
    """Тест: запуск контейнера."""
    provider = GVisorProvider()
    
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.pid = 1234
        mock_process.returncode = None
        mock_exec.return_value = mock_process
        
        result = await provider.start(
            overlay_lowerdir="/venvs/test",
            workspace_path="/workspace"
        )
        
        # Проверяем что процесс был создан
        assert result == mock_process
        
        # Проверяем что команда содержит нужные параметры
        call_args = mock_exec.call_args[0][0]
        assert "runsc" in call_args
        assert "--rootless" in call_args
        assert "--network=none" in call_args


@pytest.mark.asyncio
async def test_gvisor_provider_start_runsc_not_found():
    """Тест: ошибка если runsc не найден."""
    provider = GVisorProvider()
    
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        with pytest.raises(ContainerError, match="runsc не найден"):
            await provider.start(
                overlay_lowerdir="/venvs/test",
                workspace_path="/workspace"
            )


@pytest.mark.asyncio
async def test_gvisor_provider_stop_graceful():
    """Тест: graceful остановка контейнера."""
    provider = GVisorProvider()
    
    mock_process = AsyncMock()
    mock_process.returncode = None
    mock_process.pid = 1234
    mock_process.stdin = MagicMock()
    mock_process.stdin.is_closing.return_value = False
    mock_process.wait.return_value = 0
    
    result = await provider.stop(mock_process, timeout=5)
    
    # Проверяем что stdin был закрыт
    mock_process.stdin.close.assert_called_once()
    
    # Проверяем что был послан SIGTERM
    mock_process.terminate.assert_called_once()
    
    # Результат должен быть exit code
    assert result == 0


@pytest.mark.asyncio
async def test_gvisor_provider_stop_already_stopped():
    """Тест: остановка уже остановленного процесса."""
    provider = GVisorProvider()
    
    mock_process = AsyncMock()
    mock_process.returncode = 0  # Уже завершён
    
    result = await provider.stop(mock_process)
    
    # Не должно быть попыток остановки
    mock_process.terminate.assert_not_called()
    assert result == 0


@pytest.mark.asyncio
async def test_gvisor_provider_stop_timeout():
    """Тест: kill при таймауте остановки."""
    provider = GVisorProvider()
    
    mock_process = AsyncMock()
    mock_process.returncode = None
    mock_process.pid = 1234
    mock_process.stdin = None
    mock_process.wait.side_effect = asyncio.TimeoutError()
    
    # После kill, wait должен вернуть код
    future_call_count = 0
    async def wait_side_effect():
        nonlocal future_call_count
        future_call_count += 1
        if future_call_count == 1:
            raise asyncio.TimeoutError()
        return 1
    
    mock_process.wait.side_effect = wait_side_effect
    
    result = await provider.stop(mock_process, timeout=1)
    
    # Должен быть вызван kill
    mock_process.kill.assert_called_once()


@pytest.mark.asyncio
async def test_gvisor_provider_interrupt():
    """Тест: отправка SIGINT."""
    provider = GVisorProvider()
    
    mock_process = AsyncMock()
    mock_process.returncode = None
    
    await provider.interrupt(mock_process)
    
    # Должен быть вызван send_signal с SIGINT (код 2)
    mock_process.send_signal.assert_called_once_with(2)


@pytest.mark.asyncio
async def test_mock_gvisor_provider():
    """Тест: mock провайдер создаёт процесс."""
    provider = MockGVisorProvider()
    
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_exec.return_value = mock_process
        
        result = await provider.start(
            overlay_lowerdir="/venvs/test",
            workspace_path="/workspace"
        )
        
        # Mock должен запустить python процесс
        call_args = mock_exec.call_args[0][0]
        assert "python" in call_args


def test_gvisor_provider_init_custom_path():
    """Тест: инициализация с пользовательским путём к runsc."""
    provider = GVisorProvider(runsc_path="/usr/bin/custom-runsc")
    assert provider.runsc_path == "/usr/bin/custom-runsc"
