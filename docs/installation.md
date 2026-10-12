# Установка и запуск

Нужен Python 3.12 или новее со стандартным модулем `curses`. Игра рассчитана на Linux
и macOS, интерактивный терминал и окно от 76×24 символов. Внешних библиотек у игры
нет. Стандартная сборка Python для Windows не содержит `curses`.

## Из исходников

В каталоге репозитория:

```bash
python3 -m pvz --list-scenarios
python3 -m pvz
```

## Установленный пакет

Создайте виртуальное окружение и установите checkout. `setuptools` и `wheel` нужны
только для сборки, а не для игры. При обычной установке pip может получить их из
индекса пакетов:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/pvz-terminal --list-scenarios
.venv/bin/pvz-terminal
```

Команда `pvz-terminal` и `python -m pvz` принимают одинаковые параметры. После
установки их можно запускать из любого каталога; JSON всех сценариев находится
внутри пакета.

## Сборка и установка без сети

Если в выбранном Python уже есть `build`, `setuptools>=68` и `wheel`, можно
собрать wheel без загрузки зависимостей:

```bash
python3 -m build --wheel --no-isolation
.venv/bin/python -m pip install --no-index --no-deps dist/pvz_terminal-0.2.0-py3-none-any.whl
```

В wheel входят только пакет `pvz` и сценарии `campaign-*.json` / `challenge-*.json`.
Тесты, Git, личные сохранения и исходные доказательства прохождения туда не входят.

## Прогресс

Прогресс хранится в `$XDG_STATE_HOME/pvz-terminal/progress.json`, а при отсутствии
абсолютного `XDG_STATE_HOME` — в `~/.local/state/pvz-terminal/progress.json`.
Параметр `--progress-file /путь/к/progress.json` задаёт другой файл; `--no-save`
отключает запись прогресса. Просмотр списка сценариев не создаёт сохранения.
