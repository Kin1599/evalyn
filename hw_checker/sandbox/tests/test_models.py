"""
Модульные тесты для models и utils.
"""
import pytest
from sandbox.models import CellInfo, CellResult
from sandbox.utils import generate_id, hash_requirements, sanitize_filename


def test_generate_id():
    """Тест генерации ID."""
    id1 = generate_id("kernel")
    assert id1.startswith("kernel_")
    assert len(id1) > 10

    id2 = generate_id()
    assert len(id2) == 8


def test_hash_requirements():
    """Тест хеширования требований."""
    reqs = ["numpy==1.24.0", "pandas>=2.0"]
    hash1 = hash_requirements(reqs)
    hash2 = hash_requirements(list(reversed(reqs)))
    assert hash1 == hash2  # Порядок не влияет
    assert len(hash1) == 16


def test_sanitize_filename():
    """Тест очистки имён файлов."""
    assert sanitize_filename("notebook.ipynb") == "notebook.ipynb"
    assert sanitize_filename("my file.txt") == "my_file.txt"
    assert sanitize_filename("../../evil.py") == "______evil.py"


def test_cell_info():
    """Тест создания CellInfo."""
    cell = CellInfo(
        cell_id="cell_1",
        cell_type="code",
        source="print('hello')"
    )
    assert cell.cell_id == "cell_1"
    assert cell.origin == "original"


def test_cell_result():
    """Тест создания CellResult."""
    result = CellResult(
        cell_id="cell_1",
        stdout="hello\n",
        status="ok"
    )
    assert result.stdout == "hello\n"
    assert result.error is None
