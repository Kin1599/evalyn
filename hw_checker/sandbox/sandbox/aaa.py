# cpu_limit = 2
# memory_limit_mb = 256
# overlay_lowerdir = '/venv'
# workspace_path = '/workspace'
# orchestrator_path = '/home/rdinit/hw_checker/sandbox/sandbox/kernel_orchestrator.py'


# cmd = [
#     'docker', 'run',
#     '--rm',                          # удалить контейнер после остановки
#     '--runtime=runsc',               # использовать gVisor
#     '--name', 'test_con',
#     '--network=none',                # без сети
#     f'--cpus={cpu_limit}',           # лимит CPU
#     f'--memory={memory_limit_mb}m',  # лимит памяти
#     # Монтируем read-only слой (venv) в контейнер только для чтения
#     '--mount', f'type=bind,src={overlay_lowerdir},dst=/venv,ro',
#     # Монтируем рабочую директорию с возможностью записи (overlay будет на хосте)
#     '--mount', f'type=bind,src={workspace_path},dst=/workspace',
#         '--mount', f'type=bind,src={orchestrator_path},dst=/workspace/kernel_orchestrator.py,ro',
#     # Можно также добавить tmpfs для временных файлов
#     '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
#     # Команда внутри контейнера
#     '--workdir=/workspace',
#     'python:3.11-slim',              # образ Python (можно другой)
#     'python', 'kernel_orchestrator.py'
# ]

print("sandbox.errors.SandboxError: Failed to list variables: {'error': 'sequence item 0: expected str instance, list found', 'traceback': 'Traceback (most recent call last):\n  File '/workspace/kernel_orchestrator.py', line 66, in handle_request\n    return await self.get_variables(req)\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File '/workspace/kernel_orchestrator.py', line 240, in get_variables\n    reply = await self._run_silent_code(entry.client, code)\n            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File '/workspace/kernel_orchestrator.py', line 340, in _run_silent_code\n    return ''.join(stdout_parts)\n           ^^^^^^^^^^^^^^^^^^^^^\nTypeError: sequence item 0: expected str instance, list found\n'}")