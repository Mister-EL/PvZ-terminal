#!/usr/bin/env python3
"""Render a real, legally played Game frame as a dependency-free SVG.

Run from the repository: python3 tools/render_preview.py
The checked solution provides inputs; draw_game provides every terminal cell.
"""
from __future__ import annotations

import argparse
import curses
from html import escape
import json
import math
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz.constants import SIMULATION_STEP
from pvz.content import load_scenario
from pvz.game import Game
from pvz.recording import MatchRecording
from pvz.replay import game_stats, play_replay
from pvz.types import PlantType
from pvz.ui import draw_game

SCENARIO = "campaign-15-last-bell"
COLS, ROWS = 80, 24
CELL_WIDTH, LINE_HEIGHT = 12.2, 24
ORIGIN_X, ORIGIN_Y = 36, 89
WIDTH, HEIGHT = 1048, 724


class FrameWindow:
    """Capture the same bounded cells that a curses window would receive."""

    def __init__(self):
        self.erase()

    def getmaxyx(self):
        return ROWS, COLS

    def erase(self):
        self.cells = [[(" ", 0) for _ in range(COLS)] for _ in range(ROWS)]

    def addstr(self, row, col, text, style=0):
        for offset, char in enumerate(text):
            if 0 <= row < ROWS and 0 <= col + offset < COLS:
                self.cells[row][col + offset] = (char, style)

    def refresh(self):
        pass


def play_solution(seconds):
    scenario = load_scenario(SCENARIO)
    game = Game(SIMULATION_STEP, scenario=scenario)
    recording = MatchRecording(game)
    route = json.loads((ROOT / "docs/scenarios/solutions" / f"{SCENARIO}.json").read_text())

    def advance(target):
        while game.time_elapsed + 1e-9 < target and not game.game_over:
            game.step()
        if game.game_over:
            raise ValueError("Requested frame follows the end of the solution")

    def move(row, col):
        while game.cursor_row != row:
            recording.handle_keypress(ord("s" if game.cursor_row < row else "w"))
        while game.cursor_col != col:
            recording.handle_keypress(ord("d" if game.cursor_col < col else "a"))

    for action in route["actions"]:
        if action["time"] > seconds:
            break
        advance(action["time"])
        move(action["row"], action["col"])
        slot = tuple(PlantType).index(PlantType[action["plant"]]) + 1
        recording.handle_keypress(ord(str(slot)))
        before = game.plants_placed
        recording.handle_keypress(ord(" "))
        if game.plants_placed != before + 1:
            raise ValueError(f"Illegal solution input at {action['time']}s")
    advance(seconds)
    stats = game_stats(game)
    if play_replay(recording.finish()).stats != stats:
        raise ValueError("Preview inputs and deterministic playback disagree")
    return game, stats


def render_svg(game, stats):
    window = FrameWindow()
    draw_game(window, game)
    description = (f"Реальный кадр PvZ Terminal: {game.scenario.name}, "
                   f"{game.time_elapsed:.1f} игровой секунды, seed {game.seed}. "
                   "Поле 9 × 5, текущие растения, враги и показатели взяты из draw_game.")
    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title description">',
        '<title id="title">PvZ Terminal: защита пяти рядов</title>',
        f'<desc id="description">{escape(description)}</desc>',
        f'<metadata>{escape(json.dumps({"scenario": SCENARIO, "time": game.time_elapsed, "seed": game.seed, "state_sha256": stats["state_sha256"]}, sort_keys=True))}</metadata>',
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="18" fill="#111719"/>',
        f'<rect x="1" y="1" width="{WIDTH-2}" height="{HEIGHT-2}" rx="17" fill="none" stroke="#354145"/>',
        '<circle cx="29" cy="27" r="5" fill="#bd786b"/>',
        '<circle cx="47" cy="27" r="5" fill="#d6b46d"/>',
        '<circle cx="65" cy="27" r="5" fill="#a9c97f"/>',
        '<text x="91" y="32" fill="#c6d0ca" font-family="DejaVu Sans Mono, monospace" font-size="13">PVZ / TERMINAL</text>',
        f'<text x="{WIDTH-27}" y="32" text-anchor="end" fill="#7e9188" font-family="DejaVu Sans Mono, monospace" font-size="12">{SCENARIO} / seed {game.seed}</text>',
        f'<rect x="20" y="53" width="{WIDTH-40}" height="616" rx="8" fill="#171d1e" stroke="#293536"/>',
        '<g font-family="DejaVu Sans Mono, monospace" font-size="18">',
    ]
    for row, cells in enumerate(window.cells):
        start = 0
        while start < COLS:
            style = cells[start][1]
            end = start + 1
            while end < COLS and cells[end][1] == style:
                end += 1
            text = "".join(char for char, _ in cells[start:end])
            if text.strip():
                x, y = ORIGIN_X + start * CELL_WIDTH, ORIGIN_Y + row * LINE_HEIGHT
                color = "#eef2e8"
                if style & curses.A_REVERSE:
                    output.append(f'<rect x="{x:.1f}" y="{y-19:.1f}" width="{len(text)*CELL_WIDTH:.1f}" height="24" rx="2" fill="#eef2e8"/>')
                    color = "#171d1e"
                weight = ' font-weight="700"' if style & curses.A_BOLD else ""
                # Explicit glyph positions preserve terminal spacing in every
                # SVG renderer; textLength can stretch collapsed whitespace.
                visible = [(offset, char) for offset, char in enumerate(text) if not char.isspace()]
                positions = " ".join(f"{x + offset * CELL_WIDTH:.1f}" for offset, _ in visible)
                glyphs = "".join(char for _, char in visible)
                output.append(f'<text x="{positions}" y="{y:.1f}" fill="{color}"{weight}>{escape(glyphs)}</text>')
            start = end
    output.extend([
        '</g>',
        f'<text x="25" y="701" fill="#9fb49f" font-family="DejaVu Sans Mono, monospace" font-size="12">Реальная симуляция / {game.time_elapsed:.1f} с / разрешённые действия из проверочного маршрута</text>',
        '</svg>',
    ])
    svg = "\n".join(output) + "\n"
    ET.fromstring(svg)
    return svg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--time", type=float, default=106.0, help="Simulation seconds, aligned to .05")
    parser.add_argument("--output", type=Path, default=ROOT / "assets/gameplay.svg")
    args = parser.parse_args()
    if not math.isfinite(args.time) or not 0 <= args.time <= 7200 or abs(args.time / SIMULATION_STEP - round(args.time / SIMULATION_STEP)) > 1e-8:
        parser.error("--time must be finite, in 0..7200 and aligned to .05 seconds")
    game, stats = play_solution(args.time)
    svg = render_svg(game, stats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".pvz-preview-", suffix=".svg", dir=args.output.parent, delete=False) as target:
        temporary = Path(target.name)
        target.write(svg)
    try:
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({"output": str(args.output), "stats": stats, "input_playback_equal": True}, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
