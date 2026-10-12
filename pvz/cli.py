from __future__ import annotations

import argparse
import curses
import os
from pathlib import Path
import sys
from typing import List, Optional

from .content import ContentError, list_scenarios, load_scenario
from .ui import TerminalApp
from .progress import ProgressStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Мини Plants vs Zombies (curses).")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Зерно генератора случайных чисел",
    )
    parser.add_argument("--difficulty", choices=("easy", "normal", "hard"), default="normal", help="Сложность")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--scenario", help="Начать сценарий по его идентификатору")
    modes.add_argument("--survival", action="store_true", help="Сразу начать выживание")
    modes.add_argument("--list-scenarios", action="store_true", help="Список сценариев без запуска терминального интерфейса")
    parser.add_argument("--no-save", action="store_true", help="Играть без записи прогресса")
    parser.add_argument("--progress-file", type=Path, help="Путь к файлу прогресса")
    parser.add_argument(
        "--tick-ms",
        type=int,
        default=200,
        help="Длительность тика в миллисекундах (по умолчанию: 200)",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not 10 <= args.tick_ms <= 1000:
        parser.error("--tick-ms: допустимо10..1000мс")
    try:
        if args.list_scenarios:
            for scenario in list_scenarios():
                print(f"{scenario.id}\t{scenario.name}\t{scenario.zombie_count} врагов")
            return 0
        scenario = load_scenario(args.scenario) if args.scenario else None
    except ContentError as exc:
        parser.error(str(exc))
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Для игры нужен интерактивный терминал. Список уровней: --list-scenarios", file=sys.stderr)
        return 2
    def launch(window):
        state_home = Path(os.environ.get("XDG_STATE_HOME", "")).expanduser()
        if not state_home.is_absolute():
            state_home = Path.home() / ".local" / "state"
        progress = None if args.no_save else ProgressStore(args.progress_file or state_home / "pvz-terminal" / "progress.json").load()
        app = TerminalApp(window, tick_seconds=args.tick_ms / 1000, seed=args.seed, difficulty=args.difficulty, progress=progress)
        if progress and progress.load_error:
            app.message("Файл прогресса не прочитан", ["Повреждённый файл останется без изменений.", "Играйте с --no-save или укажите другой --progress-file."])
        if args.scenario or args.survival:
            app.session(scenario)
        else:
            app.run()
    try:
        curses.wrapper(launch)
    except KeyboardInterrupt:
        return 130
    except curses.error as exc:
        print(f"Терминал не поддерживает curses: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
