from __future__ import annotations

import curses
import math
import random
import time
from typing import Dict, List, Optional

from .constants import (
    CHOMPER_CHEW_TIME,
    DIFFICULTIES,
    GRID_HEIGHT,
    SIMULATION_STEP,
    GRID_WIDTH,
    MESSAGE_DURATION,
    PEASHOOTER_INTERVAL,
    PLANT_COOLDOWNS,
    PLANT_COSTS,
    PLANT_HEALTH,
    PROJECTILE_DAMAGE,
    PROJECTILE_SPEED_CELLS_PER_SECOND,
    STATUS_LINE_TEMPLATE,
    SUNFLOWER_INTERVAL,
    SKY_SUN_INTERVAL,
    SUN_AMOUNT,
    SUN_START,
    ZOMBIE_DPS,
    ZOMBIE_HEALTH,
    ZOMBIE_MOVE_INTERVAL,
    ZOMBIE_MOVE_INTERVALS,
    SHIELD_HEALTH,
    SLOW_DURATION,
    BOMB_FUSE,
    EXPLOSION_DAMAGE,
    MINE_ARM_TIME,
    ZOMBIE_SCORE,
)
from .grid import Grid
from .types import Plant, PlantType, Projectile, Zombie, ZombieType


class Game:
    def __init__(self, tick_seconds: float, seed: Optional[int] = None, *,
                 difficulty: str = "normal", scenario=None) -> None:
        if not math.isfinite(tick_seconds) or tick_seconds <= 0:
            raise ValueError("tick_seconds must be positive and finite")
        if difficulty not in DIFFICULTIES:
            raise ValueError("Unknown difficulty")
        self.tick_seconds = tick_seconds
        self._dt = tick_seconds
        self._time_accumulator = 0.0
        self.difficulty = difficulty
        self._difficulty = DIFFICULTIES[difficulty]
        self.scenario = scenario
        self.modifiers = dict(scenario.modifiers) if scenario else {}
        self.allowed_plants = tuple(PlantType[name] for name in scenario.allowed_plants) if scenario else tuple(PlantType)
        self.victory = False
        self.wave_number = scenario.waves[0].number if scenario and scenario.waves else 0
        self.wave_total = len(scenario.waves) if scenario else 0
        self._wave_index = 0
        self._wave_start = 0.0
        self._wave_spawn_index = 0
        self._scenario_complete = bool(scenario and not scenario.waves)
        self.grid = Grid(GRID_WIDTH, GRID_HEIGHT)
        self.projectiles: List[Projectile] = []
        self.zombies: List[Zombie] = []
        self.sun: int = scenario.sun if scenario else SUN_START
        self.score: int = 0
        self.zombies_killed = 0
        self.plants_placed = 0
        self.plants_lost = 0
        self.lawnmowers = [not self.modifiers.get("no_mowers", False)] * GRID_HEIGHT
        self.lawnmowers_used = 0
        self.selected: PlantType = (PlantType.PEASHOOTER if PlantType.PEASHOOTER in self.allowed_plants else (self.allowed_plants[0] if self.allowed_plants else PlantType.PEASHOOTER))
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
        self._next_sky_sun = SKY_SUN_INTERVAL
        self.sun_generated = 0
        self.seed = seed if seed is not None else (scenario.seed if scenario else None)
        self._rng = random.Random(self.seed)
        self._stdscr: Optional[curses.window] = None
        for item in self.modifiers.get("preplanted", ()):
            plant_type = PlantType[item["plant"]]
            self.grid.set(Plant(plant_type, item["row"], item["col"], float(PLANT_HEALTH[plant_type])))

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
        if self.paused or self.game_over:
            return
        # Fixed simulation slices keep seed, combat and economy identical at any UI tick.
        self._time_accumulator += self.tick_seconds
        self._dt = SIMULATION_STEP
        try:
            while self._time_accumulator + 1e-9 >= SIMULATION_STEP and not self.game_over:
                self._time_accumulator -= SIMULATION_STEP
                self.time_elapsed = round(self.time_elapsed + SIMULATION_STEP, 10)
                self.update_timers()
                self.move_projectiles()
                self.handle_attacks()
                self.spawn_and_move_zombies()
                self.generate_sun()
                self.check_loss()
                self.check_victory()
        finally:
            self._dt = self.tick_seconds

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
        if self.game_over:
            return
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
        elif ord("1") <= key <= ord("9"):
            self.select_plant_type(int(chr(key)))
        elif key == ord(" "):
            self.place_selected()
        elif key in (ord("r"), ord("R")):
            self.dig_up()

    def select_plant_type(self, slot: int) -> bool:
        roster = tuple(PlantType)
        if 1 <= slot <= len(roster):
            plant_type = roster[slot - 1]
            if plant_type in self.allowed_plants:
                self.selected = plant_type
                return True
            self.show_message("растение недоступно в этом испытании")
        return False

    def plant_status(self, plant: Plant) -> str:
        if plant.is_chewing(self.time_elapsed):
            return f"жуёт ещё {plant.chewing_until - self.time_elapsed:.1f} с"
        if plant.plant_type == PlantType.POTATO_MINE:
            remaining = max(0.0, MINE_ARM_TIME - (self.time_elapsed - plant.last_action_time))
            return f"подготовка: {remaining:.1f} с" if remaining else "мина готова"
        if plant.plant_type == PlantType.CHERRY_BOMB:
            remaining = max(0.0, BOMB_FUSE - (self.time_elapsed - plant.last_action_time))
            return f"взрыв через {remaining:.1f} с"
        return f"здоровье: {max(0, round(plant.hp))}/{PLANT_HEALTH[plant.plant_type]}"

    def next_spawn_in(self) -> Optional[float]:
        if not self.scenario:
            return max(0.0, self._next_spawn_time - self.time_elapsed)
        if self._scenario_complete:
            return None
        wave = self.scenario.waves[self._wave_index]
        if self._wave_spawn_index < len(wave.spawns):
            return max(0.0, self._wave_start + wave.spawns[self._wave_spawn_index].time - self.time_elapsed)
        if self._wave_index + 1 < len(self.scenario.waves):
            return max(0.0, self._wave_start + wave.duration - self.time_elapsed)
        return None

    def cooldown_remaining(self, plant_type: PlantType) -> float:
        return max(0.0, round(self._plant_ready_at[plant_type] - self.time_elapsed, 10))

    def planting_error(self) -> Optional[str]:
        if self.game_over:
            return "игра закончена"
        if self.paused:
            return "игра на паузе"
        if self.selected not in self.allowed_plants:
            return "растение недоступно в этом испытании"
        if not self.grid.is_inside(self.cursor_row, self.cursor_col):
            return "клетка вне поля"
        if self.grid.get(self.cursor_row, self.cursor_col):
            return "клетка занята"
        limit = self.modifiers.get("max_plants")
        if limit is not None and len(list(self.grid.iter_plants())) >= limit:
            return f"лимит растений: {limit}"
        if self.sun < self.plant_cost(self.selected):
            return "недостаточно солнца"
        remaining = self.cooldown_remaining(self.selected)
        if remaining > 0:
            return f"перезарядка: {remaining:.1f} с"
        return None

    def place_selected(self) -> bool:
        error = self.planting_error()
        if error:
            self.show_message(error)
            return False
        plant_type = self.selected
        plant = Plant(plant_type, self.cursor_row, self.cursor_col,
                      float(PLANT_HEALTH[plant_type]), last_action_time=self.time_elapsed)
        self.grid.set(plant)
        self.sun -= self.plant_cost(plant_type)
        self._plant_ready_at[plant_type] = self.time_elapsed + PLANT_COOLDOWNS[plant_type]
        self.plants_placed += 1
        return True

    def dig_up(self) -> None:
        if self.paused or self.game_over:
            return
        plant = self.grid.get(self.cursor_row, self.cursor_col)
        if plant:
            self.grid.remove(self.cursor_row, self.cursor_col)

    # --- Обновление состояния -----------------------------------------------
    def update_timers(self) -> None:
        now = self.time_elapsed
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
            end_col = projectile.col + PROJECTILE_SPEED_CELLS_PER_SECOND * self._dt
            # Include the initial cell: a pea created next to a zombie must hit it.
            targets = [z for z in self.zombies if z.row == projectile.row
                       and math.floor(projectile.col) <= z.col <= end_col and z.hp > 0]
            target = min(targets, key=lambda z: z.col, default=None)
            if target:
                if projectile.slows and target.shield_hp <= 0:
                    target.slowed_until = self.time_elapsed + SLOW_DURATION
                self.damage_zombie(target, PROJECTILE_DAMAGE)
                continue
            projectile.col = end_col
            if projectile.col < GRID_WIDTH:
                new_projectiles.append(projectile)
        self.projectiles = new_projectiles
        self.cleanup_dead_zombies()

    def handle_attacks(self) -> None:
        for plant in self.grid.iter_plants():
            if plant.plant_type in (PlantType.PEASHOOTER, PlantType.SNOW_PEA, PlantType.REPEATER):
                if (
                    self.time_elapsed - plant.last_action_time + 1e-9 >= PEASHOOTER_INTERVAL
                    and self.any_zombie_to_right(plant.row, plant.col)
                ):
                    shot_col = plant.col + 1
                    if shot_col < GRID_WIDTH:
                        for _ in range(2 if plant.plant_type == PlantType.REPEATER else 1):
                            self.projectiles.append(Projectile(row=plant.row, col=shot_col, slows=plant.plant_type == PlantType.SNOW_PEA))
                    plant.last_action_time = self.time_elapsed
            elif plant.plant_type == PlantType.POTATO_MINE:
                if self.time_elapsed - plant.last_action_time + 1e-9 >= MINE_ARM_TIME:
                    if self.find_zombie_in_cell(plant.row, plant.col):
                        self.explode(plant.row, plant.col, adjacent_rows=False)
                        self.grid.remove(plant.row, plant.col)
            elif plant.plant_type == PlantType.CHERRY_BOMB:
                if self.time_elapsed - plant.last_action_time + 1e-9 >= BOMB_FUSE:
                    self.explode(plant.row, plant.col)
                    self.grid.remove(plant.row, plant.col)
            elif plant.plant_type == PlantType.CHOMPER:
                if plant.is_chewing(self.time_elapsed):
                    continue
                target = self.find_zombie_in_cell(plant.row, plant.col)
                if target:
                    self.kill_zombie(target)
                    plant.chewing_until = self.time_elapsed + CHOMPER_CHEW_TIME
            # Подсолнух и Орех обрабатываются в других методах.

        self.cleanup_dead_zombies()

    def explode(self, row: int, col: int, *, adjacent_rows: bool = True) -> None:
        for zombie in list(self.zombies):
            if abs(zombie.col - col) <= 1 and (abs(zombie.row - row) <= 1 if adjacent_rows else zombie.row == row):
                self.damage_zombie(zombie, EXPLOSION_DAMAGE, bypass_shield=True)
        self.show_message("Бум!")

    def spawn_and_move_zombies(self) -> None:
        if self.scenario:
            self.spawn_scenario_zombies()
        elif self.time_elapsed >= self._next_spawn_time:
            self.spawn_zombie()

        for zombie in list(self.zombies):
            plant = self.grid.get(zombie.row, zombie.col)
            if plant:
                zombie.move_progress = 0.0
                plant.hp -= ZOMBIE_DPS[zombie.zombie_type] * self._difficulty["damage"] * self._dt * (0.5 if zombie.slowed_until > self.time_elapsed else 1.0)
                if plant.hp <= 0:
                    self.grid.remove(plant.row, plant.col)
                    self.plants_lost += 1
                continue

            zombie.move_progress += self._dt * (0.5 if zombie.slowed_until > self.time_elapsed else 1.0)
            move_interval = ZOMBIE_MOVE_INTERVALS[zombie.zombie_type] / self._difficulty["speed"]
            while zombie.move_progress + 1e-9 >= move_interval:
                zombie.move_progress -= move_interval
                target_col = zombie.col - 1
                if target_col < 0:
                    zombie.col = target_col
                    break
                occupant = self.grid.get(zombie.row, target_col)
                zombie.col = target_col
                if occupant:
                    break

        self.cleanup_dead_plants()

    def add_sun(self, amount: int) -> None:
        previous = self.sun
        self.sun += amount
        cap = self.modifiers.get("sun_cap")
        if cap is not None:
            self.sun = min(self.sun, int(cap))
        self.sun_generated += max(0, self.sun - previous)

    def generate_sun(self) -> None:
        if self.modifiers.get("passive_sun", True):
            while self.time_elapsed + 1e-9 >= self._next_sky_sun:
                self.add_sun(SUN_AMOUNT)
                self._next_sky_sun += SKY_SUN_INTERVAL
        for plant in self.grid.iter_plants():
            if plant.plant_type in (PlantType.SUNFLOWER, PlantType.DOUBLE_SUNFLOWER):
                while self.time_elapsed - plant.last_action_time + 1e-9 >= SUNFLOWER_INTERVAL:
                    self.add_sun(SUN_AMOUNT * (2 if plant.plant_type == PlantType.DOUBLE_SUNFLOWER else 1))
                    plant.last_action_time += SUNFLOWER_INTERVAL

    def kill_zombie(self, zombie: Zombie) -> None:
        if zombie in self.zombies:
            self.score += ZOMBIE_SCORE[zombie.zombie_type]
            self.zombies_killed += 1
            self.zombies.remove(zombie)

    def check_loss(self) -> None:
        for zombie in list(self.zombies):
            if zombie not in self.zombies or zombie.col >= 0:
                continue
            if self.lawnmowers[zombie.row]:
                self.lawnmowers[zombie.row] = False
                self.lawnmowers_used += 1
                for target in list(self.zombies):
                    if target.row == zombie.row:
                        self.kill_zombie(target)
                self.show_message(f"Газонокосилка спасла ряд {zombie.row + 1}")
            else:
                self.game_over = True
                self.game_over_reason = "Game Over"
                return

    # --- Вспомогательные методы для зомби -----------------------------------
    def create_zombie(self, kind: ZombieType, row: int) -> Zombie:
        shield = SHIELD_HEALTH * self._difficulty["health"] if kind == ZombieType.SHIELD else 0.0
        return Zombie(kind, row, GRID_WIDTH - 1,
                      ZOMBIE_HEALTH[kind] * self._difficulty["health"], shield_hp=shield)

    def damage_zombie(self, zombie: Zombie, damage: float, *, bypass_shield: bool = False) -> None:
        if not bypass_shield and zombie.shield_hp > 0:
            absorbed = min(damage, zombie.shield_hp)
            zombie.shield_hp -= absorbed
            damage -= absorbed
        zombie.hp -= damage
        if zombie.hp <= 0:
            self.kill_zombie(zombie)

    def spawn_zombie(self) -> None:
        row = self._rng.randrange(GRID_HEIGHT)
        z_type = self.pick_zombie_type()
        zombie = self.create_zombie(z_type, row)
        self.zombies.append(zombie)
        interval = 6.0 if self.time_elapsed < 60.0 else 3.0
        self._next_spawn_time = self.time_elapsed + interval * self._difficulty["spawn"]

    def spawn_scenario_zombies(self) -> None:
        if self._scenario_complete:
            return
        wave = self.scenario.waves[self._wave_index]
        elapsed = self.time_elapsed - self._wave_start
        while self._wave_spawn_index < len(wave.spawns):
            spawn = wave.spawns[self._wave_spawn_index]
            if spawn.time > elapsed + 1e-9:
                break
            kind = ZombieType[spawn.zombie]
            self.zombies.append(self.create_zombie(kind, spawn.row))
            self._wave_spawn_index += 1
        if self._wave_spawn_index == len(wave.spawns) and elapsed + 1e-9 >= wave.duration:
            self._wave_index += 1
            self._wave_start += wave.duration
            self._wave_spawn_index = 0
            if self._wave_index == len(self.scenario.waves):
                self._scenario_complete = True
            else:
                self.wave_number = self.scenario.waves[self._wave_index].number
                self.add_sun(int(self.modifiers.get("bonus_sun_per_wave", 0)))
                self.show_message(f"Волна {self.wave_number}/{self.wave_total}")

    def check_victory(self) -> None:
        if self.game_over or not self.scenario:
            return
        if self._scenario_complete and not self.zombies:
            self.victory = True
            self.game_over = True
            self.game_over_reason = "Победа"
            return
        limit = self.modifiers.get("time_limit")
        if limit is not None and self.time_elapsed >= float(limit):
            self.game_over = True
            self.game_over_reason = "Время вышло"

    def plant_cost(self, plant_type: PlantType) -> int:
        return max(0, round(PLANT_COSTS[plant_type] * float(self.modifiers.get("plant_cost_multiplier", 1.0))))

    def pick_zombie_type(self) -> ZombieType:
        shift_steps = int(self.time_elapsed // 45)
        total_shift = min(shift_steps * 0.05, 0.3)
        z_weight = 0.6 - total_shift
        z_weight = max(z_weight, 0.3)
        remaining_shift = 0.6 - z_weight
        cone_weight = 0.3 + remaining_shift / 3.0
        bucket_weight = 0.1 + remaining_shift * 2.0 / 3.0
        population = [ZombieType.NORMAL, ZombieType.CONE, ZombieType.BUCKET]
        weights = [z_weight, cone_weight, bucket_weight]
        if self.time_elapsed >= 30:
            population.append(ZombieType.RUNNER)
            weights.append(0.15)
        if self.time_elapsed >= 90:
            population.append(ZombieType.SHIELD)
            weights.append(0.15)
        choice = self._rng.choices(
            population=population,
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
        self._message_expires_at = self.time_elapsed + MESSAGE_DURATION

    def current_message(self) -> str:
        if self.message and self.time_elapsed <= self._message_expires_at:
            return self.message
        return ""

    # --- Отрисовка ----------------------------------------------------------
    def render(self, final: bool = False) -> None:
        if self._stdscr is not None:
            from .ui import draw_game
            draw_game(self._stdscr, self, final)

    def wait_for_exit(self) -> None:
        if self._stdscr is None:
            return
        stdscr = self._stdscr
        stdscr.nodelay(False)
        stdscr.addstr(GRID_HEIGHT + 2, 0, "")
        stdscr.addstr(GRID_HEIGHT + 3, 0, "Нажмите любую клавишу для выхода")
        stdscr.refresh()
        stdscr.getch()
