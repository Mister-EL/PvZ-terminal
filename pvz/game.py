from __future__ import annotations

import curses
import random
import time
from typing import Dict, List, Optional

from .constants import (
    CHOMPER_CHEW_TIME,
    GRID_HEIGHT,
    GRID_WIDTH,
    MESSAGE_DURATION,
    PEASHOOTER_INTERVAL,
    PLANT_COOLDOWNS,
    PLANT_COSTS,
    PLANT_HEALTH,
    PROJECTILE_DAMAGE,
    PROJECTILE_SPEED_CELLS_PER_TICK,
    STATUS_LINE_TEMPLATE,
    SUNFLOWER_INTERVAL,
    SUN_START,
    ZOMBIE_DPS,
    ZOMBIE_HEALTH,
    ZOMBIE_MOVE_INTERVAL,
    ZOMBIE_SCORE,
)
from .grid import Grid
from .types import Plant, PlantType, Projectile, Zombie, ZombieType


class Game:
    def __init__(self, tick_seconds: float, seed: Optional[int] = None) -> None:
        self.tick_seconds = tick_seconds
        self.grid = Grid(GRID_WIDTH, GRID_HEIGHT)
        self.projectiles: List[Projectile] = []
        self.zombies: List[Zombie] = []
        self.sun: int = SUN_START
        self.score: int = 0
        self.selected: PlantType = PlantType.PEASHOOTER
        self.cursor_row = 2
        self.cursor_col = 1
        self.time_elapsed = 0.0
        self.paused = False
        self.game_over = False
        self.game_over_reason: Optional[str] = None
        self.message: Optional[str] = None
        self._message_expires_at: float = 0.0
        self._plant_ready_at: Dict[PlantType, float] = {
            plant: 0.0 for plant in PlantType
        }
        self._next_spawn_time = 6.0
        self._rng = random.Random(seed)
        self._stdscr: Optional[curses.window] = None

    # --- Жизненный цикл игры -------------------------------------------------
    def setup_curses(self, stdscr: curses.window) -> None:
        self._stdscr = stdscr
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        stdscr.nodelay(True)
        stdscr.keypad(True)

    def run(self, stdscr: curses.window) -> None:
        self.setup_curses(stdscr)

        while not self.game_over:
            tick_start = time.monotonic()
            self.process_input()

            if not self.paused and not self.game_over:
                self.step()

            self.render()

            elapsed = time.monotonic() - tick_start
            sleep_time = max(0.0, self.tick_seconds - elapsed)
            time.sleep(sleep_time)

        self.render(final=True)
        if self.game_over_reason == "Game Over":
            self.wait_for_exit()

    def cleanup(self) -> None:
        if self._stdscr is not None:
            try:
                curses.curs_set(1)
            except curses.error:
                pass
            curses.nocbreak()
            self._stdscr.keypad(False)
            curses.echo()
            curses.endwin()
            self._stdscr = None

    # --- Основной цикл ------------------------------------------------------
    def step(self) -> None:
        self.time_elapsed += self.tick_seconds
        self.update_timers()
        self.move_projectiles()
        self.handle_attacks()
        self.spawn_and_move_zombies()
        self.generate_sun()
        self.check_loss()

    # --- Обработка ввода ----------------------------------------------------
    def process_input(self) -> None:
        if self._stdscr is None:
            return

        while True:
            key = self._stdscr.getch()
            if key == -1:
                break
            self.handle_keypress(key)

    def handle_keypress(self, key: int) -> None:
        if key in (ord("q"), ord("Q")):
            self.game_over = True
            self.game_over_reason = "Выход"
            return
        if key in (ord("p"), ord("P")):
            self.paused = not self.paused
            return
        if key in (ord("w"), ord("W")):
            self.cursor_row = max(0, self.cursor_row - 1)
        elif key in (ord("s"), ord("S")):
            self.cursor_row = min(GRID_HEIGHT - 1, self.cursor_row + 1)
        elif key in (ord("a"), ord("A")):
            self.cursor_col = max(0, self.cursor_col - 1)
        elif key in (ord("d"), ord("D")):
            self.cursor_col = min(GRID_WIDTH - 1, self.cursor_col + 1)
        elif key in (ord("1"), ord("2"), ord("3"), ord("4")):
            self.select_plant_type(int(chr(key)))
        elif key == ord(" "):
            self.place_selected()
        elif key in (ord("r"), ord("R")):
            self.dig_up()

    def select_plant_type(self, slot: int) -> None:
        mapping = {
            1: PlantType.PEASHOOTER,
            2: PlantType.SUNFLOWER,
            3: PlantType.WALL_NUT,
            4: PlantType.CHOMPER,
        }
        if slot in mapping:
            self.selected = mapping[slot]

    def place_selected(self) -> None:
        plant_type = self.selected
        row, col = self.cursor_row, self.cursor_col
        if self.grid.get(row, col):
            self.show_message("клетка занята")
            return
        cost = PLANT_COSTS[plant_type]
        if self.sun < cost:
            self.show_message("недостаточно Sun")
            return
        ready_at = self._plant_ready_at[plant_type]
        if self.time_elapsed < ready_at:
            self.show_message("КД не прошёл")
            return

        plant = Plant(
            plant_type=plant_type,
            row=row,
            col=col,
            hp=float(PLANT_HEALTH[plant_type]),
            last_action_time=self.time_elapsed,
        )
        self.grid.set(plant)
        self.sun -= cost
        self._plant_ready_at[plant_type] = self.time_elapsed + PLANT_COOLDOWNS[plant_type]

    def dig_up(self) -> None:
        plant = self.grid.get(self.cursor_row, self.cursor_col)
        if plant:
            self.grid.remove(self.cursor_row, self.cursor_col)

    # --- Обновление состояния -----------------------------------------------
    def update_timers(self) -> None:
        now = time.monotonic()
        if self.message and now > self._message_expires_at:
            self.message = None

        for plant in self.grid.iter_plants():
            if (
                plant.plant_type == PlantType.CHOMPER
                and plant.chewing_until
                and self.time_elapsed >= plant.chewing_until
            ):
                plant.chewing_until = 0.0

    def move_projectiles(self) -> None:
        new_projectiles: List[Projectile] = []
        for projectile in self.projectiles:
            projectile.col += PROJECTILE_SPEED_CELLS_PER_TICK
            if projectile.col >= GRID_WIDTH:
                continue
            target = self.find_zombie_in_cell(projectile.row, projectile.col)
            if target:
                target.hp -= PROJECTILE_DAMAGE
                if target.hp <= 0:
                    self.score += ZOMBIE_SCORE[target.zombie_type]
                    if target in self.zombies:
                        self.zombies.remove(target)
                continue
            new_projectiles.append(projectile)
        self.projectiles = new_projectiles
        self.cleanup_dead_zombies()

    def handle_attacks(self) -> None:
        for plant in self.grid.iter_plants():
            if plant.plant_type == PlantType.PEASHOOTER:
                if (
                    self.time_elapsed - plant.last_action_time >= PEASHOOTER_INTERVAL
                    and self.any_zombie_to_right(plant.row, plant.col)
                ):
                    shot_col = plant.col + 1
                    if shot_col < GRID_WIDTH:
                        self.projectiles.append(Projectile(row=plant.row, col=shot_col))
                    plant.last_action_time = self.time_elapsed
            elif plant.plant_type == PlantType.CHOMPER:
                if plant.is_chewing(self.time_elapsed):
                    continue
                target = self.find_zombie_in_cell(plant.row, plant.col)
                if target:
                    self.score += ZOMBIE_SCORE[target.zombie_type]
                    self.zombies.remove(target)
                    plant.chewing_until = self.time_elapsed + CHOMPER_CHEW_TIME
            # Подсолнух и Орех обрабатываются в других методах.

        self.cleanup_dead_zombies()

    def spawn_and_move_zombies(self) -> None:
        if self.time_elapsed >= self._next_spawn_time:
            self.spawn_zombie()

        for zombie in list(self.zombies):
            zombie.move_progress += self.tick_seconds
            plant = self.grid.get(zombie.row, zombie.col)
            if plant:
                plant.hp -= ZOMBIE_DPS[zombie.zombie_type] * self.tick_seconds
                if plant.hp <= 0:
                    self.grid.remove(plant.row, plant.col)
                continue

            while zombie.move_progress >= ZOMBIE_MOVE_INTERVAL:
                zombie.move_progress -= ZOMBIE_MOVE_INTERVAL
                target_col = zombie.col - 1
                if target_col < 0:
                    zombie.col = target_col
                    break
                occupant = self.grid.get(zombie.row, target_col)
                zombie.col = target_col
                if occupant:
                    break

        self.cleanup_dead_plants()

    def generate_sun(self) -> None:
        for plant in self.grid.iter_plants():
            if plant.plant_type == PlantType.SUNFLOWER:
                if self.time_elapsed - plant.last_action_time >= SUNFLOWER_INTERVAL:
                    self.sun += 25
                    plant.last_action_time = self.time_elapsed

    def check_loss(self) -> None:
        for zombie in self.zombies:
            if zombie.col < 0:
                self.game_over = True
                self.game_over_reason = "Game Over"
                return

    # --- Вспомогательные методы для зомби -----------------------------------
    def spawn_zombie(self) -> None:
        row = self._rng.randrange(GRID_HEIGHT)
        z_type = self.pick_zombie_type()
        zombie = Zombie(
            zombie_type=z_type,
            row=row,
            col=GRID_WIDTH - 1,
            hp=float(ZOMBIE_HEALTH[z_type]),
        )
        self.zombies.append(zombie)
        interval = 6.0 if self.time_elapsed < 60.0 else 3.0
        self._next_spawn_time = self.time_elapsed + interval

    def pick_zombie_type(self) -> ZombieType:
        shift_steps = int(self.time_elapsed // 45)
        total_shift = min(shift_steps * 0.05, 0.3)
        z_weight = 0.6 - total_shift
        z_weight = max(z_weight, 0.3)
        remaining_shift = 0.6 - z_weight
        cone_weight = 0.3 + remaining_shift / 3.0
        bucket_weight = 0.1 + remaining_shift * 2.0 / 3.0
        weights = [z_weight, cone_weight, bucket_weight]
        choice = self._rng.choices(
            population=[ZombieType.NORMAL, ZombieType.CONE, ZombieType.BUCKET],
            weights=weights,
            k=1,
        )[0]
        return choice

    def cleanup_dead_zombies(self) -> None:
        self.zombies = [z for z in self.zombies if z.hp > 0]

    def cleanup_dead_plants(self) -> None:
        for plant in list(self.grid.iter_plants()):
            if plant.hp <= 0:
                self.grid.remove(plant.row, plant.col)

    # --- Служебные запросы --------------------------------------------------
    def any_zombie_to_right(self, row: int, col: int) -> bool:
        return any(z.row == row and z.col > col for z in self.zombies)

    def find_zombie_in_cell(self, row: int, col: int) -> Optional[Zombie]:
        for zombie in self.zombies:
            if zombie.row == row and zombie.col == col:
                return zombie
        return None

    # --- Сообщения ----------------------------------------------------------
    def show_message(self, text: str) -> None:
        self.message = text
        self._message_expires_at = time.monotonic() + MESSAGE_DURATION

    def current_message(self) -> str:
        if self.message and time.monotonic() <= self._message_expires_at:
            return self.message
        return ""

    # --- Отрисовка ----------------------------------------------------------
    def render(self, final: bool = False) -> None:
        if self._stdscr is None:
            return

        stdscr = self._stdscr
        stdscr.erase()

        status = STATUS_LINE_TEMPLATE.format(
            sun=self.sun,
            score=self.score,
            sel=self.selected.value,
        )
        stdscr.addstr(0, 0, status)

        for row in range(GRID_HEIGHT):
            line_chars: List[str] = []
            for col in range(GRID_WIDTH):
                cell_char = "."
                zombie = self.find_zombie_in_cell(row, col)
                plant = self.grid.get(row, col)
                if zombie:
                    cell_char = zombie.char
                elif plant:
                    cell_char = plant.plant_type.value
                elif any(p.row == row and p.col == col for p in self.projectiles):
                    cell_char = "*"

                if row == self.cursor_row and col == self.cursor_col and not final:
                    line_chars.append(f"[{cell_char}]")
                else:
                    line_chars.append(f" {cell_char} ")
            line = "".join(line_chars)
            stdscr.addstr(row + 1, 0, line)

        footer_row = GRID_HEIGHT + 1
        message = ""
        if final:
            reason = self.game_over_reason or "Game Over"
            message = f"{reason}! Итоговый счёт: {self.score}"
        else:
            message = self.current_message()
            if self.paused:
                pause_info = " [Пауза]"
                message = (message + pause_info) if message else pause_info.strip()

        stdscr.addstr(footer_row + 1, 0, message)
        stdscr.refresh()

    def wait_for_exit(self) -> None:
        if self._stdscr is None:
            return
        stdscr = self._stdscr
        stdscr.nodelay(False)
        stdscr.addstr(GRID_HEIGHT + 2, 0, "Нажмите любую клавишу для выхода")
        stdscr.refresh()
        stdscr.getch()
