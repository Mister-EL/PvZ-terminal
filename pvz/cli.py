from __future__ import annotations

import argparse
import curses
import signal
import sys
import time
from typing import List, Optional

from .game import Game


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Мини Plants vs Zombies (curses).")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Зерно генератора случайных чисел",
    )
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

    tick_seconds = max(10, args.tick_ms) / 1000.0

    game = Game(tick_seconds=tick_seconds, seed=args.seed)

    def handle_interrupt(signum: int, frame: Optional[object]) -> None:
        game.game_over = True
        game.game_over_reason = "Game Over"
        raise KeyboardInterrupt

    old_handler = signal.signal(signal.SIGINT, handle_interrupt)
    stdscr: Optional[curses.window] = None
    try:
        stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        game.run(stdscr)
    except KeyboardInterrupt:
        if stdscr is not None:
            stdscr.nodelay(False)
            stdscr.erase()
            stdscr.addstr(0, 0, f"Game Over! Итоговый счёт: {game.score}")
            stdscr.refresh()
            time.sleep(1.5)
    finally:
        signal.signal(signal.SIGINT, old_handler)
        game.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
