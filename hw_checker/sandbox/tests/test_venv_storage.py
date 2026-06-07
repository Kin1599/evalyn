"""
Тесты для VenvStorage.
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from sandbox.venv_storage import VenvStorage
from sandbox.errors import VenvBuildError


@pytest.mark.asyncio
async def test_venv_storage_get_or_create_existing():
    """Тест: получить существующий venv по имени."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = VenvStorage(tmpdir)
        
        # Создаём существующий venv
        venv_path = Path(tmpdir) / "test_venv"
        venv_path.mkdir(parents=True)
        
        # Должен вернуть путь без попыток создания
        result = await storage.get_or_create(venv_name="test_venv")
        assert result == str(venv_path)


@pytest.mark.asyncio
async def test_venv_storage_get_or_create_with_requirements():
    """Тест: создать venv с зависимостями."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = VenvStorage(tmpdir)
        requirements = ["numpy", "pandas"]
        
        # Mock subprocess для uv venv
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_exec.return_value = mock_process
            
            with patch.object(storage, "_install_requirements", new_callable=AsyncMock):
                result = await storage.get_or_create(requirements=requirements)
                
                # Проверяем что был создан venv
                assert result.startswith(tmpdir)
                assert "uv" in mock_exec.call_args[0][0]


@pytest.mark.asyncio
async def test_venv_storage_error_no_args():
    """Тест: ошибка при отсутствии аргументов."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = VenvStorage(tmpdir)
        
        with pytest.raises(ValueError):
            await storage.get_or_create()


@pytest.mark.asyncio
async def test_venv_storage_uv_not_found():
    """Тест: ошибка если uv не установлен."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = VenvStorage(tmpdir)
        
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            with pytest.raises(VenvBuildError, match="uv.*не установлен"):
                await storage.get_or_create(venv_name="test")


@pytest.mark.asyncio
async def test_venv_storage_lock_prevents_duplicate():
    """Тест: блокировка предотвращает дублирование созданий."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = VenvStorage(tmpdir)
        
        call_count = 0
        
        async def mock_create_venv(venv_path):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Имитируем работу
        
        with patch.object(storage, "_create_venv", side_effect=mock_create_venv):
            # Запускаем две операции одновременно
            results = await asyncio.gather(
                storage.get_or_create(venv_name="test"),
                storage.get_or_create(venv_name="test")
            )
            
            # _create_venv должен быть вызван только один раз благодаря lock
            assert call_count == 1
            assert results[0] == results[1]


def test_venv_storage_hash_requirements():
    """Тест: хеширование требований должно быть стабильным."""
    from sandbox.utils import hash_requirements
    
    reqs1 = ["numpy==1.24.0", "pandas>=2.0"]
    reqs2 = ["pandas>=2.0", "numpy==1.24.0"]  # Другой порядок
    
    # Хеш должен быть одинаковый независимо от порядка
    assert hash_requirements(reqs1) == hash_requirements(reqs2)
