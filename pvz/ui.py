"""Terminal presentation. Simulation never depends on drawing or window size."""
from __future__ import annotations

import curses
import unicodedata

from .constants import GRID_HEIGHT, GRID_WIDTH, PLANT_DESCRIPTIONS, PLANT_NAMES
from .types import PlantType

MIN_ROWS, MIN_COLS = 24, 76


def clip_text(text: str, width: int) -> str:
    """Clip by terminal columns, including wide and combining characters."""
    result, used = [], 0
    for char in str(text):
        if unicodedata.category(char).startswith("C"):
            continue
        size = 0 if unicodedata.combining(char) else (2 if unicodedata.east_asian_width(char) in "WF" else 1)
        if used + size > max(0, width):
            break
        if size or result:
            result.append(char)
        used += size
    return "".join(result)


class Screen:
    def __init__(self, window):
        self.window = window

    @property
    def size(self):
        return self.window.getmaxyx()

    @property
    def playable(self):
        rows, cols = self.size
        return rows >= MIN_ROWS and cols >= MIN_COLS

    def put(self, y, x, text, style=0):
        rows, cols = self.size
        if y < 0 or y >= rows or x < 0 or x >= cols - 1:
            return
        value = clip_text(text, cols - x - 1)
        if value:
            try:
                self.window.addstr(y, x, value, style)
            except curses.error:
                # A resize can race a drawing operation; the next frame redraws.
                pass

    def resize_notice(self):
        self.window.erase()
        self.put(0, 0, "PVZ / TERMINAL")
        self.put(2, 0, f"Увеличьте окно до {MIN_COLS}×{MIN_ROWS}.")
        self.put(4, 0, "Игра остановлена. Q — выход.")
        self.window.refresh()


def draw_game(window, game, final=False):
    screen = Screen(window)
    if not screen.playable:
        screen.resize_notice()
        return
    window.erase()
    title = game.scenario.name if game.scenario else "Выживание"
    state = "ПОБЕДА" if game.victory else ("КОНЕЦ ИГРЫ" if game.game_over else ("ПАУЗА" if game.paused else "В БОЙ"))
    screen.put(0, 2, f"PVZ / TERMINAL   {title}   /   {state}", curses.A_BOLD)
    screen.put(1, 2, f"Солнце {game.sun:4}   Счёт {game.score:4}   Время {game.time_elapsed:5.1f}с   Косилки {sum(game.lawnmowers)}/5")
    if game.scenario:
        remaining = sum(len(w.spawns) for w in game.scenario.waves) - game.zombies_killed
        wave = f"Волна {game.wave_number}/{game.wave_total}   Осталось врагов {remaining}"
    else:
        wave = f"Бесконечные волны   Уничтожено {game.zombies_killed}"
    next_spawn = game.next_spawn_in()
    screen.put(2, 2, wave + (f"   Следующий через {next_spawn:.1f}с" if next_spawn is not None else ""))
    screen.put(3, 2, f"{PLANT_NAMES[game.selected]}: {PLANT_DESCRIPTIONS[game.selected]}")
    screen.put(4, 2, "РЯД  КОС " + "".join(f"  {col+1}   " for col in range(GRID_WIDTH)))
    screen.put(5, 2, "---------+" + "------" * GRID_WIDTH)
    for row in range(GRID_HEIGHT):
        y = 6 + row * 2
        screen.put(y, 2, f" {row+1}    {'*' if game.lawnmowers[row] else '-'}  |")
        for col in range(GRID_WIDTH):
            x = 12 + col * 6
            plant = game.grid.get(row, col)
            enemies = [z for z in game.zombies if z.row == row and z.col == col]
            flying = any(p.row == row and int(p.col) == col for p in game.projectiles)
            glyph = plant.plant_type.value if plant else ("o" if flying else ".")
            if enemies:
                glyph = (glyph if plant else "") + enemies[0].char
                if len(enemies) > 1:
                    glyph += str(len(enemies))
            focused = (row, col) == (game.cursor_row, game.cursor_col) and not final
            screen.put(y, x, f"[{glyph:^3}]" if focused else f" {glyph:^3} ", curses.A_REVERSE if focused else 0)
            detail = f"{plant.hp:.0f}hp" if plant else ""
            if enemies:
                detail = f"{enemies[0].hp + enemies[0].shield_hp:.0f}hp"
            screen.put(y + 1, x, detail)
    screen.put(16, 2, "---------+" + "------" * GRID_WIDTH)
    for slot, kind in enumerate(PlantType, 1):
        y, x = 18 + (slot - 1) // 3, 2 + ((slot - 1) % 3) * 24
        cooldown = game.cooldown_remaining(kind)
        readiness = "--" if kind not in game.allowed_plants else (f"{cooldown:.0f}с" if cooldown > 0 else "OK")
        name = clip_text(PLANT_NAMES[kind], 12)
        screen.put(y, x, f"{slot}{kind.value} {name:12} {game.plant_cost(kind):3} {readiness:>3}", curses.A_BOLD if kind == game.selected else 0)
    plant = game.grid.get(game.cursor_row, game.cursor_col)
    message = game.current_message() or (game.plant_status(plant) if plant else (game.planting_error() or "Клетка свободна"))
    screen.put(21, 2, message)
    screen.put(22, 2, "WASD/стрелки: клетка  1–9: выбор  Пробел: посадить  R: выкопать")
    screen.put(23, 2, "P: пауза  ?: справка  Q: меню")
    window.refresh()
