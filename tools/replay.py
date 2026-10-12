#!/usr/bin/env python3
"""Inspect or play a recording without starting the terminal UI.

Examples:
    python3 tools/replay.py validate party.json
    python3 tools/replay.py play party.json

Both commands print JSON on stdout and report input errors on stderr.
They never edit the recording or write scores to the player's storage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Direct execution also works from outside the repository checkout.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pvz.replay import ReplayError, load_replay, play_replay


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Проверка и воспроизведение записей без curses.")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Проверить формат записи и ограничения ввода")
    validate.add_argument("file", type=Path, help="JSON-файл записи")
    play = commands.add_parser("play", help="Воспроизвести партию и вывести итоговую статистику")
    play.add_argument("file", type=Path, help="JSON-файл записи")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        replay = load_replay(args.file)
        result: dict[str, object] = {
            "schema_version": replay.schema_version, "seed": replay.seed,
            "scenario": replay.scenario, "difficulty": replay.difficulty,
        }
        if args.command == "validate":
            result.update(format_valid=True, duration=replay.duration, actions=len(replay.actions))
        else:
            result["stats"] = play_replay(replay).stats
    except ReplayError as exc:
        print(f"Ошибка записи: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
