"""
Тесты для SandboxManager.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from sandbox.manager import SandboxManager
from sandbox.container import Container
from sandbox.session import SandboxSession


@pytest.fixture
def mock_venv_storage():
    with patch("sandbox.manager.VenvStorage") as mock:
        instance = mock.return_value
        instance.get_or_create = AsyncMock(return_value="/mock/venv")
        yield instance


@pytest.fixture
def mock_provider():
    with patch("sandbox.manager.MockGVisorProvider") as mock:
        instance = mock.return_value
        instance.start = AsyncMock(return_value=AsyncMock(returncode=None))
        instance.stop = AsyncMock()
        yield instance


@pytest.fixture
async def manager(tmp_path, mock_venv_storage, mock_provider):
    # Используем mock изоляцию
    mgr = SandboxManager(
        isolation="mock",
        containers_path=str(tmp_path),
        container_cleanup_interval=10 # Чаще для тестов, если надо
    )
    yield mgr
    await mgr.shutdown()


@pytest.mark.asyncio
async def test_manager_init(manager):
    assert manager._is_running is True
    assert manager.containers == {}
    assert manager.sessions == {}


@pytest.mark.asyncio
async def test_get_or_create_container_new(manager):
    # Создаем контейнер первый раз
    container = await manager._get_or_create_container("hash1", "/mock/venv")
    
    assert list(manager.containers.keys()) == [container.container_id]
    assert container.venv_hash == "hash1"


@pytest.mark.asyncio
async def test_get_or_create_container_reuse(manager):
    # Создаем один
    c1 = await manager._get_or_create_container("hash1", "/mock/venv")
    
    # Запрашиваем с тем же хешем
    c2 = await manager._get_or_create_container("hash1", "/mock/venv")
    
    # Должен вернуть тот же самый, так как в нем еще 0 ядер (меньше 10)
    assert c1 is c2
    assert len(manager.containers) == 1


@pytest.mark.asyncio
async def test_get_or_create_container_max_kernels(manager):
    c1 = await manager._get_or_create_container("hash1", "/mock/venv")
    c1.active_kernels = 10  # max = 10
    
    # Так как c1 заполнен, должен создать новый
    c2 = await manager._get_or_create_container("hash1", "/mock/venv")
    
    assert c1 is not c2
    assert len(manager.containers) == 2


@pytest.mark.asyncio
async def test_shutdown_container(manager):
    c1 = await manager._get_or_create_container("hash1", "/mock/venv")
    
    # Мокаем shutdown на контейнере
    c1.shutdown = AsyncMock()
    
    await manager.shutdown_container(c1.container_id)
    
    assert len(manager.containers) == 0
    c1.shutdown.assert_called_once()
    manager.provider.stop.assert_called_once()


@pytest.mark.asyncio
async def test_create_session(manager):
    # Мок создания ядра на контейнере
    with patch.object(manager, "_get_or_create_container", new_callable=AsyncMock) as mock_get_c:
        mock_cnt = MagicMock()
        mock_cnt.create_kernel = AsyncMock(return_value="kernel_1")
        mock_get_c.return_value = mock_cnt
        
        # Мокаем SandboxSession (поскольку он еще не реализован полностью)
        with patch("sandbox.manager.SandboxSession") as ModelMock:
            instance = ModelMock.return_value
            instance.session_id = "sess_1"
            
            # Вызываем проверяемый метод
            session = await manager.create_session(requirements=["numpy"])
            
            assert session is instance
            assert "sess_1" in manager.sessions
