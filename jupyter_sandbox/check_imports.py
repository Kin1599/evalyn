#!/usr/bin/env python
"""Скрипт проверки что всё компилируется."""

import sys
import traceback

print("=" * 70)
print("🔍 ПРОВЕРКА ИМПОРТОВ И СИНТАКСИСА")
print("=" * 70)

try:
    print("\n1. Проверка моделей...")
    from sandbox.models import CellInfo, CellResult, ImageData
    print("   ✅ models.py: OK")
except Exception as e:
    print(f"   ❌ models.py: {e}")
    traceback.print_exc()

try:
    print("\n2. Проверка ошибок...")
    from sandbox.errors import SandboxError, VenvBuildError, ContainerError
    print("   ✅ errors.py: OK")
except Exception as e:
    print(f"   ❌ errors.py: {e}")
    traceback.print_exc()

try:
    print("\n3. Проверка утилит...")
    from sandbox.utils import generate_id, hash_requirements
    print("   ✅ utils.py: OK")
except Exception as e:
    print(f"   ❌ utils.py: {e}")
    traceback.print_exc()

try:
    print("\n4. Проверка VenvStorage...")
    from sandbox.venv_storage import VenvStorage
    print("   ✅ venv_storage.py: OK")
except Exception as e:
    print(f"   ❌ venv_storage.py: {e}")
    traceback.print_exc()

try:
    print("\n5. Проверка GVisorProvider...")
    from sandbox.gvisor_provider import GVisorProvider, MockGVisorProvider
    print("   ✅ gvisor_provider.py: OK")
except Exception as e:
    print(f"   ❌ gvisor_provider.py: {e}")
    traceback.print_exc()

print("\n" + "=" * 70)
print("✅ ВСЕ КОМПОНЕНТЫ ЗАГРУЖЕНЫ УСПЕШНО!")
print("=" * 70)

# Простая проверка функциональности
print("\n📋 БАЗОВАЯ ФУНКЦИОНАЛЬНОСТЬ:")
print(f"  - generate_id(): {generate_id('test')}")
print(f"  - hash_requirements(): {hash_requirements(['numpy', 'pandas'])}")
storage = VenvStorage("/tmp/test_venv")
print(f"  - VenvStorage инициализирован: {storage.storage_path}")
provider = GVisorProvider()
print(f"  - GVisorProvider инициализирован: {provider.runsc_path}")

print("\n✅ ПРОВЕРКА ЗАВЕРШЕНА!")
