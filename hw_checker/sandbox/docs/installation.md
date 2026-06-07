# Установка и настройка

## Требования

- **Python 3.11+**
- **gVisor (runsc)** установлен и доступен в PATH

## Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/hw_checker/sandbox.git
cd sandbox
```

### 2. Установка зависимостей

```bash
# Создать виртуальное окружение (опционально)
python -m venv venv
source venv/bin/activate  # или venv\Scripts\activate на Windows

# Установить зависимости
pip install -e .
```

### 3. Установка gVisor

#### На Linux (Ubuntu/Debian)

```bash
# Скачать runsc
curl -fsSL https://gvisor.dev/archive/releases/release/latest/linux/runsc | sudo tee /usr/local/bin/runsc > /dev/null
sudo chmod +x /usr/local/bin/runsc

# Проверить
runsc --version
```

#### На macOS

```bash
# Через Homebrew (если доступно)
brew install gvisor-runsc
```

#### На Windows

*Примечание: gVisor поддержка на Windows ограничена. Рекомендуется использовать WSL2 или Docker.*

```bash
# Установить WSL2 и использовать Linux инструкции выше
```

### 4. Создание директорий

```bash
# Создать директорию для хранилища окружений
sudo mkdir -p USER_HOME.sandbox_data/venvs
sudo chown $USER:$USER USER_HOME.sandbox_data

# Создать директорию для контейнеров (если требуется)
mkdir -p USER_HOME.sandbox_data/containers
```

## Структура конфигурации

### Переменные окружения

```bash
# Стандартная директория хранилища venv
export SANDBOX_VENV_STORAGE=USER_HOME.sandbox_data/venvs

# Максимум ядер в контейнере
export SANDBOX_MAX_KERNELS=10

# TTL контейнера без ядер (сек)
export SANDBOX_CONTAINER_IDLE_TTL=300

# Интервал очистки (сек)
export SANDBOX_CLEANUP_INTERVAL=60
```

### Programmatic конфигурация

```python
from sandbox import SandboxManager

manager = SandboxManager(
    isolation="gvisor",
    venv_storage_path="USER_HOME.sandbox_data/venvs",
    container_idle_ttl=300,
    container_max_kernels=10,
    container_cleanup_interval=60,
)
```

## Проверка установки

```bash
# Запустить тесты
pytest tests/ -v

# Запустить пример
python examples/basic_usage.py
```

## Устранение неполадок

### gVisor не найден

```
Error: runsc: command not found
```

**Решение:** Убедитесь, что runsc установлен и добавлен в PATH:

```bash
which runsc
runsc --version
```

Если команда не найдена, переустановите gVisor.

### Ошибка прав доступа

```
Error: permission denied
```

**Решение:** runsc требует определённых прав. На Linux:

```bash
sudo usermod -aG docker $USER
# Или установить runsc с rootless поддержкой
runsc --rootless --help
```

### Ошибка подключения к контейнеру

```
Error: failed to connect to runsc container
```

**Решение:** Проверьте, что контейнер запущен корректно:

```bash
runsc list
```

Если список пуст или процесс умер, проверьте логи:

```bash
journalctl -u runsc -n 50
```

### Недостаточно памяти/CPU

```
Error: insufficient resources
```

**Решение:** Уменьшите лимиты в конфигурации:

```python
manager = SandboxManager(
    container_max_kernels=5,  # Вместо 10
)
```

Или запустите с меньшими ресурсами в `create_session`:

```python
session = await manager.create_session(
    venv_name="default",
    # В будущем: cpu_limit=0.5, memory_limit_mb=256
)
```

## Развёртывание

### Docker контейнер

Для удобства можно запушить Sandbox в Docker контейнере с gVisor:

```dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    curl

# Установить runsc
RUN curl -fsSL https://gvisor.dev/archive/releases/release/latest/linux/runsc | \
    tee /usr/local/bin/runsc > /dev/null && \
    chmod +x /usr/local/bin/runsc

# Установить Sandbox
COPY . /app
WORKDIR /app
RUN pip install -e .

CMD ["python"]
```

### Kubernetes

Sandbox может быть развёрнута в Kubernetes как StatefulSet:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: sandbox
spec:
  replicas: 3
  serviceName: sandbox-service
  selector:
    matchLabels:
      app: sandbox
  template:
    metadata:
      labels:
        app: sandbox
    spec:
      containers:
      - name: sandbox
        image: sandbox:latest
        resources:
          limits:
            cpu: "2"
            memory: "2Gi"
          requests:
            cpu: "1"
            memory: "1Gi"
        volumeMounts:
        - name: venv-storage
          mountPath: USER_HOME.sandbox_data/venvs
        - name: container-workspace
          mountPath: USER_HOME.sandbox_data/containers
  volumeClaimTemplates:
  - metadata:
      name: venv-storage
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 10Gi
  - metadata:
      name: container-workspace
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 20Gi
```

## Документация

- [Архитектура](architecture.md)
- [API Reference](api.md)
- [Примеры](../examples/)
