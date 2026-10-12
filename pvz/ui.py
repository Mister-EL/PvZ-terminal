"""Terminal presentation. Simulation never depends on drawing or window size."""
from __future__ import annotations

import curses
import time
import textwrap
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


DIFFICULTY_NAMES = {"easy": "Лёгкая", "normal": "Обычная", "hard": "Сложная"}


class TerminalApp:
    def __init__(self, window, *, tick_seconds=.2, seed=None, difficulty="normal"):
        self.window = window
        self.screen = Screen(window)
        self.tick_seconds, self.seed, self.difficulty = tick_seconds, seed, difficulty
        window.keypad(True)
        window.timeout(100)
        try:
            curses.curs_set(0)
        except curses.error:
            pass

    def choose(self, title, choices, descriptions=None):
        if not choices:
            self.message("Пока пусто", ["В этом разделе нет сценариев."])
            return None
        selected = 0
        while True:
            if not self.screen.playable:
                self.screen.resize_notice()
            else:
                rows, cols = self.screen.size
                self.window.erase()
                self.screen.put(1, 4, "PVZ / TERMINAL", curses.A_BOLD)
                self.screen.put(3, 4, title, curses.A_BOLD)
                page_size = max(1, rows - 12)
                start = (selected // page_size) * page_size
                for i in range(start, min(len(choices), start + page_size)):
                    focused = i == selected
                    self.screen.put(5 + i - start, 4, ("> " if focused else "  ") + choices[i], curses.A_REVERSE if focused else 0)
                if descriptions:
                    for i, line in enumerate(textwrap.wrap(descriptions[selected], width=cols-9)[:3]):
                        self.screen.put(rows - 6 + i, 4, line)
                self.screen.put(rows - 3, 4, f"{selected+1}/{len(choices)}   Стрелки/W/S: выбрать   Enter: открыть   Q/Esc: назад")
                self.window.refresh()
            key = self.window.getch()
            if key in (ord("q"), ord("Q"), 27):
                return None
            if not self.screen.playable:
                continue
            if key in (curses.KEY_UP, ord("w"), ord("W"), ord("k")):
                selected = (selected - 1) % len(choices)
            elif key in (curses.KEY_DOWN, ord("s"), ord("S"), ord("j")):
                selected = (selected + 1) % len(choices)
            elif key == curses.KEY_NPAGE:
                selected = min(len(choices) - 1, selected + page_size)
            elif key == curses.KEY_PPAGE:
                selected = max(0, selected - page_size)
            elif key in (10, 13, curses.KEY_ENTER, ord(" ")):
                return selected

    def message(self, title, lines):
        top = 0
        while True:
            if not self.screen.playable:
                self.screen.resize_notice()
                key = self.window.getch()
                if key in (27, ord("q"), ord("Q")):
                    return False
                continue
            rows, cols = self.screen.size
            wrapped = [part for line in lines for part in (textwrap.wrap(line, width=cols-7) or [""])]
            page_size = rows - 6
            top = min(top, max(0, len(wrapped) - page_size))
            self.window.erase()
            self.screen.put(1, 3, title, curses.A_BOLD)
            for y, line in enumerate(wrapped[top:top+page_size], 3):
                self.screen.put(y, 3, line)
            more = "   Стрелки: листать" if len(wrapped) > page_size else ""
            self.screen.put(rows - 2, 3, "Enter: продолжить   Q/Esc: назад" + more)
            self.window.refresh()
            key = self.window.getch()
            if key in (10, 13, curses.KEY_ENTER, ord(" ")):
                return True
            if key in (27, ord("q"), ord("Q")):
                return False
            if key in (curses.KEY_DOWN, curses.KEY_NPAGE, ord("s")):
                top = min(max(0, len(wrapped) - page_size), top + (page_size if key == curses.KEY_NPAGE else 1))
            elif key in (curses.KEY_UP, curses.KEY_PPAGE, ord("w")):
                top = max(0, top - (page_size if key == curses.KEY_PPAGE else 1))

    def catalogue(self, kind):
        from .content import list_scenarios
        scenarios = list_scenarios(kind)
        labels = [f"{i+1:02}  {s.name}  /  {len(s.waves)} волн" for i, s in enumerate(scenarios)]
        selected = self.choose("Кампания" if kind == "campaign" else "Испытания", labels, [s.description for s in scenarios])
        if selected is not None:
            scenario = scenarios[selected]
            if self.message(scenario.name, [scenario.description, "", scenario.objective, "", f"Начальное солнце: {scenario.sun}", f"Врагов: {scenario.zombie_count}   Волны: {len(scenario.waves)}", "", "Первые враги придут после подготовки. Начните с защиты рядов."]):
                self.session(scenario)

    def run(self):
        while True:
            choice = self.choose("Защитите пять рядов до последнего зомби.", ["Кампания", "Испытания", "Выживание", "Сложность: " + DIFFICULTY_NAMES[self.difficulty], "Управление и растения", "Выход"])
            if choice is None or choice == 5:
                return
            if choice in (0, 1):
                self.catalogue("campaign" if choice == 0 else "challenge")
            elif choice == 2:
                self.session()
            elif choice == 3:
                index = self.choose("Сложность", list(DIFFICULTY_NAMES.values()), ["Меньше здоровья, урона и скорости врагов.", "Исходные значения: тактика и экономика.", "Больше здоровья, урона и скорости врагов."])
                if index is not None:
                    self.difficulty = tuple(DIFFICULTY_NAMES)[index]
            elif choice == 4:
                self.help()

    def help(self):
        self.message("Управление", ["WASD или стрелки — выбрать клетку. 1–9 — выбрать растение.", "Пробел — посадить. R — выкопать без возврата солнца.", "P — пауза. ? — эта справка, время в ней остановлено.", "Q — вернуться в меню. Enter в меню — выбрать.", "", "P горох, S подсолнух, W орех, C зубастик, I лёд, X вишня,", "D двойной горох, M мина, F двойной подсолнух.", "", "z обычный, Z конус, B ведро, r бегун, H щитоносец.", "* слева — газонокосилка: одна последняя защита на ряд.", "hp под клеткой — здоровье растения или ближайшего врага.", "", "Защищайте все ряды. Подсолнухи приносят доход каждые4с.", "Мине нужно12с подготовки. Вишня взрывает область3×3.", "Щит блокирует лёд, но не контактные взрывы."])

    def session(self, scenario=None):
        from .game import Game
        while True:
            game = Game(self.tick_seconds, self.seed, scenario=scenario, difficulty=self.difficulty)
            self.play(game)
            if game.game_over_reason == "Выход":
                return
            result = "Победа!" if game.victory else "Оборона прорвана"
            choice = self.choose(f"{result}   Счёт {game.score}   Время {game.time_elapsed:.1f}с", ["Повторить", "Вернуться в меню"], [f"Уничтожено{game.zombies_killed}, посажено{game.plants_placed}, потеряно{game.plants_lost}", f"Потрачено косилок: {game.lawnmowers_used}"])
            if choice != 0:
                return

    def play(self, game):
        previous = time.monotonic()
        accumulator = 0.0
        while not game.game_over:
            now = time.monotonic()
            delta, previous = min(now - previous, .5), now
            playable = self.screen.playable
            if playable and not game.paused:
                accumulator += delta
                while accumulator >= game.tick_seconds and not game.game_over:
                    game.step()
                    accumulator -= game.tick_seconds
            else:
                accumulator = 0.0
            draw_game(self.window, game)
            key = self.window.getch()
            if key in (ord("q"), ord("Q"), 27):
                game.handle_keypress(ord("q"))
            elif key in (ord("?"), ord("h"), ord("H")):
                self.help()
                previous, accumulator = time.monotonic(), 0.0
            elif playable:
                direction = {curses.KEY_UP: "w", curses.KEY_DOWN: "s", curses.KEY_LEFT: "a", curses.KEY_RIGHT: "d"}
                game.handle_keypress(ord(direction[key]) if key in direction else key)
        draw_game(self.window, game, final=True)
