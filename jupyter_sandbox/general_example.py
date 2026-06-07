"""
Пример выполнения Jupyter-ноутбука.
"""
import asyncio
import json
from pathlib import Path
from sandbox import SandboxManager


async def main():
    venv_storage_path=Path.home().joinpath(".sandbox_data").joinpath("venvs")
    containers_path=Path.home().joinpath(".sandbox_data").joinpath("containers")

    containers_path.mkdir(parents=True, exist_ok=True)#.__str__,
    venv_storage_path.mkdir(parents=True, exist_ok=True)#.__str__,
    manager = SandboxManager(
        #isolation="gvisor",
        venv_storage_path=str(venv_storage_path),
        containers_path=str(containers_path)
        #"USER_HOME.sandbox_data/venvs"
    )

    # Создание сессии с загрузкой ноутбука
    notebook_path = Path("example_notebook.ipynb")
    
    session = await manager.create_session(
        venv_name="datascience-py311",
        ttl=600,
        requirements=['ipykernel>=6.29', 'jupyter-client>=8.6', 'nbformat>=5.9', 'pydantic>=2.0', 'aiofiles>=23.0'],
    )

    # Загрузка ноутбука в контейнер
    notebook_content = notebook_path.read_bytes()
    await session.upload_file("notebook.ipynb", notebook_content)

    # Парсинг и выполнение ячеек
    cells = await session.open_notebook("notebook.ipynb")
    print(f"Найдено {len(cells)} ячеек")

    for i, cell in enumerate(cells):
        if cell.cell_type == "code":
            print(f"\nВыполняю ячейку {i+1}:")
            print(f"Код: {cell.source[:50]}...")
            
            result = await session.execute_cell(cell.cell_id, timeout=30)
            
            if result.status == "ok":
                print(f"Результат: {result.stdout[:100]}")
                
                if result.images:
                    images = await session.get_images(cell.cell_id)
                    print(f"Получено {len(images)} изображений")
            else:
                print(f"Ошибка: {result.status}")
                if result.error:
                    print(result.error)

    # Получение итогового состояния
    vars_list = await session.list_variables()
    print(f"\nИтоговые переменные: {vars_list}")

    print(" Получим значение перменной b")
    b = await session.get_variable("b")
    print(f"Значение переменной b: {b}") # Значение переменной b: b'\x80\x04\x95\x04\x00\x00\x00\x00\x00\x00\x00M\x19;.'
    import pickle
    print(pickle.loads(b)) # 123

    print(" Получим значение перменной chm")
    chm = await session.get_variable("chm")
    print(f"Значение переменной chm: {chm}") # Значение переменной b: b'\x80\x04\x95\x04\x00\x00\x00\x00\x00\x00\x00M\x19;.'
    print(pickle.loads(chm)) # 123

    new_cell = await session.add_cell('print("new cell")\nnewv=1233\nprint(newv)')
    res = await session.execute_cell(new_cell)
    print('\nвыполнили новую ячейку')
    print(res)
    newv = await session.get_variable('newv')
    print('newv')
    print(newv)
    print(pickle.loads(newv))

    await session.terminate()
    await manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
